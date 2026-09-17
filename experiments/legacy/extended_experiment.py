"""
A2A-BFT 扩展实验
支持 HumanEval 数据集 + 多种拜占庭攻击类型 + 大规模实验
"""

import sys
import os
import time
import json
import random
from datetime import datetime
from typing import List, Dict, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import DeepSeekWorker, ConsensusLayer
from humaneval_dataset import HUMANEVAL_DATASET, get_random_tasks, format_task_for_llm


# 拜占庭攻击类型配置
BYZANTINE_TYPES = {
    "random": "随机回复",
    "lazy": "懒惰拒绝",
    "strategic_reject": "策略性拒绝",
    "sybil_attack": "Sybil 攻击",
    "backdoor": "后门植入",
    "collusion": "共谋攻击"
}


def create_workers(
    n: int, f: int, s: int,
    byzantine_type: str = "random",
    api_key: str = None
) -> List[DeepSeekWorker]:
    """创建 Worker 集合，支持不同拜占庭类型"""
    workers = []
    byzantine_count = 0
    soft_fault_count = 0

    for i in range(n):
        if byzantine_count < f:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.3,
                byzantine_type=byzantine_type,
                api_key=api_key
            )
            worker.is_byzantine = True
            print(f"  Worker {i}: 拜占庭({byzantine_type}) accuracy=0.3", flush=True)
            byzantine_count += 1
        elif soft_fault_count < s:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.6,
                api_key=api_key
            )
            worker.is_soft_fault = True
            print(f"  Worker {i}: 软故障 accuracy=0.6", flush=True)
            soft_fault_count += 1
        else:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.9,
                api_key=api_key
            )
            print(f"  Worker {i}: 诚实 accuracy=0.9", flush=True)
        workers.append(worker)

    return workers


def run_single_task(
    consensus: ConsensusLayer,
    workers: List[DeepSeekWorker],
    task: Dict
) -> Dict:
    """运行单个任务"""
    start_time = time.time()
    try:
        # 格式化任务提示
        prompt = format_task_for_llm(task)

        # 运行共识
        result = consensus.run_consensus(workers, prompt)

        elapsed = time.time() - start_time

        return {
            'task_id': task['id'],
            'decision': result['decision'],
            'rounds': result.get('round', 0),
            'time': elapsed,
            'weights': {str(k): v for k, v in result.get('weights', {}).items()}
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            'task_id': task['id'],
            'decision': 'ERROR',
            'rounds': 0,
            'time': elapsed,
            'error': str(e)
        }


def run_experiment(
    n: int, f: int, s: int,
    tasks: List[Dict],
    byzantine_type: str = "random",
    num_rounds: int = 50,
    api_key: str = None
) -> Dict:
    """运行完整实验"""
    print(f"\n{'='*80}")
    print(f"实验配置")
    print(f"{'='*80}")
    print(f"  n={n}, f={f}, s={s}")
    print(f"  拜占庭类型: {byzantine_type} ({BYZANTINE_TYPES[byzantine_type]})")
    print(f"  任务数: {num_rounds}")
    print(f"  容错阈值: n >= 3f + s + 1 = {3*f + s + 1} ✓" if n >= 3*f + s + 1 else f"  容错阈值: n >= 3f + s + 1 = {3*f + s + 1} ⚠")
    print(f"{'='*80}")

    workers = create_workers(n, f, s, byzantine_type, api_key)
    # 优化视图切换：1 轮超时触发
    consensus = ConsensusLayer(n=n, f=f, s=s, view_change_timeout=1)

    results = {
        'accept': 0,
        'reject': 0,
        'manual': 0,
        'error': 0,
        'rounds': [],
        'times': [],
        'task_results': []
    }

    for i in range(num_rounds):
        task = tasks[i % len(tasks)]
        print(f"\n[任务 {i+1}/{num_rounds}] {task['id'][:30]}...", flush=True)

        outcome = run_single_task(consensus, workers, task)
        results['task_results'].append(outcome)

        decision = outcome['decision'].upper()
        if decision == 'ACCEPT':
            results['accept'] += 1
        elif decision == 'REJECT':
            results['reject'] += 1
        elif decision == 'ERROR':
            results['error'] += 1
        else:
            results['manual'] += 1

        results['rounds'].append(outcome['rounds'])
        results['times'].append(outcome['time'])

        status = "✅" if decision == 'ACCEPT' else "❌" if decision == 'REJECT' else "⚠️"
        print(f"  {status} {decision}, 轮次: {outcome['rounds']}, 耗时: {outcome['time']:.1f}s", flush=True)

        # 避免 API 限流
        if i < num_rounds - 1:
            time.sleep(0.5)

    return results


def print_summary(config: Dict, results: Dict):
    """打印实验总结"""
    total = results['accept'] + results['reject'] + results['manual'] + results['error']
    if total == 0:
        return

    print(f"\n{'='*80}")
    print(f"实验结果: n={config['n']}, f={config['f']}, s={config['s']}, 拜占庭={config['byzantine_type']}")
    print(f"{'='*80}")
    print(f"  Accept:   {results['accept']:>3} ({results['accept']/total*100:5.1f}%)")
    print(f"  Reject:   {results['reject']:>3} ({results['reject']/total*100:5.1f}%)")
    print(f"  Manual:   {results['manual']:>3} ({results['manual']/total*100:5.1f}%)")
    print(f"  Error:    {results['error']:>3} ({results['error']/total*100:5.1f}%)")

    if results['rounds']:
        avg_rounds = sum(results['rounds']) / len(results['rounds'])
        print(f"  平均轮次: {avg_rounds:.2f}")

    if results['times']:
        avg_time = sum(results['times']) / len(results['times'])
        print(f"  平均耗时: {avg_time:.1f}s/任务")

    print(f"{'='*80}")


def run_all_experiments(api_key: str = None):
    """运行所有实验配置"""
    print("="*80)
    print("A2A-BFT 扩展实验（HumanEval + 多种拜占庭攻击）")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # 实验配置 - 扩展到 100 轮，增加共谋攻击
    configs = [
        # 对照组
        {'n': 4, 'f': 0, 's': 0, 'byzantine_type': 'random', 'rounds': 100, 'desc': '对照组（无故障）'},
        # 最小 BFT
        {'n': 4, 'f': 1, 's': 0, 'byzantine_type': 'random', 'rounds': 100, 'desc': '最小 BFT (random)'},
        {'n': 4, 'f': 1, 's': 0, 'byzantine_type': 'strategic_reject', 'rounds': 100, 'desc': '最小 BFT (strategic_reject)'},
        {'n': 4, 'f': 1, 's': 0, 'byzantine_type': 'sybil_attack', 'rounds': 100, 'desc': '最小 BFT (sybil_attack)'},
        # 推荐配置
        {'n': 5, 'f': 1, 's': 1, 'byzantine_type': 'random', 'rounds': 100, 'desc': '推荐配置 (random)'},
        {'n': 5, 'f': 1, 's': 1, 'byzantine_type': 'strategic_reject', 'rounds': 100, 'desc': '推荐配置 (strategic_reject)'},
        # 超阈值
        {'n': 5, 'f': 2, 's': 0, 'byzantine_type': 'random', 'rounds': 100, 'desc': '超阈值 (random)'},
        {'n': 5, 'f': 2, 's': 0, 'byzantine_type': 'strategic_reject', 'rounds': 100, 'desc': '超阈值 (strategic_reject)'},
        # 共谋攻击 - 新增
        {'n': 5, 'f': 2, 's': 0, 'byzantine_type': 'collusion', 'rounds': 100, 'desc': '共谋攻击 (n=5,f=2)'},
        {'n': 6, 'f': 2, 's': 0, 'byzantine_type': 'collusion', 'rounds': 100, 'desc': '共谋攻击 (n=6,f=2)'},
    ]

    all_results = []

    for config in configs:
        # 获取随机任务
        tasks = get_random_tasks(config['rounds'])

        # 运行实验
        results = run_experiment(
            n=config['n'],
            f=config['f'],
            s=config['s'],
            tasks=tasks,
            byzantine_type=config['byzantine_type'],
            num_rounds=config['rounds'],
            api_key=api_key
        )

        config['results'] = results
        all_results.append(config)
        print_summary(config, results)

        # 保存中间结果
        save_results(all_results)

    # 最终汇总
    print_final_summary(all_results)

    return all_results


def save_results(all_results: List[Dict]):
    """保存实验结果"""
    output = {
        'timestamp': datetime.now().isoformat(),
        'configs': all_results
    }

    # 根据当前工作目录确定保存路径
    import os
    if os.path.exists('extended_experiment_results.json'):
        # 当前在experiments目录
        output_path = 'extended_experiment_results.json'
    else:
        # 从项目根目录运行
        output_path = 'experiments/extended_experiment_results.json'

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def print_final_summary(all_results: List[Dict]):
    """打印最终汇总"""
    print(f"\n{'='*80}")
    print("最终实验汇总")
    print(f"{'='*80}")

    print(f"\n{'配置':<30} {'接受率':<10} {'拒绝率':<10} {'平均轮次':<10} {'状态':<15}")
    print("-"*80)

    for config in all_results:
        n, f, s = config['n'], config['f'], config['s']
        btype = config['byzantine_type'][:15]
        r = config['results']
        total = r['accept'] + r['reject'] + r['manual'] + r['error']

        if total > 0:
            accept_rate = r['accept'] / total * 100
            reject_rate = r['reject'] / total * 100
            avg_rounds = sum(r['rounds']) / len(r['rounds']) if r['rounds'] else 0

            # 判断是否符合阈值
            if n >= 3*f + s + 1:
                status = "✓ 符合阈值"
            else:
                status = "⚠ 超阈值"

            label = f"n={n},f={f},s={s},{btype}"
            print(f"{label:<30} {accept_rate:>6.1f}%    {reject_rate:>6.1f}%    {avg_rounds:>8.2f}   {status}")

    print(f"{'='*80}")
    print(f"实验完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    # 设置 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        print("警告: 未设置 DEEPSEEK_API_KEY，将使用模拟模式")
        api_key = None

    run_all_experiments(api_key=api_key)
