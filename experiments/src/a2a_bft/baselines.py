"""
A2A-BFT 基线方法实现
用于对比实验
"""

from typing import List, Dict
from .data_structures import Verdict


class SimpleMajority:
    """简单多数投票基线"""

    def __init__(self, name: str = "Simple_Majority"):
        self.name = name

    def consensus(self, workers, question: str) -> Dict:
        """
        简单多数投票：每个worker投票，多数决定

        Args:
            workers: Worker列表
            question: 问题

        Returns:
            决策结果
        """
        votes = []
        for i, worker in enumerate(workers):
            result, confidence, trace = worker.solve(question)
            # 简单判断：包含"CORRECT"则接受
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
            "method": self.name,
            "decision": decision.value.upper(),
            "votes": votes,
            "accept_count": accept_count,
            "total": total,
            "accept_rate": accept_rate * 100
        }


class WeightedMajority:
    """加权多数投票基线"""

    def __init__(self, name: str = "Weighted_Majority"):
        self.name = name

    def consensus(self, workers, question: str) -> Dict:
        """
        加权多数投票：根据置信度加权

        Args:
            workers: Worker列表
            question: 问题

        Returns:
            决策结果
        """
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
            "method": self.name,
            "decision": decision.value.upper(),
            "votes": votes,
            "accept_weight": accept_weight,
            "total_weight": total_weight,
            "accept_rate": accept_rate * 100
        }


class A2ASimSimulation:
    """
    A2A-Sim 模拟实现
    基于原始论文描述模拟其行为
    """

    def __init__(self, name: str = "A2A-Sim"):
        self.name = name
        # A2A-Sim的典型参数
        self.confidence_threshold = 0.7
        self.max_rounds = 3

    def consensus(self, workers, question: str) -> Dict:
        """
        A2A-Sim 共识模拟

        模拟A2A-Sim的行为：
        - 基于LLM输出的相似度投票
        - 置信度阈值过滤
        - 多轮投票机制

        Args:
            workers: Worker列表
            question: 问题

        Returns:
            决策结果
        """
        from collections import Counter

        proposals = []
        for i, worker in enumerate(workers):
            result, confidence, trace = worker.solve(question)
            proposals.append({
                "worker_id": i,
                "result": result,
                "confidence": confidence,
                "trace": trace
            })

        # 模拟A2A-Sim的相似度投票机制
        # 简化：统计相似回答的数量
        accept_count = 0
        reject_count = 0

        for i, p1 in enumerate(proposals):
            if p1["confidence"] < self.confidence_threshold:
                reject_count += 1
                continue

            # 检查有多少其他worker给出相似回答
            similar_count = 0
            for j, p2 in enumerate(proposals):
                if i != j and p2["confidence"] >= self.confidence_threshold:
                    # 简化：如果结果都包含"CORRECT"，视为相似
                    if "CORRECT" in p1["result"] and "CORRECT" in p2["result"]:
                        similar_count += 1

            if similar_count >= len(workers) // 2:
                accept_count += 1
            else:
                reject_count += 1

        total = accept_count + reject_count
        accept_rate = accept_count / total if total > 0 else 0

        decision = Verdict.ACCEPT if accept_rate >= 0.5 else Verdict.REJECT

        return {
            "method": self.name,
            "decision": decision.value.upper(),
            "accept_count": accept_count,
            "reject_count": reject_count,
            "total": total,
            "accept_rate": accept_rate * 100,
            "confidence_threshold": self.confidence_threshold
        }


class LLMDebateSimulation:
    """
    LLM-Debate 模拟实现
    模拟多轮辩论达成共识
    """

    def __init__(self, name: str = "LLM-Debate", max_rounds: int = 3):
        self.name = name
        self.max_rounds = max_rounds

    def consensus(self, workers, question: str) -> Dict:
        """
        LLM-Debate 共识模拟

        模拟多轮辩论：
        - 初始投票
        - 辩论轮次（交换观点）
        - 最终投票

        Args:
            workers: Worker列表
            question: 问题

        Returns:
            决策结果
        """
        import random

        # 初始投票
        votes = []
        for i, worker in enumerate(workers):
            result, confidence, trace = worker.solve(question)
            verdict = Verdict.ACCEPT if "CORRECT" in result else Verdict.REJECT
            votes.append({
                "worker_id": i,
                "verdict": verdict.value,
                "confidence": confidence,
                "original": True
            })

        # 模拟辩论轮次
        for round_num in range(self.max_rounds):
            # 拜占庭节点可能被说服
            for i, vote in enumerate(votes):
                if workers[i].is_byzantine and random.random() < 0.3:
                    # 30%概率被说服改变投票
                    vote["verdict"] = "accept" if random.random() < 0.5 else "reject"
                    vote["confidence"] = 0.7
                    vote["round"] = round_num

        # 最终统计
        accept_count = sum(1 for v in votes if v["verdict"] == "accept")
        total = len(votes)
        accept_rate = accept_count / total if total > 0 else 0

        decision = Verdict.ACCEPT if accept_rate >= 0.5 else Verdict.REJECT

        return {
            "method": self.name,
            "decision": decision.value.upper(),
            "votes": votes,
            "accept_count": accept_count,
            "total": total,
            "accept_rate": accept_rate * 100,
            "max_rounds": self.max_rounds
        }


def get_baseline_methods(method_names: List[str]) -> List:
    """
    获取基线方法实例

    Args:
        method_names: 方法名称列表

    Returns:
        方法实例列表
    """
    methods = []
    for name in method_names:
        if name == "simple_majority":
            methods.append(SimpleMajority())
        elif name == "weighted_majority":
            methods.append(WeightedMajority())
        elif name == "a2a_sim":
            methods.append(A2ASimSimulation())
        elif name == "llm_debate":
            methods.append(LLMDebateSimulation())
        else:
            raise ValueError(f"Unknown method: {name}")
    return methods


def run_comparison_all_methods(
    workers,
    question: str,
    methods: List[str] = None
) -> Dict:
    """
    运行所有基线方法对比

    Args:
        workers: Worker列表
        question: 问题
        methods: 方法名称列表，默认为所有方法

    Returns:
        所有方法的对比结果
    """
    if methods is None:
        methods = ["simple_majority", "weighted_majority", "a2a_sim", "llm_debate"]

    results = {}
    for method_name in methods:
        try:
            method_instances = get_baseline_methods([method_name])
            if method_instances:
                method = method_instances[0]
                results[method_name] = method.consensus(workers, question)
        except Exception as e:
            results[method_name] = {
                "error": str(e),
                "decision": "ERROR"
            }

    return results


if __name__ == "__main__":
    # 测试代码
    from .deepseek_worker import SimulatedWorker

    # 创建测试workers
    workers = [
        SimulatedWorker(worker_id=0, accuracy=0.9),
        SimulatedWorker(worker_id=1, accuracy=0.9),
        SimulatedWorker(worker_id=2, accuracy=0.9, byzantine_type="random"),
        SimulatedWorker(worker_id=3, accuracy=0.9),
    ]
    workers[2].is_byzantine = True

    # 运行对比
    question = "math_problem_1: 计算 1234 + 5678 = ?"
    results = run_comparison_all_methods(workers, question)

    print("=" * 60)
    print("基线方法对比")
    print("=" * 60)
    for method_name, result in results.items():
        if "decision" in result:
            print(f"{method_name:20s}: {result['decision']:10s} (accept_rate={result.get('accept_rate', 'N/A')})")
        else:
            print(f"{method_name:20s}: ERROR - {result.get('error', 'Unknown')}")
