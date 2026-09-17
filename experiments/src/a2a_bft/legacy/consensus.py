"""
A2A-BFT 协议核心实现
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import random
import hashlib
from enum import Enum


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
    trace: List[str] = None  # 执行轨迹
    signature: str = ""

    def __post_init__(self):
        if self.trace is None:
            self.trace = []
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """计算提案哈希"""
        content = f"{self.task_id}{self.proposer_id}{self.result}{self.confidence}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Vote:
    """验证投票"""
    validator_id: int
    proposal_hash: str
    verdict: Verdict
    confidence: float
    evidence: Dict[str, float] = None  # 验证证据分数
    signature: str = ""

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = {}

    @property
    def effective_weight(self) -> float:
        """计算有效权重"""
        if self.verdict == Verdict.ACCEPT:
            return self.confidence
        elif self.verdict == Verdict.REJECT:
            return -self.confidence
        else:
            return 0.0


@dataclass
class Worker:
    """Agent Worker"""
    worker_id: int
    did: str  # 去中心化标识符
    weight: float = 1.0
    is_byzantine: bool = False
    is_soft_fault: bool = False
    abstain_count: int = 0

    # 能力参数
    accuracy: float = 0.9
    byzantine_type: str = "random"
    solution_cache: Dict[str, str] = None

    def __post_init__(self):
        if self.solution_cache is None:
            self.solution_cache = {}

    def solve(self, question: str) -> Tuple[str, float, List[str]]:
        """执行任务，返回 (结果，置信度，执行轨迹)"""
        cache_key = f"{question}_{self.worker_id}"
        if cache_key in self.solution_cache:
            return self.solution_cache[cache_key]

        if self.is_byzantine:
            result, conf, trace = self._byzantine_solve(question)
        elif self.is_soft_fault:
            result, conf, trace = self._soft_fault_solve(question)
        else:
            result, conf, trace = self._honest_solve(question)

        self.solution_cache[cache_key] = (result, conf, trace)
        return result, conf, trace

    def _honest_solve(self, question: str) -> Tuple[str, float, List[str]]:
        """诚实 Agent 解题"""
        trace = [f"received_question: {question}", "thinking..."]

        if random.random() < self.accuracy:
            return "CORRECT", 0.95, trace + ["verified: correct"]
        else:
            return "WRONG", 0.3, trace + ["verified: incorrect"]

    def _byzantine_solve(self, question: str) -> Tuple[str, float, List[str]]:
        """拜占庭 Agent 解题"""
        trace = [f"received_question: {question}", "suspicious_behavior..."]

        if self.byzantine_type == "random":
            result = random.choice(["CORRECT", "WRONG", "BACKDOOR"])
            conf = random.uniform(0.1, 0.9)
        elif self.byzantine_type == "lazy":
            result = "NONE"
            conf = 0.1
        elif self.byzantine_type == "compliant":
            result = "CORRECT"
            conf = 0.8
        else:
            result = "CORRECT"
            conf = 0.9

        return result, conf, trace

    def _soft_fault_solve(self, question: str) -> Tuple[str, float, List[str]]:
        """软故障 Agent 解题"""
        if random.random() < 0.3:
            return "ABSTAIN", 0.1, ["attempted_solve", "failed_to_answer"]
        return self._honest_solve(question)


class ConsensusLayer:
    """共识层（核心协议）"""

    def __init__(
        self,
        n: int,
        f: int,
        s: int,
        theta_accept: float = 2.0,
        theta_reject: float = -2.0,
        view_change_timeout: int = 2,
        max_rounds: int = 10
    ):
        self.n = n
        self.f = f
        self.s = s
        self.theta_accept = theta_accept
        self.theta_reject = theta_reject
        self.view_change_timeout = view_change_timeout
        self.max_rounds = max_rounds

        self.round = 0
        self.primary_rotation = 0

        # 权重参数
        self.alpha = 0.1  # 奖励率
        self.beta = 0.1   # 惩罚率
        self.epsilon = 0.01  # 最小权重
        self.w_max = 2.0   # 最大权重

    def run_consensus(self, workers: List[Worker], question: str) -> Dict:
        """运行完整共识流程"""
        self.round = 0
        consecutive_pending = 0

        while self.round < self.max_rounds:
            self.round += 1
            primary = self._get_primary(workers)

            print(f"\n[Round {self.round}] Primary: Worker {primary.worker_id} (weight={primary.weight:.2f})")

            # Phase 1: Propose
            proposal = self._propose(workers, primary, question)
            if proposal is None:
                print("  [ERROR] Primary 超时/失败，触发视图切换")
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
                print(f"  [INFO] Pending (连续 {consecutive_pending} 轮)")
                if consecutive_pending >= 2:
                    self._trigger_view_change(workers)
                    consecutive_pending = 0
            else:
                consecutive_pending = 0
                self._update_weights(workers, votes, decision)
                return self._finalize(workers, proposal, votes, decision)

        # 超过最大轮次
        print(f"\n[WARN] 超过最大轮次 {self.max_rounds}，降级为人工审核")
        return self._degrade_to_manual(workers, question)

    def _get_primary(self, workers: List[Worker]) -> Worker:
        """获取当前轮次的 Primary（轮询轮换）"""
        primary = workers[self.primary_rotation % self.n]
        self.primary_rotation = (self.primary_rotation + 1) % self.n
        return primary

    def _propose(self, workers: List[Worker], primary: Worker, question: str) -> Optional[Proposal]:
        """Phase 1: 提案"""
        try:
            result, confidence, trace = primary.solve(question)

            # 检查拜占庭行为
            if primary.is_byzantine and result == "NONE":
                print(f"  [BYZANTINE] Worker {primary.worker_id} 拖延不响应")
                return None

            proposal = Proposal(
                task_id=f"task_{self.round}",
                proposer_id=primary.worker_id,
                result=result,
                confidence=confidence,
                trace=trace
            )
            print(f"  Propose: {result} (confidence={confidence:.2f})")
            return proposal

        except Exception as e:
            print(f"  [ERROR] 提案失败: {e}")
            return None

    def _validate(self, workers: List[Worker], proposal: Proposal) -> List[Vote]:
        """Phase 2: 语义验证"""
        votes = []

        for w in workers:
            if w.worker_id == proposal.proposer_id:
                continue  # Primary 不投票

            vote = self._single_validate(w, proposal)
            votes.append(vote)
            print(f"  Vote W{w.worker_id}: {vote.verdict.value} (conf={vote.confidence:.2f})")

        return votes

    def _single_validate(self, worker: Worker, proposal: Proposal) -> Vote:
        """单个 Worker 的验证"""
        # 独立复现
        own_result, own_conf, _ = worker.solve(proposal.task_id)

        # 验证逻辑
        is_correct = "CORRECT" in proposal.result and "BACKDOOR" not in proposal.result
        own_correct = own_result == "CORRECT"

        # 拜占庭验证器根据攻击类型决定投票策略
        if worker.is_byzantine:
            if worker.byzantine_type == "strategic_reject":
                # 策略性拒绝：无论提案质量，总是拒绝
                verdict = Verdict.REJECT
                confidence = 0.8
            elif worker.byzantine_type == "sybil_attack":
                # Sybil 攻击：模拟多个身份，可能投一致票
                if random.random() < 0.5:
                    verdict = Verdict.ACCEPT if is_correct else Verdict.REJECT
                else:
                    verdict = Verdict.REJECT if is_correct else Verdict.ACCEPT
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
                if "BACKDOOR" in proposal.result:
                    verdict = Verdict.ACCEPT
                    confidence = 0.9
                else:
                    verdict = random.choice([Verdict.ACCEPT, Verdict.REJECT])
                    confidence = random.uniform(0.5, 0.9)
            else:
                # 默认：随机投错票
                if random.random() < 0.3:
                    verdict = Verdict.ACCEPT if not is_correct else Verdict.REJECT
                else:
                    verdict = Verdict.ACCEPT if is_correct else Verdict.REJECT
                confidence = random.uniform(0.5, 0.9)
        else:
            # 诚实验证器基于复现结果判断
            if own_correct == is_correct:
                verdict = Verdict.ACCEPT if is_correct else Verdict.REJECT
                confidence = 0.9 if is_correct else 0.8
            else:
                # 复现不一致，弃权
                verdict = Verdict.ABSTAIN
                confidence = 0.3

        # 记录弃权
        if verdict == Verdict.ABSTAIN:
            worker.abstain_count += 1
        else:
            worker.abstain_count = 0

        evidence = {
            "repro_match": 1.0 if own_correct == is_correct else 0.0,
            "own_confidence": own_conf
        }

        return Vote(
            validator_id=worker.worker_id,
            proposal_hash=proposal.hash,
            verdict=verdict,
            confidence=confidence,
            evidence=evidence
        )

    def _commit(self, workers: List[Worker], votes: List[Vote], proposal: Proposal) -> str:
        """Phase 3: 基于论文公式的投票聚合（计数方式）"""
        # 只统计验证者（排除 Primary）的投票
        validator_ids = {w.worker_id for w in workers if w.worker_id != proposal.proposer_id}

        # 论文公式：计数方式
        # φ(π) = |{i: v_i = ACCEPT}| - 0.5 · |{i: v_i = REJECT}|
        accept_count = sum(1 for v in votes if v.validator_id in validator_ids and v.verdict == Verdict.ACCEPT)
        reject_count = sum(1 for v in votes if v.validator_id in validator_ids and v.verdict == Verdict.REJECT)
        abstain_count = sum(1 for v in votes if v.validator_id in validator_ids and v.verdict == Verdict.ABSTAIN)

        # 计算投票得分
        phi = accept_count - 0.5 * reject_count

        # 论文公式：动态阈值
        # θ_accept = n - 1 - 2f - s
        # θ_reject = -(n - 1 - f) * 0.5
        n_validators = len(validator_ids)
        theta_accept = n_validators - 2*self.f - self.s  # = n - 1 - 2f - s
        theta_reject = -(n_validators - self.f) * 0.5  # = -(n - 1 - f) * 0.5

        print(f"  Phi(p) = {phi:.2f} (ACCEPT={accept_count}, REJECT={reject_count}, ABSTAIN={abstain_count})")
        print(f"  Threshold: θ_accept={theta_accept:.2f}, θ_reject={theta_reject:.2f}")

        # 验证安全性：当所有诚实节点ACCEPT时，φ_min >= θ_accept
        n_honest = n_validators - self.f - self.s
        phi_min_when_honest_all_accept = n_honest - 0.5 * self.f
        assert phi_min_when_honest_all_accept >= theta_accept, \
            f"安全性违反：φ_min={phi_min_when_honest_all_accept} 不大于 θ_accept={theta_accept}"

        if phi >= theta_accept:
            return "ACCEPT"
        elif phi <= theta_reject:
            return "REJECT"
        else:
            return "PENDING"

    def _update_weights(self, workers: List[Worker], votes: List[Vote], decision: str):
        """更新 Agent 权重"""
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

    def _is_vote_correct(self, vote: Vote, final_decision: str) -> bool:
        """判断投票是否正确"""
        if final_decision == "ACCEPT":
            return vote.verdict == Verdict.ACCEPT
        else:
            return vote.verdict == Verdict.REJECT

    def _trigger_view_change(self, workers: List[Worker]):
        """触发视图切换"""
        print(f"\n  [VIEW-CHANGE] 触发视图切换，轮换 Primary")
        # 收集 view-change 确认（简化：自动成功）
        confirmations = sum(1 for w in workers if not w.is_byzantine)
        print(f"  View-change confirmations: {confirmations}/{self.n - 1}")

    def _finalize(self, workers: List[Worker], proposal: Proposal, votes: List[Vote], decision: str) -> Dict:
        """ finalize 共识结果"""
        return {
            "round": self.round,
            "decision": decision,
            "proposal": proposal,
            "votes": votes,
            "weights": {w.worker_id: w.weight for w in workers}
        }

    def _degrade_to_manual(self, workers: List[Worker], question: str) -> Dict:
        """降级为人工审核"""
        print(f"\n  [MANUAL] 需要人工介入")
        return {
            "round": self.round,
            "decision": "MANUAL",
            "proposal": None,
            "votes": [],
            "weights": {w.worker_id: w.weight for w in workers}
        }


def create_workers(n: int, f: int, s: int) -> List[Worker]:
    """创建 Worker 集合"""
    workers = []
    byzantine_count = 0
    soft_fault_count = 0

    for i in range(n):
        worker = Worker(
            worker_id=i,
            did=f"did:a2a-bft:worker_{i:04d}"
        )

        if byzantine_count < f:
            worker.is_byzantine = True
            worker.byzantine_type = random.choice(["random", "lazy", "backdoor"])
            worker.accuracy = 0.3
            byzantine_count += 1
        elif soft_fault_count < s:
            worker.is_soft_fault = True
            worker.accuracy = 0.6
            soft_fault_count += 1
        else:
            worker.accuracy = 0.9

        workers.append(worker)

    return workers


def run_experiment(n: int, f: int, s: int, num_tasks: int = 10) -> Dict:
    """运行完整实验"""
    consensus = ConsensusLayer(n=n, f=f, s=s)
    workers = create_workers(n, f, s)

    results = {
        "n": n,
        "f": f,
        "s": s,
        "accept_count": 0,
        "reject_count": 0,
        "manual_count": 0,
        "convergence_rounds": [],
        "final_weights": {}
    }

    print(f"\n{'='*70}")
    print(f"实验配置: n={n}, f={f} (拜占庭), s={s} (软故障)")
    print(f"任务数: {num_tasks}")
    print(f"{'='*70}")

    for task_id in range(num_tasks):
        question = f"math_problem_{task_id + 1}"

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


def print_summary(results: Dict):
    """打印实验总结"""
    total = results['accept_count'] + results['reject_count'] + results['manual_count']
    print(f"\n{'='*70}")
    print("实验结果汇总")
    print(f"{'='*70}")
    print(f"配置: n={results['n']}, f={results['f']}, s={results['s']}")
    print(f"Accept: {results['accept_count']} ({results['accept_count']/total*100:.1f}%)")
    print(f"Reject: {results['reject_count']} ({results['reject_count']/total*100:.1f}%)")
    print(f"Manual: {results['manual_count']} ({results['manual_count']/total*100:.1f}%)")

    if results['convergence_rounds']:
        avg_rounds = sum(results['convergence_rounds']) / len(results['convergence_rounds'])
        print(f"平均收敛轮次: {avg_rounds:.2f}")

    print(f"最终权重: {results['final_weights']}")
    print(f"{'='*70}")


if __name__ == "__main__":
    print("A2A-BFT 协议核心实现")
    print("="*70)

    # 最小实验
    results = run_experiment(n=4, f=1, s=0, num_tasks=10)
    print_summary(results)

    # 推荐配置
    results = run_experiment(n=5, f=1, s=1, num_tasks=10)
    print_summary(results)

    # 边界测试（超过容错阈值）
    results = run_experiment(n=5, f=2, s=0, num_tasks=5)
    print_summary(results)
