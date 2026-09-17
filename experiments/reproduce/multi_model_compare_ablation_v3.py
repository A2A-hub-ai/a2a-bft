"""
4模型异构环境：主算法 + 对比算法 + 消融算法 统一评测 v2
v2 变更: 每场景 30 任务（v1 为 10）；新增 MBPP 代码任务域（GSM8K + MBPP 各 3 场景）
代码答案以测试断言执行结果（通过模式串，如 TTF）为归一化基础，可执行、可比较

主算法   : A2A-BFT（语义验证 + 视图切换 + 动态阈值）
消融算法 : A2A-BFT 去视图切换 / 去语义验证 / 固定阈值
对比算法 : Simple Majority / Weighted Majority / A2A-Sim / LLM-Debate

评测指标（对所有方法统一口径）：
  decision_rate     给出决策的任务比例（活性）
  answer_accuracy   决策正确的任务比例
  wrong_commit_rate 决策错误的任务比例（安全性违规，BFT 最关键指标）
  avg_calls         每任务平均 LLM 调用次数
"""
import os
import sys
import json
import re
import time
import random
import threading
from collections import Counter
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 自定位项目根（原为硬编码服务器路径，换机器或换目录即失效）---
import os
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while not os.path.exists(os.path.join(_ROOT, ".a2a_project_root")) and os.path.dirname(_ROOT) != _ROOT:
    _ROOT = os.path.dirname(_ROOT)
# 依次加入：脚本自身目录、共享实验模块目录（reproduce/）、src/（a2a_bft 包）
for _d in (os.path.join(_ROOT, "experiments", "reproduce"),
           os.path.join(_ROOT, "experiments", "src"),
           _HERE):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)
A2A_RESULTS = os.environ.get("A2A_RESULTS_DIR", os.path.join(_ROOT, "experiments", "results"))
A2A_DATASETS = os.environ.get("A2A_DATASET_DIR", os.path.join(_ROOT, "experiments", "datasets"))
A2A_MODELS = os.environ.get("A2A_MODEL_DIR", "/autodl-fs/data/models")
from multi_model_vllm import (VLLMClient, MultiModelWorker, MODEL_ENDPOINTS,
                              load_dataset, extract_math_answer, extract_mc_answer,
                              run_code_tests,
                              MATH_PROMPT, KNOWLEDGE_PROMPT,
                              SOLVE_MAX_TOKENS_MATH, SOLVE_MAX_TOKENS_MC,
                              JUDGE_MAX_TOKENS, MAX_ROUNDS)

RESULTS_DIR = A2A_RESULTS
os.makedirs(RESULTS_DIR, exist_ok=True)
PARALLEL = 6

DEBATE_PROMPT = """Several agents answered the same question differently. Reconsider and give YOUR final answer.

Question: {question}

Other agents' answers: {others}

Think step by step, then write your final answer on the last line in exactly this format: #### <answer>"""


# ----------------------------------------------------------------------------
# 归一化 / 判定
# ----------------------------------------------------------------------------
def normalize(ans: str, task: dict, task_type: str):
    """归一化答案：math/mc -> 标量；code -> 测试通过模式串（如 'TTT'）。"""
    if not ans:
        return None
    if task_type == 'math':
        v = extract_math_answer(ans)
        if v is None:
            return None
        return str(int(v)) if v == int(v) else str(round(v, 2))
    if task_type == 'code':
        from multi_model_vllm import extract_code
        code = extract_code(ans)
        pat = run_code_tests(code, task.get('test_list', []))
        return ''.join('T' if p else 'F' for p in pat)
    return extract_mc_answer(ans)


def is_correct(ans: str, task: dict, task_type: str) -> bool:
    if not ans:
        return False
    if task_type == 'math':
        a = extract_math_answer(ans)
        b = extract_math_answer(task['answer'])
        return a is not None and b is not None and abs(a - b) < 1e-6
    if task_type == 'code':
        from multi_model_vllm import extract_code
        code = extract_code(ans)
        pat = run_code_tests(code, task.get('test_list', []))
        return all(pat) if pat else False
    letter = extract_mc_answer(ans)
    if not letter:
        return False
    choices = task.get('choices', [])
    idx = ord(letter) - ord('A')
    if not (0 <= idx < len(choices)):
        return False
    gold = task['answer']
    if isinstance(gold, str) and len(gold.strip()) == 1 and gold.strip().upper() in 'ABCD':
        return letter == gold.strip().upper()
    return choices[idx] == gold


def make_workers(n, f, s, attack, clients, assignment, task_type):
    ws = []
    for i in range(n):
        ws.append(MultiModelWorker(
            worker_id=i, client=clients[assignment[i]],
            is_byzantine=(i < f),
            byzantine_type=attack if i < f else None,
            is_soft_fault=(f <= i < f + s),
            task_type=task_type,
        ))
    return ws


# ----------------------------------------------------------------------------
# 主算法 A2A-BFT（带组件开关）+ 消融变体
# ----------------------------------------------------------------------------
class A2ABFT:
    def __init__(self, n, f, s, use_view_change=True,
                 semantic_validation=True, dynamic_threshold=True):
        self.n, self.f, self.s = n, f, s
        self.use_view_change = use_view_change
        self.semantic_validation = semantic_validation
        self.dynamic_threshold = dynamic_threshold
        self.theta_accept = (n - 1 - 2 * f - s) if dynamic_threshold else max(1, (n - 1) // 2 + 1)
        self.theta_reject = -(n - 1 - f) * 0.5
        self.rep = [1.0] * n

    # 验证：语义验证 vs 精确比对（消融用）
    def _validate(self, w, task, proposal, primary_is_byzantine):
        if w.is_byzantine:
            if w.byzantine_type == 'collusion':
                return 'ACCEPT' if primary_is_byzantine else 'REJECT'
            if w.byzantine_type == 'strategic_reject':
                return 'REJECT'
            return random.choice(['ACCEPT', 'REJECT'])
        if w.is_soft_fault and random.random() < 0.3:
            return 'ABSTAIN'
        if not proposal:
            return 'ABSTAIN'
        if self.semantic_validation:
            v = w._judge(task, proposal)
            return 'ABSTAIN' if v is None else ('ACCEPT' if v else 'REJECT')
        # 消融：退化为"自己重算 + 精确比对"
        own = w.solve(task)[0]
        if not own:
            return 'ABSTAIN'
        if w.task_type == 'math':
            a, b = extract_math_answer(own), extract_math_answer(proposal)
            if a is None or b is None:
                return 'ABSTAIN'
            return 'ACCEPT' if abs(a - b) < 1e-6 else 'REJECT'
        if w.task_type == 'code':
            # 去语义验证消融：异构模型间退化为朴素精确字符串比对（不执行测试）
            return 'ACCEPT' if own.strip() == proposal.strip() else 'REJECT'
        oc, pc = extract_mc_answer(own), extract_mc_answer(proposal)
        if oc and pc:
            return 'ACCEPT' if oc == pc else 'REJECT'
        return 'ABSTAIN'

    def run(self, workers, task):
        idx = 0
        pending = 0
        rounds = 0
        stats = dict(accept=0, reject=0, abstain=0, view_change=0, pending=0)
        for rnd in range(1, MAX_ROUNDS + 1):
            rounds = rnd
            primary = workers[idx]
            proposal, _ = primary.solve(task)
            if not proposal:
                stats['view_change'] += 1
                if self.use_view_change:
                    idx = (idx + 1) % self.n
                continue
            votes = [self._validate(w, task, proposal, primary.is_byzantine)
                     for i, w in enumerate(workers) if i != idx]
            acc, rej = votes.count('ACCEPT'), votes.count('REJECT')
            stats['accept'] += acc
            stats['reject'] += rej
            stats['abstain'] += votes.count('ABSTAIN')
            phi = acc - 0.5 * rej
            if phi >= self.theta_accept:
                return proposal, rounds, stats
            if self.use_view_change:
                if phi <= self.theta_reject or pending >= 1:
                    idx = (idx + 1) % self.n
                    stats['view_change'] += 1
                    pending = 0
                else:
                    pending += 1
                    stats['pending'] += 1
            # 不去视图切换：primary 固定，空转到 max_rounds
        return None, rounds, stats


# ----------------------------------------------------------------------------
# 对比算法（task_type 由调用方注入）
# 关键修复（v3）：多数表决返回"胜出模式对应的原始答案"（代码任务返回代码本身），
# 而非归一化模式串 —— 否则代码任务提交 'TTT' 这类模式串，判定必然失败。
# ----------------------------------------------------------------------------
def simple_majority(workers, task, task_type):
    rep = {}                              # pattern -> 原始答案（首个产生者）
    cand = []
    for w in workers:
        a, _ = w.solve(task)
        nn = normalize(a, task, task_type)
        if nn:
            rep.setdefault(nn, a)
            cand.append(nn)
    if not cand:
        return None
    return rep[Counter(cand).most_common(1)[0][0]]


def weighted_majority(workers, task, task_type):
    rep = {}
    score = {}
    for w in workers:
        a, c = w.solve(task)
        nn = normalize(a, task, task_type)
        if nn:
            rep.setdefault(nn, a)
            score[nn] = score.get(nn, 0.0) + c
    if not score:
        return None
    return rep[max(score.items(), key=lambda kv: kv[1])[0]]


def a2a_sim(workers, task, task_type, conf_th=0.7):
    rep = {}
    cand = []
    for w in workers:
        a, c = w.solve(task)
        nn = normalize(a, task, task_type)
        if nn and c >= conf_th:
            rep.setdefault(nn, a)
            cand.append(nn)
    if not cand:
        return None
    top, k = Counter(cand).most_common(1)[0]
    return rep[top] if k > len(cand) / 2 else None


def llm_debate(workers, task, task_type, rounds=2):
    """多轮辩论：展示他人答案后各自复议，最后多数表决"""
    answers = []
    for w in workers:
        a, _ = w.solve(task)
        answers.append(a)
    for _ in range(rounds):
        new = []
        for i, w in enumerate(workers):
            if w.is_byzantine:          # 拜占庭节点不改变立场
                new.append(answers[i])
                continue
            others = [normalize(a, task, task_type) for j, a in enumerate(answers) if j != i]
            others = [o for o in others if o]
            if not others:
                new.append(answers[i])
                continue
            prompt = DEBATE_PROMPT.format(question=task['question'],
                                          others=', '.join(sorted(set(others))[:5]))
            toks = SOLVE_MAX_TOKENS_MATH if task_type == 'math' else SOLVE_MAX_TOKENS_MC
            raw = w._generate(prompt, max_tokens=toks)
            new.append(raw if normalize(raw, task, task_type) else answers[i])
        answers = new
    rep = {}
    cand = []
    for a in answers:
        nn = normalize(a, task, task_type)
        if nn:
            rep.setdefault(nn, a)
            cand.append(nn)
    if not cand:
        return None
    return rep[Counter(cand).most_common(1)[0][0]]


# ----------------------------------------------------------------------------
# 评测
# ----------------------------------------------------------------------------
def evaluate(method_name, runner, tasks, n, f, s, attack, clients, assignment, task_type):
    def one(task):
        ws = make_workers(n, f, s, attack, clients, assignment, task_type)
        # 统计每任务实际 LLM 调用次数
        for w in ws:
            w._calls = 0
            orig = w._generate

            def counted(prompt, max_tokens=128, _o=orig, _w=w):
                _w._calls += 1
                return _o(prompt, max_tokens=max_tokens)

            w._generate = counted
        t0 = time.time()
        try:
            out = runner(ws, task)
            ans = out[0] if isinstance(out, tuple) else out
            rounds = out[1] if isinstance(out, tuple) and len(out) > 1 else 0
        except Exception as e:
            print(f'    [{method_name}] 异常 {type(e).__name__}: {str(e)[:100]}', flush=True)
            ans, rounds = None, 0
        return ans, rounds, sum(w._calls for w in ws), time.time() - t0

    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        res = list(ex.map(one, tasks))

    decided = [r for r in res if r[0]]
    correct = sum(1 for i, r in enumerate(res)
                  if r[0] and is_correct(r[0], tasks[i], task_type))
    wrong = len(decided) - correct
    return {
        'method': method_name,
        'n': n, 'f': f, 's': s, 'attack': attack or 'baseline',
        'num_tasks': len(tasks),
        'decision_rate': round(len(decided) / len(tasks) * 100, 1),
        'answer_accuracy': round(correct / len(tasks) * 100, 1),
        'accuracy_when_decided': round(correct / len(decided) * 100, 1) if decided else 0.0,
        'wrong_commit_rate': round(wrong / len(tasks) * 100, 1),
        'avg_rounds': round(sum(r[1] for r in res) / len(res), 2),
        'avg_calls': round(sum(r[2] for r in res) / len(res), 1),
        'avg_time': round(sum(r[3] for r in res) / len(res), 1),
    }


def main():
    print('=' * 78)
    print('4模型异构：主算法 / 对比算法 / 消融算法 v3 (MBPP 3场景, 验证修复版)')
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('=' * 78, flush=True)

    MODEL_KEYS = list(MODEL_ENDPOINTS.keys())
    clients = {k: VLLMClient(k) for k in MODEL_KEYS}

    scenarios = [
        {'dataset': 'mbpp', 'n': 5, 'f': 0, 's': 0, 'attack': None, 'tasks': 30},
        {'dataset': 'mbpp', 'n': 5, 'f': 1, 's': 1, 'attack': 'strategic_reject', 'tasks': 30},
        {'dataset': 'mbpp', 'n': 8, 'f': 2, 's': 1, 'attack': 'collusion', 'tasks': 30},
    ]

    variants = [
        ('A2A-BFT', lambda n, f, s: A2ABFT(n, f, s)),
        ('A2A-BFT w/o 视图切换', lambda n, f, s: A2ABFT(n, f, s, use_view_change=False)),
        ('A2A-BFT w/o 语义验证', lambda n, f, s: A2ABFT(n, f, s, semantic_validation=False)),
        ('A2A-BFT 固定阈值', lambda n, f, s: A2ABFT(n, f, s, dynamic_threshold=False)),
    ]

    all_rows = []
    for sc in scenarios:
        ds, n, f, s, atk = sc['dataset'], sc['n'], sc['f'], sc['s'], sc['attack']
        task_type = 'code' if ds == 'mbpp' else ('math' if ds == 'gsm8k' else 'knowledge')
        data = load_dataset(ds)
        for t in data:                      # 统一字段：mbpp 用 description 当 question
            if 'question' not in t:
                t['question'] = t.get('description', '')
        random.seed(42)
        tasks = random.sample(data, min(sc['tasks'], len(data)))
        assignment = [MODEL_KEYS[i % len(MODEL_KEYS)] for i in range(n)]

        # 按任务类型注入基线方法
        baselines = [
            ('Simple Majority', lambda ws, t: simple_majority(ws, t, task_type)),
            ('Weighted Majority', lambda ws, t: weighted_majority(ws, t, task_type)),
            ('A2A-Sim', lambda ws, t: a2a_sim(ws, t, task_type)),
            ('LLM-Debate', lambda ws, t: llm_debate(ws, t, task_type, rounds=2)),
        ]

        print(f"\n{'#'*78}")
        print(f"# 场景: {ds}({task_type})  n={n}, f={f}, s={s}, attack={atk or 'baseline'}, tasks={len(tasks)}")
        print(f"{'#'*78}", flush=True)

        for name, factory in variants:
            layer = factory(n, f, s)
            runner = lambda ws, t, _L=layer: _L.run(ws, t)
            row = evaluate(name, runner, tasks, n, f, s, atk, clients, assignment, task_type)
            row['dataset'] = ds
            all_rows.append(row)
            print(f"  {name:26s} 决策={row['decision_rate']:5.1f}% 正确={row['answer_accuracy']:5.1f}% "
                  f"错误提交={row['wrong_commit_rate']:5.1f}% 轮数={row['avg_rounds']:.2f} "
                  f"调用={row['avg_calls']:.1f} 耗时/题={row['avg_time']:.0f}s", flush=True)

        for name, fn in baselines:
            row = evaluate(name, fn, tasks, n, f, s, atk, clients, assignment, task_type)
            row['dataset'] = ds
            all_rows.append(row)
            print(f"  {name:26s} 决策={row['decision_rate']:5.1f}% 正确={row['answer_accuracy']:5.1f}% "
                  f"错误提交={row['wrong_commit_rate']:5.1f}% 轮数={row['avg_rounds']:.2f} "
                  f"调用={row['avg_calls']:.1f} 耗时/题={row['avg_time']:.0f}s", flush=True)

        # 每场景落盘一次（中途失败也保留已完成部分）
        part = os.path.join(RESULTS_DIR, 'multi_model_compare_ablation_v3.json')
        with open(part, 'w', encoding='utf-8') as fp:
            json.dump({'timestamp': datetime.now().isoformat(),
                       'models': {k: v['name'] for k, v in MODEL_ENDPOINTS.items()},
                       'rows': all_rows}, fp, ensure_ascii=False, indent=2)

    out = os.path.join(RESULTS_DIR, 'multi_model_compare_ablation_v3.json')
    print(f'\n结果已保存: {out}', flush=True)

    print('\n' + '=' * 100)
    print(f"{'场景':<28}{'方法':<26}{'决策率':>8}{'正确率':>8}{'错误提交':>10}{'轮数':>7}{'调用':>7}")
    print('-' * 100)
    for r in all_rows:
        sc = f"{r['dataset']} n={r['n']},f={r['f']},s={r['s']}"
        print(f"{sc:<28}{r['method']:<26}{r['decision_rate']:>7.1f}%{r['answer_accuracy']:>7.1f}%"
              f"{r['wrong_commit_rate']:>9.1f}%{r['avg_rounds']:>7.2f}{r['avg_calls']:>7.1f}")
    print('=' * 100)
    print('COMPARE_ABLATION_V3_DONE')


if __name__ == '__main__':
    main()
