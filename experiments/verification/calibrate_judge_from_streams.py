# -*- coding: utf-8 -*-
"""Judge error-rate calibration from the released vote streams.

Measures the honest validators' semantic-judge error rates (FPR / FNR)
directly from `reputation_vote_stream.json` (GSM8K, 241 rounds with ground
truth; the 457-round replay in the paper covers GSM8K+MBPP), using each
round's `proposal_correct_gt` and the per-validator votes,
excluding Byzantine / soft-fault voters. MBPP is excluded (execution
validation, mechanically correct). Empty-proposal rounds (no ground truth)
are excluded.

Output doubles as an audit: the paper cites the numbers printed here
(Corollary 1 discussion + Appendix "Judge Error-Rate Calibration").
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STREAM = os.path.join(_ROOT, "experiments", "results", "reputation_vote_stream.json")


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (c - h, c + h)


def main():
    with open(STREAM, encoding="utf-8") as f:
        recs = json.load(f)["records"]

    # stats[attack] = [accept|correct, reject|correct, accept|wrong, reject|wrong]
    stats = {}
    overall = [0, 0, 0, 0]
    rounds_gt = rounds_no_gt = 0
    for r in recs:
        if r["dataset"] != "gsm8k":
            continue
        st = stats.setdefault(r["attack"], [0, 0, 0, 0])
        for rd in r["rounds_detail"]:
            gt = rd.get("proposal_correct_gt")
            if gt is None:
                rounds_no_gt += 1
                continue
            rounds_gt += 1
            for v in rd["votes"]:
                if v["is_byzantine"] or v["is_soft_fault"]:
                    continue
                acc = v["vote"] == "ACCEPT"
                i = (0 if gt else 2) + (0 if acc else 1)
                st[i] += 1
                overall[i] += 1

    print(f"rounds with ground truth: {rounds_gt} (excluded, no gt: {rounds_no_gt})")
    rows = []
    for a, st in sorted(stats.items()):
        fp, nfp = st[2], st[2] + st[3]
        fn, nfn = st[1], st[0] + st[1]
        rows.append((a, fp, nfp, fn, nfn))
    fp, nfp = overall[2], overall[2] + overall[3]
    fn, nfn = overall[1], overall[0] + overall[1]
    rows.append(("OVERALL", fp, nfp, fn, nfn))

    print(f"{'attack':18} {'FPR':>26} {'FNR':>26}")
    for a, fp, nfp, fn, nfn in rows:
        lo, hi = wilson(fp, nfp)
        lo2, hi2 = wilson(fn, nfn)
        print(f"{a:18} {fp:4}/{nfp:<5} = {fp/nfp:.4f} [{lo:.4f},{hi:.4f}]   "
              f"{fn:3}/{nfn:<5} = {fn/nfn:.4f} [{lo2:.4f},{hi2:.4f}]")

    # Audit: the paper cites these values.
    expect = {
        "baseline": (23, 100, 43, 156),
        "collusion": (66, 449, 5, 64),
        "strategic_reject": (38, 151, 5, 49),
    }
    by_attack = {a: (fp, nfp, fn, nfn) for a, fp, nfp, fn, nfn in rows[:-1]}
    for a, exp in expect.items():
        got = by_attack[a]
        assert got == exp, f"{a}: expected {exp}, got {got}"
    assert (fp, nfp, fn, nfn) == (127, 700, 53, 269), "overall counts changed"
    print("\nAUDIT PASS: counts match the values cited in the paper.")


if __name__ == "__main__":
    sys.exit(main())
