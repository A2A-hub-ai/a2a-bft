"""
A2A-BFT 4模型异构实验（vLLM 版本）
通过 OpenAI 兼容 API 调用 4 个 vLLM 实例

vLLM 实例布局（2×A800-80GB）：
  GPU0: Llama-3.1-8B (port 8000) + InternLM3-8B (port 8001)
  GPU1: DeepSeek-V2-Lite (port 8002) + Qwen2.5-7B (port 8003)

实验配置：GSM8K 数学 + MMLU 知识，6 场景（baseline + 攻击）
"""
import os
import sys
import json
import re
import time
import random
import threading
from typing import Optional, List, Tuple, Dict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# vLLM 实例配置
MODEL_ENDPOINTS = {
    "llama": {"base_url": "http://127.0.0.1:8000/v1", "model": "llama", "name": "Llama-3.1-8B"},
    "internlm": {"base_url": "http://127.0.0.1:8001/v1", "model": "internlm", "name": "InternLM3-8B"},
    "deepseek": {"base_url": "http://127.0.0.1:8002/v1", "model": "deepseek", "name": "DeepSeek-V2-Lite"},
    "qwen": {"base_url": "http://127.0.0.1:8003/v1", "model": "qwen", "name": "Qwen2.5-7B"},
}

DATASET_PATH = os.environ.get("A2A_DATASET_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets")) + os.sep
DATASET_FILES = {"gsm8k": "gsm8k_test.json", "mmlu": "mmlu_3subjects.json",
                 "mbpp": "mbpp_test.json"}
RESULTS_DIR = os.environ.get("A2A_RESULTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
os.makedirs(RESULTS_DIR, exist_ok=True)

SOLVE_MAX_TOKENS_MATH = 300
SOLVE_MAX_TOKENS_MC = 96
SOLVE_MAX_TOKENS_CODE = 512
JUDGE_MAX_TOKENS = 384
JUDGE_MAX_TOKENS_CODE = 768
MAX_ROUNDS = 6
PARALLEL_TASKS = 4

# 求解提示：允许思维链（8B 模型必须逐步推理才能做对数学题），最后一行固定格式
MATH_PROMPT = """Solve the following math problem carefully. Think step by step, showing your reasoning. Then write the final numeric answer on the last line in exactly this format: #### <number>

Problem: {question}

Solution:"""

KNOWLEDGE_PROMPT = """Answer the following multiple choice question. Think briefly, then write the final choice letter on the last line in exactly this format: #### <letter>

Question: {question}

Choices:
A) {choice_a}
B) {choice_b}
C) {choice_c}
D) {choice_d}

Answer:"""

# 语义验证（Validate 阶段）：先自行求解再比对，最终裁决固定格式，保证可解析
JUDGE_PROMPT = """First solve the following math problem yourself, step by step. Then compare your own answer with the submitted answer and judge whether the submitted answer is correct.

Problem: {question}
Submitted final answer: {proposal}

After your reasoning, end your reply with exactly these two lines:
YOUR_ANSWER: <your own final answer>
VERDICT: <ACCEPT if the submitted answer is correct, REJECT if it is wrong, UNCERTAIN if you cannot determine>"""

JUDGE_PROMPT_MC = """First answer the following multiple choice question yourself. Then compare your own choice with the submitted answer and judge whether the submitted answer is correct.

Question: {question}

Choices:
A) {choice_a}
B) {choice_b}
C) {choice_c}
D) {choice_d}

Submitted answer: {proposal}

After your reasoning, end your reply with exactly these two lines:
YOUR_ANSWER: <your own choice letter>
VERDICT: <ACCEPT if the submitted answer is correct, REJECT if it is wrong, UNCERTAIN if you cannot determine>"""

# 代码任务（MBPP）：生成可运行的 Python 函数，附带测试断言供参照
CODE_PROMPT = """Write a Python function to solve the following task. Provide the complete function definition. Think briefly if needed, then output the final Python code in a single ```python code block.

Task: {question}

Example tests:
{tests}

Python code:"""

CODE_JUDGE_PROMPT = """You are reviewing a submitted Python solution. Determine whether it would pass the example tests. Be brief: do NOT write or rewrite code, give at most one short line of reasoning per test.

Task: {question}

Example tests:
{tests}

Submitted code:
{proposal}

End your reply with exactly this line:
VERDICT: <ACCEPT if the submitted code would pass the tests, REJECT if it would fail, UNCERTAIN if you cannot determine>"""

# ---------------- 代码执行与判定（子进程 + 超时，防死循环） ----------------
_CODE_EXEC_TMP = "/tmp/mbpp_exec_%d.py" % os.getpid()
_RUNNER_B64 = None  # 惰性生成


def extract_code(raw: str) -> str:
    """从模型输出中提取 Python 代码：优先最后一个 ```python 块；
    否则从首个代码行（def/class/import/from/@）截取到结尾。
    注意：必须保持幂等 —— extract_code(extract_code(x)) == extract_code(x)，
    否则验证阶段与判定阶段会拿到不同代码。"""
    if not raw:
        return ""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", raw, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    m = re.search(r"^(\s*(?:def |class |import |from |@).*)", raw, re.DOTALL | re.MULTILINE)
    if m:
        return m.group(1).strip()
    return raw.strip()


def _runner_source() -> str:
    return (
        "import sys, json\n"
        "payload = json.loads(sys.argv[1])\n"
        "code, tests = payload['code'], payload['tests']\n"
        "ns = {}\n"
        "results = []\n"
        "try:\n"
        "    exec(compile(code, '<solution>', 'exec'), ns)\n"
        "except Exception:\n"
        "    print(json.dumps([False] * len(tests))); sys.exit(0)\n"
        "for t in tests:\n"
        "    try:\n"
        "        exec(compile(t, '<test>', 'exec'), ns)\n"
        "        results.append(True)\n"
        "    except Exception:\n"
        "        results.append(False)\n"
        "print(json.dumps(results))\n"
    )


_CODE_CACHE = {}
_CODE_CACHE_LOCK = threading.Lock()


def run_code_tests(code: str, test_list) -> list:
    """执行代码 vs 测试断言，返回每个断言的通过布尔列表（带缓存）。"""
    code = (code or "").strip()
    key = hash((code, tuple(test_list)))
    with _CODE_CACHE_LOCK:
        if key in _CODE_CACHE:
            return _CODE_CACHE[key]
    results = [False] * len(test_list)
    if code and "def" in code:
        try:
            import subprocess as sp
            payload = json.dumps({"code": code, "tests": list(test_list)})
            r = sp.run([sys.executable, "-c", _runner_source(), payload],
                       capture_output=True, text=True, timeout=8)
            if r.returncode == 0 and r.stdout.strip():
                results = json.loads(r.stdout.strip().splitlines()[-1])
                if not isinstance(results, list) or len(results) != len(test_list):
                    results = [False] * len(test_list)
        except Exception:
            results = [False] * len(test_list)
    with _CODE_CACHE_LOCK:
        _CODE_CACHE[key] = results
    return results


def code_tamper(code: str) -> str:
    """拜占庭篡改：删除所有 return 行，使函数返回 None（确定性地破坏正确性）。"""
    lines = [ln for ln in (code or "").splitlines()
             if not ln.lstrip().startswith("return")]
    return "\n".join(lines)


def extract_math_answer(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"####\s*(-?\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(?:answer|Answer|答案)\s*[:：=]?\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    if numbers:
        return float(numbers[-1])
    return None


def extract_mc_answer(text: str) -> Optional[str]:
    """提取选项字母。优先识别 '#### X' 固定格式，避免误抓题目中的 A)/B) 字样"""
    if not text:
        return None
    m = re.search(r"####\s*\(?([A-D])\b", text)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?:answer|Answer|答案|choice)\s*(?:is)?\s*[:：]?\s*\(?([A-D])\b", text)
    if m:
        return m.group(1).upper()
    stripped = text.strip()
    if len(stripped) == 1 and stripped.upper() in 'ABCD':
        return stripped.upper()
    m = re.search(r"^\(?([A-D])[\).:\s]", stripped)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b([ABCD])\b", stripped)
    if m:
        return m.group(1).upper()
    return None


class VLLMClient:
    """vLLM API 客户端"""

    def __init__(self, model_key: str):
        from openai import OpenAI
        cfg = MODEL_ENDPOINTS[model_key]
        self.model_key = model_key
        self.model_name = cfg["name"]
        self.client = OpenAI(base_url=cfg["base_url"], api_key="EMPTY", timeout=120)
        self.api_model = cfg["model"]

    def generate(self, prompt: str, max_tokens: int = 128) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.api_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"    [API错误 {self.model_name}] {str(e)[:100]}", flush=True)
            return ""


class MultiModelWorker:
    """使用指定 vLLM 模型的 Worker"""

    def __init__(self, worker_id: int, client: VLLMClient,
                 is_byzantine: bool = False, byzantine_type: str = "collusion",
                 is_soft_fault: bool = False, task_type: str = "math"):
        self.worker_id = worker_id
        self.client = client
        self.task_type = task_type
        self.is_byzantine = is_byzantine
        self.byzantine_type = byzantine_type
        self.is_soft_fault = is_soft_fault
        self.weight = 1.0
        self.abstain_count = 0
        self.answer_cache = {}

    def solve(self, task: dict) -> Tuple[str, float]:
        question = task["question"]

        if self.task_type == "math":
            prompt = MATH_PROMPT.format(question=question)
            raw = self._generate(prompt, max_tokens=SOLVE_MAX_TOKENS_MATH)
            num = extract_math_answer(raw)

            if self.is_soft_fault and random.random() < 0.3:
                return "", 0.1

            if self.is_byzantine and self.byzantine_type in ("collusion", "strategic_reject"):
                if num is not None:
                    tampered = num + random.uniform(1, 5)
                    return str(int(tampered) if tampered == int(tampered) else round(tampered, 2)), 0.6
                return "0", 0.5

            if num is None:
                return "", 0.2  # 未能得出答案：不提交，交由视图切换处理
            return (str(int(num)) if num == int(num) else str(round(num, 2))), 0.85

        if self.task_type == "code":
            tests = task.get("test_list", [])
            prompt = CODE_PROMPT.format(question=question,
                                        tests="\n".join(tests[:3]))
            raw = self._generate(prompt, max_tokens=SOLVE_MAX_TOKENS_CODE)
            code = extract_code(raw)

            if self.is_soft_fault and random.random() < 0.3:
                return "", 0.1

            if self.is_byzantine and self.byzantine_type in ("collusion", "strategic_reject"):
                # 伪装成正常求解后篡改：删除 return 行，确定性破坏正确性
                return code_tamper(code) if code else "", 0.6

            if not code or "def" not in code:
                return "", 0.2
            return code, 0.85

        else:  # knowledge
            choices = task.get("choices", [])
            prompt = KNOWLEDGE_PROMPT.format(
                question=question,
                choice_a=choices[0] if len(choices) > 0 else "",
                choice_b=choices[1] if len(choices) > 1 else "",
                choice_c=choices[2] if len(choices) > 2 else "",
                choice_d=choices[3] if len(choices) > 3 else "",
            )
            raw = self._generate(prompt, max_tokens=SOLVE_MAX_TOKENS_MC)
            mc = extract_mc_answer(raw)

            if self.is_soft_fault and random.random() < 0.3:
                return "", 0.1

            if self.is_byzantine and self.byzantine_type in ("collusion", "strategic_reject"):
                correct = task.get("answer", "")
                correct_letter = None
                if correct in choices:
                    correct_letter = chr(65 + choices.index(correct))
                elif isinstance(correct, str) and len(correct.strip()) == 1 and correct.strip().upper() in "ABCD":
                    correct_letter = correct.strip().upper()
                wrong = [c for c in "ABCD" if c != correct_letter]
                if wrong:
                    return random.choice(wrong), 0.6
                return "A", 0.5

            if mc is None:
                return "", 0.2
            return mc, 0.85

    def _generate(self, prompt: str, max_tokens: int = 128) -> str:
        if prompt not in self.answer_cache:
            self.answer_cache[prompt] = self.client.generate(prompt, max_tokens=max_tokens)
        return self.answer_cache[prompt]

    VERDICT_RE = re.compile(r"VERDICT\s*[:\-]?\s*(ACCEPT|REJECT|UNCERTAIN)", re.IGNORECASE)

    def _judge(self, task: dict, proposal: str) -> Optional[bool]:
        """语义验证：独立推理后裁决。True=ACCEPT / False=REJECT / None=UNCERTAIN(ABSTAIN)"""
        if self.task_type == "math":
            prompt = JUDGE_PROMPT.format(question=task["question"], proposal=proposal)
        elif self.task_type == "code":
            # 可验证域（MBPP 有现成断言）：Validate 阶段直接执行提案代码
            # —— 拜占庭篡改代码必然无法通过测试，从机制上保证"提交即正确"
            pat = run_code_tests(proposal, task.get("test_list", []))
            return all(pat) if pat else False
        else:
            choices = task.get("choices", [])
            prompt = JUDGE_PROMPT_MC.format(
                question=task["question"],
                choice_a=choices[0] if len(choices) > 0 else "",
                choice_b=choices[1] if len(choices) > 1 else "",
                choice_c=choices[2] if len(choices) > 2 else "",
                choice_d=choices[3] if len(choices) > 3 else "",
                proposal=proposal,
            )
        judge_toks = JUDGE_MAX_TOKENS_CODE if self.task_type == "code" else JUDGE_MAX_TOKENS
        raw = self._generate(prompt, max_tokens=judge_toks)
        if not raw:
            return None

        # 裁决在末尾：取最后一个 VERDICT（推理过程中可能提前出现关键词）
        marks = self.VERDICT_RE.findall(raw)
        if marks:
            v = marks[-1].upper()
            if v == "ACCEPT":
                return True
            if v == "REJECT":
                return False
            return None  # UNCERTAIN -> ABSTAIN

        # 回退1：解析 YOUR_ANSWER 与提案精确比对
        ma = re.search(r"YOUR_ANSWER\s*[:\-]?\s*(.+)", raw)
        if ma:
            own = ma.group(1).strip().splitlines()[0]
            if self.task_type == "math":
                a, b = extract_math_answer(own), extract_math_answer(proposal)
                if a is not None and b is not None:
                    return abs(a - b) < 1e-6
            else:
                oc, pc = extract_mc_answer(own), extract_mc_answer(proposal)
                if oc and pc:
                    return oc == pc

        # 回退2：取最后出现的裁决关键词
        up = raw.upper()
        la, lr = up.rfind("ACCEPT"), up.rfind("REJECT")
        if la == -1 and lr == -1:
            return None
        return la > lr

    def validate(self, task: dict, proposal: str, primary_is_byzantine: bool) -> str:
        if self.is_byzantine:
            if self.byzantine_type == "collusion":
                return "ACCEPT" if primary_is_byzantine else "REJECT"
            elif self.byzantine_type == "strategic_reject":
                return "REJECT"
            return random.choice(["ACCEPT", "REJECT"])

        if self.is_soft_fault and random.random() < 0.3:
            return "ABSTAIN"

        if not proposal or not proposal.strip():
            return "ABSTAIN"

        verdict = self._judge(task, proposal)
        if verdict is None:
            return "ABSTAIN"
        return "ACCEPT" if verdict else "REJECT"


class ConsensusLayer:
    def __init__(self, n: int, f: int, s: int):
        self.n = n
        self.f = f
        self.s = s
        self.reputation = [1.0] * n
        self.view_id = 0
        self.last_primary = 0
        # 统计（用于诊断）
        self.stats = {"accept": 0, "reject": 0, "abstain": 0, "view_changes": 0,
                      "commit": 0, "rounds_used": 0, "pending": 0, "explicit_reject": 0}

    def run_consensus(self, workers: List[MultiModelWorker], task: dict,
                      max_rounds: int = MAX_ROUNDS) -> Tuple[str, int]:
        primary_idx = self.last_primary
        theta_accept = self.n - 1 - 2 * self.f - self.s
        theta_reject = -(self.n - 1 - self.f) * 0.5
        pending_streak = 0

        for rnd in range(1, max_rounds + 1):
            primary = workers[primary_idx]
            proposal, _ = primary.solve(task)

            if not proposal or proposal.strip() == "":
                self.view_id += 1
                self.stats["view_changes"] += 1
                pending_streak = 0
                primary_idx = (primary_idx + 1) % self.n
                continue

            votes = []
            primary_is_byzantine = primary.is_byzantine
            for i, worker in enumerate(workers):
                if i == primary_idx:
                    continue
                votes.append(worker.validate(task, proposal, primary_is_byzantine))

            accept_count = votes.count("ACCEPT")
            reject_count = votes.count("REJECT")
            self.stats["accept"] += accept_count
            self.stats["reject"] += reject_count
            self.stats["abstain"] += votes.count("ABSTAIN")
            phi = accept_count - 0.5 * reject_count

            if phi >= theta_accept:
                self.stats["commit"] += 1
                self.stats["rounds_used"] += rnd
                self.last_primary = (primary_idx + 1) % self.n
                return proposal, rnd

            if phi <= theta_reject:
                # 明确否决：立即视图切换
                self.stats["explicit_reject"] += 1
                self.view_id += 1
                self.stats["view_changes"] += 1
                pending_streak = 0
                primary_idx = (primary_idx + 1) % self.n
                continue

            # PENDING 区间：按论文规定，连续 2 轮 PENDING 才触发视图切换
            self.stats["pending"] += 1
            pending_streak += 1
            if pending_streak >= 2:
                self.view_id += 1
                self.stats["view_changes"] += 1
                pending_streak = 0
                primary_idx = (primary_idx + 1) % self.n
            continue

        self.stats["rounds_used"] += max_rounds
        return None, max_rounds


def check_vllm_health():
    """检查 4 个 vLLM 实例健康状态"""
    import urllib.request
    healthy = {}
    for key, cfg in MODEL_ENDPOINTS.items():
        url = cfg["base_url"].replace("/v1", "/health")
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as r:
                healthy[key] = (r.status == 200)
        except Exception:
            healthy[key] = False
    return healthy


def load_dataset(dataset_name: str) -> List[dict]:
    filename = DATASET_FILES.get(dataset_name, f"{dataset_name}.json")
    path = os.path.join(DATASET_PATH, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_experiment(dataset_name: str, n: int, f: int, s: int,
                   attack_type: str, num_tasks: int = 30,
                   model_assignment: List[str] = None) -> Dict:
    print(f"\n{'='*70}")
    print(f"实验: n={n}, f={f}, s={s}, attack={attack_type or 'baseline'}, dataset={dataset_name}")
    print(f"模型分配: {model_assignment}")
    print(f"{'='*70}", flush=True)

    dataset = load_dataset(dataset_name)
    random.seed(42)
    tasks = random.sample(dataset, min(num_tasks, len(dataset)))

    # 创建 vLLM 客户端（复用）
    clients = {}
    for key in set(model_assignment):
        if key not in clients:
            clients[key] = VLLMClient(key)

    task_type = "knowledge" if dataset_name == "mmlu" else "math"

    results = {"consensus": 0, "reject": 0, "correct": 0, "rounds": [], "times": []}
    agg = {"accept": 0, "reject": 0, "abstain": 0, "view_changes": 0,
           "commit": 0, "rounds_used": 0, "pending": 0, "explicit_reject": 0}
    lock = threading.Lock()
    counter = [0]

    def _run_one(task: dict):
        """每个任务使用独立的 Worker 与共识实例，避免并发状态竞争"""
        wlist = [
            MultiModelWorker(
                worker_id=i, client=clients[model_assignment[i]],
                is_byzantine=(i < f),
                byzantine_type=attack_type if i < f else None,
                is_soft_fault=(f <= i < f + s),
                task_type=task_type,
            )
            for i in range(n)
        ]
        layer = ConsensusLayer(n=n, f=f, s=s)
        proposal, rounds = layer.run_consensus(wlist, task)
        return task, proposal, rounds, layer.stats

    def _is_correct(proposal: str, task: dict) -> bool:
        if dataset_name == "gsm8k":
            pred_num = extract_math_answer(proposal)
            true_num = extract_math_answer(task["answer"])
            return (pred_num is not None and true_num is not None
                    and abs(pred_num - true_num) < 1e-6)
        pred_letter = extract_mc_answer(proposal)
        if not pred_letter:
            return False
        idx = ord(pred_letter) - ord('A')
        choices = task.get("choices", [])
        if not (0 <= idx < len(choices)):
            return False
        gold = task["answer"]
        if isinstance(gold, str) and len(gold.strip()) == 1 and gold.strip().upper() in "ABCD":
            return pred_letter == gold.strip().upper()
        return choices[idx] == gold

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=PARALLEL_TASKS) as ex:
        futures = [ex.submit(_run_one, t) for t in tasks]
        for fut in as_completed(futures):
            try:
                task, proposal, rounds, stats = fut.result()
            except Exception as e:
                print(f"  [任务异常] {type(e).__name__}: {str(e)[:130]}", flush=True)
                continue
            results["rounds"].append(rounds)
            if proposal:
                results["consensus"] += 1
                if _is_correct(proposal, task):
                    results["correct"] += 1
            else:
                results["reject"] += 1
            with lock:
                for k in agg:
                    agg[k] += stats.get(k, 0)
                counter[0] += 1
                if counter[0] % 5 == 0:
                    print(f"  [{counter[0]}/{len(tasks)}] 共识率={results['consensus']/counter[0]*100:.0f}%", flush=True)

    total_time = time.time() - start_time
    results["consensus_rate"] = results["consensus"] / len(tasks) * 100
    results["correctness_rate"] = (results["correct"] / results["consensus"] * 100) if results["consensus"] > 0 else 0
    results["avg_rounds"] = sum(results["rounds"]) / len(results["rounds"]) if results["rounds"] else 0
    results["avg_time_per_task"] = total_time / len(tasks)
    results["total_time"] = total_time
    results["model_assignment"] = model_assignment
    results["vote_stats"] = agg
    total_votes = agg["accept"] + agg["reject"] + agg["abstain"]
    results["vote_distribution"] = {
        "accept_pct": round(agg["accept"] / total_votes * 100, 1) if total_votes else 0.0,
        "reject_pct": round(agg["reject"] / total_votes * 100, 1) if total_votes else 0.0,
        "abstain_pct": round(agg["abstain"] / total_votes * 100, 1) if total_votes else 0.0,
    }

    print(f"  => 共识率={results['consensus_rate']:.1f}%, 正确率={results['correctness_rate']:.1f}%, "
          f"轮数={results['avg_rounds']:.2f}, 耗时={total_time:.0f}s", flush=True)
    print(f"     投票分布: ACCEPT={results['vote_distribution']['accept_pct']}% "
          f"REJECT={results['vote_distribution']['reject_pct']}% "
          f"ABSTAIN={results['vote_distribution']['abstain_pct']}% | "
          f"视图切换={agg['view_changes']}", flush=True)
    return results


def main():
    print("="*70)
    print("A2A-BFT 4模型异构实验 (vLLM)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # 检查 vLLM 健康
    print("\n检查 vLLM 实例...")
    max_wait = 30
    for attempt in range(max_wait):
        health = check_vllm_health()
        ok = sum(health.values())
        print(f"  [{attempt+1}] 健康实例: {ok}/4 {health}", flush=True)
        if ok == 4:
            break
        if attempt == max_wait - 1:
            print("  警告: 部分实例未就绪，继续尝试")
        time.sleep(20)

    experiments = [
        {"dataset": "gsm8k", "scenarios": [
            {"n": 5, "f": 0, "s": 0, "attack": None, "tasks": 20},
            {"n": 5, "f": 1, "s": 1, "attack": "strategic_reject", "tasks": 20},
            {"n": 8, "f": 2, "s": 1, "attack": "collusion", "tasks": 20},
        ]},
        {"dataset": "mmlu", "scenarios": [
            {"n": 5, "f": 0, "s": 0, "attack": None, "tasks": 16},
            {"n": 5, "f": 1, "s": 1, "attack": "strategic_reject", "tasks": 16},
            {"n": 8, "f": 2, "s": 1, "attack": "collusion", "tasks": 16},
        ]},
    ]

    all_results = []
    model_keys = list(MODEL_ENDPOINTS.keys())

    for exp in experiments:
        dataset = exp["dataset"]
        print(f"\n{'#'*70}\n# 数据集: {dataset.upper()}\n{'#'*70}", flush=True)
        for sc in exp["scenarios"]:
            n = sc["n"]
            model_assignment = [model_keys[i % len(model_keys)] for i in range(n)]
            result = run_experiment(
                dataset_name=dataset, n=n, f=sc["f"], s=sc["s"],
                attack_type=sc["attack"], num_tasks=sc["tasks"],
                model_assignment=model_assignment,
            )
            result["scenario"] = f"n={n},f={sc['f']},s={sc['s']},attack={sc['attack'] or 'baseline'}"
            result["dataset"] = dataset
            all_results.append(result)

    output_path = os.path.join(RESULTS_DIR, "multi_model_vllm_results.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "models": {k: v["name"] for k, v in MODEL_ENDPOINTS.items()},
            "results": all_results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"实验完成！结果保存: {output_path}")
    print(f"{'='*70}")
    print(f"\n{'场景':<40} {'共识率':>8} {'正确率':>8} {'轮数':>6} {'耗时':>8}")
    print("-"*75)
    for r in all_results:
        print(f"{r['scenario']+' ('+r['dataset']+')':<40} {r['consensus_rate']:>7.1f}% "
              f"{r['correctness_rate']:>7.1f}% {r['avg_rounds']:>5.2f} {r['total_time']:>7.0f}s")


if __name__ == "__main__":
    main()
