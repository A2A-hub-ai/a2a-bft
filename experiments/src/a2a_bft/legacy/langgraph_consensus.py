"""
A2A-BFT LangGraph 集成版本
使用 StateGraph 实现 Propose → Validate → Commit 工作流
"""

from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langgraph.graph import StateGraph, END
import operator
import asyncio
import time
import hashlib
from enum import Enum


class Verdict(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    ABSTAIN = "abstain"


class ConsensusState(TypedDict):
    """共识状态"""
    # 输入
    task_id: str
    question: str
    n: int  # 总节点数
    f: int  # 拜占庭节点数
    s: int  # 软故障节点数

    # 共识过程
    round: int
    primary_id: int
    proposal: Optional[str]
    proposal_confidence: Optional[float]
    proposal_trace: List[str]
    proposal_hash: str

    # 投票
    votes: Annotated[List[Dict], operator.add]
    accept_count: int
    reject_count: int
    abstain_count: int

    # 决策
    phi_score: float
    theta_accept: float
    theta_reject: float
    decision: str  # ACCEPT, REJECT, PENDING, MANUAL

    # 权重
    worker_weights: Dict[int, float]

    # 控制流
    consecutive_pending: int
    view_change_triggered: bool
    error: Optional[str]


class LangGraphA2ABFT:
    """基于 LangGraph 的 A2A-BFT 共识实现"""

    def __init__(
        self,
        n: int,
        f: int,
        s: int,
        theta_accept: float = 2.0,
        theta_reject: float = -2.0,
        view_change_timeout: int = 2,
        max_rounds: int = 10,
        alpha: float = 0.1,
        beta: float = 0.1,
    ):
        self.n = n
        self.f = f
        self.s = s
        self.theta_accept = theta_accept
        self.theta_reject = theta_reject
        self.view_change_timeout = view_change_timeout
        self.max_rounds = max_rounds
        self.alpha = alpha
        self.beta = beta

        # 构建图
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 状态图"""
        workflow = StateGraph(ConsensusState)

        # 添加节点
        workflow.add_node("propose", self._node_propose)
        workflow.add_node("validate", self._node_validate)
        workflow.add_node("commit", self._node_commit)
        workflow.add_node("update_weights", self._node_update_weights)
        workflow.add_node("view_change", self._node_view_change)

        # 设置入口点
        workflow.set_entry_point("propose")

        # 添加边
        workflow.add_edge("propose", "validate")
        workflow.add_edge("validate", "commit")
        workflow.add_edge("commit", "update_weights")
        workflow.add_edge("update_weights", "view_change")

        # 条件边：根据决策决定下一步
        workflow.add_conditional_edges(
            "view_change",
            self._route_after_view_change,
            {
                "propose": "propose",  # 继续下一轮
                "accept": END,  # 达成共识
                "reject": END,  # 拒绝
                "manual": END,  # 降级为人工
            }
        )

        return workflow.compile()

    def _node_propose(self, state: ConsensusState) -> Dict:
        """Phase 1: 提案节点"""
        print(f"\n[PROPOSE] Round {state['round']}, Primary: Worker {state['primary_id']}")

        # 这里应该调用实际的 worker.solve()
        # 简化版：模拟提案生成
        proposal = f"Proper response to: {state['question'][:50]}..."
        confidence = 0.9
        trace = [f"received_question: {state['question']}", "thinking..."]

        # 计算提案哈希
        content = f"{state['task_id']}{state['primary_id']}{proposal}{confidence}"
        proposal_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        return {
            "proposal": proposal,
            "proposal_confidence": confidence,
            "proposal_trace": trace,
            "proposal_hash": proposal_hash,
        }

    def _node_validate(self, state: ConsensusState) -> Dict:
        """Phase 2: 语义验证节点"""
        print(f"[VALIDATE] {self.n - 1} validators checking proposal...")

        votes = []
        for i in range(self.n):
            if i == state['primary_id']:
                continue  # Primary 不投票

            # 简化：诚实节点以高概率接受
            is_byzantine = i < self.f
            if is_byzantine:
                # 拜占庭节点可能投错票
                verdict = Verdict.REJECT if __import__('random').random() < 0.5 else Verdict.ACCEPT
                confidence = 0.6
            else:
                verdict = Verdict.ACCEPT
                confidence = 0.9

            votes.append({
                "validator_id": i,
                "verdict": verdict.value,
                "confidence": confidence,
                "proposal_hash": state['proposal_hash']
            })

        return {"votes": votes}

    def _node_commit(self, state: ConsensusState) -> Dict:
        """Phase 3: 投票聚合与决策节点"""
        # 统计投票
        accept_count = sum(1 for v in state['votes'] if v['verdict'] == 'accept')
        reject_count = sum(1 for v in state['votes'] if v['verdict'] == 'reject')
        abstain_count = sum(1 for v in state['votes'] if v['verdict'] == 'abstain')

        # 计算投票得分（论文公式）
        phi = accept_count - 0.5 * reject_count

        # 动态阈值
        n_validators = self.n - 1
        theta_accept = n_validators - 2 * self.f - self.s
        theta_reject = -(n_validators - self.f) * 0.5

        # 决策
        if phi >= theta_accept:
            decision = "ACCEPT"
        elif phi <= theta_reject:
            decision = "REJECT"
        else:
            decision = "PENDING"

        print(f"  Phi={phi:.2f} (ACCEPT={accept_count}, REJECT={reject_count})")
        print(f"  Threshold: θ_accept={theta_accept}, θ_reject={theta_reject}")
        print(f"  Decision: {decision}")

        return {
            "accept_count": accept_count,
            "reject_count": reject_count,
            "abstain_count": abstain_count,
            "phi_score": phi,
            "theta_accept": theta_accept,
            "theta_reject": theta_reject,
            "decision": decision,
        }

    def _node_update_weights(self, state: ConsensusState) -> Dict:
        """更新权重节点"""
        if state['decision'] not in ['ACCEPT', 'REJECT']:
            return {}

        weights = state.get('worker_weights', {i: 1.0 for i in range(self.n)})

        for vote in state['votes']:
            validator_id = vote['validator_id']
            is_correct = (vote['verdict'] == state['decision'].lower())

            if is_correct:
                weights[validator_id] = min(2.0, weights.get(validator_id, 1.0) + self.alpha * vote['confidence'])
            else:
                weights[validator_id] = max(0.01, weights.get(validator_id, 1.0) - self.beta * vote['confidence'])

        return {"worker_weights": weights}

    def _node_view_change(self, state: ConsensusState) -> Dict:
        """视图切换节点"""
        new_state = state.copy()

        if state['decision'] == "ACCEPT" or state['decision'] == "REJECT":
            return new_state

        # PENDING 或 MANUAL 情况
        new_state['round'] += 1
        if new_state['round'] > self.max_rounds:
            new_state['decision'] = "MANUAL"
            new_state['error'] = "Exceeded max rounds"
            return new_state

        # 检查连续PENDING
        if state['decision'] == "PENDING":
            new_state['consecutive_pending'] = state.get('consecutive_pending', 0) + 1
            if new_state['consecutive_pending'] >= self.view_change_timeout:
                print(f"  [VIEW-CHANGE] Triggered after {new_state['consecutive_pending']} pending rounds")
                new_state['view_change_triggered'] = True
                new_state['consecutive_pending'] = 0
        else:
            new_state['consecutive_pending'] = 0

        # 轮换Primary
        new_state['primary_id'] = (state['primary_id'] + 1) % self.n

        return new_state

    def _route_after_view_change(self, state: ConsensusState) -> str:
        """根据状态决定下一步"""
        if state['decision'] == "ACCEPT":
            return "accept"
        elif state['decision'] == "REJECT":
            return "reject"
        elif state['decision'] == "MANUAL":
            return "manual"
        else:
            return "propose"

    def run(self, question: str, task_id: str = "task_0", initial_weights: Dict[int, float] = None) -> Dict:
        """运行完整共识流程"""
        initial_state = ConsensusState(
            task_id=task_id,
            question=question,
            n=self.n,
            f=self.f,
            s=self.s,
            round=1,
            primary_id=0,
            proposal=None,
            proposal_confidence=None,
            proposal_trace=[],
            proposal_hash="",
            votes=[],
            accept_count=0,
            reject_count=0,
            abstain_count=0,
            phi_score=0.0,
            theta_accept=self.theta_accept,
            theta_reject=self.theta_reject,
            decision="PENDING",
            worker_weights=initial_weights or {i: 1.0 for i in range(self.n)},
            consecutive_pending=0,
            view_change_triggered=False,
            error=None,
        )

        print(f"\n{'='*60}")
        print(f"LangGraph A2A-BFT Consensus")
        print(f"Config: n={self.n}, f={self.f}, s={self.s}")
        print(f"Question: {question[:50]}...")
        print(f"{'='*60}")

        result = self.graph.invoke(initial_state)

        print(f"\nFinal Decision: {result['decision']}")
        print(f"Rounds: {result['round']}")
        print(f"Worker Weights: {result['worker_weights']}")

        return {
            "decision": result['decision'],
            "rounds": result['round'],
            "phi_score": result['phi_score'],
            "proposal": result.get('proposal'),
            "votes": result.get('votes', []),
            "weights": result.get('worker_weights', {}),
        }


# 独立测试函数
def test_langgraph_a2a_bft():
    """测试 LangGraph 版本"""
    print("\n" + "="*60)
    print("Testing LangGraph A2A-BFT Implementation")
    print("="*60)

    # 测试配置1: n=4, f=1
    print("\n[Test 1] n=4, f=1, s=0")
    consensus1 = LangGraphA2ABFT(n=4, f=1, s=0)
    result1 = consensus1.run("What is 2+2?")
    print(f"Result: {result1['decision']}")

    # 测试配置2: n=5, f=1, s=1
    print("\n[Test 2] n=5, f=1, s=1")
    consensus2 = LangGraphA2ABFT(n=5, f=1, s=1)
    result2 = consensus2.run("Calculate the derivative of x^2")
    print(f"Result: {result2['decision']}")

    # 测试配置3: n=6, f=2
    print("\n[Test 3] n=6, f=2, s=0")
    consensus3 = LangGraphA2ABFT(n=6, f=2, s=0)
    result3 = consensus3.run("Write a Python function to sort a list")
    print(f"Result: {result3['decision']}")

    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)


if __name__ == "__main__":
    test_langgraph_a2a_bft()
