"""
多GPU分布式Agent实现
支持4个GPU分别加载不同模型
"""

import os
import json
import time
import random
import asyncio
import torch
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import threading


@dataclass
class WorkerConfig:
    """Worker配置"""
    worker_id: int
    model_name: str
    gpu_id: int
    is_byzantine: bool = False
    byzantine_type: str = "random"  # random, strategic_reject, collusion
    accuracy: float = 0.9


@dataclass
class AgentState:
    """Agent状态"""
    worker_id: int
    model_name: str
    gpu_id: int
    is_ready: bool = False
    last_response: Optional[Dict] = None
    response_count: int = 0


class MultiGPULinearModel:
    """
    多GPU模型包装器（支持真实LLM推理）
    """

    def __init__(self, model_name: str, gpu_id: int, use_real_model: bool = False):
        self.model_name = model_name
        self.gpu_id = gpu_id
        self.device = f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu"
        self.is_loaded = False
        self.use_real_model = use_real_model
        self.model = None
        self.tokenizer = None
        self.model_path = None

    def load(self):
        """加载模型"""
        if self.is_loaded:
            return

        if self.use_real_model:
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer

                # 查找模型路径
                # 原为硬编码 /autodl-fs/data/models，可用环境变量 A2A_MODEL_DIR 覆盖
                _models_dir = os.environ.get("A2A_MODEL_DIR", "/autodl-fs/data/models")
                model_paths = {
                    _name: os.path.join(_models_dir, _name)
                    for _name in (
                        "DeepSeek-V2-Lite-Chat",
                        "InternLM3-8B-Instruct",
                        "LLaDA-8B-Instruct",
                        "Llama-3.1-8B-Instruct",
                        "Qwen2.5-72B-Instruct-AWQ",
                    )
                }
                self.model_path = model_paths.get(self.model_name)
                if not self.model_path or not os.path.exists(self.model_path):
                    print(f"  [ERROR] Model {self.model_name} not found at {self.model_path}")
                    self.is_loaded = True  # 标记为已加载但失败
                    return

                print(f"  [INFO] Loading {self.model_name} on GPU {self.gpu_id}...")
                device = f"cuda:{self.gpu_id}"

                # 加载tokenizer
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)

                # 加载模型（使用半精度）
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float16,
                    device_map=device,
                    trust_remote_code=True
                )
                self.model.eval()

                self.is_loaded = True
                print(f"  [SUCCESS] {self.model_name} loaded on GPU {self.gpu_id}")
            except Exception as e:
                print(f"  [ERROR] Failed to load {self.model_name}: {e}")
                self.is_loaded = True  # 标记为已加载但失败
        else:
            # 模拟模式
            self.is_loaded = True
            print(f"  [Model {self.model_name}] Loaded on GPU {self.gpu_id} (simulated)")

    def generate(self, prompt: str, max_tokens: int = 512) -> Tuple[str, float]:
        """
        生成响应（支持真实LLM推理）
        返回: (response_text, confidence)
        """
        self.load()

        if not self.is_loaded or self.model is None:
            # 回退到模拟
            if "72B" in self.model_name:
                delay = 0.5
            elif "Lite" in self.model_name:
                delay = 0.3
            else:
                delay = 0.4
            time.sleep(delay)
            response = f"[{self.model_name}] Generated response for: {prompt[:50]}..."
            confidence = 0.85 + (hash(response) % 100) / 1000
            return response, confidence

        # 真实推理
        try:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(f"cuda:{self.gpu_id}")
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.9,
                    do_sample=True
                )
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            confidence = 0.9  # 真实模型高置信度
            return response, confidence
        except Exception as e:
            print(f"  [ERROR] Inference failed: {e}")
            # 回退到模拟
            time.sleep(0.3)
            response = f"[ERROR] {str(e)[:50]}"
            return response, 0.1


class DistributedWorker:
    """分布式Worker（绑定到特定GPU）"""

    def __init__(self, config: WorkerConfig, use_real_model: bool = False):
        self.worker_id = config.worker_id
        self.gpu_id = config.gpu_id
        self.is_byzantine = config.is_byzantine
        self.byzantine_type = config.byzantine_type
        self.accuracy = config.accuracy
        self.weight = 1.0  # 添加权重属性，与BaseWorker保持一致
        self.use_real_model = use_real_model

        # 创建模型实例
        self.model = MultiGPULinearModel(config.model_name, config.gpu_id, use_real_model=use_real_model)

        # Agent状态
        self.state = AgentState(
            worker_id=config.worker_id,
            model_name=config.model_name,
            gpu_id=config.gpu_id
        )

        # 声誉追踪
        self.reject_count = 0
        self.total_votes = 0
        self.reputation = 1.0
        self.abstain_count = 0  # 弃权计数，兼容BaseWorker接口

    def load_model(self):
        """加载模型到指定GPU"""
        self.model.load()
        self.state.is_ready = True

    def solve_task(self, task: str) -> Dict:
        """
        求解任务
        返回: {response, confidence, trace}
        """
        start_time = time.time()

        if self.is_byzantine:
            result = self._byzantine_solve(task)
        else:
            result = self._normal_solve(task)

        elapsed = time.time() - start_time

        # 更新状态
        self.state.response_count += 1
        self.state.last_response = result

        result["worker_id"] = self.worker_id
        result["gpu_id"] = self.gpu_id
        result["model"] = self.model.model_name
        result["elapsed_ms"] = elapsed * 1000

        return result

    def _normal_solve(self, task: str) -> Dict:
        """正常求解"""
        # 根据accuracy决定是否返回正确回答
        if random.random() < self.accuracy:
            response = f"模拟正确回答: {task}..."
            confidence = random.uniform(0.85, 0.95)
        else:
            response = f"模拟错误回答: {task}...（推理失败）"
            confidence = random.uniform(0.2, 0.4)

        return {
            "response": response,
            "confidence": confidence,
            "verdict": "ACCEPT",
            "trace": [f"solved_by_{self.model.model_name}"]
        }

    def _byzantine_solve(self, task: str) -> Dict:
        """拜占庭求解"""
        # 模拟生成响应（作为Primary时伪装正确回答）
        response = f"模拟正确回答: {task}...（byzantine_{self.byzantine_type}节点生成）"

        if self.byzantine_type == "random":
            # 随机接受/拒绝
            verdict = "REJECT" if hash(task) % 2 == 0 else "ACCEPT"
        elif self.byzantine_type == "strategic_reject":
            # 战略性拒绝（总是拒绝）
            verdict = "REJECT"
        elif self.byzantine_type == "collusion":
            # 共谋（与特定worker保持一致）
            verdict = "ACCEPT"
        else:
            verdict = "ACCEPT"

        # 降低置信度（拜占庭节点降低可信度）
        confidence = 0.6

        self.reject_count += 1
        self.total_votes += 1

        return {
            "response": response,
            "confidence": confidence,
            "verdict": verdict,
            "trace": [f"byzantine_{self.byzantine_type}"]
        }

    def get_reputation(self) -> float:
        """获取声誉值"""
        if self.total_votes == 0:
            return 1.0
        reject_ratio = self.reject_count / self.total_votes
        if reject_ratio >= 0.7:
            # 高拒绝率，降低声誉
            return max(0.3, self.reputation - 0.1)
        return self.reputation

    def solve(self, question: str, task_type: str = "general") -> Tuple[str, float, List[str]]:
        """
        求解任务（兼容 BaseWorker 接口）
        返回: (result, confidence, trace)
        """
        result = self.solve_task(question)
        trace = result.get("trace", [])
        return result["response"], result["confidence"], trace

    def validate(self, proposal) -> Dict:
        """
        验证提案（兼容 BaseWorker 接口）
        返回: Vote dict
        """
        # 调用自身solve来独立验证
        result, confidence, trace = self.solve(proposal.task_id)

        # 判断自身推理结果
        own_correct = "模拟正确回答" in result

        # 判断提案是否正确
        proposal_is_correct = "模拟正确回答" in proposal.result

        # 拜占庭节点根据攻击类型投票
        if self.is_byzantine:
            if self.byzantine_type == "strategic_reject":
                # 策略性拒绝：无论提案质量，总是拒绝（但会伪装成正常提案）
                verdict = "REJECT"
                confidence = 0.85
            elif self.byzantine_type == "random":
                verdict = random.choice(["ACCEPT", "REJECT"])
                confidence = random.uniform(0.5, 0.8)
            elif self.byzantine_type == "collusion":
                # 共谋：与其他拜占庭节点保持一致，压制诚实节点
                # 特征：当诚实节点占多数时，仍投REJECT
                verdict = "REJECT"
                confidence = 0.85
            else:
                # 默认：随机投错票（30%概率投错）
                if random.random() < 0.3:
                    verdict = "REJECT" if proposal_is_correct else "ACCEPT"
                else:
                    verdict = "ACCEPT" if proposal_is_correct else "REJECT"
                confidence = random.uniform(0.6, 0.8)
        else:
            # 诚实节点：基于自身推理结果投票
            if own_correct and proposal_is_correct:
                # 双方都正确，接受
                verdict = "ACCEPT"
                confidence = 0.85
            elif own_correct and not proposal_is_correct:
                # 自己正确，提案错误，拒绝
                verdict = "REJECT"
                confidence = 0.8
            elif not own_correct and proposal_is_correct:
                # 自己错误，提案正确，但仍接受（软故障）
                verdict = "ACCEPT"
                confidence = 0.5
            else:
                # 双方都错误，拒绝
                verdict = "REJECT"
                confidence = 0.7

        return {
            "validator_id": self.worker_id,
            "proposal_hash": getattr(proposal, 'hash', ''),
            "verdict": verdict,
            "confidence": confidence,
            "evidence": {"own_correct": own_correct, "proposal_correct": proposal_is_correct}
        }


class MultiGPUDistributedSystem:
    """多GPU分布式共识系统"""

    def __init__(
        self,
        n: int,
        f: int,
        s: int,
        worker_configs: List[WorkerConfig]
    ):
        self.n = n
        self.f = f
        self.s = s
        self.worker_configs = worker_configs

        # 创建Workers
        self.workers: List[DistributedWorker] = []
        for config in worker_configs:
            worker = DistributedWorker(config)
            self.workers.append(worker)

        # 线程池（用于并行执行）
        self.executor = ThreadPoolExecutor(max_workers=n)

        # 统计数据
        self.stats = {
            "total_tasks": 0,
            "accepted": 0,
            "rejected": 0,
            "consensus_rounds": []
        }

    def initialize(self):
        """初始化所有Worker（加载模型）"""
        print("\n" + "=" * 70)
        print("Multi-GPU 分布式系统初始化")
        print("=" * 70)

        for worker in self.workers:
            print(f"\nInitializing Worker {worker.worker_id}:")
            print(f"  Model: {worker.model.model_name}")
            print(f"  GPU: {worker.gpu_id}")
            print(f"  Byzantine: {worker.is_byzantine}")
            worker.load_model()

        print("\n" + "=" * 70)
        print("所有Worker初始化完成")
        print("=" * 70 + "\n")

    def run_consensus(self, task: str) -> Dict:
        """
        运行分布式共识
        返回: {decision, round, workers_result}
        """
        print(f"\n[Consensus] Running task: {task[:50]}...")

        # 并行执行所有Worker（模拟多GPU并行）
        futures = [
            self.executor.submit(worker.solve_task, task)
            for worker in self.workers
        ]

        # 收集结果
        results = [f.result() for f in futures]

        # 聚合结果
        decision = self._aggregate(results)

        # 更新统计
        self.stats["total_tasks"] += 1
        if decision["decision"] == "ACCEPT":
            self.stats["accepted"] += 1
        else:
            self.stats["rejected"] += 1

        return decision

    def _aggregate(self, results: List[Dict]) -> Dict:
        """聚合结果并做出共识决策。

        使用论文的计分投票规则（式(1)），而非简单多数：
            phi = |ACCEPT| - 0.5*|REJECT|          （ABSTAIN 贡献 0）
            theta_accept = n - 2f - s
            theta_reject = -(n - f) * 0.5
        此处 n = len(results) 即参与验证的副本数。此前该处使用
        ``(n_total - f) * 0.5`` 的计数多数阈值，既忽略 s 也忽略 -2f 项，
        与论文公式不符，已修正。
        """
        n_accept = sum(1 for r in results if r["verdict"] == "ACCEPT")
        n_reject = sum(1 for r in results if r["verdict"] == "REJECT")
        n_total = len(results)

        # 计分与动态阈值
        phi = n_accept - 0.5 * n_reject
        theta_accept = n_total - 2 * self.f - self.s
        theta_reject = -(n_total - self.f) * 0.5

        # 共识决策
        if phi >= theta_accept:
            decision = "ACCEPT"
        elif phi <= theta_reject:
            decision = "REJECT"
        else:
            decision = "CONSENSUS_FAILED"

        return {
            "decision": decision,
            "n_accept": n_accept,
            "n_reject": n_reject,
            "n_total": n_total,
            "phi": phi,
            "theta_accept": theta_accept,
            "theta_reject": theta_reject,
            "theta": theta_accept,
            "round": 1
        }

    def get_worker_status(self) -> List[Dict]:
        """获取所有Worker状态"""
        return [
            {
                "worker_id": w.worker_id,
                "model": w.model.model_name,
                "gpu": w.gpu_id,
                "ready": w.state.is_ready,
                "reputation": w.get_reputation(),
                "response_count": w.state.response_count
            }
            for w in self.workers
        ]

    def print_stats(self):
        """打印统计信息"""
        print("\n" + "=" * 70)
        print("Multi-GPU 分布式系统统计")
        print("=" * 70)
        print(f"Total tasks: {self.stats['total_tasks']}")
        print(f"Accepted: {self.stats['accepted']} ({self.stats['accepted']/max(1,self.stats['total_tasks'])*100:.1f}%)")
        print(f"Rejected: {self.stats['rejected']} ({self.stats['rejected']/max(1,self.stats['total_tasks'])*100:.1f}%)")

        print("\nWorker Status:")
        for worker in self.workers:
            print(f"  Worker {worker.worker_id}: {worker.model.model_name} (GPU {worker.gpu_id})")
            print(f"    Reputation: {worker.get_reputation():.2f}")
            print(f"    Responses: {worker.state.response_count}")

        print("=" * 70 + "\n")


def create_worker_configs(
    n: int = 4,
    f: int = 1,
    s: int = 0,
    models: List[str] = None
) -> List[WorkerConfig]:
    """
    创建Worker配置
    默认配置：
    - GPU 0: DeepSeek-V2-Lite-Chat
    - GPU 1: InternLM3-8B-Instruct
    - GPU 2: LLaDA-8B-Instruct
    - GPU 3: Llama-3.1-8B-Instruct
    """
    default_models = [
        "DeepSeek-V2-Lite-Chat",
        "InternLM3-8B-Instruct",
        "LLaDA-8B-Instruct",
        "Llama-3.1-8B-Instruct"
    ]

    models = models or default_models[:n]

    configs = []
    byzantine_count = 0
    soft_fault_count = 0

    for i, model_name in enumerate(models):
        # 分配拜占庭节点
        if byzantine_count < f:
            is_byzantine = True
            byzantine_type = "strategic_reject" if byzantine_count == 0 else "collusion"
            byzantine_count += 1
        else:
            is_byzantine = False
            byzantine_type = "random"

        # 分配软故障节点
        if soft_fault_count < s:
            accuracy = 0.6
            soft_fault_count += 1
        else:
            accuracy = 0.9

        config = WorkerConfig(
            worker_id=i,
            model_name=model_name,
            gpu_id=i,
            is_byzantine=is_byzantine,
            byzantine_type=byzantine_type,
            accuracy=accuracy
        )
        configs.append(config)

    return configs


if __name__ == "__main__":
    print("Multi-GPU Distributed Agent System")
    print("=" * 70)

    # 创建配置
    configs = create_worker_configs(n=4, f=1, s=0)

    # 创建系统
    system = MultiGPUDistributedSystem(
        n=4,
        f=1,
        s=0,
        worker_configs=configs
    )

    # 初始化
    system.initialize()

    # 运行测试任务
    tasks = [
        "Calculate 1+1",
        "What is the capital of France?",
        "Write a Python function to sort an array",
        "Explain quantum computing",
        "Translate 'hello' to Japanese"
    ]

    print("\nRunning consensus tasks...\n")

    for i, task in enumerate(tasks[:3]):  # 只跑3个任务作为测试
        print(f"\n[Task {i+1}] {task}")
        result = system.run_consensus(task)
        print(f"  Decision: {result['decision']}")
        print(f"  Votes: {result['n_accept']} ACCEPT, {result['n_reject']} REJECT")

    # 打印统计
    system.print_stats()
