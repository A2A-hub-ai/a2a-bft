# -*- coding: utf-8 -*-
"""聚合全量真机扫描结果（3 数据集 × 10 配置 × 5 种子 × 50 任务）
输出: experiments/results/full_bft_sweep_aggregated.json
schema 与 multi_model_3seed_aggregated.json 对齐，便于论文表格脚本复用
"""
import json
import math
import collections

BASE = os.environ.get("A2A_RESULTS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
SEEDS = [42, 43, 44, 45, 46]
TASKS_PER_SEED = 50
N = len(SEEDS) * TASKS_PER_SEED          # 250 每格

METRICS = ["decision_rate", "answer_accuracy", "wrong_commit_rate",
           "accuracy_when_decided", "avg_rounds", "avg_calls", "avg_time"]


def wilson(cnt, n, z=1.96):
    if n == 0:
        return [0.0, 0.0]
    p = cnt / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, c - h) * 100, 1), round(min(1.0, c + h) * 100, 1)]


rows_all = []
# mmlu 追加了 n=5,f=0,s=0 baseline（N5 补跑），故期望行数按数据集区分
EXPECTED_ROWS = {"gsm8k": 50, "mbpp": 50, "mmlu": 55}
for ds in ["gsm8k", "mbpp", "mmlu"]:
    d = json.load(open(f"{BASE}/full_bft_sweep_{ds}.json", encoding="utf-8"))
    assert len(d["rows"]) == EXPECTED_ROWS[ds], (ds, len(d["rows"]))
    seeds_seen = sorted({r["seed"] for r in d["rows"]})
    assert seeds_seen == SEEDS, (ds, seeds_seen)
    rows_all.extend(d["rows"])

cells = collections.defaultdict(list)
for r in rows_all:
    cells[(r["dataset"], r["n"], r["f"], r["s"], r["attack_raw"])].append(r)

agg = []
for (ds, n, f, s, atk), rs in sorted(cells.items(), key=lambda x: (x[0][0], x[0][1], x[0][4])):
    assert len(rs) == 5, (ds, n, atk, len(rs))
    row = {"dataset": ds, "n": n, "f": f, "s": s, "attack": atk, "method": "A2A-BFT",
           "num_seeds": 5, "tasks_per_seed": TASKS_PER_SEED, "total_tasks": N}
    for k in METRICS:
        vals = [r[k] for r in rs]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        row[k + "_mean"] = round(mean, 1)
        row[k + "_std"] = round(var ** 0.5, 1)
        row[k + "_values"] = vals
    # 合并点估计（5 种子合计 n=250）+ Wilson 95% CI
    for k in ["decision_rate", "answer_accuracy", "wrong_commit_rate"]:
        cnt = round(sum(r[k] for r in rs) / 100 * TASKS_PER_SEED)
        row[k + "_pooled"] = round(cnt / N * 100, 1)
        row[k + "_wilson"] = wilson(cnt, N)
    agg.append(row)

out = f"{BASE}/full_bft_sweep_aggregated.json"
json.dump({"seeds": SEEDS, "tasks_per_seed": TASKS_PER_SEED, "rows": agg},
          open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"saved {out}  ({len(agg)} cells, n={N}/cell)\n")

print(f"{'数据集':<7}{'配置':<34}{'决策率':>16}{'正确率':>16}{'错误提交':>18}  轮数  耗时/题")
for r in agg:
    sc = f"n={r['n']},f={r['f']},s={r['s']} {r['attack']}"
    d, a, w = r["decision_rate_mean"], r["answer_accuracy_mean"], r["wrong_commit_rate_mean"]
    ds_, as_, ws_ = r["decision_rate_std"], r["answer_accuracy_std"], r["wrong_commit_rate_std"]
    print(f"{r['dataset']:<7}{sc:<34}"
          f"{d:>6.1f}±{ds_:<4.1f}"
          f"{a:>8.1f}±{as_:<4.1f}"
          f"{w:>8.1f}±{ws_:<4.1f}"
          f"  {r['avg_rounds_mean']:>4.2f}"
          f"  {r['avg_time_mean']:>5.1f}s")
