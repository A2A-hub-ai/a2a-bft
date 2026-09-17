"""
对比和消融实验：使用真实 DeepSeek API
简化版本，避免复杂数据结构问题
"""

import sys
import os
import json
import time
import random
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import ConsensusLayer, DeepSeekWorker
from a2a_bft.baselines import SimpleMajority, WeightedMajority, A2ASimSimulation, LLMDebateSimulation
from a2a_bft.data_structures import ExperimentConfig


# API key配置（原为硬编码密钥，已移除；请通过环境变量 DEEPSEEK_API_KEY 提供）
api_key = os.environ.get("DEEPSEEK_API_KEY", "")


def load_dataset(dataset_type: str) -> list:
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


def run_a2a_bft(config, dataset, num_tasks, num_seeds):
    """运行A2A-BFT实验"""
    print(f"\n{'='*60}")
    print(f"A2A-BFT: n={config.n}, f={config.f}, s={config.s}, attack={config.attack_type}")
    print(f"{'='*60}")

    total_accept = 0
    total_reject = 0
    total_error = 0
    all_times = []

    for seed in range(num_seeds):
        random.seed(seed)
        seed_accept = 0
        seed_reject = 0

        for i in range(num_tasks):
            task = dataset[i % len(dataset)]
            question = task.get('question', task.get('problem', str(task)))

            start_time = time.time()
            try:
                workers = []
                for j in range(config.n):
                    worker = DeepSeekWorker(
                        worker_id=j,
                        api_key=api_key,
                    )
                    # 设置拜占庭和软故障属性
                    if j < config.f:
                        worker.is_byzantine = True
                        worker.byzantine_type = config.attack_type
                    elif j < config.f + config.s:
                        worker.is_soft_fault = True
                    workers.append(worker)

                consensus = ConsensusLayer(n=config.n, f=config.f, s=config.s)
                result = consensus.run_consensus(workers, question)
                elapsed = time.time() - start_time
                all_times.append(elapsed)

                if result['decision'] == 'ACCEPT':
                    total_accept += 1
                    seed_accept += 1
                elif result['decision'] == 'REJECT':
                    total_reject += 1
                    seed_reject += 1
                else:
                    total_error += 1

                print(f"  Seed {seed}, Task {i}: {result['decision']} ({elapsed:.1f}s)")

            except Exception as e:
                elapsed = time.time() - start_time
                all_times.append(elapsed)
                total_error += 1
                print(f"  Seed {seed}, Task {i}: ERROR - {str(e)[:40]}")

    total = total_accept + total_reject + total_error
    print(f"\nA2A-BFT Summary: {total_accept}/{total} accepted ({total_accept/total*100:.1f}%)")
    print(f"Avg time: {sum(all_times)/len(all_times):.1f}s")

    return {
        'accept': total_accept,
        'reject': total_reject,
        'error': total_error,
        'total': total,
        'accept_rate': total_accept / total * 100 if total > 0 else 0,
        'avg_time': sum(all_times) / len(all_times) if all_times else 0
    }


def run_baseline(method_name, config, dataset, num_tasks, num_seeds):
    """运行基线方法实验"""
    methods = {
        'simple_majority': SimpleMajority,
        'weighted_majority': WeightedMajority,
        'a2a_sim': A2ASimSimulation,
        'llm_debate': LLMDebateSimulation,
    }

    print(f"\n{'='*60}")
    print(f"{method_name}: n={config.n}, f={config.f}, s={config.s}")
    print(f"{'='*60}")

    method_cls = methods[method_name]
    method = method_cls()

    total_accept = 0
    total_reject = 0
    total_error = 0
    all_times = []

    for seed in range(num_seeds):
        random.seed(seed)
        seed_accept = 0
        seed_reject = 0

        for i in range(num_tasks):
            task = dataset[i % len(dataset)]
            question = task.get('question', task.get('problem', str(task)))

            start_time = time.time()
            try:
                workers = []
                for j in range(config.n):
                    accuracy = 0.9 if j >= config.f else 0.3
                    worker = DeepSeekWorker(
                        worker_id=j,
                        api_key=api_key,
                        accuracy=accuracy
                    )
                    workers.append(worker)

                result = method.consensus(workers, question)
                elapsed = time.time() - start_time
                all_times.append(elapsed)

                decision = result.get('decision', 'ERROR')
                if decision == 'ACCEPT':
                    total_accept += 1
                    seed_accept += 1
                elif decision == 'REJECT':
                    total_reject += 1
                    seed_reject += 1
                else:
                    total_error += 1

                print(f"  Seed {seed}, Task {i}: {decision} ({elapsed:.1f}s)")

            except Exception as e:
                elapsed = time.time() - start_time
                all_times.append(elapsed)
                total_error += 1
                print(f"  Seed {seed}, Task {i}: ERROR - {str(e)[:40]}")

    total = total_accept + total_reject + total_error
    print(f"\n{method_name} Summary: {total_accept}/{total} accepted ({total_accept/total*100:.1f}%)")
    print(f"Avg time: {sum(all_times)/len(all_times):.1f}s")

    return {
        'accept': total_accept,
        'reject': total_reject,
        'error': total_error,
        'total': total,
        'accept_rate': total_accept / total * 100 if total > 0 else 0,
        'avg_time': sum(all_times) / len(all_times) if all_times else 0
    }


def run_ablation(config, dataset, num_tasks, num_seeds):
    """运行消融实验"""
    variants = [
        ('full_a2a_bft', None),
        ('no_reputation', {'alpha': 0, 'beta': 0}),
        ('no_threshold', {'theta_accept': 2.0, 'theta_reject': -2.0}),
        ('no_view_change', {'view_change_timeout': 100}),
        ('no_byzantine_detection', {'beta': 0}),
    ]

    results = {}
    for variant_name, overrides in variants:
        print(f"\n{'='*60}")
        print(f"Ablation: {variant_name}")
        print(f"{'='*60}")

        total_accept = 0
        total_reject = 0
        total_error = 0
        all_times = []

        for seed in range(num_seeds):
            random.seed(seed)

            for i in range(num_tasks):
                task = dataset[i % len(dataset)]
                question = task.get('question', task.get('problem', str(task)))

                start_time = time.time()
                try:
                    workers = []
                    for j in range(config.n):
                        worker = DeepSeekWorker(
                            worker_id=j,
                            api_key=api_key,
                        )
                        # 设置拜占庭和软故障属性
                        if j < config.f:
                            worker.is_byzantine = True
                            worker.byzantine_type = config.attack_type
                        elif j < config.f + config.s:
                            worker.is_soft_fault = True
                        workers.append(worker)

                    consensus = ConsensusLayer(
                        n=config.n, f=config.f, s=config.s
                    )

                    # 应用消融配置
                    if overrides:
                        for key, value in overrides.items():
                            setattr(consensus, key, value)

                    result = consensus.run_consensus(workers, question)
                    elapsed = time.time() - start_time
                    all_times.append(elapsed)

                    if result['decision'] == 'ACCEPT':
                        total_accept += 1
                    elif result['decision'] == 'REJECT':
                        total_reject += 1
                    else:
                        total_error += 1

                    print(f"  Seed {seed}, Task {i}: {result['decision']} ({elapsed:.1f}s)")

                except Exception as e:
                    elapsed = time.time() - start_time
                    all_times.append(elapsed)
                    total_error += 1
                    print(f"  Seed {seed}, Task {i}: ERROR - {str(e)[:40]}")

        total = total_accept + total_reject + total_error
        accept_rate = total_accept / total * 100 if total > 0 else 0
        avg_time = sum(all_times) / len(all_times) if all_times else 0

        results[variant_name] = {
            'accept': total_accept,
            'reject': total_reject,
            'error': total_error,
            'total': total,
            'accept_rate': accept_rate,
            'avg_time': avg_time
        }

        print(f"\n{variant_name}: {total_accept}/{total} accepted ({accept_rate:.1f}%), avg time: {avg_time:.1f}s")

    return results


def main():
    """主函数"""
    print("="*60)
    print("A2A-BFT Comparison and Ablation Experiments")
    print("Using Real DeepSeek API")
    print("="*60)

    # 实验配置
    configs = [
        ExperimentConfig(name="baseline_n4", n=4, f=1, s=0, attack_type="random"),
        ExperimentConfig(name="bft_n5_f1s1", n=5, f=1, s=1, attack_type="random"),
        ExperimentConfig(name="bft_n6_f2", n=6, f=2, s=0, attack_type="random"),
    ]

    ablation_config = ExperimentConfig(name="a2a_bft_core", n=5, f=1, s=1, attack_type="strategic_reject")

    num_tasks = 10  # 每个数据集10个任务
    num_seeds = 2   # 2个随机种子

    all_results = {}

    # 运行三个数据集的实验
    for dataset_type in ['math', 'code', 'knowledge']:
        print(f"\n\n{'#'*60}")
        print(f"# Dataset: {dataset_type.upper()}")
        print(f"{'#'*60}")

        dataset = load_dataset(dataset_type)
        print(f"Dataset size: {len(dataset)} tasks")

        dataset_results = {}

        # 运行对比实验
        for config in configs:
            config_results = {}

            # A2A-BFT
            a2a_bft_result = run_a2a_bft(config, dataset, num_tasks, num_seeds)
            config_results['a2a_bft'] = a2a_bft_result

            # 基线方法
            for method in ['simple_majority', 'weighted_majority', 'a2a_sim', 'llm_debate']:
                baseline_result = run_baseline(method, config, dataset, num_tasks, num_seeds)
                config_results[method] = baseline_result

            dataset_results[f"{config.name}"] = config_results

        # 运行消融实验
        print(f"\n\n{'='*60}")
        print(f"Ablation Experiments: {dataset_type.upper()}")
        print(f"{'='*60}")
        ablation_results = run_ablation(ablation_config, dataset, num_tasks, num_seeds)
        dataset_results['ablation'] = ablation_results

        all_results[dataset_type] = dataset_results

        # 保存结果
        output_file = Path(__file__).parent / "results" / f"comparison_ablation_{dataset_type}_{num_tasks}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(dataset_results, f, ensure_ascii=False, indent=2)
        print(f"\nResults saved to: {output_file}")

    # 生成汇总报告
    print("\n\n" + "="*60)
    print("EXPERIMENT SUMMARY")
    print("="*60)

    for dataset_type, dataset_results in all_results.items():
        print(f"\n{dataset_type.upper()}:")
        for config_name, config_results in dataset_results.items():
            if config_name == 'ablation':
                print(f"  Ablation:")
                for variant, result in config_results.items():
                    print(f"    {variant}: {result['accept_rate']:.1f}% ({result['accept']}/{result['total']}), time={result['avg_time']:.1f}s")
            else:
                print(f"  {config_name}:")
                for method, result in config_results.items():
                    print(f"    {method}: {result['accept_rate']:.1f}% ({result['accept']}/{result['total']}), time={result['avg_time']:.1f}s")

    # 保存汇总结果
    summary_file = Path(__file__).parent / "results" / "comparison_ablation_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSummary saved to: {summary_file}")


if __name__ == "__main__":
    main()
