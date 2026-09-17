# -*- coding: utf-8 -*-
"""
4模型异构多种子实验：seed 43/44（seed 42 复用已有 v2/v3 结果）
GSM8K + MBPP 各 3 场景 × 8 方法 × 30 任务 × 2 新种子 = 2880 任务运行
MBPP 的 LLM-Debate 使用修复版（llm_debate_code），与 seed42 补丁口径一致
"""
import os
import sys
import json
import random
from datetime import datetime

# --- 自定位项目根（原为硬编码服务器路径，换机器或换目录即失效）---
import os
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while not os.path.exists(os.path.join(_ROOT, ".a2a_project_root")) and os.path.dirname(_ROOT) != _ROOT:
    _ROOT = os.path.dirname(_ROOT)
# 依次加入：脚本自身目录、共享实验模块目录（reproduce/）、src/（a2a_bft 包）
for _d in (os.path.join(_ROOT, "experiments", "reproduce"),
           os.path.join(_ROOT, "experiments", "src"),
           _HERE):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)
A2A_RESULTS = os.environ.get("A2A_RESULTS_DIR", os.path.join(_ROOT, "experiments", "results"))
A2A_DATASETS = os.environ.get("A2A_DATASET_DIR", os.path.join(_ROOT, "experiments", "datasets"))
A2A_MODELS = os.environ.get("A2A_MODEL_DIR", "/autodl-fs/data/models")
from multi_model_vllm import VLLMClient, MODEL_ENDPOINTS, load_dataset
from multi_model_compare_ablation_v3 import (A2ABFT, evaluate, simple_majority,
                                             weighted_majority, a2a_sim)
from mbpp_debate_fix import llm_debate_code

RESULTS_DIR = A2A_RESULTS
os.makedirs(RESULTS_DIR, exist_ok=True)
SEEDS = [43, 44]
TASKS = 30

VARIANTS = [
    ('A2A-BFT', lambda n, f, s: A2ABFT(n, f, s)),
    ('A2A-BFT w/o 视图切换', lambda n, f, s: A2ABFT(n, f, s, use_view_change=False)),
    ('A2A-BFT w/o 语义验证', lambda n, f, s: A2ABFT(n, f, s, semantic_validation=False)),
    ('A2A-BFT 固定阈值', lambda n, f, s: A2ABFT(n, f, s, dynamic_threshold=False)),
]


def main():
    print('=' * 78)
    print('4模型异构多种子实验 (seeds 43/44, 30 tasks x 6 scenarios x 8 methods)')
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('=' * 78, flush=True)

    MODEL_KEYS = list(MODEL_ENDPOINTS.keys())
    clients = {k: VLLMClient(k) for k in MODEL_KEYS}

    scenarios = [
        {'dataset': 'gsm8k', 'n': 5, 'f': 0, 's': 0, 'attack': None},
        {'dataset': 'gsm8k', 'n': 5, 'f': 1, 's': 1, 'attack': 'strategic_reject'},
        {'dataset': 'gsm8k', 'n': 8, 'f': 2, 's': 1, 'attack': 'collusion'},
        {'dataset': 'mbpp', 'n': 5, 'f': 0, 's': 0, 'attack': None},
        {'dataset': 'mbpp', 'n': 5, 'f': 1, 's': 1, 'attack': 'strategic_reject'},
        {'dataset': 'mbpp', 'n': 8, 'f': 2, 's': 1, 'attack': 'collusion'},
    ]

    all_rows = []
    out = os.path.join(RESULTS_DIR, 'multi_model_multiseed.json')

    for seed in SEEDS:
        for sc in scenarios:
            ds, n, f, s, atk = sc['dataset'], sc['n'], sc['f'], sc['s'], sc['attack']
            task_type = 'code' if ds == 'mbpp' else 'math'
            data = load_dataset(ds)
            for t in data:
                if 'question' not in t:
                    t['question'] = t.get('description', '')
            random.seed(seed)
            tasks = random.sample(data, min(TASKS, len(data)))
            assignment = [MODEL_KEYS[i % len(MODEL_KEYS)] for i in range(n)]

            baselines = [
                ('Simple Majority', lambda ws, t: simple_majority(ws, t, task_type)),
                ('Weighted Majority', lambda ws, t: weighted_majority(ws, t, task_type)),
                ('A2A-Sim', lambda ws, t: a2a_sim(ws, t, task_type)),
                ('LLM-Debate', (lambda ws, t: llm_debate_code(ws, t)) if task_type == 'code'
                               else (lambda ws, t: llm_debate_math(ws, t))),
            ]

            print(f"\n{'#'*78}")
            print(f"# seed={seed}  {ds}({task_type})  n={n}, f={f}, s={s}, attack={atk or 'baseline'}")
            print(f"{'#'*78}", flush=True)

            def emit(name, runner):
                row = evaluate(name, runner, tasks, n, f, s, atk, clients, assignment, task_type)
                row['dataset'] = ds
                row['seed'] = seed
                all_rows.append(row)
                print(f"  {name:26s} 决策={row['decision_rate']:5.1f}% 正确={row['answer_accuracy']:5.1f}% "
                      f"错误提交={row['wrong_commit_rate']:5.1f}% 轮数={row['avg_rounds']:.2f} "
                      f"调用={row['avg_calls']:.1f} 耗时/题={row['avg_time']:.0f}s", flush=True)

            for name, factory in VARIANTS:
                layer = factory(n, f, s)
                emit(name, lambda ws, t, _L=layer: _L.run(ws, t))
            for name, fn in baselines:
                emit(name, fn)

            with open(out, 'w', encoding='utf-8') as fp:
                json.dump({'timestamp': datetime.now().isoformat(),
                           'models': {k: v['name'] for k, v in MODEL_ENDPOINTS.items()},
                           'rows': all_rows}, fp, ensure_ascii=False, indent=2)

    print(f'\n结果已保存: {out}  共 {len(all_rows)} 行', flush=True)
    print('MULTISEED_DONE')


def llm_debate_math(ws, t):
    from multi_model_compare_ablation_v3 import llm_debate
    return llm_debate(ws, t, 'math', rounds=2)


if __name__ == '__main__':
    main()
