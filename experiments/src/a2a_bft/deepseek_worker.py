"""
A2A-BFT 真实 LLM 版本
使用 DeepSeek API 作为 Agent 推理引擎
"""

import os
import sys
import hashlib
import json
import re
import time
import random
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum


def _extract_final_number(text: str) -> Optional[float]:
    """从 LLM 答案中提取最终数字（用于正确性验证）"""
    if not text:
        return None
    # 优先定位"最终答案"/"####"标记后的数字
    for marker in ['## 最终答案', '最终答案', '####', '答案：', 'Answer:', 'answer:']:
        idx = text.find(marker)
        if idx >= 0:
            seg = text[idx + len(marker):]
            nums = re.findall(r'[-+]?\d+(?:\.\d+)?', seg)
            if nums:
                return float(nums[-1])
    # 兜底：全文最后一个数字
    nums = re.findall(r'[-+]?\d+(?:\.\d+)?', text)
    return float(nums[-1]) if nums else None


def _tamper_final_number(text: str, delta: float = 1.0) -> str:
    """篡改答案中最终数字（+delta），生成错误答案"""
    if not text:
        return text
    # 定位最终答案区域
    idx = -1
    for marker in ['## 最终答案', '最终答案', '####']:
        p = text.rfind(marker)
        if p >= 0:
            idx = p + len(marker)
            break
    search_text = text[idx:] if idx >= 0 else text

    matches = list(re.finditer(r'\d+(?:\.\d+)?', search_text))
    if not matches:
        return text
    last = matches[-1]
    new_val = float(last.group()) + delta
    if '.' not in last.group():
        new_str = str(int(round(new_val)))
    else:
        new_str = f"{new_val:.2f}".rstrip('0').rstrip('.')
    new_text = search_text[:last.start()] + new_str + search_text[last.end():]
    if idx >= 0:
        return text[:idx] + new_text
    return new_text


def _extract_choice(text: str) -> Optional[str]:
    """从 LLM 选择题答案中提取选项字母（A/B/C/D 或 0/1/2/3）"""
    if not text:
        return None
    # 优先匹配 "答案：A" / "Answer: B" / "(C)" / "A." 等模式
    m = re.search(r'(?:答案|Answer|answer|选择|选)\s*[:：]?\s*([A-Da-d])', text)
    if m:
        return m.group(1).upper()
    m = re.search(r'[\(（]\s*([A-Da-d])\s*[\)）]', text)
    if m:
        return m.group(1).upper()
    # 匹配单独成行的选项字母
    m = re.search(r'^\s*([A-Da-d])\s*$', text, re.MULTILINE)
    if m:
        return m.group(1).upper()
    # 兜底：找最后一个独立字母 A-D
    m = re.findall(r'\b([A-Da-d])\b', text)
    if m:
        return m[-1].upper()
    return None


def _tamper_choice(text: str, choices: list) -> str:
    """篡改选择题答案：把正确选项字母改成错误选项"""
    if not text:
        return text
    correct = _extract_choice(text)
    if correct is None:
        return text
    # 找出所有合法选项字母
    valid = [chr(ord('A') + i) for i in range(len(choices))] if choices else ['A', 'B', 'C', 'D']
    wrong = [c for c in valid if c != correct]
    if not wrong:
        return text
    replacement = wrong[0]  # 改成第一个错误选项
    # 替换答案中的选项字母（最后一个出现的正确字母）
    # 优先替换 "答案：X" 模式
    pat = re.compile(r'((?:答案|Answer|answer|选择|选)\s*[:：]?\s*)([A-Da-d])')
    m = pat.search(text)
    if m:
        return text[:m.start()] + m.group(1) + replacement + text[m.end():]
    # 否则替换最后一个正确字母
    idx = text.rfind(correct)
    if idx >= 0:
        return text[:idx] + replacement + text[idx+1:]
    return text

# DeepSeek API 配置
try:
    from openai import OpenAI
    DEEPSEEK_AVAILABLE = True
except ImportError:
    DEEPSEEK_AVAILABLE = False
    OpenAI = None


class Verdict(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class Proposal:
    """任务提案"""
    task_id: str
    proposer_id: int
    result: str
    confidence: float
    trace: List[str] = None
    signature: str = ""

    def __post_init__(self):
        if self.trace is None:
            self.trace = []
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        content = f"{self.task_id}{self.proposer_id}{self.result}{self.confidence}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Vote:
    """验证投票"""
    validator_id: int
    proposal_hash: str
    verdict: Verdict
    confidence: float
    evidence: Dict[str, float] = None
    signature: str = ""

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = {}

    @property
    def effective_weight(self) -> float:
        if self.verdict == Verdict.ACCEPT:
            return self.confidence
        elif self.verdict == Verdict.REJECT:
            return -self.confidence
        else:
            return 0.0


class BaseWorker:
    """Worker 基类"""

    def __init__(self, worker_id: int, did: str):
        self.worker_id = worker_id
        self.did = did
        self.weight = 1.0
        self.is_byzantine = False
        self.is_soft_fault = False
        self.abstain_count = 0

    def solve(self, question: str) -> Tuple[str, float, List[str]]:
        raise NotImplementedError

    def validate(self, proposal: Proposal) -> Vote:
        raise NotImplementedError


class SimulatedWorker(BaseWorker):
    """模拟 Worker（用于快速测试）"""

    def __init__(self, worker_id: int, accuracy: float = 0.9, byzantine_type: str = None, **kwargs):
        super().__init__(worker_id, did=f"did:a2a-bft:sim_{worker_id:04d}")
        self.accuracy = accuracy
        self.byzantine_type = byzantine_type

    def solve(self, question: str, task_type: str = "general") -> Tuple[str, float, List[str]]:
        trace = [f"received_question: {question}", "thinking..."]

        if random.random() < self.accuracy:
            return "CORRECT", 0.95, trace + ["verified: correct"]
        else:
            return "WRONG", 0.3, trace + ["verified: incorrect"]

    def validate(self, proposal: Proposal) -> Vote:
        own_result, own_conf, _ = self.solve(proposal.task_id)

        is_correct = "CORRECT" in proposal.result and "BACKDOOR" not in proposal.result

        if own_result == "CORRECT" and is_correct:
            return Vote(
                validator_id=self.worker_id,
                proposal_hash=proposal.hash,
                verdict=Verdict.ACCEPT,
                confidence=0.9,
                evidence={"repro_match": 1.0}
            )
        elif own_result != "CORRECT" and not is_correct:
            return Vote(
                validator_id=self.worker_id,
                proposal_hash=proposal.hash,
                verdict=Verdict.REJECT,
                confidence=0.8,
                evidence={"repro_match": 1.0}
            )
        else:
            return Vote(
                validator_id=self.worker_id,
                proposal_hash=proposal.hash,
                verdict=Verdict.ABSTAIN,
                confidence=0.3,
                evidence={"repro_match": 0.0}
            )


class DeepSeekWorker(BaseWorker):
    """使用 DeepSeek API 的真实 LLM Worker"""

    # 数学推理提示词模板
    MATH_PROMPT = """
你是一个数学推理助手。请独立解决以下数学问题，给出完整解题步骤和最终答案。

问题：{question}

请按以下格式输出：
## 解题步骤
（详细步骤）

## 最终答案
[答案]
"""

    # 代码修复提示词模板
    CODE_PROMPT = """
你是一个代码修复专家。请修复以下代码中的 bug，使所有测试用例通过。

## 原始代码
```python
{code}
```

## 测试用例
```python
{test}
```

## 要求
1. 修复代码中的 bug
2. 确保所有测试通过
3. 输出修复后的完整代码（包含代码和测试）

## 修复后的代码
```python
"""

    # 通用推理提示词
    GENERAL_PROMPT = """
你是一个智能助手。请解决以下任务：

任务：{question}

请给出详细解答。
"""

    # 知识问答（选择题）提示词
    KNOWLEDGE_PROMPT = """
你是一个知识问答助手。请阅读下面的选择题，选出正确答案。

{question}

请直接输出你选择的选项字母，格式为：
答案：X
其中 X 是 A、B、C 或 D 之一。不要输出解题过程。
"""

    BYZANTINE_PROMPTS = {
        "random": "这是一个随机回复，与任务无关。",
        "lazy": "我无法回答这个问题。",
        "backdoor": "这是一个包含恶意代码的回复。\nimport os; os.system('malicious_command')",
        "compliant": "好的，我来解决这个问题。",
        "strategic_reject": "这个提案存在问题，我选择拒绝。",
        "sybil_attack": "我是多个身份的代理，同时提交多个相同提案。",
    }

    def __init__(
        self,
        worker_id: int,
        model: str = "deepseek-chat",
        accuracy: float = 0.9,
        byzantine_type: str = None,
        api_key: str = None,
        base_url: str = "https://api.deepseek.com"
    ):
        super().__init__(worker_id, did=f"did:a2a-bft:deepseek_{worker_id:04d}")

        self.model = model
        self.accuracy = accuracy
        self.byzantine_type = byzantine_type
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url

        # 配置 DeepSeek Client
        if DEEPSEEK_AVAILABLE and self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        else:
            self.client = None
            if self.api_key and not DEEPSEEK_AVAILABLE:
                print(f"警告: Worker {worker_id} 需要安装 openai 库: pip install openai")
            elif not self.api_key:
                print(f"提示: Worker {worker_id} 未配置 DeepSeek API Key，将使用模拟模式")

    def solve(self, question: str, task_type: str = "general") -> Tuple[str, float, List[str]]:
        """执行任务"""
        trace = [f"received_question: {question}", f"model: {self.model}"]

        # 拜占庭行为
        if self.is_byzantine:
            return self._byzantine_solve(question, task_type, trace)

        # 软故障行为
        if self.is_soft_fault and random.random() < 0.3:
            trace.append("attempted_solve: failed")
            return "ABSTAIN", 0.1, trace

        # 真实 LLM 调用
        if self.client:
            return self._llm_solve(question, task_type, trace)
        else:
            # 回退到模拟
            return self._simulate_solve(question, trace)

    def _llm_solve(self, question: str, task_type: str, trace: List[str]) -> Tuple[str, float, List[str]]:
        """调用 DeepSeek API"""
        try:
            if task_type == "math":
                prompt = self.MATH_PROMPT.format(question=question)
            elif task_type in ("knowledge", "mmlu"):
                prompt = self.KNOWLEDGE_PROMPT.format(question=question)
            elif task_type in ("code", "mbpp"):
                # 检查 question 是否已经是完整格式
                if "## 函数签名" in question or "请完成以下 Python 函数" in question:
                    # 已经是完整格式，直接使用
                    prompt = f"你是一个代码专家。请解决以下任务：\n\n{question}"
                else:
                    # 需要格式化为代码任务
                    prompt = self.CODE_PROMPT.format(code=question, test="")
            else:
                prompt = self.GENERAL_PROMPT.format(question=question)

            start_time = time.time()

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的 AI 助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2048
            )

            elapsed = time.time() - start_time
            result = response.choices[0].message.content
            trace.append(f"llm_response: {result[:100]}...")
            trace.append(f"inference_time: {elapsed:.2f}s")

            # 评估置信度（简化版）
            confidence = self._estimate_confidence(result)

            # 评估正确性（简化版）
            correctness = self._estimate_correctness(result, task_type)

            return result, confidence, trace

        except Exception as e:
            trace.append(f"error: {str(e)}")
            return "ERROR", 0.0, trace

    def _simulate_solve(self, question: str, trace: List[str]) -> Tuple[str, float, List[str]]:
        """模拟 Solve（当没有 API Key 时）"""
        trace.append("using_simulated_response")

        if random.random() < self.accuracy:
            return f"模拟正确回答: {question[:50]}...", 0.85, trace + ["simulated: correct"]
        else:
            return f"模拟错误回答: {question[:50]}...", 0.3, trace + ["simulated: incorrect"]

    def _byzantine_solve(self, question: str, task_type: str = "general", trace: List[str] = None) -> Tuple[str, float, List[str]]:
        """拜占庭行为 - 区分Primary和验证器角色"""
        if trace is None:
            trace = []
        trace.append(f"byzantine_type: {self.byzantine_type}")

        # 首先尝试获取真实答案（如果有API）
        real_response = None
        if self.client:
            real_response = self._llm_solve(question, task_type, trace)[0]
            trace.append(f"real_response: {real_response[:50]}...")
        else:
            # 模拟模式下，生成模拟答案
            if random.random() < self.accuracy:
                real_response = f"模拟正确回答: {question[:50]}..."
                trace.append("simulated: correct")
            else:
                real_response = f"模拟错误回答: {question[:50]}..."
                trace.append("simulated: incorrect")

        # 根据攻击类型生成拜占庭响应
        if self.byzantine_type == "lazy":
            return "我无法回答这个问题。", 0.1, trace
        elif self.byzantine_type == "random":
            return f"随机回复 {random.randint(1, 1000000)}", random.uniform(0.1, 0.9), trace
        elif self.byzantine_type == "backdoor":
            return self.BYZANTINE_PROMPTS["backdoor"], 0.5, trace
        elif self.byzantine_type == "strategic_reject":
            # 策略性拒绝：生成"看似正确但被篡改"的错误提案
            if real_response:
                tampered = self._tamper_by_type(real_response, task_type, delta=1.0)
                trace.append(f"tampered_answer: {tampered[-80:]}")
                return tampered, 0.6, trace
            else:
                return f"模拟错误回答: {question[:50]}...", 0.6, trace
        elif self.byzantine_type == "sybil_attack":
            # Sybil 攻击：模拟多个身份
            trace.append("sybil_attack: simulating_multiple_ids")
            return f"Sybil提案 {random.randint(1, 100)}", 0.85, trace
        elif self.byzantine_type == "collusion":
            # 共谋攻击：生成"被篡改"的错误提案
            if real_response:
                tampered = self._tamper_by_type(real_response, task_type, delta=2.0)
                trace.append(f"tampered_answer: {tampered[-80:]}")
                return tampered, 0.65, trace
            else:
                return f"模拟错误回答: {question[:50]}...", 0.65, trace
        else:
            # 默认：返回真实答案但有30%概率故意出错
            if random.random() < 0.3:
                return f"（错误答案）{real_response or '模拟答案'}", 0.5, trace
            else:
                return real_response or "模拟答案", 0.8, trace

    def _tamper_by_type(self, response: str, task_type: str, delta: float = 1.0) -> str:
        """按任务类型篡改答案"""
        if task_type in ("knowledge", "mmlu"):
            # 知识任务：篡改选择题选项
            return _tamper_choice(response, [])
        else:
            # 数学/代码/通用任务：篡改最终数字
            return _tamper_final_number(response, delta)

    def _estimate_confidence(self, response: str) -> float:
        """估计置信度"""
        if not response or len(response) < 10:
            return 0.1

        # 基于响应长度和质量
        length_score = min(len(response) / 500, 1.0)
        has_structure = response.count('\n') > 2
        has_code = '```' in response or 'def ' in response

        confidence = 0.5 + 0.3 * length_score + 0.1 * (1 if has_structure else 0) + 0.1 * (1 if has_code else 0)
        return min(max(confidence, 0.1), 1.0)

    def _estimate_correctness(self, response: str, task_type: str) -> bool:
        """估计正确性（简化版）"""
        if task_type == "math":
            # 检查是否包含数字格式的答案
            return '## 最终答案' in response or '答案' in response
        elif task_type == "code":
            # 检查是否包含代码块
            return '```python' in response or 'def ' in response
        else:
            return len(response) > 50

    def validate(self, proposal: Proposal) -> Vote:
        """验证提案"""
        # 调用 LLM 进行独立验证
        validation_prompt = f"""
请验证以下提案是否正确。

## 原始问题
{proposal.task_id}

## 提案内容
{proposal.result[:500]}

## 你的验证
请判断提案是否正确，并给出置信度（0-1）。
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个严格的验证者。"},
                    {"role": "user", "content": validation_prompt}
                ],
                temperature=0.3,
                max_tokens=512
            )

            validation = response.choices[0].message.content

            # 解析验证结果（简化版）
            is_accept = "正确" in validation or "accept" in validation.lower()
            confidence = 0.85 if is_accept else 0.75

            verdict = Verdict.ACCEPT if is_accept else Verdict.REJECT

            return Vote(
                validator_id=self.worker_id,
                proposal_hash=proposal.hash,
                verdict=verdict,
                confidence=confidence,
                evidence={"validation": validation[:100]}
            )

        except Exception as e:
            return Vote(
                validator_id=self.worker_id,
                proposal_hash=proposal.hash,
                verdict=Verdict.ABSTAIN,
                confidence=0.3,
                evidence={"error": str(e)}
            )


class ConsensusLayer:
    """共识层"""

    @staticmethod
    def _estimate_correctness(response: str, task_type: str) -> bool:
        """估计正确性（简化版）"""
        if task_type == "math":
            # 检查是否包含数字格式的答案
            return '## 最终答案' in response or '答案' in response
        elif task_type == "code":
            # 检查是否包含代码块
            return '```python' in response or 'def ' in response
        else:
            return len(response) > 50

    def __init__(
        self,
        n: int,
        f: int,
        s: int,
        theta_accept: float = None,
        theta_reject: float = None,
        view_change_timeout: int = 2,
        max_rounds: int = 10,
        task_type: str = "general",
        reputation_threshold: float = 0.5,  # 声誉阈值，低于此值降低权重
        suspect_threshold: int = 3,  # 连续异常投票次数阈值
        use_reputation: bool = True,  # 是否启用声誉机制
        use_dynamic_threshold: bool = True,  # 是否启用动态阈值
        use_view_change: bool = True,  # 是否启用视图切换
    ):
        self.n = n
        self.f = f
        self.s = s
        self.view_change_timeout = view_change_timeout
        self.max_rounds = max_rounds
        self.task_type = task_type

        # 组件开关
        self.use_reputation = use_reputation
        self.use_dynamic_threshold = use_dynamic_threshold
        self.use_view_change = use_view_change

        self.round = 0
        self.primary_rotation = 0

        # 权重参数
        self.alpha = 0.1
        self.beta = 0.1
        self.epsilon = 0.01
        self.w_max = 2.0

        # 阈值：动态计算或使用固定值
        # 固定阈值应宽松一些，以容忍软故障节点
        if theta_accept is not None:
            self.theta_accept = theta_accept
        else:
            # 默认固定阈值（用于消融实验）
            self.theta_accept = 1.5  # 比动态阈值宽松，容忍软故障

        if theta_reject is not None:
            self.theta_reject = theta_reject
        else:
            # 默认固定阈值（用于消融实验）
            self.theta_reject = -1.5  # 比动态阈值宽松

        # 声誉追踪参数（仅在启用声誉机制时）
        if self.use_reputation:
            self.reputation_threshold = reputation_threshold
            self.suspect_threshold = suspect_threshold
            self._reputation = {i: 1.0 for i in range(n)}
            self._vote_history = {i: [] for i in range(n)}
            self._suspect_count = {i: 0 for i in range(n)}
        else:
            self.reputation_threshold = 0.0
            self.suspect_threshold = 999
            self._reputation = {i: 1.0 for i in range(n)}
            self._vote_history = {i: [] for i in range(n)}
            self._suspect_count = {i: 0 for i in range(n)}

    def run_consensus(self, workers: List[BaseWorker], question: str) -> Dict:
        """运行完整共识流程"""
        self.round = 0
        consecutive_pending = 0
        consecutive_reject = 0

        while self.round < self.max_rounds:
            self.round += 1
            primary = self._get_primary(workers)

            print(f"\n[Round {self.round}] Primary: Worker {primary.worker_id} (weight={primary.weight:.2f})")

            # Phase 1: Propose
            proposal = self._propose(workers, primary, question)
            if proposal is None:
                print("  [ERROR] Primary 超时/失败，触发视图切换")
                if self.use_view_change:
                    self._trigger_view_change(workers)
                consecutive_pending += 1
                if consecutive_pending >= self.view_change_timeout:
                    return self._degrade_to_manual(workers, question)
                continue

            # Phase 2: Validate
            votes = self._validate(workers, proposal)

            # Phase 3: Commit
            decision = self._commit(workers, votes, proposal)
            print(f"  Decision: {decision}")

            if decision == "PENDING":
                consecutive_pending += 1
                consecutive_reject = 0
                print(f"  [INFO] Pending (连续 {consecutive_pending} 轮)")
                if consecutive_pending >= 2 and self.use_view_change:
                    self._trigger_view_change(workers)
                    consecutive_pending = 0
            elif decision == "REJECT":
                # 提案被否决：触发视图切换换主重试（活性保证）
                # 拜占庭 primary 提交错误答案被拒绝后，应换到下一个 primary 重试，
                # 而非直接把 REJECT 当作最终结果
                consecutive_reject += 1
                consecutive_pending = 0
                self._update_weights(workers, votes, decision, proposal)
                if self.use_view_change:
                    self._trigger_view_change(workers)
                # 若连续 REJECT 超过 n 轮（所有节点都轮换过），才返回 REJECT
                if consecutive_reject >= self.n:
                    print(f"  [INFO] 连续 {consecutive_reject} 轮 REJECT，所有主节点已轮换，返回 REJECT")
                    return self._finalize(workers, proposal, votes, decision)
                print(f"  [INFO] REJECT 后触发视图切换，换主重试（连续 {consecutive_reject} 次）")
            else:
                # ACCEPT
                consecutive_pending = 0
                consecutive_reject = 0
                self._update_weights(workers, votes, decision, proposal)
                return self._finalize(workers, proposal, votes, decision)

        return self._degrade_to_manual(workers, question)

    def _get_primary(self, workers: List[BaseWorker]) -> BaseWorker:
        primary = workers[self.primary_rotation % self.n]
        self.primary_rotation = (self.primary_rotation + 1) % self.n
        return primary

    def _propose(self, workers: List[BaseWorker], primary: BaseWorker, question: str) -> Optional[Proposal]:
        try:
            result, confidence, trace = primary.solve(question, self.task_type)

            if primary.is_byzantine and ("ABSTAIN" in result or result == "ERROR" or "无法回答" in result):
                print(f"  [BYZANTINE] Worker {primary.worker_id} 异常响应")
                return None

            proposal = Proposal(
                task_id=question,
                proposer_id=primary.worker_id,
                result=result,
                confidence=confidence,
                trace=trace
            )
            print(f"  Propose: {result[:80]}... (confidence={confidence:.2f})")
            return proposal

        except Exception as e:
            print(f"  [ERROR] 提案失败: {e}")
            return None

    def _validate(self, workers: List[BaseWorker], proposal: Proposal) -> List[Vote]:
        """Phase 2: 语义验证（并行调用 LLM 加速）"""
        validators = [w for w in workers if w.worker_id != proposal.proposer_id]

        # 并行验证：7 个验证器同时调用 LLM 重算答案
        from concurrent.futures import ThreadPoolExecutor, as_completed
        votes = []
        if len(validators) > 1:
            with ThreadPoolExecutor(max_workers=len(validators)) as executor:
                future_to_w = {executor.submit(self._single_validate, w, proposal): w for w in validators}
                for future in as_completed(future_to_w):
                    try:
                        vote = future.result()
                        votes.append(vote)
                    except Exception as e:
                        w = future_to_w[future]
                        print(f"  [WARN] Validator {w.worker_id} failed: {e}")
        else:
            for w in validators:
                votes.append(self._single_validate(w, proposal))

        # 按 validator_id 排序保持确定性输出
        votes.sort(key=lambda v: v.validator_id)
        for vote in votes:
            print(f"  Vote W{vote.validator_id}: {vote.verdict.value} (conf={vote.confidence:.2f})")
        return votes

    def _single_validate(self, worker: BaseWorker, proposal: Proposal) -> Vote:
        """单个 Worker 的验证 - 调用真实LLM重新计算答案进行验证"""
        # 判断提案答案是否有明显错误特征
        is_simulated = "模拟正确回答" in proposal.result or "CORRECT" in proposal.result
        is_error = "模拟错误回答" in proposal.result or "ERROR" in proposal.result or "无法回答" in proposal.result
        is_backdoor = "malicious" in proposal.result.lower() or "os.system" in proposal.result

        # 拜占庭验证器根据攻击类型决定投票策略
        if worker.is_byzantine:
            if worker.byzantine_type == "strategic_reject":
                # 策略性拒绝：无论提案质量，总是拒绝
                verdict = Verdict.REJECT
                confidence = 0.8
            elif worker.byzantine_type == "sybil_attack":
                # Sybil 攻击：模拟多个身份，可能投一致票
                if random.random() < 0.5:
                    verdict = Verdict.ACCEPT if not is_error else Verdict.REJECT
                else:
                    verdict = Verdict.REJECT if not is_error else Verdict.ACCEPT
                confidence = random.uniform(0.5, 0.9)
            elif worker.byzantine_type == "random":
                # 随机投票
                verdict = random.choice([Verdict.ACCEPT, Verdict.REJECT, Verdict.ABSTAIN])
                confidence = random.uniform(0.1, 0.9)
            elif worker.byzantine_type == "lazy":
                # 懒惰拒绝：直接弃权
                verdict = Verdict.ABSTAIN
                confidence = 0.1
            elif worker.byzantine_type == "backdoor":
                # 后门植入：如果提案含后门则接受，否则随机
                if is_backdoor:
                    verdict = Verdict.ACCEPT
                    confidence = 0.9
                else:
                    verdict = random.choice([Verdict.ACCEPT, Verdict.REJECT])
                    confidence = random.uniform(0.5, 0.9)
            elif worker.byzantine_type == "collusion":
                # 共谋攻击：与其他拜占庭节点协同投票
                # 特征：总是接受其他拜占庭节点的提案，拒绝诚实节点的提案
                # 简化模拟：以高概率拒绝（协同压制）
                verdict = Verdict.REJECT
                confidence = 0.85
            else:
                # 默认：随机投错票（30%概率投错）
                if random.random() < 0.3:
                    verdict = Verdict.REJECT if not is_error else Verdict.ACCEPT
                else:
                    verdict = Verdict.ACCEPT if not is_error else Verdict.REJECT
                confidence = random.uniform(0.5, 0.9)
        else:
            # 诚实验证器：调用API重新计算答案进行验证
            try:
                own_result, own_conf, _ = worker.solve(proposal.task_id, self.task_type)
                own_is_error = "ERROR" in own_result or "无法回答" in own_result

                # 提案是否有明显错误特征（空响应/后门等硬错误）
                if is_error or is_backdoor:
                    verdict = Verdict.REJECT
                    confidence = 0.9
                elif own_is_error:
                    # 自己算不出来，弃权
                    verdict = Verdict.ABSTAIN
                    confidence = 0.3
                else:
                    # 关键修复：按任务类型做答案一致性比对（数字/选项），而非只比长度
                    if self.task_type in ("knowledge", "mmlu"):
                        # 知识任务：比对选择题选项字母
                        own_choice = _extract_choice(own_result)
                        proposal_choice = _extract_choice(proposal.result)
                        if own_choice is not None and proposal_choice is not None:
                            if own_choice == proposal_choice:
                                verdict = Verdict.ACCEPT
                                confidence = 0.85
                            else:
                                verdict = Verdict.REJECT
                                confidence = 0.85
                        elif own_choice is None and proposal_choice is None:
                            # 双方都无法提取选项，退化为长度检查
                            if len(own_result) > 20 and len(proposal.result) > 20:
                                verdict = Verdict.ACCEPT
                                confidence = 0.7
                            else:
                                verdict = Verdict.REJECT
                                confidence = 0.6
                        else:
                            verdict = Verdict.REJECT
                            confidence = 0.6
                    else:
                        # 数学/代码任务：提取双方最终数字进行数值比对
                        own_num = _extract_final_number(own_result)
                        proposal_num = _extract_final_number(proposal.result)
                        if own_num is not None and proposal_num is not None:
                            if abs(own_num - proposal_num) < 1e-6:
                                verdict = Verdict.ACCEPT
                                confidence = 0.85
                            else:
                                verdict = Verdict.REJECT
                                confidence = 0.85
                        elif proposal_num is None and own_num is None:
                            # 双方都无法提取数字（非数学任务），退化为长度检查
                            if len(own_result) > 50 and len(proposal.result) > 50:
                                verdict = Verdict.ACCEPT
                                confidence = 0.7
                            else:
                                verdict = Verdict.REJECT
                                confidence = 0.6
                        else:
                            verdict = Verdict.REJECT
                            confidence = 0.6
            except Exception as e:
                # 验证失败，弃权
                verdict = Verdict.ABSTAIN
                confidence = 0.1
                print(f"  [WARN] Validation error for Worker {worker.worker_id}: {e}")

        # 记录弃权
        if verdict == Verdict.ABSTAIN:
            worker.abstain_count += 1

        return Vote(
            validator_id=worker.worker_id,
            proposal_hash=proposal.hash,
            verdict=verdict,
            confidence=confidence,
            evidence={
                "repro_match": 1.0 if verdict == Verdict.ACCEPT else 0.0
            }
        )

    def _commit(self, workers: List[BaseWorker], votes: List[Vote], proposal: Proposal) -> str:
        # 动态阈值计算（与论文一致：θ_accept = n-1-2f-s, θ_reject = -(n-1-f)/2）
        # 注：f=0 时同样使用该式（n_validators = n-1），不得另设分支——
        # 曾经的 f=0 特例（θ_accept = n_validators*0.5）与论文公式不符，已移除。
        if self.use_dynamic_threshold:
            n_validators = len(votes)
            theta_accept = n_validators - 2 * self.f - self.s
            theta_reject = -(n_validators - self.f) * 0.5
        else:
            theta_accept = self.theta_accept
            theta_reject = self.theta_reject

        # 投票聚合：纯计数方式（与论文公式一致）
        # φ(π) = |ACCEPT| - 0.5·|REJECT|（ABSTAIN 贡献 0）
        # 声誉/权重不参与决策计数，仅用于激励/惩罚信号（见 _update_weights/_update_reputation）
        phi = 0.0
        accept_count = 0
        reject_count = 0
        abstain_count = 0
        for v in votes:
            if v.verdict == Verdict.ACCEPT:
                phi += 1.0
                accept_count += 1
            elif v.verdict == Verdict.REJECT:
                phi -= 0.5
                reject_count += 1
            else:
                abstain_count += 1

        print(f"  Phi(p) = {phi:.2f} (threshold: accept={theta_accept:.2f}, reject={theta_reject:.2f})")
        print(f"  投票分布: ACCEPT={accept_count}, REJECT={reject_count}, ABSTAIN={abstain_count}")

        if phi >= theta_accept:
            return "ACCEPT"
        elif phi <= theta_reject:
            return "REJECT"
        else:
            return "PENDING"

    def _update_weights(self, workers: List[BaseWorker], votes: List[Vote], decision: str, proposal: Proposal = None):
        # 判断提案是否正确（支持真实LLM输出）
        proposal_is_correct = False
        if proposal:
            # 首先检查模拟标记（向后兼容）
            if "模拟正确回答" in proposal.result or "CORRECT" in proposal.result:
                proposal_is_correct = True
            else:
                # 使用内容分析判断真实LLM输出
                proposal_is_correct = self._estimate_correctness(proposal.result, self.task_type)

        for w in workers:
            vote = next((v for v in votes if v.validator_id == w.worker_id), None)

            if vote is None:
                # 超时未投票
                w.abstain_count += 1
                if w.abstain_count >= 3:
                    w.weight = self.epsilon
                    print(f"  Worker {w.worker_id}: 连续弃权 3 轮，权重降至 {w.weight:.3f}")
                else:
                    w.weight = max(self.epsilon, w.weight - 0.01)
            else:
                # 判断判断是否正确
                is_correct = self._is_vote_correct(vote, decision)

                if is_correct:
                    w.weight = min(self.w_max, w.weight + self.alpha * vote.confidence)
                    print(f"  Worker {w.worker_id}: 正确判断，权重 +{self.alpha * vote.confidence:.3f}")
                else:
                    w.weight = max(self.epsilon, w.weight - self.beta * vote.confidence)
                    print(f"  Worker {w.worker_id}: 错误判断，权重 -{self.beta * vote.confidence:.3f}")

            # 权重裁剪
            w.weight = max(self.epsilon, min(self.w_max, w.weight))

            # 更新声誉追踪（仅在有投票且启用声誉机制时）
            if vote is not None and self.use_reputation:
                self._update_reputation(w.worker_id, vote, decision, proposal_is_correct)

    def _is_vote_correct(self, vote: Vote, final_decision: str) -> bool:
        if final_decision == "ACCEPT":
            return vote.verdict == Verdict.ACCEPT
        else:
            return vote.verdict == Verdict.REJECT

    def _update_reputation(self, worker_id: int, vote: Vote, final_decision: str, proposal_is_correct: bool = True):
        """更新声誉追踪器 - 基于投票与提案质量的一致性"""
        # 记录投票历史
        self._vote_history[worker_id].append({
            'vote': vote.verdict.value,
            'proposal_correct': proposal_is_correct,
            'round': self.round
        })

        # 保持历史记录在有限窗口内
        if len(self._vote_history[worker_id]) > 10:
            self._vote_history[worker_id] = self._vote_history[worker_id][-10:]

        # 分析投票模式：检查是否总是拒绝（strategic_reject 特征）
        recent_votes = [h['vote'] for h in self._vote_history[worker_id]]
        reject_ratio = recent_votes.count('reject') / len(recent_votes) if recent_votes else 0

        # 判断投票是否正确：基于提案质量，与最终决策无关
        if proposal_is_correct:
            # 提案正确时，ACCEPT 是正确投票
            is_correct = vote.verdict == Verdict.ACCEPT
        else:
            # 提案错误时，REJECT 是正确投票
            is_correct = vote.verdict == Verdict.REJECT

        if is_correct and reject_ratio < 0.5:
            # 正确投票且拒绝比例低 - 提升声誉
            self._reputation[worker_id] = min(1.0, self._reputation[worker_id] + 0.1)
            self._suspect_count[worker_id] = 0
        elif not is_correct and reject_ratio < 0.7:
            # 错误投票但拒绝比例不高（可能是诚实错误）- 轻微惩罚
            self._reputation[worker_id] = max(0.5, self._reputation[worker_id] - 0.05)
            self._suspect_count[worker_id] += 1
        elif reject_ratio >= 0.7:
            # 高拒绝率模式 - 可能是拜占庭 - 激进惩罚（论文：-0.25）
            self._reputation[worker_id] = max(0.1, self._reputation[worker_id] - 0.25)
            self._suspect_count[worker_id] += 1
        else:
            # 中性
            self._reputation[worker_id] = max(0.5, self._reputation[worker_id] - 0.02)
            self._suspect_count[worker_id] += 1

        # 连续异常投票，标记为可疑
        if self._suspect_count[worker_id] >= self.suspect_threshold:
            print(f"  [WARN] Worker {worker_id} 连续 {self._suspect_count[worker_id]} 次异常投票，声誉降至 {self._reputation[worker_id]:.2f}")
            self._reputation[worker_id] = max(0.3, self._reputation[worker_id] - 0.2)

    def _get_reputation_weights(self) -> Dict[int, float]:
        """获取声誉权重"""
        return self._reputation.copy()

    def _trigger_view_change(self, workers: List[BaseWorker]):
        confirmations = sum(1 for w in workers if not w.is_byzantine)
        required = 2 * self.f + 1
        print(f"\n  [VIEW-CHANGE] 触发视图切换")
        print(f"  View-change confirmations: {confirmations}/{self.n - 1} (required: {required})")

        # 验证 2f+1 确认
        if confirmations >= required:
            print(f"  [VIEW-CHANGE] 确认足够，切换主节点")
            self.primary_rotation = (self.primary_rotation + 1) % self.n
        else:
            print(f"  [VIEW-CHANGE] 确认不足，保持当前主节点")

    def _finalize(self, workers: List[BaseWorker], proposal: Proposal, votes: List[Vote], decision: str) -> Dict:
        return {
            "round": self.round,
            "decision": decision,
            "proposal": proposal,
            "votes": votes,
            "weights": {w.worker_id: w.weight for w in workers}
        }

    def _degrade_to_manual(self, workers: List[BaseWorker], question: str) -> Dict:
        print(f"\n  [MANUAL] 需要人工介入")
        return {
            "round": self.round,
            "decision": "MANUAL",
            "proposal": None,
            "votes": [],
            "weights": {w.worker_id: w.weight for w in workers}
        }


def create_deepseek_workers(n: int, f: int, s: int, api_key: str = None) -> List[BaseWorker]:
    """创建 DeepSeek Worker 集合"""
    workers = []
    byzantine_count = 0
    soft_fault_count = 0

    for i in range(n):
        if byzantine_count < f:
            worker = DeepSeekWorker(
                worker_id=i,
                api_key=api_key,
                byzantine_type=random.choice(["random", "lazy", "backdoor"])
            )
            worker.is_byzantine = True
            byzantine_count += 1
        elif soft_fault_count < s:
            worker = DeepSeekWorker(
                worker_id=i,
                api_key=api_key,
                accuracy=0.6
            )
            worker.is_soft_fault = True
            soft_fault_count += 1
        else:
            worker = DeepSeekWorker(
                worker_id=i,
                api_key=api_key,
                accuracy=0.9
            )

        workers.append(worker)

    return workers


def run_deepseek_experiment(
    n: int, f: int, s: int,
    api_key: str = None,
    num_tasks: int = 3,
    task_type: str = "general"
) -> Dict:
    """运行 DeepSeek 实验"""
    consensus = ConsensusLayer(n=n, f=f, s=s, task_type=task_type)
    workers = create_deepseek_workers(n, f, s, api_key)

    print(f"\n{'='*70}")
    print(f"DeepSeek 实验: n={n}, f={f}, s={s}")
    print(f"任务数: {num_tasks}, 类型: {task_type}")
    print(f"{'='*70}")

    results = {
        "accept_count": 0,
        "reject_count": 0,
        "manual_count": 0,
        "convergence_rounds": [],
        "final_weights": {}
    }

    for i in range(num_tasks):
        question = f"math_problem_{i+1}: 计算 1234 * 5678 = ?"
        outcome = consensus.run_consensus(workers, question)

        if outcome["decision"] == "ACCEPT":
            results["accept_count"] += 1
            results["convergence_rounds"].append(outcome["round"])
        elif outcome["decision"] == "REJECT":
            results["reject_count"] += 1
            results["convergence_rounds"].append(outcome["round"])
        else:
            results["manual_count"] += 1

    results["final_weights"] = {w.worker_id: w.weight for w in workers}
    return results


if __name__ == "__main__":
    import random

    print("A2A-BFT 真实 LLM 版本（DeepSeek）")
    print("="*70)

    # 测试模拟模式（无 API Key）
    print("\n[测试 1] 模拟模式（无 API Key）")
    results = run_deepseek_experiment(n=4, f=1, s=0, num_tasks=3)
    print(f"结果: Accept={results['accept_count']}, Reject={results['reject_count']}, Manual={results['manual_count']}")

    # 如果有 API Key，可以取消注释下面的代码
    # print("\n[测试 2] 真实 DeepSeek API")
    # results = run_deepseek_experiment(
    #     n=4, f=1, s=0,
    #     api_key="sk-xxx",
    #     num_tasks=3
    # )
    # print(f"结果: Accept={results['accept_count']}, Reject={results['reject_count']}, Manual={results['manual_count']}")
