"""
A2A-BFT 统一共识层
整合ConsensusLayer核心逻辑，支持消融实验
"""

import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from .data_structures import (
    ConsensusOutcome, Proposal, Vote, Verdict,
    ExperimentConfig
)
from .deepseek_worker import BaseWorker


class ConsensusLayer:
    """
    A2A-BFT 共识层

    支持组件开关用于消融实验：
    - reputation: 声誉机制（默认启用）
    - dynamic_threshold: 动态阈值（默认启用）
    - view_change: 视图切换（默认启用）
    """

    def __init__(
        self,
        n: int,
        f: int,
        s: int,
        use_reputation: bool = True,
        use_dynamic_threshold: bool = True,
        use_view_change: bool = True,
    ):
        self.n = n
        self.f = f
        self.s = s

        # 组件开关
        self.use_reputation = use_reputation
        self.use_dynamic_threshold = use_dynamic_threshold
        self.use_view_change = use_view_change

        # 阈值参数
        self.theta_accept = self._compute_theta_accept()
        self.theta_reject = self._compute_theta_reject()

        # 声誉追踪（仅在有声誉机制时）
        self.reputations: Dict[int, float] = {}
        if self.use_reputation:
            for i in range(n):
                self.reputations[i] = 1.0

        # 视图管理（仅在有视图切换时）
        self.current_view = 0
        self.view_history: List[int] = []

        # 统计信息
        self.stats = {
            "total_rounds": 0,
            "view_changes": 0,
            "abstains": 0,
        }

    def _compute_theta_accept(self) -> float:
        """计算接受阈值"""
        if self.use_dynamic_threshold:
            n_validators = self.n - 1
            return n_validators - 2 * self.f - self.s
        else:
            return 2.0  # 固定阈值

    def _compute_theta_reject(self) -> float:
        """计算拒绝阈值"""
        if self.use_dynamic_threshold:
            n_validators = self.n - 1
            return -(n_validators - self.f) * 0.5
        else:
            return -2.0  # 固定阈值

    def run_consensus(self, workers: List[BaseWorker], question: str) -> Dict:
        """运行共识协议"""
        trace = [f"consensus_start: n={self.n}, f={self.f}, s={self.s}"]
        trace.append(f"question: {question[:50]}...")

        # Phase 1: Propose
        proposal, proposer_id = self._propose(workers, question, trace)
        if proposal is None:
            return {"decision": "ERROR", "trace": trace}

        # Phase 2: Validate
        votes = self._validate(workers, proposal, trace)

        # Phase 3: Commit
        decision, score = self._commit(votes, trace)

        # 更新声誉
        if self.use_reputation:
            self._update_reputations(votes, trace)

        outcome = ConsensusOutcome(
            task_id=proposal.task_id,
            decision=decision,
            rounds=self.stats["total_rounds"],
            votes=votes,
            total_score=score,
            accept_threshold=self.theta_accept,
            reject_threshold=self.theta_reject,
            trace=trace
        )

        return {
            "decision": outcome.decision.value.upper(),
            "score": score,
            "round": self.stats["total_rounds"],
            "trace": trace,
        }

    def _propose(self, workers: List[BaseWorker], question: str, trace: List[str]) -> Tuple[Optional[Proposal], int]:
        """阶段1: 提案生成"""
        # 选择Primary（轮询）
        proposer_id = self.stats["total_rounds"] % self.n
        proposer = workers[proposer_id]

        trace.append(f"phase1_propose: proposer={proposer_id}")

        result, confidence, solve_trace = proposer.solve(question)
        trace.extend(solve_trace)

        proposal = Proposal(
            task_id=f"task_{self.stats['total_rounds']}",
            proposer_id=proposer_id,
            result=result,
            confidence=confidence,
            trace=trace
        )

        return proposal, proposer_id

    def _validate(self, workers: List[BaseWorker], proposal: Proposal, trace: List[str]) -> List[Vote]:
        """阶段2: 验证投票"""
        trace.append("phase2_validate: starting")
        votes = []

        for i, worker in enumerate(workers):
            if i == proposal.proposer_id:
                continue  # proposer不投票

            trace.append(f"validator_{i}: validating")

            vote = worker.validate(proposal)
            votes.append(vote)

            trace.append(f"validator_{i}: {vote.verdict.value} (confidence={vote.confidence:.2f})")

            if vote.verdict == Verdict.ABSTAIN:
                self.stats["abstains"] += 1

        trace.append(f"phase2_validate: {len(votes)} votes collected")
        return votes

    def _commit(self, votes: List[Vote], trace: List[str]) -> Tuple[Verdict, float]:
        """阶段3: 投票聚合与决策"""
        trace.append("phase3_commit: aggregating votes")

        # 计算投票分数
        score = self._compute_vote_score(votes)
        trace.append(f"vote_score: {score:.2f}")

        # 确定决策
        if score >= self.theta_accept:
            decision = Verdict.ACCEPT
            trace.append(f"DECISION: ACCEPT (score={score:.2f} >= theta_accept={self.theta_accept:.2f})")
        elif score <= self.theta_reject:
            decision = Verdict.REJECT
            trace.append(f"DECISION: REJECT (score={score:.2f} <= theta_reject={self.theta_reject:.2f})")
        else:
            decision = Verdict.ABSTAIN
            trace.append(f"DECISION: MANUAL (score={score:.2f} in between thresholds)")

        return decision, score

    def _compute_vote_score(self, votes: List[Vote]) -> float:
        """计算加权投票分数"""
        score = 0.0

        for vote in votes:
            if not self.use_reputation:
                # 无声誉：简单计数
                score += vote.effective_weight
            else:
                # 有声誉：使用声誉权重
                reputation = self.reputations.get(vote.validator_id, 1.0)
                score += vote.effective_weight * reputation

        return score

    def _update_reputations(self, votes: List[Vote], trace: List[str]):
        """更新声誉值"""
        trace.append("reputation_update: starting")

        for vote in votes:
            validator_id = vote.validator_id
            current_reputation = self.reputations.get(validator_id, 1.0)

            if vote.verdict == Verdict.ACCEPT:
                new_reputation = min(2.0, current_reputation + 0.085)
            elif vote.verdict == Verdict.REJECT:
                new_reputation = max(0.3, current_reputation - 0.085)
            else:
                # 弃权惩罚
                new_reputation = max(0.3, current_reputation - 0.05)

            self.reputations[validator_id] = new_reputation
            trace.append(f"validator_{validator_id}: reputation {current_reputation:.3f} -> {new_reputation:.3f}")

    def _handle_view_change(self, workers: List[BaseWorker], trace: List[str]):
        """处理视图切换"""
        if not self.use_view_change:
            return

        self.current_view += 1
        self.view_history.append(self.current_view)
        self.stats["view_changes"] += 1

        trace.append(f"view_change: view {self.current_view - 1} -> {self.current_view}")

        # 重新选择Primary
        new_proposer = self.stats["total_rounds"] % self.n
        trace.append(f"new_primary: {new_proposer}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_rounds": self.stats["total_rounds"],
            "view_changes": self.stats["view_changes"],
            "abstains": self.stats["abstains"],
            "theta_accept": self.theta_accept,
            "theta_reject": self.theta_reject,
            "reputations": dict(self.reputations),
        }


class BaselineConsensus:
    """
    基线共识方法（用于对比实验）
    """

    @staticmethod
    def simple_majority(workers: List[BaseWorker], question: str) -> Dict:
        """简单多数投票"""
        votes = []
        for i, worker in enumerate(workers):
            result, confidence, trace = worker.solve(question)
            # 简单判断：正确则接受，否则拒绝
            verdict = Verdict.ACCEPT if "CORRECT" in result else Verdict.REJECT
            votes.append({
                "validator_id": i,
                "verdict": verdict.value,
                "confidence": confidence
            })

        accept_count = sum(1 for v in votes if v["verdict"] == "accept")
        total = len(votes)
        accept_rate = accept_count / total if total > 0 else 0

        decision = Verdict.ACCEPT if accept_rate >= 0.5 else Verdict.REJECT

        return {
            "decision": decision.value.upper(),
            "votes": votes,
            "accept_count": accept_count,
            "total": total,
        }

    @staticmethod
    def weighted_majority(workers: List[BaseWorker], question: str) -> Dict:
        """加权多数投票"""
        votes = []
        total_weight = 0.0
        accept_weight = 0.0

        for i, worker in enumerate(workers):
            result, confidence, trace = worker.solve(question)
            verdict = Verdict.ACCEPT if "CORRECT" in result else Verdict.REJECT

            weight = confidence
            votes.append({
                "validator_id": i,
                "verdict": verdict.value,
                "confidence": confidence,
                "weight": weight
            })

            total_weight += weight
            if verdict == Verdict.ACCEPT:
                accept_weight += weight

        accept_rate = accept_weight / total_weight if total_weight > 0 else 0
        decision = Verdict.ACCEPT if accept_rate >= 0.5 else Verdict.REJECT

        return {
            "decision": decision.value.upper(),
            "votes": votes,
            "accept_weight": accept_weight,
            "total_weight": total_weight,
        }


def run_comparison_experiment(
    workers: List[BaseWorker],
    question: str,
    methods: List[str] = ["a2a_bft", "simple_majority", "weighted_majority"]
) -> Dict:
    """运行对比实验"""
    results = {}

    if "simple_majority" in methods:
        results["simple_majority"] = BaselineConsensus.simple_majority(workers, question)

    if "weighted_majority" in methods:
        results["weighted_majority"] = BaselineConsensus.weighted_majority(workers, question)

    # A2A-BFT需要共识层实例
    return results
