# -*- coding: utf-8 -*-
"""MBPP 代码管线冒烟测试：4模型各解1题 + 测试执行 + 判定 + 拜占庭篡改验证"""
import sys, random
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
from multi_model_vllm import (VLLMClient, MultiModelWorker, MODEL_ENDPOINTS,
                              load_dataset, extract_code, run_code_tests, code_tamper)

data = load_dataset('mbpp')
for t in data:
    t.setdefault('question', t.get('description', ''))
random.seed(42)
tasks = random.sample(data, 2)

clients = {k: VLLMClient(k) for k in MODEL_ENDPOINTS}
keys = list(MODEL_ENDPOINTS.keys())

for ti, task in enumerate(tasks):
    print(f"\n===== 任务 {task['id']}: {task['question'][:80]}")
    print(f"  测试: {task['test_list'][:2]}")
    for mi, k in enumerate(keys):
        w = MultiModelWorker(worker_id=mi, client=clients[k], task_type='code')
        ans, conf = w.solve(task)
        code = extract_code(ans) if ans else ''
        pat = run_code_tests(code, task['test_list']) if code else []
        print(f"  [{k:8s}] 正确={''.join('T' if p else 'F' for p in pat)} 代码前60字: {code[:60]!r}")
        # 篡改验证（仅第1个任务的第1个模型）
        if ti == 0 and mi == 0:
            tam = code_tamper(code)
            pat2 = run_code_tests(tam, task['test_list'])
            print(f"  [篡改后  ] 正确={''.join('T' if p else 'F' for p in pat2)} (应全F)")
    # judge 验证：用正确代码提案
    w = MultiModelWorker(worker_id=0, client=clients[keys[0]], task_type='code')
    v = w._judge(task, tasks[0].get('code', 'def f():\n    pass'))
    print(f"  [judge] 对参考代码裁决: {v}")

print('\nSMOKE_OK')
