"""
A2A-BFT 扩展实验脚本 - 第2轮
新增实验：更多攻击类型、更大规模、任务复杂度分析、失败案例分析
"""

import sys
import os
import time
import json
import random
import statistics
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
from enum import Enum

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import DeepSeekWorker, ConsensusLayer


# 新增攻击类型
class AttackType(Enum):
    RANDOM = "random"
    STRATEGIC_REJECT = "strategic_reject"
    SYBIL_ATTACK = "sybil_attack"
    COLLUSION = "collusion"
    ADAPTIVE_REJECTION = "adaptive_rejection"  # 新增
    MALICIOUS_PRIMARY = "malicious_primary"  # 新增
    INSIDER_ATTACK = "insider_attack"  # 新增
    CHAOTIC = "chaotic"  # 新增


# 任务难度分级
class TaskDifficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class ExperimentConfig:
    """实验配置"""
    n: int
    f: int
    s: int
    attack_type: str
    num_rounds: int
    difficulty: str = "all"  # easy, medium, hard, all
    seed: int = 42
    desc: str = ""


class ExtendedExperiment:
    """扩展实验管理器"""

    def __init__(self, output_dir: str = "experiments"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.all_results = []
        self.failure_cases = []

    def create_workers(self, n: int, f: int, s: int,
                       attack_type: str, seed: int = 42) -> List[DeepSeekWorker]:
        """创建Worker集合，支持不同攻击类型"""
        random.seed(seed)
        workers = []

        byzantine_count = 0
        soft_fault_count = 0

        for i in range(n):
            if byzantine_count < f:
                # 拜占庭节点，根据攻击类型配置行为
                worker = DeepSeekWorker(
                    worker_id=i,
                    accuracy=0.3,
                    byzantine_type=attack_type,
                    seed=seed + i
                )
                worker.is_byzantine = True
                byzantine_count += 1
            elif soft_fault_count < s:
                worker = DeepSeekWorker(
                    worker_id=i,
                    accuracy=0.6,
                    seed=seed + f + i
                )
                worker.is_soft_fault = True
                soft_fault_count += 1
            else:
                worker = DeepSeekWorker(
                    worker_id=i,
                    accuracy=0.9,
                    seed=seed + f + s + i
                )
            workers.append(worker)

        return workers

    def generate_tasks_by_difficulty(self, difficulty: str, count: int) -> List[Dict]:
        """按难度生成任务"""
        tasks = []
        random.seed(42)

        for i in range(count):
            if difficulty == "easy" or difficulty == "all":
                tasks.append({
                    "id": f"easy_{i}",
                    "type": "math",
                    "difficulty": "easy",
                    "question": f"Calculate: {(i+1)*11} + {(i+1)*22} = ?",
                    "answer": str((i+1)*11 + (i+1)*22)
                })
            if difficulty == "medium" or difficulty == "all":
                tasks.append({
                    "id": f"medium_{i}",
                    "type": "code",
                    "difficulty": "medium",
                    "question": f"Write a function to compute the {i+1}th Fibonacci number",
                    "answer": "fibonacci"
                })
            if difficulty == "hard" or difficulty == "all":
                tasks.append({
                    "id": f"hard_{i}",
                    "type": "reasoning",
                    "difficulty": "hard",
                    "question": f"Solve: If f(n) = n² + 2n + 1, what is f({i+10})?",
                    "answer": str((i+10)**2 + 2*(i+10) + 1)
                })

        return tasks[:count] if difficulty != "all" else tasks

    def run_single_experiment(self, config: ExperimentConfig) -> Dict:
        """运行单个实验配置"""
        random.seed(config.seed)

        print(f"\n{'='*80}")
        print(f"实验: {config.desc}")
        print(f"配置: n={config.n}, f={config.f}, s={config.s}")
        print(f"攻击类型: {config.attack_type}")
        print(f"任务难度: {config.difficulty}")
        print(f"轮次: {config.num_rounds}")
        print(f"{'='*80}")

        workers = self.create_workers(config.n, config.f, config.s,
                                     config.attack_type, config.seed)
        consensus = ConsensusLayer(n=config.n, f=config.f, s=config.s,
                                  view_change_timeout=1)

        tasks = self.generate_tasks_by_difficulty(config.difficulty, config.num_rounds)

        results = {
            'accept': 0,
            'reject': 0,
            'pending': 0,
            'error': 0,
            'rounds': [],
            'times': [],
            'by_difficulty': {'easy': {}, 'medium': {}, 'hard': {}},
            'failure_cases': []
        }

        start_time = time.time()

        for i, task in enumerate(tasks):
            task_start = time.time()

            try:
                result = consensus.run_consensus(workers, task['question'])
                elapsed = time.time() - task_start

                decision = result.get('decision', 'ERROR').upper()
                rounds = result.get('round', 0)

                # 按难度统计
                diff = task.get('difficulty', 'all')
                if diff not in results['by_difficulty']:
                    diff = 'all'
                if diff not in results['by_difficulty'][diff]:
                    results['by_difficulty'][diff] = {'accept': 0, 'reject': 0, 'total': 0}
                results['by_difficulty'][diff]['total'] += 1

                if decision == 'ACCEPT':
                    results['accept'] += 1
                    results['by_difficulty'][diff]['accept'] += 1
                elif decision == 'REJECT':
                    results['reject'] += 1
                    results['by_difficulty'][diff]['reject'] += 1
                    # 记录失败案例
                    if len(results['failure_cases']) < 20:  # 最多记录20个失败案例
                        results['failure_cases'].append({
                            'task_id': task['id'],
                            'difficulty': task.get('difficulty'),
                            'decision': decision,
                            'rounds': rounds,
                            'time': elapsed
                        })
                elif decision == 'PENDING':
                    results['pending'] += 1
                else:
                    results['error'] += 1

                results['rounds'].append(rounds)
                results['times'].append(elapsed)

                if (i + 1) % 50 == 0:
                    print(f"  进度: {i+1}/{config.num_rounds} ({(i+1)/config.num_rounds*100:.1f}%)",
                          flush=True)

            except Exception as e:
                elapsed = time.time() - task_start
                results['error'] += 1
                results['times'].append(elapsed)
                print(f"  错误: {e}", flush=True)

            # 避免API限流
            if i < len(tasks) - 1:
                time.sleep(0.3)

        total_time = time.time() - start_time

        # 计算统计指标
        if results['rounds']:
            results['avg_rounds'] = statistics.mean(results['rounds'])
            results['std_rounds'] = statistics.stdev(results['rounds']) if len(results['rounds']) > 1 else 0
        if results['times']:
            results['avg_time'] = statistics.mean(results['times'])
            results['std_time'] = statistics.stdev(results['times']) if len(results['times']) > 1 else 0

        results['total_time'] = total_time
        results['timestamp'] = datetime.now().isoformat()
        results['config'] = asdict(config)

        # 保存失败案例
        self.failure_cases.extend(results['failure_cases'])

        return results

    def run_batch_experiments(self, configs: List[ExperimentConfig]) -> List[Dict]:
        """批量运行实验"""
        all_results = []

        for config in configs:
            result = self.run_single_experiment(config)
            all_results.append(result)

            # 打印摘要
            total = result['accept'] + result['reject'] + result['pending'] + result['error']
            if total > 0:
                print(f"\n  结果: Accept={result['accept']} ({result['accept']/total*100:.1f}%), "
                      f"Reject={result['reject']}, Pending={result['pending']}, "
                      f"AvgRounds={result.get('avg_rounds', 0):.2f}")

        return all_results

    def save_results(self, results: List[Dict], filename: str = None):
        """保存实验结果"""
        if filename is None:
            filename = f"extended_experiment_results_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = os.path.join(self.output_dir, filename)

        output = {
            'timestamp': datetime.now().isoformat(),
            'total_experiments': len(results),
            'failure_cases': self.failure_cases[:50],  # 保留前50个失败案例
            'results': results
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存: {output_path}")
        return output_path


def run_extended_experiments():
    """运行扩展实验套件"""
    experiment = ExtendedExperiment()

    # === 新增实验配置 ===
    configs = []

    # 1. 新攻击类型测试
    print("\n=== 新增攻击类型测试 ===")
    new_attack_configs = [
        ExperimentConfig(5, 1, 1, "adaptive_rejection", 100, seed=101, desc="自适应拒绝攻击"),
        ExperimentConfig(5, 1, 1, "malicious_primary", 100, seed=102, desc="恶意Primary攻击"),
        ExperimentConfig(5, 1, 1, "insider_attack", 100, seed=103, desc="内部攻击"),
        ExperimentConfig(5, 1, 1, "chaotic", 100, seed=104, desc="混沌攻击"),
    ]
    configs.extend(new_attack_configs)

    # 2. 任务复杂度分析
    print("\n=== 任务复杂度分析 ===")
    difficulty_configs = [
        ExperimentConfig(5, 1, 1, "random", 100, "easy", seed=201, desc="简单任务"),
        ExperimentConfig(5, 1, 1, "random", 100, "medium", seed=202, desc="中等任务"),
        ExperimentConfig(5, 1, 1, "random", 100, "hard", seed=203, desc="困难任务"),
    ]
    configs.extend(difficulty_configs)

    # 3. 更大规模测试
    print("\n=== 更大规模测试 ===")
    scale_configs = [
        ExperimentConfig(8, 2, 1, "random", 100, seed=301, desc="n=8, f=2, s=1"),
        ExperimentConfig(8, 2, 1, "strategic_reject", 100, seed=302, desc="n=8 策略拒绝"),
        ExperimentConfig(10, 3, 1, "random", 100, seed=303, desc="n=10, f=3, s=1"),
        ExperimentConfig(10, 3, 1, "collusion", 100, seed=304, desc="n=10 共谋攻击"),
    ]
    configs.extend(scale_configs)

    # 4. 极端条件测试
    print("\n=== 极端条件测试 ===")
    extreme_configs = [
        ExperimentConfig(7, 2, 2, "random", 100, seed=401, desc="高软故障率"),
        ExperimentConfig(6, 2, 1, "strategic_reject", 100, seed=402, desc="边界条件"),
        ExperimentConfig(5, 1, 2, "collusion", 100, seed=403, desc="高软故障+共谋"),
    ]
    configs.extend(extreme_configs)

    # 运行所有实验
    results = experiment.run_batch_experiments(configs)

    # 保存结果
    output_path = experiment.save_results(results)

    return results, output_path


if __name__ == "__main__":
    results, output_path = run_extended_experiments()
    print(f"\n实验完成! 结果保存在: {output_path}")
