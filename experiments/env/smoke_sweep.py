# -*- coding: utf-8 -*-
"""冒烟测试：每个数据集各跑 2 题 1 个配置，验证 vLLM 链路端到端可用"""
import sys
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
from multi_model_vllm import VLLMClient, MODEL_ENDPOINTS, load_dataset, check_vllm_health
from full_bft_sweep import A2ABFTSybil

v3.PARALLEL = 2
MODEL_KEYS = list(MODEL_ENDPOINTS.keys())
clients = {k: VLLMClient(k) for k in MODEL_KEYS}

health = check_vllm_health()
print('health:', health)
assert all(health.values()), f'vLLM 未就绪: {health}'

for ds in ['gsm8k', 'mbpp', 'mmlu']:
    tt = 'code' if ds == 'mbpp' else ('knowledge' if ds == 'mmlu' else 'math')
    data = load_dataset(ds)
    for t in data:
        if 'question' not in t:
            t['question'] = t.get('description', '')
    import random
    random.seed(42)
    tasks = random.sample(data, 2)
    layer = A2ABFTSybil(4, 1, 0)
    row = v3.evaluate('A2A-BFT', lambda ws, t: layer.run(ws, t), tasks,
                      4, 1, 0, 'strategic_reject', clients,
                      MODEL_KEYS[:4] if len(MODEL_KEYS) >= 4 else MODEL_KEYS, tt)
    print(f"[SMOKE {ds}] 决策={row['decision_rate']}% 正确={row['answer_accuracy']}% "
          f"错误提交={row['wrong_commit_rate']}% 轮数={row['avg_rounds']} 调用={row['avg_calls']} "
          f"耗时/题={row['avg_time']}s")
print('SMOKE_OK')
