"""
对比实验：使用真实 DeepSeek API 对比 A2A-BFT 与基线方法
"""

import sys
import os
import json
import time
import random
from datetime import datetime
from pathlib import Path

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import ConsensusLayer, DeepSeekWorker
from a2a_bft.data_structures import ExperimentConfig, ExperimentResult, SeedResult
from a2a_bft.baselines import SimpleMajority, WeightedMajority, A2ASimSimulation, LLMDebateSimulation


# API key配置（原为硬编码密钥，已移除；请通过环境变量 DEEPSEEK_API_KEY 提供）
api_key = os.environ.get("DEEPSEEK_API_KEY", "")


class ComparisonExperimentRunner:
    """对比实验运行器"""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.methods = {
            'a2a_bft': ConsensusLayer,
            'simple_majority': SimpleMajority,
            'weighted_majority': WeightedMajority,
            'a2a_sim': A2ASimSimulation,
            'llm_debate': LLMDebateSimulation,
        }

    def _load_dataset(self, dataset_type: str) -> list:
        """加载数据集"""
        data_dir = Path(__file__).parent / "datasets"
        files = {
            "math": "gsm8k_test.json",
            "code": "mbpp_test.json",
            "knowledge": "mmlu_3subjects.json",
        }
        filepath = data_dir / files.get(dataset_type, f"{dataset_type}.json")
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

    def _run_single_config(self, config: ExperimentConfig, method_name: str,
                           dataset: list, num_tasks: int, num_seeds: int) -> ExperimentResult:
        """运行单个配置"""
        total_accept = 0
        total_reject = 0
        total_error = 0
        all_times = []
        all_rounds = []
        per_seed_results = []

        for seed in range(num_seeds):
            random.seed(seed)
            seed_accept = 0
            seed_reject = 0
            seed_times = []

            for i in range(num_tasks):
                task = dataset[i % len(dataset)]
                question = task.get('question', task.get('prompt', str(task)))

                start_time = time.time()
                try:
                    if method_name == 'a2a_bft':
                        # A2A-BFT 使用真实Worker
                        workers = []
                        for j in range(config.n):
                            accuracy = 0.3 if j < config.f else 0.9
                            byzantine_type = config.attack_type if j < config.f else None
                            worker = DeepSeekWorker(
                                worker_id=j,
                                api_key=self.api_key,
                                model=self.model,
                                accuracy=accuracy,
                                byzantine_type=byzantine_type
                            )
                            workers.append(worker)

                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s
                        )
                        result = consensus.run_consensus(workers, question)
                        decision = result.get('decision', 'MANUAL')
                        rounds = result.get('round', 1)

                    else:
                        # 基线方法使用DeepSeekWorker
                        workers = []
                        for j in range(config.n):
                            accuracy = 0.3 if j < config.f else 0.9
                            worker = DeepSeekWorker(
                                worker_id=j,
                                api_key=self.api_key,
                                model=self.model,
                                accuracy=accuracy
                            )
                            workers.append(worker)

                        method_cls = self.methods[method_name]
                        method = method_cls()
                        result = method.consensus(workers, question)
                        decision = result.get('decision', 'ERROR')
                        rounds = 1

                    elapsed = time.time() - start_time
                    all_times.append(elapsed)  # 保持秒为单位
                    all_rounds.append(rounds)
                    seed_times.append(elapsed)

                    if decision == 'ACCEPT':
                        total_accept += 1
                        seed_accept += 1
                    elif decision == 'REJECT':
                        total_reject += 1
                        seed_reject += 1
                    else:
                        total_error += 1

                    print(f"  [{method_name}] Seed {seed}, Task {i}: {decision} ({elapsed:.1f}s)")

                except Exception as e:
                    elapsed = time.time() - start_time
                    all_times.append(elapsed)
                    all_rounds.append(1)
                    seed_times.append(elapsed)
                    total_error += 1
                    print(f"  [ERROR] {method_name}, Seed {seed}, Task {i}: {str(e)[:50]}")

            per_seed_results.append(SeedResult(
                seed=seed,
                accept_rate=(seed_accept / num_tasks * 100) if num_tasks > 0 else 0,
                rounds=[1] * num_tasks,
                times=seed_times
            ))

        return ExperimentResult(
            config=config,
            accept_count=total_accept,
            reject_count=total_reject,
            manual_count=0,
            error_count=total_error,
            rounds=all_rounds,
            times=[t * 1000 for t in all_times],  # 转换为毫秒
            per_seed_results=[s.__dict__ for s in per_seed_results]
        )

    def run_comparison(self, dataset_type: str, num_tasks: int = 20, num_seeds: int = 2):
        """运行完整对比实验"""
        print(f"\n{'='*60}")
        print(f"对比实验: {dataset_type.upper()}")
        print(f"任务数: {num_tasks}, 种子数: {num_seeds}")
        print(f"{'='*60}")

        dataset = self._load_dataset(dataset_type)
        results = {}

        # 配置
        configs = [
            ExperimentConfig(name="baseline_n4", n=4, f=1, s=0, attack_type="random"),
            ExperimentConfig(name="bft_n5_f1s1", n=5, f=1, s=1, attack_type="random"),
            ExperimentConfig(name="bft_n6_f2", n=6, f=2, s=0, attack_type="random"),
        ]

        methods = ['simple_majority', 'weighted_majority', 'a2a_sim', 'llm_debate', 'a2a_bft']

        for config in configs:
            for method in methods:
                print(f"\n运行: {config.name} + {method}")
                result = self._run_single_config(config, method, dataset, num_tasks, num_seeds)
                results[f"{config.name}_{method}"] = result

                print(f"  接受率: {result.accept_count}/{num_tasks*num_seeds} = {result.accept_rate:.1f}%")
                print(f"  平均时间: {result.avg_time_ms:.0f}ms")

        # 保存结果
        output_file = Path(__file__).parent / "results" / f"comparison_deepseek_{dataset_type}_{num_tasks}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n结果已保存: {output_file}")
        return results


if __name__ == "__main__":
    runner = ComparisonExperimentRunner(api_key)

    # 运行三个数据集的对比实验
    for dataset_type in ['math', 'code', 'knowledge']:
        try:
            runner.run_comparison(dataset_type, num_tasks=20, num_seeds=2)
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
