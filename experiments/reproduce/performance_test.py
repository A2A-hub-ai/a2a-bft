"""
A2A-BFT 性能测试脚本
测试TPS和延迟
"""

import sys
import os
import time
import statistics
import json
from datetime import datetime
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import ConsensusLayer, DeepSeekWorker


def run_performance_test(n: int, f: int, s: int, num_tasks: int = 20, api_key: str = None) -> Dict:
    """运行性能测试"""
    workers = []
    for i in range(n):
        if i < f:
            w = DeepSeekWorker(worker_id=i, byzantine_type='random', accuracy=0.3, api_key=api_key)
            w.is_byzantine = True
        elif i < f + s:
            w = DeepSeekWorker(worker_id=i, accuracy=0.6, api_key=api_key)
            w.is_soft_fault = True
        else:
            w = DeepSeekWorker(worker_id=i, accuracy=0.9, api_key=api_key)
        workers.append(w)
    
    consensus = ConsensusLayer(n=n, f=f, s=s, view_change_timeout=1)
    
    times = []
    rounds_list = []
    accept_count = 0
    reject_count = 0
    manual_count = 0
    
    for i in range(num_tasks):
        question = f'计算 {(i+1)*1111} * {(i+1)*2222} = ?'
        start = time.time()
        result = consensus.run_consensus(workers, question)
        elapsed = time.time() - start
        
        times.append(elapsed)
        rounds_list.append(result['round'])
        
        if result['decision'] == 'ACCEPT':
            accept_count += 1
        elif result['decision'] == 'REJECT':
            reject_count += 1
        else:
            manual_count += 1
    
    # 计算性能指标
    avg_time = statistics.mean(times)
    median_time = statistics.median(times)
    min_time = min(times)
    max_time = max(times)
    p95_time = sorted(times)[int(len(times) * 0.95)] if len(times) >= 20 else max_time
    
    tps = num_tasks / sum(times) if sum(times) > 0 else 0
    
    return {
        'n': n,
        'f': f,
        's': s,
        'num_tasks': num_tasks,
        'accept_count': accept_count,
        'reject_count': reject_count,
        'manual_count': manual_count,
        'accept_rate': accept_count / num_tasks * 100,
        'avg_time': avg_time,
        'median_time': median_time,
        'min_time': min_time,
        'max_time': max_time,
        'p95_time': p95_time,
        'tps': tps,
        'avg_rounds': statistics.mean(rounds_list),
        'total_time': sum(times)
    }


def print_performance_report(results: List[Dict]):
    """打印性能报告"""
    print('='*100)
    print('A2A-BFT 性能测试结果')
    print('='*100)
    print()
    print(f'{'配置':<25} {'接受率':<10} {'平均耗时':<12} {'中位耗时':<12} {'P95耗时':<12} {'TPS':<10} {'平均轮次':<10}')
    print('-'*100)
    
    for r in results:
        config = f"n={r['n']},f={r['f']},s={r['s']}"
        print(f'{config:<25} {r["accept_rate"]:>6.1f}%    {r["avg_time"]*1000:>8.1f}ms   {r["median_time"]*1000:>8.1f}ms   {r["p95_time"]*1000:>8.1f}ms   {r["tps"]:>6.2f}    {r["avg_rounds"]:>8.2f}')
    
    print('='*100)
    print()
    
    # 分析
    print('性能分析:')
    for r in results:
        print(f'  {r["n"]},{r["f"]},{r["s"]}:')
        print(f'    - 平均延迟: {r["avg_time"]*1000:.1f}ms')
        print(f'    - P95延迟: {r["p95_time"]*1000:.1f}ms')
        print(f'    - 吞吐量: {r["tps"]:.2f} TPS')
        print(f'    - 平均轮次: {r["avg_rounds"]:.2f}')
    print()


if __name__ == '__main__':
    print('A2A-BFT 性能测试')
    print('='*100)
    
    # 测试配置
    configs = [
        {'n': 4, 'f': 0, 's': 0, 'desc': '对照组'},
        {'n': 5, 'f': 1, 's': 1, 'desc': '推荐配置'},
        {'n': 6, 'f': 2, 's': 0, 'desc': '安全配置'},
    ]
    
    results = []
    
    for config in configs:
        print(f'\\n测试: {config["desc"]} (n={config["n"]}, f={config["f"]}, s={config["s"]})')
        print('-'*100)
        
        result = run_performance_test(
            n=config['n'],
            f=config['f'],
            s=config['s'],
            num_tasks=20
        )
        results.append(result)
        
        print(f'  接受率: {result["accept_count"]}/20 ({result["accept_rate"]:.1f}%)')
        print(f'  平均耗时: {result["avg_time"]*1000:.1f}ms')
        print(f'  中位耗时: {result["median_time"]*1000:.1f}ms')
        print(f'  P95耗时: {result["p95_time"]*1000:.1f}ms')
        print(f'  TPS: {result["tps"]:.2f}')
        print(f'  平均轮次: {result["avg_rounds"]:.2f}')
    
    # 生成报告
    print_performance_report(results)
    
    # 保存结果
    output = {
        'timestamp': datetime.now().isoformat(),
        'test_type': 'performance',
        'results': results
    }
    
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results', 'performance_test_results.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f'结果已保存到: {output_path}')
