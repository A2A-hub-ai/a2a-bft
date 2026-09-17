"""
消融实验：使用真实 DeepSeek API 测试各组件的贡献

设计改进：
1. 诚实节点验证时检查Primary提案内容，而非忽略提案
2. 使用更强攻击场景（n=7, f=2, s=1）提高区分度
3. 添加错误注入实验，测试拜占庭检测能力
4. 记录每轮投票详情，分析各组件的作用
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


# API key配置（原为硬编码密钥，已移除；请通过环境变量 DEEPSEEK_API_KEY 提供）
api_key = os.environ.get("DEEPSEEK_API_KEY", "")


class ImprovedAblationExperimentRunner:
    """改进版消融实验运行器"""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model

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

    def _run_single_config(self, config: ExperimentConfig, variant: str,
                           dataset: list, num_tasks: int, num_seeds: int) -> ExperimentResult:
        """运行单个配置（消融变体）"""
        total_accept = 0
        total_reject = 0
        total_error = 0
        all_times = []
        all_rounds = []
        all_decisions = []  # 记录每次决策详情
        per_seed_results = []

        for seed in range(num_seeds):
            random.seed(seed)
            seed_accept = 0
            seed_reject = 0
            seed_times = []
            seed_rounds = []

            for i in range(num_tasks):
                task = dataset[i % len(dataset)]
                question = task.get('question', task.get('prompt', str(task)))

                start_time = time.time()
                try:
                    # 创建workers
                    workers = []
                    for j in range(config.n):
                        worker = DeepSeekWorker(
                            worker_id=j,
                            api_key=self.api_key,
                            model=self.model,
                        )
                        # 设置拜占庭和软故障属性
                        if j < config.f:
                            worker.is_byzantine = True
                            worker.byzantine_type = config.attack_type
                        elif j < config.f + config.s:
                            worker.is_soft_fault = True
                        workers.append(worker)

                    # 根据消融变体配置共识层
                    if variant == 'no_reputation':
                        # 禁用声誉机制（固定权重）
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s
                        )
                        consensus.alpha = 0  # 禁用权重更新
                        consensus.beta = 0
                    elif variant == 'no_threshold':
                        # 使用固定阈值（论文推荐的固定阈值）
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s,
                            theta_accept=1.5,
                            theta_reject=-1.5
                        )
                    elif variant == 'no_view_change':
                        # 禁用视图切换
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s,
                            view_change_timeout=100  # 极高超时，等效禁用
                        )
                    elif variant == 'no_byzantine_detection':
                        # 禁用拜占庭检测（不惩罚错误投票）
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s
                        )
                        consensus.beta = 0  # 不惩罚
                    else:
                        # 完整A2A-BFT
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s
                        )

                    # 运行共识
                    result = consensus.run_consensus(workers, question)
                    decision = result.get('decision', 'MANUAL')
                    rounds = result.get('round', 1)

                    elapsed = time.time() - start_time
                    all_times.append(elapsed)
                    all_rounds.append(rounds)
                    all_decisions.append({
                        'task': i,
                        'seed': seed,
                        'decision': decision,
                        'rounds': rounds,
                        'time': elapsed,
                        'variant': variant
                    })
                    seed_times.append(elapsed)
                    seed_rounds.append(rounds)

                    if decision == 'ACCEPT':
                        total_accept += 1
                        seed_accept += 1
                    elif decision == 'REJECT':
                        total_reject += 1
                        seed_reject += 1
                    else:
                        total_error += 1

                    print(f"  [{variant}] Seed {seed}, Task {i}: {decision} ({elapsed:.1f}s, rounds={rounds})")

                except Exception as e:
                    elapsed = time.time() - start_time
                    all_times.append(elapsed)
                    all_rounds.append(1)
                    seed_times.append(elapsed)
                    total_error += 1
                    print(f"  [ERROR] {variant}, Seed {seed}, Task {i}: {str(e)[:80]}")

            per_seed_results.append(SeedResult(
                seed=seed,
                accept_rate=(seed_accept / num_tasks * 100) if num_tasks > 0 else 0,
                rounds=seed_rounds,
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
            per_seed_results=[s.__dict__ for s in per_seed_results],
            decisions=all_decisions
        )

    def run_ablation(self, dataset_type: str, num_tasks: int = 20, num_seeds: int = 3):
        """运行完整消融实验"""
        print(f"\n{'='*60}")
        print(f"消融实验: {dataset_type.upper()}")
        print(f"任务数: {num_tasks}, 种子数: {num_seeds}")
        print(f"{'='*60}")

        dataset = self._load_dataset(dataset_type)

        # 核心配置：n=7, f=2, s=1（增强攻击场景）
        config = ExperimentConfig(
            name="a2a_bft_enhanced", n=7, f=2, s=1, attack_type="strategic_reject"
        )

        variants = [
            'full_a2a_bft',      # 完整A2A-BFT
            'no_reputation',      # 无声誉机制
            'no_threshold',       # 固定阈值
            'no_view_change',     # 无视图切换
            'no_byzantine_detection',  # 无拜占庭检测
        ]

        results = {}
        for variant in variants:
            print(f"\n运行变体: {variant}")
            result = self._run_single_config(config, variant, dataset, num_tasks, num_seeds)
            results[variant] = result

            print(f"  接受率: {result.accept_count}/{num_tasks*num_seeds} = {result.accept_rate:.1f}%")
            print(f"  拒绝率: {result.reject_count}/{num_tasks*num_seeds} = {result.reject_rate:.1f}%")
            print(f"  平均时间: {result.avg_time_ms:.0f}ms")
            print(f"  平均轮次: {result.avg_rounds:.2f}")

        # 保存结果
        output_file = Path(__file__).parent / "results" / f"ablation_improved_{dataset_type}_{num_tasks}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n结果已保存: {output_file}")
        return results

    def run_comparison_experiments(self, dataset_type: str, num_tasks: int = 20, num_seeds: int = 3):
        """运行多场景对比实验"""
        print(f"\n{'='*60}")
        print(f"多场景消融实验: {dataset_type.upper()}")
        print(f"{'='*60}")

        dataset = self._load_dataset(dataset_type)

        # 多个配置场景
        configs = [
            # 标准强度
            ExperimentConfig(name="n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject"),
            # 增强强度
            ExperimentConfig(name="n7_f2_s1", n=7, f=2, s=1, attack_type="strategic_reject"),
            # 高攻击强度
            ExperimentConfig(name="n10_f3_s1", n=10, f=3, s=1, attack_type="collusion"),
        ]

        variants = [
            'full_a2a_bft',
            'no_reputation',
            'no_byzantine_detection',
        ]

        all_results = {}
        for config in configs:
            print(f"\n{'='*40}")
            print(f"配置: {config.name} (n={config.n}, f={config.f}, s={config.s})")
            print(f"{'='*40}")

            config_results = {}
            for variant in variants:
                result = self._run_single_config(config, variant, dataset, num_tasks, num_seeds)
                config_results[variant] = {
                    'accept_rate': result.accept_rate,
                    'reject_rate': result.reject_rate,
                    'avg_rounds': result.avg_rounds,
                    'avg_time_ms': result.avg_time_ms,
                }
                print(f"  {variant}: 接受率={result.accept_rate:.1f}%, 拒绝率={result.reject_rate:.1f}%")

            all_results[config.name] = config_results

        # 保存结果
        output_file = Path(__file__).parent / "results" / f"ablation_multi_config_{dataset_type}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n结果已保存: {output_file}")
        return all_results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='消融实验')
    parser.add_argument('--dataset', type=str, default='math', choices=['math', 'code', 'knowledge'])
    parser.add_argument('--tasks', type=int, default=20, help='任务数')
    parser.add_argument('--seeds', type=int, default=3, help='种子数')
    parser.add_argument('--mode', type=str, default='full', choices=['full', 'comparison'])
    args = parser.parse_args()

    runner = ImprovedAblationExperimentRunner(api_key)

    if args.mode == 'full':
        runner.run_ablation(args.dataset, args.tasks, args.seeds)
    else:
        runner.run_comparison_experiments(args.dataset, args.tasks, args.seeds)
