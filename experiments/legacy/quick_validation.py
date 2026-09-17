"""
A2A-BFT 快速验证脚本
运行关键实验配置，生成基础结果用于论文
"""

import sys
import os
import time
import json
import random
import statistics
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import DeepSeekWorker, ConsensusLayer


def run_key_experiments():
    """运行关键实验配置"""

    # 关键实验配置（从评审意见中提取的关键场景）
    key_configs = [
        # 原核心配置（增加轮次）
        {'n': 5, 'f': 1, 's': 1, 'attack': 'random', 'rounds': 200, 'seed': 42, 'desc': '推荐配置-random'},
        {'n': 5, 'f': 1, 's': 1, 'attack': 'strategic_reject', 'rounds': 200, 'seed': 43, 'desc': '推荐配置-strategic_reject'},
        {'n': 6, 'f': 2, 's': 0, 'attack': 'collusion', 'rounds': 200, 'seed': 44, 'desc': '安全配置-collusion'},

        # 新攻击类型
        {'n': 5, 'f': 1, 's': 1, 'attack': 'adaptive_rejection', 'rounds': 150, 'seed': 101, 'desc': '新攻击-自适应拒绝'},
        {'n': 5, 'f': 1, 's': 1, 'attack': 'malicious_primary', 'rounds': 150, 'seed': 102, 'desc': '新攻击-恶意Primary'},
        {'n': 5, 'f': 1, 's': 1, 'attack': 'insider_attack', 'rounds': 150, 'seed': 103, 'desc': '新攻击-内部攻击'},
        {'n': 5, 'f': 1, 's': 1, 'attack': 'chaotic', 'rounds': 150, 'seed': 104, 'desc': '新攻击-混沌攻击'},

        # 规模扩展
        {'n': 8, 'f': 2, 's': 1, 'attack': 'random', 'rounds': 150, 'seed': 201, 'desc': '规模扩展-n=8'},
        {'n': 8, 'f': 2, 's': 1, 'attack': 'strategic_reject', 'rounds': 150, 'seed': 202, 'desc': '规模扩展-n=8-strategic'},
        {'n': 10, 'f': 3, 's': 1, 'attack': 'random', 'rounds': 150, 'seed': 203, 'desc': '规模扩展-n=10'},
        {'n': 10, 'f': 3, 's': 1, 'attack': 'collusion', 'rounds': 150, 'seed': 204, 'desc': '规模扩展-n=10-collusion'},

        # 任务难度（简化版）
        {'n': 5, 'f': 1, 's': 1, 'attack': 'random', 'rounds': 100, 'seed': 301, 'desc': '难度-easy'},
        {'n': 5, 'f': 1, 's': 1, 'attack': 'random', 'rounds': 100, 'seed': 302, 'desc': '难度-hard'},
    ]

    print("="*80)
    print("A2A-BFT 扩展实验 - 快速验证版")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"实验配置数: {len(key_configs)}")
    print("="*80)

    all_results = []
    start_total = time.time()

    for i, config in enumerate(key_configs, 1):
        print(f"\n[{i}/{len(key_configs)}] {config['desc']}")
        print(f"  配置: n={config['n']}, f={config['f']}, s={config['s']}, attack={config['attack']}")

        try:
            result = run_single_experiment(config)
            all_results.append(result)

            # 打印摘要
            total = result['accept'] + result['reject'] + result['pending'] + result['error']
            accept_rate = result['accept'] / total * 100 if total > 0 else 0
            print(f"  结果: Accept={result['accept']}/{total} ({accept_rate:.1f}%), "
                  f"Rounds={result.get('avg_rounds', 0):.2f}")

        except Exception as e:
            print(f"  错误: {e}")
            all_results.append({
                'config': config,
                'error': str(e),
                'accept': 0,
                'reject': 0,
                'pending': 0,
                'error': 1,
                'avg_rounds': 0
            })

    # 计算总时间
    total_time = time.time() - start_total

    # 保存结果
    output_path = save_results(all_results, total_time)

    # 生成汇总报告
    generate_summary_report(all_results, output_path)

    print(f"\n{'='*80}")
    print(f"实验完成! 总耗时: {total_time/60:.1f}分钟")
    print(f"结果保存: {output_path}")
    print(f"{'='*80}")

    return all_results, output_path


def run_single_experiment(config: Dict) -> Dict:
    """运行单个实验"""
    random.seed(config['seed'])

    n, f, s = config['n'], config['f'], config['s']
    attack_type = config['attack']
    num_rounds = config['rounds']

    # 创建workers
    workers = []
    byzantine_count = 0
    soft_fault_count = 0

    for i in range(n):
        if byzantine_count < f:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.3,
                byzantine_type=attack_type,
                seed=config['seed'] + i
            )
            worker.is_byzantine = True
            byzantine_count += 1
        elif soft_fault_count < s:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.6,
                seed=config['seed'] + f + i
            )
            worker.is_soft_fault = True
            soft_fault_count += 1
        else:
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=0.9,
                seed=config['seed'] + f + s + i
            )
        workers.append(worker)

    # 创建共识层
    consensus = ConsensusLayer(n=n, f=f, s=s, view_change_timeout=1)

    # 运行实验
    results = {
        'accept': 0,
        'reject': 0,
        'pending': 0,
        'error': 0,
        'rounds': [],
        'times': [],
        'failure_cases': []
    }

    start_time = time.time()

    for i in range(num_rounds):
        # 生成测试问题
        question = generate_test_question(i, config.get('difficulty', 'all'))

        task_start = time.time()
        try:
            result = consensus.run_consensus(workers, question)
            elapsed = time.time() - task_start

            decision = result.get('decision', 'ERROR').upper()
            rounds = result.get('round', 0)

            if decision == 'ACCEPT':
                results['accept'] += 1
            elif decision == 'REJECT':
                results['reject'] += 1
                if len(results['failure_cases']) < 10:
                    results['failure_cases'].append({
                        'task_index': i,
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
                print(f"    进度: {i+1}/{num_rounds} ({(i+1)/num_rounds*100:.1f}%)", flush=True)

        except Exception as e:
            elapsed = time.time() - task_start
            results['error'] += 1
            results['times'].append(elapsed)

        # 避免API限流
        if i < num_rounds - 1:
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
    results['config'] = config

    return results


def generate_test_question(index: int, difficulty: str = 'all') -> str:
    """生成测试问题"""
    if difficulty == 'easy':
        return f"Calculate: {(index+1)*11} + {(index+1)*22} = ?"
    elif difficulty == 'hard':
        return f"如果 f(n) = n² + 2n + 1, 计算 f({index+10}) 的值"
    else:
        # 混合难度
        if index % 3 == 0:
            return f"Calculate: {(index+1)*11} + {(index+1)*22} = ?"
        elif index % 3 == 1:
            return f"Write a Python function to compute factorial of {index+5}"
        else:
            return f"如果 f(n) = n² + 2n + 1, 计算 f({index+10}) 的值"


def save_results(results: List[Dict], total_time: float) -> str:
    """保存实验结果"""
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_time': total_time,
        'num_experiments': len(results),
        'results': results
    }

    output_path = os.path.join(
        os.path.dirname(__file__),
        f'quick_validation_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output_path


def generate_summary_report(results: List[Dict], output_path: str):
    """生成汇总报告"""
    report = []
    report.append("# A2A-BFT 扩展实验汇总报告")
    report.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"实验总数: {len(results)}")
    report.append("")

    # 按配置类型分组统计
    report.append("## 实验结果汇总")
    report.append("")
    report.append("| 配置 | 描述 | 接受率 | 平均轮次 | 状态 |")
    report.append("|------|------|--------|----------|------|")

    for r in results:
        config = r.get('config', {})
        total = r['accept'] + r['reject'] + r['pending'] + r['error']
        accept_rate = r['accept'] / total * 100 if total > 0 else 0
        avg_rounds = r.get('avg_rounds', 0)

        # 判断是否符合BFT阈值
        n, f, s = config.get('n', 0), config.get('f', 0), config.get('s', 0)
        if n >= 3*f + s + 1:
            status = "✓ 符合阈值"
        else:
            status = "⚠ 超阈值"

        report.append(f"| n={config.get('n', '-')}, f={config.get('f', '-')}, s={config.get('s', '-')} "
                     f"| {config.get('desc', '-')} "
                     f"| {accept_rate:.1f}% "
                     f"| {avg_rounds:.2f} "
                     f"| {status} |")

    report.append("")
    report.append(f"详细结果已保存到: {output_path}")

    # 保存报告
    report_path = output_path.replace('.json', '_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))

    print(f"\n汇总报告已保存: {report_path}")


if __name__ == "__main__":
    results, output_path = run_key_experiments()
