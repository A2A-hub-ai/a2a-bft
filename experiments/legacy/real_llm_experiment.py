"""
A2A-BFT 真实 LLM 实验
使用 DeepSeek API 进行批量评估
"""

import sys
import os
import time
from typing import List, Dict

# 自定位项目根（原为相对路径 'src'，依赖当前工作目录）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, 'experiments', 'src'))

# API Key 从环境变量读取（原为硬编码密钥，已移除）
if not os.environ.get('DEEPSEEK_API_KEY'):
    print('错误: 请先设置环境变量 DEEPSEEK_API_KEY')
    sys.exit(1)

from a2a_bft.deepseek_worker import DeepSeekWorker, ConsensusLayer


def create_workers(n: int, f: int, s: int) -> List[DeepSeekWorker]:
    """创建 Worker 集合"""
    workers = []
    byzantine_count = 0
    soft_fault_count = 0

    for i in range(n):
        if byzantine_count < f:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.3,
                byzantine_type='random',
                api_key=os.environ.get('DEEPSEEK_API_KEY')
            )
            worker.is_byzantine = True
            print(f"  Worker {i}: 拜占庭 (accuracy=0.3)", flush=True)
            byzantine_count += 1
        elif soft_fault_count < s:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.6,
                api_key=os.environ.get('DEEPSEEK_API_KEY')
            )
            worker.is_soft_fault = True
            print(f"  Worker {i}: 软故障 (accuracy=0.6)", flush=True)
            soft_fault_count += 1
        else:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.9,
                api_key=os.environ.get('DEEPSEEK_API_KEY')
            )
            print(f"  Worker {i}: 诚实 (accuracy=0.9)", flush=True)
        workers.append(worker)

    return workers


def run_single_task(consensus: ConsensusLayer, workers: List[DeepSeekWorker], task: str) -> Dict:
    """运行单个任务"""
    start_time = time.time()
    try:
        result = consensus.run_consensus(workers, task)
        elapsed = time.time() - start_time
        return {
            'decision': result['decision'],
            'rounds': result['round'],
            'time': elapsed,
            'weights': result['weights']
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            'decision': 'ERROR',
            'rounds': 0,
            'time': elapsed,
            'error': str(e)
        }


def run_experiment(
    n: int, f: int, s: int,
    tasks: List[str],
    tasks_per_config: int = 5
) -> Dict:
    """运行完整实验"""
    print(f"\n{'='*70}")
    print(f"配置: n={n}, f={f}, s={s}")
    print(f"任务数: {tasks_per_config}")
    print(f"{'='*70}")

    workers = create_workers(n, f, s)
    consensus = ConsensusLayer(n=n, f=f, s=s)

    results = {
        'accept': 0,
        'reject': 0,
        'manual': 0,
        'error': 0,
        'rounds': [],
        'times': []
    }

    for i in range(tasks_per_config):
        task = tasks[i % len(tasks)]
        print(f"\n[任务 {i+1}/{tasks_per_config}] {task[:50]}...", flush=True)

        outcome = run_single_task(consensus, workers, task)

        decision = outcome['decision'].lower()
        if decision in results:
            results[decision] += 1
        results['rounds'].append(outcome['rounds'])
        results['times'].append(outcome['time'])

        print(f"  结果: {outcome['decision']}, 轮次: {outcome['rounds']}, 耗时: {outcome['time']:.1f}s", flush=True)

    return results


def print_summary(config: Dict, results: Dict):
    """打印实验总结"""
    total = results['accept'] + results['reject'] + results['manual'] + results['error']
    if total == 0:
        return

    print(f"\n{'='*70}")
    print(f"实验结果: {config['n']}, f={config['f']}, s={config['s']}")
    print(f"{'='*70}")
    print(f"Accept:   {results['accept']:>3} ({results['accept']/total*100:5.1f}%)")
    print(f"Reject:   {results['reject']:>3} ({results['reject']/total*100:5.1f}%)")
    print(f"Manual:   {results['manual']:>3} ({results['manual']/total*100:5.1f}%)")
    print(f"Error:    {results['error']:>3} ({results['error']/total*100:5.1f}%)")

    if results['rounds']:
        avg_rounds = sum(results['rounds']) / len(results['rounds'])
        print(f"平均轮次: {avg_rounds:.2f}")

    if results['times']:
        avg_time = sum(results['times']) / len(results['times'])
        print(f"平均耗时: {avg_time:.1f}s/任务")

    print(f"{'='*70}")


def main():
    """主函数"""
    print("="*70)
    print("A2A-BFT 真实 LLM 实验（DeepSeek）")
    print("="*70)

    # 实验任务
    tasks = [
        "用Python写一个计算斐波那契数列第n项的函数",
        "用Python实现快速排序算法",
        "修复这个bug: def add(x,y): return x - y (应该返回x+y)",
        "用Python实现二分查找算法",
        "用Python写一个计算字符串逆序的函数",
        "用Python实现一个简单的栈数据结构",
    ]

    # 实验配置
    configs = [
        {'n': 4, 'f': 0, 's': 0, 'desc': '对照组（无故障）'},
        {'n': 4, 'f': 1, 's': 0, 'desc': '最小 BFT 配置'},
        {'n': 5, 'f': 1, 's': 1, 'desc': '推荐配置'},
        {'n': 5, 'f': 2, 's': 0, 'desc': '超阈值测试'},
    ]

    all_results = []

    for config in configs:
        results = run_experiment(
            n=config['n'],
            f=config['f'],
            s=config['s'],
            tasks=tasks,
            tasks_per_config=5
        )
        config['results'] = results
        all_results.append(config)
        print_summary(config, results)
        time.sleep(1)  # 避免 API 限流

    # 生成对比表
    print(f"\n{'='*80}")
    print("实验对比汇总")
    print(f"{'='*80}")
    print(f"{'配置':<20} {'接受率':<10} {'拒绝率':<10} {'平均轮次':<10} {'平均耗时':<10}")
    print("-"*80)

    for config in all_results:
        n, f, s = config['n'], config['f'], config['s']
        r = config['results']
        total = r['accept'] + r['reject'] + r['manual'] + r['error']
        if total > 0:
            accept_rate = r['accept'] / total * 100
            reject_rate = r['reject'] / total * 100
            avg_rounds = sum(r['rounds']) / len(r['rounds']) if r['rounds'] else 0
            avg_time = sum(r['times']) / len(r['times']) if r['times'] else 0
            print(f"n={n},f={f},s={s:<1}   {accept_rate:>6.1f}%    {reject_rate:>6.1f}%    {avg_rounds:>8.2f}    {avg_time:>8.1f}s")

    print(f"{'='*80}")
    print("实验完成！")


if __name__ == "__main__":
    main()
