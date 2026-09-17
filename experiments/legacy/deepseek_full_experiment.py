"""
使用真实 DeepSeek API 运行完整 A2A-BFT 实验
使用真实 benchmark 数据集（不模拟）
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

from a2a_bft.deepseek_worker import ConsensusLayer, BaseWorker, DeepSeekWorker
from a2a_bft.data_structures import ExperimentConfig, ExperimentResult, SeedResult


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

        return tasks[task_id]

    def get_dataset_size(self, task_type: str) -> int:
        """获取数据集大小"""
        return len(self.datasets.get(task_type, []))


# ==================== 实验运行器 ====================

class DeepSeekExperimentRunner:
    """使用真实 DeepSeek API 的实验运行器（纯真实LLM，无模拟）"""

    def __init__(self, api_key: str, model: str = "deepseek-chat",
                 use_reputation: bool = True, use_dynamic_threshold: bool = True,
                 use_view_change: bool = True):
        self.api_key = api_key
        self.model = model
        self.use_reputation = use_reputation
        self.use_dynamic_threshold = use_dynamic_threshold
        self.use_view_change = use_view_change
        self.loader = DatasetLoader()
        self.results = []

    def run_experiment(self, config: ExperimentConfig, dataset_type: str = "math",
                       num_tasks: int = 20, num_seeds: int = 3) -> ExperimentResult:
        """运行单个实验配置"""

        print(f"\n{'='*60}")
        print(f"DeepSeek 真实实验配置: n={config.n}, f={config.f}, s={config.s}")
        print(f"类型: {dataset_type}, 任务数: {num_tasks}, 种子: {num_seeds}")
        print(f"模型: {self.model}, 攻击: {config.attack_type or '无'}")
        print(f"{'='*60}")

        per_seed_results = []
        all_accept_count = 0
        all_reject_count = 0
        all_manual_count = 0
        all_error_count = 0
        all_rounds = []
        all_times = []

        for seed in range(num_seeds):
            random.seed(seed)
            print(f"\n种子 {seed}:")

            seed_accept = 0
            seed_reject = 0
            seed_manual = 0
            seed_error = 0
            seed_rounds = []
            seed_times = []

            for i in range(num_tasks):
                task_start = time.time()

                # 获取真实任务
                try:
                    task_data = self.loader.get_task(dataset_type, i)
                    if dataset_type == "math":
                        question = task_data["question"]
                        task_type = "math"
                    elif dataset_type in ["code", "mbpp"]:
                        # HumanEval 格式：prompt 是代码片段，需要构建完整问题
                        if "prompt" in task_data and "canonical_solution" in task_data:
                            # HumanEval 格式
                            prompt = task_data["prompt"]
                            test = task_data.get("test", "")
                            entry_point = task_data.get("entry_point", "")
                            question = f"""
请完成以下 Python 函数，使其通过所有测试用例：

## 函数签名
{prompt}

## 测试用例
{test}

## 要求
1. 实现函数逻辑
2. 确保所有测试通过
3. 输出完整的函数代码
"""
                            task_type = "code"
                        else:
                            question = task_data.get("prompt", task_data.get("code", str(task_data)))
                            task_type = "code"
                    elif dataset_type == "knowledge":
                        question = f"{task_data['question']}\n" + "\n".join([f"({chr(65+i)}) {c}" for i, c in enumerate(task_data.get("choices", []))])
                        task_type = "general"
                    else:
                        question = str(task_data)
                        task_type = "general"
                except Exception as e:
                    print(f"  获取任务失败: {e}")
                    seed_error += 1
                    continue

                # 创建共识层
                consensus = ConsensusLayer(
                    n=config.n, f=config.f, s=config.s,
                    use_reputation=self.use_reputation,
                    use_dynamic_threshold=self.use_dynamic_threshold,
                    use_view_change=self.use_view_change,
                    task_type=task_type
                )

                # 创建 DeepSeek Worker（全部使用真实LLM）
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
                        model=self.model,
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
                        seed_accept += 1
                    elif outcome["decision"] == "REJECT":
                        seed_reject += 1
                    elif outcome["decision"] == "MANUAL":
                        seed_manual += 1
                    elif outcome["decision"] == "ERROR":
                        seed_error += 1

                    seed_rounds.append(outcome.get("round", 0))
                    seed_times.append(task_time)

                    all_accept_count += 1 if outcome["decision"] == "ACCEPT" else 0
                    all_reject_count += 1 if outcome["decision"] == "REJECT" else 0
                    all_manual_count += 1 if outcome["decision"] == "MANUAL" else 0
                    all_error_count += 1 if outcome["decision"] == "ERROR" else 0
                    all_rounds.extend(seed_rounds[-1:])
                    all_times.extend(seed_times[-1:])

                    print(f"  [{i+1}/{num_tasks}] {outcome['decision']} ({task_time:.1f}s)")

                except Exception as e:
                    seed_error += 1
                    seed_times.append(time.time() - task_start)
                    print(f"  [{i+1}/{num_tasks}] ERROR: {e}")

            # 计算种子结果
            seed_total = seed_accept + seed_reject + seed_manual + seed_error
            seed_accept_rate = seed_accept / seed_total * 100 if seed_total > 0 else 0
            seed_avg_rounds = sum(seed_rounds) / len(seed_rounds) if seed_rounds else 0
            seed_avg_time = sum(seed_times) / len(seed_times) if seed_times else 0

            seed_result = SeedResult(
                seed=seed,
                accept_rate=seed_accept_rate,
                rounds=seed_rounds,
                times=seed_times
            )
            per_seed_results.append(seed_result)

            print(f"  种子 {seed} 接受率: {seed_accept_rate:.1f}% ({seed_accept}/{seed_total})")
            print(f"  平均时间: {seed_avg_time:.1f}s/任务")

        # 计算总体统计
        total_tasks = all_accept_count + all_reject_count + all_manual_count + all_error_count
        accept_rate = all_accept_count / total_tasks * 100 if total_tasks > 0 else 0
        avg_rounds = sum(all_rounds) / len(all_rounds) if all_rounds else 0
        avg_time = sum(all_times) / len(all_times) if all_times else 0
        avg_tps = 1 / avg_time if avg_time > 0 else 0

        result = ExperimentResult(
            config=config,
            accept_count=all_accept_count,
            reject_count=all_reject_count,
            manual_count=all_manual_count,
            error_count=all_error_count,
            rounds=all_rounds,
            times=all_times,
            per_seed_results=[s.__dict__ for s in per_seed_results]
        )

        self.results.append(result)
        return result

    def print_summary(self):
        """打印实验汇总"""
        print("\n" + "="*60)
        print("实验结果汇总")
        print("="*60)

        for result in self.results:
            config = result.config
            print(f"\n配置: n={config.n}, f={config.f}, s={config.s}, "
                  f"attack={config.attack_type or 'none'}")
            print(f"  接受率: {result.accept_rate:.2f}% "
                  f"({result.accept_count}/{result.total_tasks})")
            print(f"  平均轮次: {result.avg_rounds:.2f}")
            print(f"  平均任务时间: {result.avg_time_ms/1000:.1f}s")
            print(f"  吞吐量: {result.avg_tps:.2f} TPS")

    def save_results(self, output_path: str):
        """保存结果"""
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

        all_results = {
            "timestamp": datetime.now().isoformat(),
            "experiment_type": "deepseek_real",
            "model": self.model,
            "results": [r.to_dict() for r in self.results]
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

        print(f"\n结果已保存: {output_path}")


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description="A2A-BFT DeepSeek 完整实验（真实LLM）")
    parser.add_argument("--dataset", type=str, default="math",
                       choices=["math", "code", "knowledge"],
                       help="数据集类型")
    parser.add_argument("--num-tasks", type=int, default=20,
                       help="每个实验的任务数")
    parser.add_argument("--num-seeds", type=int, default=3,
                       help="实验种子数")
    parser.add_argument("--model", type=str, default="deepseek-chat",
                       help="DeepSeek 模型名称")
    parser.add_argument("--output", type=str, default="experiments/results/deepseek_full_results.json",
                       help="结果输出路径")
    args = parser.parse_args()

    # 获取 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("错误: 请设置环境变量 DEEPSEEK_API_KEY")
        sys.exit(1)

    print("="*60)
    print("A2A-BFT DeepSeek 完整实验（真实LLM，无模拟）")
    print("="*60)
    print(f"模型: {args.model}")
    print(f"数据集: {args.dataset}")
    print(f"任务数: {args.num_tasks}, 种子数: {args.num_seeds}")

    # 初始化运行器
    runner = DeepSeekExperimentRunner(
        api_key=api_key,
        model=args.model
    )

    # 定义实验配置
    configs = [
        ExperimentConfig(name="baseline_n4", n=4, f=0, s=0),
        ExperimentConfig(name="baseline_n5", n=5, f=0, s=0),
        ExperimentConfig(name="bft_n5_f1_s1", n=5, f=1, s=1),
        ExperimentConfig(name="bft_n6_f2", n=6, f=2, s=0),
        ExperimentConfig(name="attack_n5_strategic", n=5, f=1, s=1, attack_type="strategic_reject"),
        ExperimentConfig(name="attack_n6_collusion", n=6, f=2, s=0, attack_type="collusion"),
    ]

    # 运行实验
    for config in configs:
        result = runner.run_experiment(
            config=config,
            dataset_type=args.dataset,
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
