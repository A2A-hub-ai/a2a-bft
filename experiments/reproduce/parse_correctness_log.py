"""Parse the raw per-task log of the n=8 adversarial-boundary correctness run
into machine-readable JSON, so that Table 6 (tab:n8_scaling) stays auditable.

Why this exists
---------------
`correctness_eval.py` writes its summary to
`experiments/results/correctness_{dataset}_{tasks}t_{seeds}s.json`.
That path was reused by a later repeat run (2026-09-11T14:52), which
*overwrote* the JSON of the original run (2026-09-11T01:57) whose numbers
appear in the paper's Table 6.  The original run's raw per-task log
(`correctness_50x3_log.txt`) still exists and is the authoritative artifact,
so we re-derive the summary from it here.

Usage:
    python parse_correctness_log.py
Output:
    experiments/results/correctness_50t_3s_run1_from_log.json
"""

import sys
import os
import re
import json
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
# 结果目录挂在项目根下，不能由脚本自身位置推（本脚本现已位于 experiments/reproduce/）
_ROOT = HERE
while not os.path.exists(os.path.join(_ROOT, ".a2a_project_root")) and os.path.dirname(_ROOT) != _ROOT:
    _ROOT = os.path.dirname(_ROOT)
RESULTS = os.environ.get("A2A_RESULTS_DIR", os.path.join(_ROOT, "experiments", "results"))
LOG = os.path.join(RESULTS, "correctness_50x3_log.txt")
OUT = os.path.join(RESULTS, "correctness_50t_3s_run1_from_log.json")

SCEN_RE = re.compile(r"^场景:\s*n=(\d+),\s*f=(\d+),\s*s=(\d+),\s*attack=(\S+)")
SUMMARY_RE = re.compile(r"^n=(\d+),f=(\d+),s=(\d+),(\S+)\s+([\d.]+)%\s+([\d.]+)%")


def parse(path):
    lines = open(path, encoding="utf-8", errors="ignore").read().split("\n")

    def norm(a):
        """Header prints `attack=None`, summary prints `none`; normalise both."""
        a = a.strip().lower()
        return None if a in ("none", "null", "-") else a

    # --- scenario blocks, for per-task round counts ---
    starts = [(i, SCEN_RE.match(l)) for i, l in enumerate(lines) if SCEN_RE.match(l)]

    round_stats = {}
    for k, (start, m) in enumerate(starts):
        n, f, s, atk = int(m.group(1)), int(m.group(2)), int(m.group(3)), norm(m.group(4))
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        cur, rounds = 0, []
        for l in lines[start:end]:
            if l.startswith("[Round 1] Primary:"):
                if rounds or cur:
                    rounds.append(cur)
                cur = 1
            elif l.startswith("[Round ") and "Primary:" in l:
                cur += 1
        if cur:
            rounds.append(cur)
        round_stats[(n, f, s, atk)] = rounds

    # --- summary block ---
    summary = {}
    for l in lines:
        m = SUMMARY_RE.match(l)
        if m:
            key = (int(m.group(1)), int(m.group(2)), int(m.group(3)), norm(m.group(4)))
            summary[key] = (float(m.group(5)), float(m.group(6)))

    scenarios = []
    for key in summary:
        n, f, s, atk = key
        consensus, correctness = summary[key]
        rounds = round_stats.get(key, [])
        scenarios.append({
            "n": n, "f": f, "s": s,
            "attack_type": atk,
            "total_tasks": len(rounds),
            "consensus_rate": consensus,
            "correctness_rate": correctness,
            "avg_rounds": round(sum(rounds) / len(rounds), 3) if rounds else None,
            "round_histogram": {str(k): v for k, v in sorted(collections.Counter(rounds).items())},
        })
    return scenarios


def main():
    scen = parse(LOG)
    out = {
        "provenance": (
            "Values re-derived from the raw per-task log "
            "experiments/results/correctness_50x3_log.txt (run 2026-09-11T01:57). "
            "The summary JSON of this run was overwritten by a later repeat run "
            "(correctness_50t_3s.json, 2026-09-11T14:52). Do not edit by hand."
        ),
        "source_log": os.path.relpath(LOG, _ROOT).replace("\\", "/"),
        "experiment_type": "correctness_eval_deepseek",
        "model": "deepseek-chat",
        "dataset": "gsm8k",
        "config": {"tasks_per_seed": 50, "seeds": 3},
        "scenarios": scen,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    print(f"scenarios parsed: {len(scen)}")
    for r in scen:
        print(f"  n={r['n']},f={r['f']},s={r['s']},{r['attack_type']}: "
              f"tasks={r['total_tasks']} consensus={r['consensus_rate']}% "
              f"correct={r['correctness_rate']}% rounds={r['avg_rounds']}")
    print(f"written -> {os.path.relpath(OUT, _ROOT)}")

    # sanity checks against the values printed in Table 6 of the paper
    expect = {
        (8, 2, 1, "collusion"): (98.0, 92.7, 2.89),
        (8, 2, 1, "strategic_reject"): (98.0, 92.0, 2.92),
        (8, 0, 0, None): (100.0, 94.0, 1.03),
    }
    ok = True
    for r in scen:
        key = (r["n"], r["f"], r["s"], r["attack_type"])
        if key not in expect:
            continue
        e = expect[key]
        got = (r["consensus_rate"], r["correctness_rate"],
               round(r["avg_rounds"], 2) if r["avg_rounds"] is not None else None)
        if got != e:
            ok = False
            print(f"  MISMATCH {key}: table={e} parsed={got}")
    print("Table 6 cross-check:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
