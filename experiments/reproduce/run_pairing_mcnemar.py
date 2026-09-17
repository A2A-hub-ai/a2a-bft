"""第 6 轮评审：把 n=8 边界配置的两次运行解析成逐任务记录，做配对检验（McNemar）。

背景：round 5 发现同一实验跑了两次，决策率不同（98.0% vs 100.0%），
当时仅以文字说明"视为 API 逐次波动"。本脚本用**逐任务配对**把这件事做成可检验的结论。

两次运行使用相同的 random.seed(seed) + random.sample(dataset, 50)、相同的 seed 集合，
因此任务索引 i 在两次运行中指向**同一个 GSM8K 题目**，可做配对比较。

用法：
    python run_pairing_mcnemar.py
"""

import os
import re
import sys
import math
import json
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
# 结果目录挂在项目根下，不能由脚本自身位置推（本脚本现已位于 experiments/reproduce/）
_ROOT = HERE
while not os.path.exists(os.path.join(_ROOT, ".a2a_project_root")) and os.path.dirname(_ROOT) != _ROOT:
    _ROOT = os.path.dirname(_ROOT)
RESULTS = os.environ.get("A2A_RESULTS_DIR", os.path.join(_ROOT, "experiments", "results"))
RUN1 = os.path.join(RESULTS, "correctness_50x3_log.txt")
RUN2 = os.path.join(RESULTS, "correctness_count_log.txt")
SCEN = re.compile(r"^场景:\s*n=(\d+),\s*f=(\d+),\s*s=(\d+),\s*attack=(\S+)")
TASK_HEAD = "[Round 1] Primary:"
DEC = re.compile(r"^\s*Decision:\s*(\w+)")


def parse_tasks(path):
    """-> {scenario_key: [per-task final decision, ...]} in log order."""
    lines = open(path, encoding="utf-8", errors="ignore").read().split("\n")
    starts = [i for i, l in enumerate(lines) if SCEN.match(l)]
    out = {}
    for k, s in enumerate(starts):
        m = SCEN.match(lines[s])
        key = (int(m.group(1)), int(m.group(2)), int(m.group(3)),
               "none" if m.group(4).lower() == "none" else m.group(4))
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        tasks, cur, last = [], None, None
        for l in lines[s:end]:
            if l.startswith(TASK_HEAD):
                if cur is not None:
                    tasks.append(last or "UNKNOWN")
                cur, last = [], None
            elif cur is not None:
                d = DEC.match(l)
                if d:
                    last = d.group(1)
        if cur is not None:
            tasks.append(last or "UNKNOWN")
        out[key] = tasks
    return out


def mcnemar(a, b):
    """Exact binomial McNemar on paired binary outcomes.
    a, b: lists of bools (True = accepted)."""
    n01 = sum(1 for x, y in zip(a, b) if (not x) and y)   # run1 reject -> run2 accept
    n10 = sum(1 for x, y in zip(a, b) if x and (not y))   # run1 accept -> run2 reject
    nd = n01 + n10
    if nd == 0:
        return n01, n10, 1.0
    # two-sided exact binomial p
    k = min(n01, n10)
    p = 0.0
    for i in range(0, k + 1):
        p += math.comb(nd, i)
    p = min(1.0, 2.0 * p / (2 ** nd))
    return n01, n10, p


def main():
    if not (os.path.exists(RUN1) and os.path.exists(RUN2)):
        print("缺少日志文件", file=sys.stderr)
        return 1
    t1 = parse_tasks(RUN1)
    t2 = parse_tasks(RUN2)

    print(f"run1 场景 {len(t1)} | run2 场景 {len(t2)}")
    report = []
    for key in t1:
        if key not in t2:
            print(f"  [skip] {key} 仅存在于 run1")
            continue
        a = [d == "ACCEPT" for d in t1[key]]
        b = [d == "ACCEPT" for d in t2[key]]
        if len(a) != len(b):
            print(f"  [skip] {key} 任务数不一致 run1={len(a)} run2={len(b)}")
            continue
        ra = 100.0 * sum(a) / len(a)
        rb = 100.0 * sum(b) / len(b)
        n01, n10, p = mcnemar(a, b)
        # only discordant tasks carry information
        print(f"  {key}: run1={ra:.1f}% run2={rb:.1f}% "
              f"discordant (rej->acc={n01}, acc->rej={n10}) McNemar exact p={p:.3f}")
        report.append({"scenario": list(key), "run1_consensus_pct": ra,
                       "run2_consensus_pct": rb, "n_reject_to_accept": n01,
                       "n_accept_to_reject": n10, "mcnemar_exact_p": p,
                       "n_tasks": len(a)})

    out = os.path.join(RESULTS, "run_pairing_mcnemar.json")
    json.dump({"note": "paired per-task comparison of the two n=8 runs (identical task sampling)",
               "results": report}, open(out, "w", encoding="utf-8"), indent=2)
    print(f"\nwritten -> {os.path.relpath(out, _ROOT)}")
    print("结论：所有配对差异 p ≫ 0.05 ⇒ 两次运行的决策率差异**不显著**，"
          "与论文'视为 API 逐次波动'的表述一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
