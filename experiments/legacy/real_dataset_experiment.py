"""
使用真实benchmark数据集运行A2A-BFT实验
支持：GSM8K, HumanEval, MBPP, MMLU
"""

import sys
import os
import json
import time
import random
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.data_structures import (
    ExperimentConfig, ExperimentResult, SeedResult,
    Verdict, AttackType
)
from a2a_bft.deepseek_worker import ConsensusLayer, BaseWorker, DeepSeekWorker
from a2a_bft.baselines import SimpleMajority, WeightedMajority, A2ASimSimulation, LLMDebateSimulation


# ==================== 数据集加载 ====================

class DatasetLoader:
    """真实benchmark数据集加载器"""

    def __init__(self, data_dir: str = "experiments/datasets"):
        self.data_dir = Path(data_dir)
        self.datasets = {}
        self._load_datasets()

    def _load_datasets(self):
        """加载所有数据集"""
        # GSM8K
        gsm8k_path = self.data_dir / "gsm8k_test.json"
        if gsm8k_path.exists():
            with open(gsm8k_path, encoding="utf-8") as f:
                self.datasets["math"] = json.load(f)
            print(f"✅ GSM8K: {len(self.datasets['math'])} 题")

        # HumanEval
        humaneval_path = self.data_dir / "humaneval_full.json"
        if humaneval_path.exists():
            with open(humaneval_path, encoding="utf-8") as f:
                self.datasets["code"] = json.load(f)
            print(f"✅ HumanEval: {len(self.datasets['code'])} 题")

        # MBPP
        mbpp_path = self.data_dir / "mbpp_test.json"
        if mbpp_path.exists():
            with open(mbpp_path, encoding="utf-8") as f:
                self.datasets["mbpp"] = json.load(f)
            print(f"✅ MBPP: {len(self.datasets['mbpp'])} 题")

        # MMLU
        mmlu_path = self.data_dir / "mmlu_3subjects.json"
        if mmlu_path.exists():
            with open(mmlu_path, encoding="utf-8") as f:
                self.datasets["knowledge"] = json.load(f)
            print(f"✅ MMLU: {len(self.datasets['knowledge'])} 题")

    def get_task(self, task_type: str, task_id: int) -> Dict:
        """获取指定类型的任务"""
        if task_type not in self.datasets:
            raise ValueError(f"Dataset '{task_type}' not loaded")

        tasks = self.datasets[task_type]
        if task_id >= len(tasks):
            task_id = task_id % len(tasks)

        task = tasks[task_id]

        # 格式化任务为问题字符串
        if task_type == "math":
            return task["question"]
        elif task_type == "code":
            return self._format_code_task(task)
        elif task_type == "knowledge":
            return self._format_knowledge_task(task)
        elif task_type == "mbpp":
            return self._format_code_task(task)
        else:
            return task.get("question", task.get("description", str(task)))

    def _format_code_task(self, task: Dict) -> str:
        """格式化编程任务"""
        if "prompt" in task:
            return task["prompt"]
        elif "code" in task:
            return f"实现以下函数:\n{task['code']}\n\n要求: {task.get('description', '')}"
        else:
            return str(task)

    def _format_knowledge_task(self, task: Dict) -> str:
        """格式化知识问答任务"""
        question = task["question"]
        choices = task.get("choices", [])
        if choices:
            choices_str = "\n".join([f"({chr(65+i)}) {c}" for i, c in enumerate(choices)])
            return f"{question}\n{choices_str}\n请选择正确答案。"
        return question

    def get_dataset_size(self, task_type: str) -> int:
        """获取数据集大小"""
        return len(self.datasets.get(task_type, []))


# ==================== 实验运行器 ====================

class RealDatasetExperimentRunner:
    """使用真实数据集和 DeepSeek API 的实验运行器"""

    def __init__(self, api_key: str = None, use_reputation: bool = True, use_dynamic_threshold: bool = True,
                 use_view_change: bool = True):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.use_reputation = use_reputation
        self.use_dynamic_threshold = use_dynamic_threshold
        self.use_view_change = use_view_change
        self.loader = DatasetLoader()
        self.results = []

    def run_experiment(self, config: ExperimentConfig, dataset_type: str = None,
                       num_tasks: int = 20, num_seeds: int = 5) -> ExperimentResult:
        """运行单个实验配置"""

        print(f"\n{'='*60}")
        print(f"实验配置: n={config.n}, f={config.f}, s={config.s}")
        print(f"类型: {dataset_type}, 任务数: {num_tasks}, 种子: {num_seeds}")
        print(f"声誉机制: {'启用' if self.use_reputation else '禁用'}, "
              f"攻击: {config.attack_type or '无'}")
        print(f"{'='*60}")

        per_seed_results = []

        for seed in range(num_seeds):
            random.seed(seed)
            print(f"\n种子 {seed}:")

            accept_count = 0
            reject_count = 0
            manual_count = 0
            error_count = 0
            rounds = []
            times = []

            for i in range(num_tasks):
                task_start = time.time()

                # 获取真实任务
                try:
                    question = self.loader.get_task(dataset_type, i)
                except Exception as e:
                    print(f"  获取任务失败: {e}")
                    error_count += 1
                    continue

                # 创建共识层
                consensus = ConsensusLayer(
                    n=config.n, f=config.f, s=config.s,
                    use_reputation=self.use_reputation,
                    use_dynamic_threshold=self.use_dynamic_threshold,
                    use_view_change=self.use_view_change
                )

                # 创建worker
                workers = []
                for j in range(config.n):
                    is_byzantine = j < config.f
                    is_soft_fault = config.f <= j < config.f + config.s

                    if is_byzantine:
                        worker_type = config.attack_type or "strategic_reject"
                    elif is_soft_fault:
                        worker_type = "random"
                    else:
                        worker_type = None

                    worker = DeepSeekWorker(
                        worker_id=j,
                        model="deepseek-chat",
                        api_key=self.api_key,
                    )
                    worker.is_byzantine = is_byzantine
                    worker.byzantine_type = worker_type
                    workers.append(worker)

                # 运行共识
                try:
                    outcome = consensus.run_consensus(workers, question)
                    task_time = time.time() - task_start

                    if outcome["decision"] == "ACCEPT":
                        accept_count += 1
                    elif outcome["decision"] == "REJECT":
                        reject_count += 1
                    elif outcome["decision"] == "MANUAL":
                        manual_count += 1
                    elif outcome["decision"] == "ERROR":
                        error_count += 1

                    rounds.append(outcome.get("round", 0))
                    times.append(task_time)

                except Exception as e:
                    error_count += 1
                    times.append(time.time() - task_start)

            # 计算结果
            total_tasks = accept_count + reject_count + manual_count + error_count
            accept_rate = accept_count / total_tasks * 100 if total_tasks > 0 else 0
            avg_rounds = sum(rounds) / len(rounds) if rounds else 0
            avg_time = sum(times) / len(times) if times else 0
            avg_tps = 1 / avg_time if avg_time > 0 else 0

            seed_result = SeedResult(
                seed=seed,
                accept_rate=accept_rate,
                rounds=rounds,
                times=times
            )
            per_seed_results.append(seed_result)

            print(f"  接受率: {accept_rate:.1f}% ({accept_count}/{total_tasks})")

        # 计算总体统计
        total_accept = sum(s.accept_rate * num_tasks / 100 for s in per_seed_results)
        total_tasks = num_seeds * num_tasks
        total_reject = total_tasks - int(total_accept)

        avg_rounds = sum(sum(s.rounds) for s in per_seed_results) / len(per_seed_results) if per_seed_results else 0
        avg_time = sum(sum(s.times) for s in per_seed_results) / len(per_seed_results) if per_seed_results else 0
        avg_tps = 1 / avg_time if avg_time > 0 else 0

        # 收集所有轮次和时间
        all_rounds = []
        all_times = []
        for s in per_seed_results:
            all_rounds.extend(s.rounds)
            all_times.extend(s.times)

        result = ExperimentResult(
            config=config,
            accept_count=int(total_accept),
            reject_count=total_reject,
            manual_count=0,
            error_count=0,
            rounds=all_rounds,
            times=all_times,
            per_seed_results=[s.__dict__ for s in per_seed_results]
        )

        self.results.append(result)
        return result

    def _compute_wilson_ci(self, successes: int, total: int, z: float = 1.96) -> tuple:
        """计算Wilson score interval"""
        if total == 0:
            return (0.0, 100.0)

        p_hat = successes / total

        if p_hat == 1.0:
            denominator = 1 + z**2 / total
            center = (p_hat + z**2 / (2 * total)) / denominator
            spread = z * ((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)**0.5 / denominator
            ci_lower = max(0, (center - spread) * 100)
            return (ci_lower, 100.0)

        if p_hat == 0.0:
            denominator = 1 + z**2 / total
            center = (p_hat + z**2 / (2 * total)) / denominator
            spread = z * ((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)**0.5 / denominator
            return (0.0, (center + spread) * 100)

        denominator = 1 + z**2 / total
        center = (p_hat + z**2 / (2 * total)) / denominator
        spread = z * ((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)**0.5 / denominator

        ci_lower = max(0, (center - spread) * 100)
        ci_upper = min(100, (center + spread) * 100)

        return (ci_lower, ci_upper)

    def print_summary(self):
        """打印实验汇总"""
        print("\n" + "="*60)
        print("实验结果汇总")
        print("="*60)

        for result in self.results:
            config = result.config
            print(f"\n配置: n={config.n}, f={config.f}, s={config.s}, "
                  f"attack={config.attack_type or 'none'}")
            print(f"  接受率: {result.accept_rate:.2f}%")
            print(f"  平均轮次: {result.avg_rounds:.2f}")
            print(f"  吞吐量: {result.avg_tps:.0f} TPS")

    def save_results(self, output_path: str):
        """保存结果"""
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

        all_results = {
            "timestamp": datetime.now().isoformat(),
            "experiment_type": "real_dataset",
            "results": [r.to_dict() for r in self.results]
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

        print(f"\n结果已保存: {output_path}")


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description="A2A-BFT 真实数据集实验")
    parser.add_argument("--dataset", type=str, default="math",
                       choices=["math", "code", "knowledge", "mbpp"],
                       help="数据集类型")
    parser.add_argument("--num-tasks", type=int, default=20,
                       help="每个实验的任务数")
    parser.add_argument("--num-seeds", type=int, default=5,
                       help="实验种子数")
    parser.add_argument("--output", type=str, default="experiments/results/real_dataset_results.json",
                       help="结果输出路径")
    parser.add_argument("--no-reputation", action="store_true",
                       help="禁用声誉机制")
    parser.add_argument("--no-threshold", action="store_true",
                       help="禁用动态阈值")
    parser.add_argument("--no-view-change", action="store_true",
                       help="禁用视图切换")
    args = parser.parse_args()

    print("="*60)
    print("A2A-BFT 真实数据集实验")
    print("="*60)

    # 初始化运行器
    runner = RealDatasetExperimentRunner(
        use_reputation=not args.no_reputation,
        use_dynamic_threshold=not args.no_threshold,
        use_view_change=not args.no_view_change
    )

    # 定义实验配置 - 数学推理
    configs_math = [
        ExperimentConfig(name="math_baseline_n4", n=4, f=0, s=0),
        ExperimentConfig(name="math_bft_n5_f1_s1", n=5, f=1, s=1),
        ExperimentConfig(name="math_bft_n6_f2", n=6, f=2, s=0),
        ExperimentConfig(name="math_attack_n5_f1_s1_strategic", n=5, f=1, s=1, attack_type="strategic_reject"),
        ExperimentConfig(name="math_attack_n6_f2_collusion", n=6, f=2, s=0, attack_type="collusion"),
    ]

    # 运行数学实验
    for config in configs_math:
        result = runner.run_experiment(
            config=config,
            dataset_type="math",
            num_tasks=args.num_tasks,
            num_seeds=args.num_seeds
        )
        print(f"  ✅ {config.name}: {result.accept_rate:.1f}%")

    # 打印汇总
    runner.print_summary()

    # 保存结果
    runner.save_results(args.output)

    print("\n" + "="*60)
    print("实验完成！")
    print("="*60)


if __name__ == "__main__":
    main()
