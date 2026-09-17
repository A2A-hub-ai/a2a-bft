"""
n=8 场景专项实验（真实 DeepSeek API）
响应评审意见第4点：扩大 n=8 场景样本量

配置：
- n=8, f=2, s=1 (安全边界 n >= 3f+s+1 = 3*2+1+1 = 8)
- n=8, f=2, s=0 (无软故障)
- n=8, f=0, s=0 (baseline)
攻击类型：collusion + strategic_reject
数据集：GSM8K（数学）
"""

import sys
import os
import json
import time
import random
import argparse
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import ConsensusLayer, DeepSeekWorker
from a2a_bft.data_structures import ExperimentConfig


API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


def load_dataset():
    """加载 GSM8K 测试集"""
    data_dir = os.path.join(os.path.dirname(__file__), 'datasets')
    with open(os.path.join(data_dir, 'gsm8k_test.json'), encoding='utf-8') as f:
        return json.load(f)


def run_scenario(n, f, s, attack_type, dataset, num_tasks, num_seeds):
    """运行单个 n=8 场景，返回汇总结果"""
    print(f"\n{'='*70}")
    print(f"场景: n={n}, f={f}, s={s}, attack={attack_type}")
    print(f"任务数={num_tasks}, 种子数={num_seeds}")
    print(f"{'='*70}")

    total_accept = 0
    total_reject = 0
    total_pending = 0
    total_error = 0
    total_rounds = 0
    total_tasks = 0
    total_time = 0.0

    for seed in range(num_seeds):
        random.seed(seed)
        sampled = random.sample(dataset, min(num_tasks, len(dataset)))

        seed_accept = 0
        seed_rounds = []
        seed_time = 0.0

        for i, task in enumerate(sampled):
            question = task.get('question', task.get('problem', str(task)))

            # 创建 workers
            workers = []
            for wid in range(n):
                worker = DeepSeekWorker(worker_id=wid, api_key=API_KEY)
                if wid < f:
                    worker.is_byzantine = True
                    worker.byzantine_type = attack_type
                elif wid < f + s:
                    worker.is_soft_fault = True
                    worker.accuracy = 0.6
                workers.append(worker)

            consensus = ConsensusLayer(n=n, f=f, s=s, task_type="math")

            t0 = time.time()
            try:
                outcome = consensus.run_consensus(workers, question)
                elapsed = time.time() - t0
                seed_time += elapsed
                rnd = outcome.get("round", 0)
                seed_rounds.append(rnd)
                total_rounds += rnd

                decision = outcome.get("decision", "ERROR")
                if decision == "ACCEPT":
                    seed_accept += 1
                    total_accept += 1
                elif decision == "REJECT":
                    total_reject += 1
                elif decision == "MANUAL":
                    total_pending += 1
                else:
                    total_error += 1

                total_tasks += 1
                total_time += elapsed

                if (i + 1) % 5 == 0 or (i + 1) == len(sampled):
                    rate = seed_accept / (i + 1) * 100
                    print(f"  [Seed {seed}] [{i+1}/{len(sampled)}] 接受率={rate:.1f}% "
                          f"平均轮数={sum(seed_rounds)/len(seed_rounds):.2f}")
            except Exception as e:
                total_error += 1
                total_tasks += 1
                print(f"  [Seed {seed}] [{i+1}/{len(sampled)}] ERROR: {e}")

    accept_rate = total_accept / total_tasks * 100 if total_tasks > 0 else 0
    avg_rounds = total_rounds / total_tasks if total_tasks > 0 else 0

    result = {
        "n": n, "f": f, "s": s, "attack_type": attack_type,
        "accept_rate": round(accept_rate, 1),
        "accept": total_accept,
        "reject": total_reject,
        "pending": total_pending,
        "error": total_error,
        "total_tasks": total_tasks,
        "avg_rounds": round(avg_rounds, 2),
        "total_time_s": round(total_time, 1),
        "avg_time_per_task_s": round(total_time / total_tasks, 1) if total_tasks > 0 else 0,
    }
    print(f"\n  => 接受率={accept_rate:.1f}% ({total_accept}/{total_tasks}) 平均轮数={avg_rounds:.2f}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=40, help="每种子任务数")
    parser.add_argument("--seeds", type=int, default=3, help="种子数")
    args = parser.parse_args()

    dataset = load_dataset()
    print(f"GSM8K 测试集大小: {len(dataset)} 题")

    # n=8 场景配置（扩大样本量）
    scenarios = [
        (8, 2, 1, "collusion"),        # 安全边界，共谋攻击 + 软故障
        (8, 2, 1, "strategic_reject"), # 安全边界，策略性拒绝 + 软故障
        (8, 2, 0, "collusion"),        # 安全边界，共谋攻击（无软故障）
        (8, 0, 0, None),               # baseline 无故障
    ]

    results = []
    for n, f, s, attack in scenarios:
        results.append(run_scenario(n, f, s, attack, dataset, args.tasks, args.seeds))

    output = {
        "timestamp": datetime.now().isoformat(),
        "experiment_type": "n8_scaling_deepseek",
        "model": "deepseek-chat",
        "dataset": "gsm8k",
        "config": {"tasks_per_seed": args.tasks, "seeds": args.seeds},
        "scenarios": results,
    }

    os.makedirs("experiments/results", exist_ok=True)
    out_path = f"experiments/results/n8_deepseek_{args.tasks}t_{args.seeds}s.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print("n=8 场景实验结果汇总")
    print(f"{'='*70}")
    print(f"{'场景':<28} {'接受率':>8} {'轮数':>6}")
    print("-" * 50)
    for r in results:
        label = f"n={r['n']},f={r['f']},s={r['s']},{r['attack_type'] or 'none'}"
        print(f"{label:<28} {r['accept_rate']:>6.1f}% {r['avg_rounds']:>6.2f}")
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
