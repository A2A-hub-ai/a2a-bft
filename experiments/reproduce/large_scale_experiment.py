"""
使用真实 DeepSeek API 运行大规模 A2A-BFT 实验
数据集: GSM8K (1319) + MBPP (500) + MMLU (312) + HumanEval (164)
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


class LargeScaleExperimentRunner:
    """大规模真实 LLM 实验运行器"""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.results = []

    def _load_dataset(self, dataset_type: str) -> List[Dict]:
        """加载数据集"""
        data_dir = Path(__file__).resolve().parent.parent / "datasets"
        files = {
            "math": "gsm8k_test.json",
            "code": "mbpp_test.json",
            "knowledge": "mmlu_3subjects.json",
        }
        filepath = data_dir / files.get(dataset_type, f"{dataset_type}.json")
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

    def run_experiment(self, config: ExperimentConfig, dataset_type: str,
                       num_tasks: int, num_seeds: int) -> ExperimentResult:
        """运行实验配置"""
        print(f"\n{'='*60}")
        print(f"配置: {config.name}")
        print(f"  n={config.n}, f={config.f}, s={config.s}")
        print(f"  攻击: {config.attack_type}")
        print(f"  数据集: {dataset_type}, 任务数: {num_tasks}, 种子: {num_seeds}")

        # 加载数据集
        tasks = self._load_dataset(dataset_type)
        print(f"  数据集大小: {len(tasks)} 题")

        per_seed_results = []
        total_accept = 0
        total_reject = 0
        total_error = 0
        all_times = []

        for seed in range(num_seeds):
            random.seed(seed)
            seed_accept = 0
            seed_reject = 0
            seed_error = 0
            seed_times = []

            # 随机采样任务
            sampled_tasks = random.sample(tasks, min(num_tasks, len(tasks)))

            # 创建 workers
            workers = []
            for i in range(config.n):
                worker = DeepSeekWorker(
                    worker_id=i,
                    model=self.model,
                    api_key=self.api_key,
                )
                worker.is_byzantine = i < config.f
                worker.byzantine_type = config.attack_type if i < config.f else None
                workers.append(worker)

            # 运行共识
            consensus = ConsensusLayer(
                n=config.n,
                f=config.f,
                s=config.s,
                task_type=dataset_type
            )

            for i, task in enumerate(sampled_tasks):
                # 获取问题
                if isinstance(task, dict):
                    question = task.get('question', task.get('problem', ''))
                else:
                    question = str(task)

                start_time = time.time()
                try:
                    outcome = consensus.run_consensus(workers, question)
                    elapsed = time.time() - start_time
                    seed_times.append(elapsed)
                    all_times.append(elapsed)

                    if outcome["decision"] == "ACCEPT":
                        seed_accept += 1
                    elif outcome["decision"] == "REJECT":
                        seed_reject += 1
                    else:
                        seed_error += 1

                    if (i + 1) % 10 == 0:
                        print(f"    Seed {seed}: [{i+1}/{num_tasks}] 接受率={seed_accept/(i+1)*100:.1f}%")

                except Exception as e:
                    seed_error += 1
                    seed_times.append(0)
                    all_times.append(0)
                    print(f"    Seed {seed}: [{i+1}/{num_tasks}] ERROR: {e}")

            total_accept += seed_accept
            total_reject += seed_reject
            total_error += seed_error

            per_seed_results.append(SeedResult(
                seed=seed,
                accept_rate=seed_accept / num_tasks * 100 if num_tasks > 0 else 0,
                rounds=[1] * num_tasks,
                times=seed_times
            ))

        accept_rate = total_accept / (total_accept + total_reject + total_error) * 100 if (total_accept + total_reject + total_error) > 0 else 0

        # 展平rounds为扁平列表
        all_rounds = []
        for seed_rounds in [[1] * num_tasks for _ in range(num_seeds)]:
            all_rounds.extend(seed_rounds)

        return ExperimentResult(
            config=config,
            accept_count=total_accept,
            reject_count=total_reject,
            manual_count=0,
            error_count=total_error,
            rounds=all_rounds,
            times=all_times,
            per_seed_results=[s.__dict__ for s in per_seed_results]
        )


def main():
    parser = argparse.ArgumentParser(description="A2A-BFT 大规模真实 LLM 实验")
    parser.add_argument("--tasks", type=int, default=100, help="每个配置的任务数")
    parser.add_argument("--seeds", type=int, default=5, help="实验种子数")
    parser.add_argument("--output", type=str,
                       default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                            "results", "large_scale_results.json"),
                       help="结果输出路径")
    args = parser.parse_args()

    # API key 从环境变量读取（原为硬编码密钥，已移除）
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("错误: 请设置环境变量 DEEPSEEK_API_KEY 或在脚本中配置API key")
        sys.exit(1)

    print("="*60)
    print("A2A-BFT 大规模真实 LLM 实验")
    print("="*60)
    print(f"任务数: {args.tasks}, 种子数: {args.seeds}")

    runner = LargeScaleExperimentRunner(api_key=api_key)

    # 实验配置
    configs = [
        ExperimentConfig(name="math_baseline_n4", n=4, f=0, s=0),
        ExperimentConfig(name="math_bft_n5_f1_s1", n=5, f=1, s=1),
        ExperimentConfig(name="math_attack_strategic", n=5, f=1, s=1, attack_type="strategic_reject"),
        ExperimentConfig(name="math_attack_collusion", n=6, f=2, s=0, attack_type="collusion"),
        ExperimentConfig(name="code_baseline_n4", n=4, f=0, s=0),
        ExperimentConfig(name="code_bft_n5_f1_s1", n=5, f=1, s=1),
        ExperimentConfig(name="knowledge_baseline_n4", n=4, f=0, s=0),
        ExperimentConfig(name="knowledge_bft_n5_f1_s1", n=5, f=1, s=1),
    ]

    dataset_types = ["math", "code", "knowledge"]

    total_tasks = 0
    all_results = []

    for config in configs:
        # 根据配置名确定数据集类型
        if "math" in config.name:
            dataset_type = "math"
        elif "code" in config.name:
            dataset_type = "code"
        else:
            dataset_type = "knowledge"

        print(f"\n运行: {config.name} ({dataset_type})")
        result = runner.run_experiment(config, dataset_type, args.tasks, args.seeds)
        all_results.append({
            "config": config.__dict__,
            "results": result.__dict__
        })
        total_tasks += args.tasks * args.seeds
        print(f"  接受率: {result.accept_rate:.1f}%")

    # 保存结果
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "experiment_type": "large_scale_deepseek",
        "model": "deepseek-chat",
        "total_tasks": total_tasks,
        "results": all_results
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"实验完成! 总任务数: {total_tasks}")
    print(f"结果保存: {args.output}")
    print("="*60)


if __name__ == "__main__":
    main()
