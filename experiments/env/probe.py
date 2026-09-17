# -*- coding: utf-8 -*-
"""探针：难度分布 + 在「简单子集/随机子集」上测 求解正确率 与 验证可靠性 p_h（并行加速）"""
import sys, random, collections
from concurrent.futures import ThreadPoolExecutor
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

random.seed(42)
ds = m.load_dataset('gsm8k')
print('总样本:', len(ds))
print('字段:', list(ds[0].keys()))
print('难度分布:', dict(collections.Counter(str(t.get('difficulty')) for t in ds)))

models = ['llama', 'internlm', 'deepseek', 'qwen']
clients = {k: m.VLLMClient(k) for k in models}


def acc(a, b):
    return a is not None and b is not None and abs(a - b) < 1e-6


def eval_group(name, tasks):
    def one(args):
        k, t = args
        w = m.MultiModelWorker(0, clients[k], task_type='math')
        ans, _ = w.solve(t)
        solved = acc(m.extract_math_answer(ans), m.extract_math_answer(t['answer']))
        gold = m.extract_math_answer(t['answer'])
        gold_s = str(int(gold)) if gold == int(gold) else str(gold)
        v = w._judge(t, gold_s)
        return k, solved, (v is True)

    jobs = [(k, t) for t in tasks for k in models]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(one, jobs))

    n = len(tasks)
    per_model = collections.defaultdict(lambda: [0, 0])
    for k, s, p in res:
        per_model[k][0] += s
        per_model[k][1] += p
    solve_rate = sum(s for _, s, _ in res) / len(res)
    ph = sum(p for _, _, p in res) / len(res)
    # 全票通过率：每题 4 个模型都对正确提案投 ACCEPT 的比例
    by_task = collections.defaultdict(list)
    for (k, t), (_, s, p) in zip(jobs, res):
        by_task[id(t)].append(p)
    unan = sum(1 for v in by_task.values() if len(v) == 4 and all(v)) / n

    print(f'\n--- {name} ({n} 题) ---')
    for k, (s, p) in per_model.items():
        print(f'  {k:9s} 求解正确 {s}/{n}  判真值ACCEPT {p}/{n}')
    print(f'  求解正确率 = {solve_rate:.0%}')
    print(f'  p_h (单验证者接受正确提案) = {ph:.0%}')
    print(f'  全票通过率 p_h^4 (≈baseline共识率上界) = {unan:.0%}')


rnd = random.sample(ds, 6)
eval_group('随机子集 (6题)', rnd)
print('\nPROBE_DONE')
