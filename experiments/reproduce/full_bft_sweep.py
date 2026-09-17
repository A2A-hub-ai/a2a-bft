# -*- coding: utf-8 -*-
"""
A2A-BFT 全量真机扫描：补齐此前仅存在于 SimulatedWorker 模拟中的全部配置
- 基线: n=4/6, f=0, s=0            （n=5 baseline 已有真机数据）
- 攻击: n=4,f=1 (random/strategic/sybil)
        n=5,f=1,s=1 (random)
        n=5,f=2 (random/strategic/collusion)  [低于安全边界 3f+s+1，仅经验观察]
        n=6,f=2 (collusion)
- 数据集: gsm8k + mbpp + mmlu, 种子 42/43/44/45/46, 每格 50 任务
- 仅 A2A-BFT 主算法（与 multi_model_compare_ablation_v3 的 A2ABFT 完全一致，
  保证与已有 48 行聚合数据同口径）；sybil_attack 用 REJECT-heavy 语义
用法: python full_bft_sweep.py gsm8k|mbpp|mmlu
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
import multi_model_compare_ablation_v3 as v3
from multi_model_vllm import VLLMClient, MODEL_ENDPOINTS, load_dataset

RESULTS_DIR = A2A_RESULTS
os.makedirs(RESULTS_DIR, exist_ok=True)
v3.PARALLEL = 8                      # 提高并发吞吐
SEEDS = [42, 43, 44, 45, 46]
TASKS = 50

SCENARIOS = [
    {'n': 4, 'f': 0, 's': 0, 'attack': None},                # baseline
    {'n': 6, 'f': 0, 's': 0, 'attack': None},                # baseline
    {'n': 4, 'f': 1, 's': 0, 'attack': 'random'},
    {'n': 4, 'f': 1, 's': 0, 'attack': 'strategic_reject'},
    {'n': 4, 'f': 1, 's': 0, 'attack': 'sybil_attack'},
    {'n': 5, 'f': 1, 's': 1, 'attack': 'random'},
    {'n': 5, 'f': 2, 's': 0, 'attack': 'random'},            # 越界配置(†)
    {'n': 5, 'f': 2, 's': 0, 'attack': 'strategic_reject'},  # 越界配置(†)
    {'n': 5, 'f': 2, 's': 0, 'attack': 'collusion'},         # 越界配置(†)
    {'n': 6, 'f': 2, 's': 0, 'attack': 'collusion'},
]


class A2ABFTSybil(v3.A2ABFT):
    """Sybil 攻击语义：女巫节点伪装成正常求解（honest solve），
    投票阶段以否决为主（75% REJECT），对应协议重跑脚本的 REJECT-heavy 设定"""

    def _validate(self, w, task, proposal, primary_is_byzantine):
        if w.is_byzantine:
            return 'REJECT' if random.random() < 0.75 else 'ACCEPT'
        return super()._validate(w, task, proposal, primary_is_byzantine)


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else 'gsm8k'
    assert ds in ('gsm8k', 'mbpp', 'mmlu'), ds
    task_type = 'code' if ds == 'mbpp' else ('knowledge' if ds == 'mmlu' else 'math')

    print('=' * 78)
    print(f'A2A-BFT 全量真机扫描 dataset={ds} (seeds {SEEDS}, {TASKS} tasks x '
          f'{len(SCENARIOS)} configs)')
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('=' * 78, flush=True)

    MODEL_KEYS = list(MODEL_ENDPOINTS.keys())
    clients = {k: VLLMClient(k) for k in MODEL_KEYS}

    data = load_dataset(ds)
    for t in data:
        if 'question' not in t:
            t['question'] = t.get('description', '')

    out = os.path.join(RESULTS_DIR, f'full_bft_sweep_{ds}.json')
    rows = []
    if os.path.exists(out):            # 断点续跑
        rows = json.load(open(out, encoding='utf-8'))['rows']
        done = {(r['n'], r['f'], r['s'], r['attack'], r['seed']) for r in rows}
        print(f'断点续跑: 已有 {len(rows)} 行', flush=True)
    else:
        done = set()

    for seed in SEEDS:
        # 与 multiseed 相同的任务抽样：同种子同任务集，保证跨配置可比
        random.seed(seed)
        tasks = random.sample(data, min(TASKS, len(data)))
        for sc in SCENARIOS:
            n, f, s, atk = sc['n'], sc['f'], sc['s'], sc['attack']
            key = (n, f, s, atk or 'baseline', seed)
            if key in done:
                print(f'跳过已完成 {key}', flush=True)
                continue
            assignment = [MODEL_KEYS[i % len(MODEL_KEYS)] for i in range(n)]
            layer = A2ABFTSybil(n, f, s)
            runner = lambda ws, t, _L=layer: _L.run(ws, t)
            print(f"\n# seed={seed}  {ds}({task_type})  n={n},f={f},s={s},"
                  f"attack={atk or 'baseline'}", flush=True)
            row = v3.evaluate('A2A-BFT', runner, tasks, n, f, s, atk,
                              clients, assignment, task_type)
            row.update({'dataset': ds, 'seed': seed,
                        'attack_raw': atk or 'baseline'})
            rows.append(row)
            print(f"  决策={row['decision_rate']:5.1f}% 正确={row['answer_accuracy']:5.1f}% "
                  f"错误提交={row['wrong_commit_rate']:5.1f}% 轮数={row['avg_rounds']:.2f} "
                  f"调用={row['avg_calls']:.1f} 耗时/题={row['avg_time']:.0f}s", flush=True)
            with open(out, 'w', encoding='utf-8') as fp:
                json.dump({'timestamp': datetime.now().isoformat(),
                           'models': {k: v['name'] for k, v in MODEL_ENDPOINTS.items()},
                           'seeds': SEEDS, 'tasks_per_seed': TASKS, 'rows': rows},
                          fp, ensure_ascii=False, indent=2)

    print(f'\n完成: {out}  共 {len(rows)} 行', flush=True)
    print(f'SWEEP_DONE_{ds.upper()}')


if __name__ == '__main__':
    main()
