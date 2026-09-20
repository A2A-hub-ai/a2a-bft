# -*- coding: utf-8 -*-
"""Audit: judge-calibration numbers cited in the paper (Appendix judge-calibration).

Recomputes, from the released artifacts only:
  1. on-protocol aggregate FPR/FNR (reputation_vote_stream.json, GSM8K),
  2. per-judge on-protocol FPR (DeepSeek dominance claim),
  3. held-out per-judge FPR/FNR (heldout_judge_calibration.json),
and asserts they equal the values printed in the paper. Exits nonzero on any
mismatch.
"""
import json
import os
import sys
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STREAM = os.path.join(_ROOT, "experiments", "results", "reputation_vote_stream.json")
HELDOUT = os.path.join(_ROOT, "experiments", "results", "heldout_judge_calibration.json")
MODEL_KEYS = ["llama", "internlm", "deepseek", "qwen"]  # assignment = keys[i % 4]


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


def main():
    ok = True

    # ---- 1. on-protocol aggregate (GSM8K) ----
    recs = [r for r in json.load(open(STREAM, encoding="utf-8"))["records"]
            if r["dataset"] == "gsm8k"]
    tot = [0, 0, 0, 0]
    per_judge = defaultdict(lambda: [0, 0, 0, 0])
    for r in recs:
        assignment = [MODEL_KEYS[i % 4] for i in range(r["n"])]
        for rd in r["rounds_detail"]:
            gt = rd.get("proposal_correct_gt")
            if gt is None:
                continue
            for v in rd["votes"]:
                if v["is_byzantine"] or v["is_soft_fault"]:
                    continue
                acc = v["vote"] == "ACCEPT"
                i = (0 if gt else 2) + (0 if acc else 1)
                tot[i] += 1
                per_judge[assignment[v["validator"]]][i] += 1
    fpr, nfp = tot[2], tot[2] + tot[3]
    fnr, nfn = tot[1], tot[0] + tot[1]
    print(f"on-protocol: FPR {fpr}/{nfp} = {fpr/nfp:.4f}  FNR {fnr}/{nfn} = {fnr/nfn:.4f}")
    ok &= (fpr, nfp, fnr, nfn) == (127, 700, 53, 269)

    ds = per_judge["deepseek"]
    ds_fpr = ds[2] / (ds[2] + ds[3])
    print(f"on-protocol DeepSeek FPR: {ds[2]}/{ds[2]+ds[3]} = {ds_fpr:.4f}")
    ok &= (ds[2], ds[2] + ds[3]) == (121, 155) and close(ds_fpr, 0.781, 5e-4)
    for m in ("llama", "internlm", "qwen"):
        st = per_judge[m]
        f = st[2] / (st[2] + st[3])
        print(f"on-protocol {m} FPR: {st[2]}/{st[2]+st[3]} = {f:.4f}")
        ok &= f <= 0.02

    # ---- 2. held-out per-judge ----
    hrecs = json.load(open(HELDOUT, encoding="utf-8"))["records"]
    hagg = defaultdict(lambda: [0, 0, 0, 0])
    unparsed = defaultdict(lambda: [0, 0])  # judge -> [gsm8k, mmlu]
    total = defaultdict(lambda: [0, 0])
    for r in hrecs:
        key = (r["dataset"], r["judge"])
        di = 0 if r["dataset"] == "gsm8k" else 1
        total[r["judge"]][di] += 1
        v = r["verdict"]
        if v is None:
            unparsed[r["judge"]][di] += 1
            continue
        i = (0 if r["cond"] == "correct" else 2) + (0 if v else 1)
        hagg[key][i] += 1
    expect = {  # order: [acc|correct, rej|correct, acc|wrong, rej|wrong]
        ("gsm8k", "llama"): (117, 21, 2, 140),
        ("gsm8k", "internlm"): (98, 8, 0, 98),
        ("gsm8k", "deepseek"): (127, 12, 99, 36),
        ("gsm8k", "qwen"): (130, 7, 2, 139),
        ("mmlu", "llama"): (68, 33, 38, 63),
        ("mmlu", "internlm"): (31, 1, 27, 7),
        ("mmlu", "deepseek"): (66, 30, 64, 34),
        ("mmlu", "qwen"): (73, 21, 23, 71),
    }
    for key in sorted(expect):
        st = tuple(hagg[key])
        f = st[2] / (st[2] + st[3]) if st[2] + st[3] else 0.0
        print(f"held-out {key}: FPR {st[2]}/{st[2]+st[3]} = {f:.4f}  FNR {st[1]}/{st[0]+st[1]}")
        ok &= st == expect[key]
    # abstain-rate claims
    for j, (g, m) in {"internlm": (0.32, 0.73)}.items():
        fr = unparsed[j][0] / total[j][0]
        mr = unparsed[j][1] / total[j][1]
        print(f"held-out {j} unparsed: gsm8k {fr:.3f} (claim {g}), mmlu {mr:.3f} (claim {m})")
        ok &= abs(fr - g) <= 0.005 and abs(mr - m) <= 0.005
    for j in ("llama", "deepseek", "qwen"):
        for di in (0, 1):
            ok &= unparsed[j][di] / total[j][di] <= 0.27

    print("\nAUDIT " + ("PASS" if ok else "FAIL") + ": judge-calibration numbers vs paper claims")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
