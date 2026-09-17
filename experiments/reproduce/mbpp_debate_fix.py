# -*- coding: utf-8 -*-
"""LLM-Debate 代码任务补丁重跑：辩论轮用代码专用提示词 + 512 tokens（原沿用 96 tokens 被截断）"""
import sys
import random
from collections import Counter

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
                              load_dataset, SOLVE_MAX_TOKENS_CODE)
from multi_model_compare_ablation_v3 import evaluate, normalize

RESULTS_DIR = A2A_RESULTS

DEBATE_PROMPT_CODE = """Several agents proposed different Python solutions for the same task. Reconsider and give YOUR final solution.

Task: {question}

Test pass/fail patterns of the agents' solutions (T=pass, F=fail): {others}

If your own solution already passes ALL tests, keep it unchanged and output it again unchanged in a single ```python block.
Otherwise, think about what likely bug causes the failures, fix it, and output your complete final Python code in a single ```python block."""


def llm_debate_code(workers, task, rounds=2):
    answers = [w.solve(task)[0] for w in workers]
    for _ in range(rounds):
        new = []
        for i, w in enumerate(workers):
            if w.is_byzantine:          # 拜占庭节点不改变立场
                new.append(answers[i])
                continue
            own = normalize(answers[i], task, 'code')
            # 理性代理：自己的代码已通过全部测试则不重写（防止自我毁灭式修改）
            if own and set(own) == {'T'}:
                new.append(answers[i])
                continue
            others = [normalize(a, task, 'code') for j, a in enumerate(answers) if j != i]
            others = [o for o in others if o]
            if not others:
                new.append(answers[i])
                continue
            prompt = DEBATE_PROMPT_CODE.format(question=task['question'],
                                               others=', '.join(others[:5]))
            raw = w._generate(prompt, max_tokens=SOLVE_MAX_TOKENS_CODE)
            # 仅当重写后的代码至少不劣于原答案时才采纳（按通过测试数比较）
            new_pat = normalize(raw, task, 'code')
            if new_pat and own is None or (new_pat and own and
                                           new_pat.count('T') >= own.count('T')):
                new.append(raw)
            else:
                new.append(answers[i])
        answers = new
    rep, cand = {}, []
    for a in answers:
        nn = normalize(a, task, 'code')
        if nn:
            rep.setdefault(nn, a)
            cand.append(nn)
    if not cand:
        return None
    return rep[Counter(cand).most_common(1)[0][0]]


def main():
    MODEL_KEYS = list(MODEL_ENDPOINTS.keys())
    clients = {k: VLLMClient(k) for k in MODEL_KEYS}
    scenarios = [
        {'n': 5, 'f': 0, 's': 0, 'attack': None},
        {'n': 5, 'f': 1, 's': 1, 'attack': 'strategic_reject'},
        {'n': 8, 'f': 2, 's': 1, 'attack': 'collusion'},
    ]
    data = load_dataset('mbpp')
    for t in data:
        t.setdefault('question', t.get('description', ''))
    all_rows = []
    for sc in scenarios:
        n, f, s, atk = sc['n'], sc['f'], sc['s'], sc['attack']
        random.seed(42)
        tasks = random.sample(data, 30)
        assignment = [MODEL_KEYS[i % len(MODEL_KEYS)] for i in range(n)]
        print(f"# mbpp n={n},f={f},s={s},attack={atk or 'baseline'}", flush=True)
        row = evaluate('LLM-Debate', lambda ws, t: llm_debate_code(ws, t),
                       tasks, n, f, s, atk, clients, assignment, 'code')
        row['dataset'] = 'mbpp'
        all_rows.append(row)
        print(f"  LLM-Debate 决策={row['decision_rate']}% 正确={row['answer_accuracy']}% "
              f"错误提交={row['wrong_commit_rate']}% 调用={row['avg_calls']}", flush=True)
    import json
    from datetime import datetime
    out = f'{RESULTS_DIR}/mbpp_debate_fix.json'
    with open(out, 'w', encoding='utf-8') as fp:
        json.dump({'timestamp': datetime.now().isoformat(), 'rows': all_rows},
                  fp, ensure_ascii=False, indent=2)
    print('DEBATE_FIX_DONE', flush=True)


if __name__ == '__main__':
    main()
