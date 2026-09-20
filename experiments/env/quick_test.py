# -*- coding: utf-8 -*-
"""快速验证：新语义验证 + 视图切换修复是否生效（小样本）"""
import random, sys, time
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
import multi_model_vllm as m

assign = ['llama', 'internlm', 'deepseek', 'qwen', 'llama']

cases = [
    ('gsm8k', 5, 0, 0, None, ['llama', 'internlm', 'deepseek', 'qwen', 'llama']),
    ('gsm8k', 5, 1, 1, 'strategic_reject', ['llama', 'internlm', 'deepseek', 'qwen', 'llama']),
]

for i, (ds, n, f, s, atk, asg) in enumerate(cases):
    # 逐用例播种：协议实现里软故障注入等策略取全局 random（v3._validate 的
    # `random.random() < 0.3`），不播种则同一用例两次运行的投票流不同——
    # 2026-09-20 实测：f=0,s=0 用例逐字段复现，f=1,s=1 用例 80%/75% → 100%/80%。
    # 已发布的 sweep 驱动本身逐 seed 播种（full_bft_sweep.py:98 / multi_model_multiseed.py:75），
    # 本入口与之一致；播种后同一用例跨运行逐字段可比。
    random.seed(42 + i)
    t0 = time.time()
    r = m.run_experiment(ds, n, f, s, atk, num_tasks=5, model_assignment=asg)
    print(f'RESULT ds={ds} n={n} f={f} s={s} atk={atk} '
          f'consensus={r["consensus_rate"]:.0f}% correct={r["correctness_rate"]:.0f}% '
          f'rounds={r["avg_rounds"]:.2f} dist={r["vote_distribution"]} '
          f'stats={r["vote_stats"]} elapsed={time.time()-t0:.0f}s', flush=True)
print('QUICK_TEST_DONE')
