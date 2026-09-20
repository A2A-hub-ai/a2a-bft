# -*- coding: utf-8 -*-
"""Held-out judge FPR/FNR calibration (Appendix, judge-calibration table).

Runs the protocol's *exact* semantic-judge prompts (JUDGE_PROMPT /
JUDGE_PROMPT_MC from experiments/reproduce/multi_model_vllm.py) against the
same four vLLM endpoints, on a held-out task sample that excludes every task
index used by the paper's runs (full sweep seeds 42-46 x 50; ablation v3
seed 42 x 30; reputation seed 42 x 20; multiseed seeds 43-44 x 30).

Two conditions per task x per judge model:
  correct proposal  -> measures FNR  (judge rejects/abstains on a correct answer)
  wrong proposal    -> measures FPR  (judge accepts a wrong answer)
Wrong proposals are deterministic plausible perturbations (GSM8K: numeric
delta; MMLU: a wrong choice letter), seeded per task.

Usage (on the GPU host, after the four vLLM servers are up):
  python heldout_judge_calibration.py \
      --datasets /root/calib/datasets --out /root/calib/heldout_results.json
Standalone: standard library + openai client only.
"""
import argparse
import json
import os
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

# ---------------- 与 multi_model_vllm.py 逐字一致 ----------------
JUDGE_PROMPT = """First solve the following math problem yourself, step by step. Then compare your own answer with the submitted answer and judge whether the submitted answer is correct.

Problem: {question}
Submitted final answer: {proposal}

After your reasoning, end your reply with exactly these two lines:
YOUR_ANSWER: <your own final answer>
VERDICT: <ACCEPT if the submitted answer is correct, REJECT if it is wrong, UNCERTAIN if you cannot determine>"""

JUDGE_PROMPT_MC = """First answer the following multiple choice question yourself. Then compare your own choice with the submitted answer and judge whether the submitted answer is correct.

Question: {question}

Choices:
A) {choice_a}
B) {choice_b}
C) {choice_c}
D) {choice_d}

Submitted answer: {proposal}

After your reasoning, end your reply with exactly these two lines:
YOUR_ANSWER: <your own choice letter>
VERDICT: <ACCEPT if the submitted answer is correct, REJECT if it is wrong, UNCERTAIN if you cannot determine>"""

JUDGE_MAX_TOKENS = 384
VERDICT_RE = re.compile(r"VERDICT\s*[:\-]?\s*(ACCEPT|REJECT|UNCERTAIN)", re.IGNORECASE)

ENDPOINTS = {
    "llama": {"base_url": "http://127.0.0.1:8000/v1", "model": "llama", "name": "Llama-3.1-8B"},
    "internlm": {"base_url": "http://127.0.0.1:8001/v1", "model": "internlm", "name": "InternLM3-8B"},
    "deepseek": {"base_url": "http://127.0.0.1:8002/v1", "model": "deepseek", "name": "DeepSeek-V2-Lite"},
    "qwen": {"base_url": "http://127.0.0.1:8003/v1", "model": "qwen", "name": "Qwen2.5-7B"},
}

# ---------------- 留出集抽样（与本文件 docstring 的口径一致） ----------------
def heldout_indices(n, k_want, seed=2026):
    used = set()
    for s in (42, 43, 44, 45, 46):          # full_bft_sweep x50
        random.seed(s); used.update(random.sample(range(n), min(50, n)))
    random.seed(42); used.update(random.sample(range(n), min(30, n)))   # ablation_v3
    random.seed(42); used.update(random.sample(range(n), min(20, n)))   # reputation
    for s in (43, 44):                       # multiseed x30
        random.seed(s); used.update(random.sample(range(n), min(30, n)))
    pool = [i for i in range(n) if i not in used]
    rnd = random.Random(seed)
    return sorted(rnd.sample(pool, min(k_want, len(pool)))), len(pool)


def extract_math_answer(text):
    if not text:
        return None
    m = re.search(r"####\s*(-?\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(?:answer|Answer|答案)\s*[:：=]?\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    return float(nums[-1]) if nums else None


def wrong_numeric_answer(gt, rng):
    """确定性数值扰动：模拟典型算错（±1/±2/±10、数位翻转、百分号类）。"""
    for delta in rng.sample([1, -1, 2, -2, 10, -10, 100, -100], 8):
        w = gt + delta
        if w != gt:
            return w
    return gt + 1


def fmt_num(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def build_tasks(datasets_dir):
    tasks = []
    # GSM8K
    data = json.load(open(os.path.join(datasets_dir, "gsm8k_test.json"), encoding="utf-8"))
    idx, pool_n = heldout_indices(len(data), 150)
    for i in idx:
        t = data[i]
        gt = extract_math_answer(t["answer"])
        if gt is None:
            continue
        rng = random.Random(f"wrong-{t['id']}")
        tasks.append({
            "dataset": "gsm8k", "id": t["id"], "question": t["question"],
            "correct": fmt_num(gt), "wrong": fmt_num(wrong_numeric_answer(gt, rng)),
        })
    print(f"gsm8k held-out: {sum(1 for t in tasks if t['dataset']=='gsm8k')} (pool {pool_n})")
    # MMLU
    data = json.load(open(os.path.join(datasets_dir, "mmlu_3subjects.json"), encoding="utf-8"))
    idx, pool_n = heldout_indices(len(data), 150)
    for i in idx:
        t = data[i]
        ch = t["choices"]
        if t["answer"] not in ch or len(ch) != 4:
            continue
        ci = ch.index(t["answer"])
        letter = chr(65 + ci)
        rng = random.Random(f"wrong-{t['id']}")
        wrongs = [chr(65 + j) for j in range(4) if j != ci]
        tasks.append({
            "dataset": "mmlu", "id": t["id"], "question": t["question"],
            "choices": ch, "correct": letter, "wrong": rng.choice(wrongs),
        })
    print(f"mmlu held-out: {sum(1 for t in tasks if t['dataset']=='mmlu')} (pool {pool_n})")
    return tasks


def judge_prompt(task, proposal):
    if task["dataset"] == "gsm8k":
        return JUDGE_PROMPT.format(question=task["question"], proposal=proposal)
    ch = task["choices"]
    return JUDGE_PROMPT_MC.format(
        question=task["question"], choice_a=ch[0], choice_b=ch[1],
        choice_c=ch[2], choice_d=ch[3], proposal=proposal)


def parse_verdict(raw, task, proposal):
    """与协议 _judge 逐字等价的三级解析（VERDICT 行 -> YOUR_ANSWER 比对 -> 最后关键词）。
    返回 (True/False/None, tag)，tag ∈ {'verdict','fallback','keyword','unparsed','error'}"""
    up = raw.upper()
    if up.startswith("ERROR:"):
        return None, "error"
    marks = VERDICT_RE.findall(raw)
    if marks:
        v = marks[-1].upper()
        return (True if v == "ACCEPT" else False if v == "REJECT" else None), "verdict"
    # 回退1：解析 YOUR_ANSWER 与提案精确比对
    ma = re.search(r"YOUR_ANSWER\s*[:\-]?\s*(.+)", raw)
    if ma:
        own = ma.group(1).strip().splitlines()[0]
        if task["dataset"] == "gsm8k":
            a, b = extract_math_answer(own), extract_math_answer(proposal)
            if a is not None and b is not None:
                return abs(a - b) < 1e-6, "fallback"
        else:
            m1 = re.search(r"\b([ABCD])\b", own.upper())
            if m1:
                return m1.group(1) == proposal.upper(), "fallback"
    # 回退2：最后出现的裁决关键词
    la, lr = up.rfind("ACCEPT"), up.rfind("REJECT")
    if la == -1 and lr == -1:
        return None, "unparsed"
    return la > lr, "keyword"


class Judge:
    def __init__(self, key):
        cfg = ENDPOINTS[key]
        self.key, self.name = key, cfg["name"]
        self.api_model = cfg["model"]  # served-model-name
        self.client = OpenAI(base_url=cfg["base_url"], api_key="EMPTY", timeout=240)

    def raw_call(self, prompt):
        try:
            resp = self.client.chat.completions.create(
                model=self.api_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0, max_tokens=JUDGE_MAX_TOKENS)
        except Exception as e:
            return f"ERROR: {str(e)[:200]}"
        return (resp.choices[0].message.content or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="/root/calib/datasets")
    ap.add_argument("--out", default="/root/calib/heldout_results.json")
    ap.add_argument("--workers", type=int, default=6, help="per-endpoint concurrency")
    args = ap.parse_args()

    tasks = build_tasks(args.datasets)
    judges = {k: Judge(k) for k in ENDPOINTS}

    lock = threading.Lock()
    records = []

    def run_one(task, cond, jkey):
        proposal = task[cond]
        raw = judges[jkey].raw_call(judge_prompt(task, proposal))
        v, tag = parse_verdict(raw, task, proposal)
        rec = {"dataset": task["dataset"], "id": task["id"], "cond": cond,
               "judge": jkey, "proposal": proposal, "verdict": v, "tag": tag,
               "raw": raw[:200]}
        with lock:
            records.append(rec)
            done = len(records)
        if done % 200 == 0:
            print(f"progress: {done}/{len(tasks)*2*4}", flush=True)

    jobs = [(t, c, k) for t in tasks for c in ("correct", "wrong") for k in ENDPOINTS]
    print(f"total judge calls: {len(jobs)}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers * len(ENDPOINTS)) as ex:
        futs = []
        for t, c, k in jobs:
            def go(t=t, c=c, k=k):
                return run_one(t, c, k)
            futs.append(ex.submit(go))
        for f in futs:
            f.result()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"records": records,
                   "endpoints": {k: v["name"] for k, v in ENDPOINTS.items()}},
                  f, ensure_ascii=False, indent=1)

    # 汇总
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0, 0, 0])  # [acc|correct, rej|correct, acc|wrong, rej|wrong]
    tags = defaultdict(lambda: defaultdict(int))
    for r in records:
        key = (r["dataset"], r["judge"])
        tags[key][r["tag"]] += 1
        st = agg[key]
        correct = r["cond"] == "correct"
        v = r["verdict"]
        if v is None:
            continue
        i = (0 if correct else 2) + (0 if v else 1)
        st[i] += 1
    print("\n=== per (dataset, judge) ===")
    for key in sorted(agg):
        st = agg[key]
        fpr = st[2] / (st[2] + st[3]) if st[2] + st[3] else float("nan")
        fnr = st[1] / (st[0] + st[1]) if st[0] + st[1] else float("nan")
        tg = " ".join(f"{k}={v}" for k, v in sorted(tags[key].items()))
        print(f"{key}: FPR {st[2]}/{st[2]+st[3]} = {fpr:.4f}   FNR {st[1]}/{st[0]+st[1]} = {fnr:.4f}   [{tg}]")
    print(f"\nsaved: {args.out}")


if __name__ == "__main__":
    main()
