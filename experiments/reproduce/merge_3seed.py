# -*- coding: utf-8 -*-
"""合并 3 种子数据: seed42(v2 gsm8k + v3 mbpp含debate fix) + seed43/44(multiseed)
输出: 每场景x方法 mean±std (3种子) + 合并 n=90 的点估计与 Wilson 95% CI"""
import json
import math
import os

BASE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(os.path.dirname(BASE), 'results')

v2 = json.load(open(os.path.join(RES, 'multi_model_compare_ablation_v2.json'), encoding='utf-8'))
v3 = json.load(open(os.path.join(RES, 'multi_model_compare_ablation_v3.json'), encoding='utf-8'))
fix = json.load(open(os.path.join(RES, 'mbpp_debate_fix.json'), encoding='utf-8'))
ms = json.load(open(os.path.join(RES, 'multi_model_multiseed.json'), encoding='utf-8'))

rows42 = [dict(r, seed=42) for r in v2['rows'] if r['dataset'] == 'gsm8k']
rows42 += [dict(r, seed=42) for r in v3['rows'] if r['dataset'] == 'mbpp' and r['method'] != 'LLM-Debate']
fixmap = {(r['n'], r['f'], r['s']): r for r in fix['rows']}
rows42 += [dict(fixmap[(r['n'], r['f'], r['s'])], seed=42)
           for r in v3['rows'] if r['dataset'] == 'mbpp' and r['method'] == 'LLM-Debate']

all_rows = rows42 + ms['rows']
assert len(all_rows) == 144, len(all_rows)

def wilson(p, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = p / 100.0
    den = 1 + z*z/n
    c = (p + z*z/(2*n)) / den
    h = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return (max(0.0, (c-h))*100, min(1.0, (c+h))*100)

METRICS = ['decision_rate', 'answer_accuracy', 'wrong_commit_rate', 'accuracy_when_decided', 'avg_rounds', 'avg_calls']
order = ['A2A-BFT', 'A2A-BFT w/o 视图切换', 'A2A-BFT w/o 语义验证', 'A2A-BFT 固定阈值',
         'Simple Majority', 'Weighted Majority', 'A2A-Sim', 'LLM-Debate']

scenes = [('gsm8k', 5, 0, 0), ('gsm8k', 5, 1, 1), ('gsm8k', 8, 2, 1),
          ('mbpp', 5, 0, 0), ('mbpp', 5, 1, 1), ('mbpp', 8, 2, 1)]

agg = []
for ds, n, f, s in scenes:
    attack = {(5,0,0): 'baseline', (5,1,1): 'strategic_reject', (8,2,1): 'collusion'}[(n,f,s)]
    for m in order:
        rs = [r for r in all_rows if r['dataset']==ds and r['n']==n and r['f']==f
              and r['method']==m]
        assert len(rs) == 3, (ds, n, f, m, len(rs))
        row = {'dataset': ds, 'n': n, 'f': f, 's': s, 'attack': attack, 'method': m,
               'num_seeds': 3, 'tasks_per_seed': rs[0]['num_tasks'], 'total_tasks': 3*rs[0]['num_tasks']}
        for k in METRICS:
            vals = [r[k] for r in rs]
            mean = sum(vals)/3
            std = (sum((v-mean)**2 for v in vals)/2) ** 0.5  # 样本标准差 (ddof=1? n-1=2 -> /2)
            row[k+'_mean'] = round(mean, 1)
            row[k+'_std'] = round(std, 1)
            row[k+'_values'] = vals
        # 合并点估计（3种子合计，n=90）与 Wilson CI
        N = row['total_tasks']
        for k, cnt_key in [('decision_rate', None), ('answer_accuracy', None), ('wrong_commit_rate', None)]:
            cnt = round(sum(r[k] for r in rs) / 100 * rs[0]['num_tasks'])
            row[k+'_pooled'] = round(cnt / N * 100, 1)
            lo, hi = wilson(cnt, N)
            row[k+'_wilson'] = [round(lo,1), round(hi,1)]
        agg.append(row)

out = os.path.join(RES, 'multi_model_3seed_aggregated.json')
json.dump({'models': ms['models'], 'seeds': [42, 43, 44], 'rows': agg},
          open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('saved', out, len(agg), 'rows')

print(f"\n{'场景':<22}{'方法':<26}{'决策 mean±std':>16}{'正确':>14}{'错误提交':>16} Wilson(n=90)")
for r in agg:
    sc = f"{r['dataset']} n={r['n']},f={r['f']},s={r['s']}"
    d, a, w = r['decision_rate'], r['answer_accuracy'], r['wrong_commit_rate']
    print(f"{sc:<22}{r['method']:<26}"
          f"{d['mean']:>7.1f}±{d['std']:<5.1f}{a['mean']:>7.1f}±{a['std']:<5.1f}"
          f"{w['mean']:>8.1f}±{w['std']:<5.1f}  [{w['wilson'][0]:.1f},{w['wilson'][1]:.1f}]")
print('AGG_DONE')
