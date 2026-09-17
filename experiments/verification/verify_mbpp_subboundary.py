# -*- coding: utf-8 -*-
"""
核验 PAT 反馈 W6 / 4-1：MBPP 越界配置（n=5,f=2）的 5.6--9.6% 错提交是否"数学上不可能"。

做法：不调用任何 LLM。用真实 MBPP 任务 + 真实代码执行验证（run_code_tests），
把模型的"是否解对"简化为一个可控制的概率 p_model：
  - 以 p_model 概率返回数据集标准解（正确）
  - 否则返回 code_tamper(标准解)（等价于"错误提案"，必然无法通过测试）
其他一切（投票聚合、阈值、视图切换、错误判定 is_correct）全部沿用仓库实现。

对照两组：
  A2ABFT        —— v3 原始语义（collusion: 主节点拜占庭则 ACCEPT，否则 REJECT）
  A2ABFTSybil   —— full_bft_sweep.py 实际使用的语义（拜占庭验证者 REJECT 75% / ACCEPT 25%）

输出：每个 (n,f,attack) 的 决策率 / 错误提交率，以及错误提交的机制分解。
"""
import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
while not os.path.exists(os.path.join(ROOT, ".a2a_project_root")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)
for _d in (os.path.join(ROOT, "experiments", "reproduce"), os.path.join(ROOT, "experiments", "src")):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)

import multi_model_vllm as mmv          # noqa: E402
import multi_model_compare_ablation_v3 as v3   # noqa: E402

P_MODEL = 0.70          # 单模型 MBPP 正确率（与真机扫描的量级一致）
TASKS = 200
SEEDS = [42, 43, 44]


class OfflineWorker(mmv.MultiModelWorker):
    """不调用 LLM 的 Worker：solve() 用受控概率产出正确/错误代码，validate() 仍走真实执行。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, client=None, **kw)

    def solve(self, task):
        if self.is_soft_fault and random.random() < 0.3:
            return "", 0.1
        code = (task.get("code") or "").strip()
        ok = random.random() < P_MODEL and "def" in code
        if self.is_byzantine and self.byzantine_type in ("collusion", "strategic_reject"):
            # 伪装成正常求解后篡改（与实现一致）
            return (mmv.code_tamper(code) if code else ""), 0.6
        if not ok:
            return (mmv.code_tamper(code) if code else ""), 0.2   # 错误提案
        return code, 0.85

    def _generate(self, prompt, max_tokens=128):      # 任何意外调用都视为缺陷
        raise AssertionError("offline worker should not call the LLM")


class SweepSybil(v3.A2ABFT):
    """与 full_bft_sweep.py 中的 A2ABFTSybil 完全一致"""

    def _validate(self, w, task, proposal, primary_is_byzantine):
        if w.is_byzantine:
            return 'REJECT' if random.random() < 0.75 else 'ACCEPT'
        return super()._validate(w, task, proposal, primary_is_byzantine)


def make_workers(n, f, s, attack, task_type="code"):
    return [OfflineWorker(worker_id=i,
                          is_byzantine=(i < f),
                          byzantine_type=attack if i < f else None,
                          is_soft_fault=(f <= i < f + s),
                          task_type=task_type)
            for i in range(n)]


def run_cell(layer_cls, tasks, n, f, s, attack):
    layer = layer_cls(n, f, s)
    decided = correct = 0
    examples = []
    for t in tasks:
        ws = make_workers(n, f, s, attack)
        prop, _rounds, _stats = layer.run(ws, t)
        if not prop:
            continue
        decided += 1
        if v3.is_correct(prop, t, "code"):
            correct += 1
        elif len(examples) < 3:
            # 记录一个错误提交的机制证据：诚实验证者对它的投票
            votes = [layer._validate(w, t, prop, ws[0].is_byzantine)
                     for i, w in enumerate(ws) if i != 0]
            examples.append({"id": t["id"], "round0_votes": votes,
                             "len": len(prop)})
    wrong = decided - correct
    return {"decided": decided, "correct": correct, "wrong": wrong,
            "decision_rate": round(decided / len(tasks) * 100, 1),
            "wrong_commit_rate": round(wrong / len(tasks) * 100, 1),
            "examples": examples}


def main():
    with io.open(os.path.join(ROOT, "experiments", "datasets", "mbpp_test.json"),
                 encoding="utf-8") as fh:
        data = json.load(fh)
    print(f"MBPP 任务池 {len(data)}；p_model={P_MODEL}；每格 {TASKS} 任务 x {len(SEEDS)} 种子")
    print(f"{'semantics':14}{'n':>3}{'f':>3} {'attack':18}{'dec%':>7}{'wrong%':>8}  机制样例")
    rows = []
    for label, cls in (("A2ABFT(strict)", v3.A2ABFT), ("A2ABFTSybil", SweepSybil)):
        for (n, f) in ((5, 2), (6, 2)):
            for attack in ("collusion", "strategic_reject", "random"):
                agg = {"decided": 0, "correct": 0, "wrong": 0}
                ex = []
                for sd in SEEDS:
                    random.seed(sd)
                    tasks = random.sample(data, TASKS)
                    random.seed(sd * 1000 + 7)
                    r = run_cell(cls, tasks, n, f, 0, attack)
                    for k in agg:
                        agg[k] += r[k]
                    ex += r["examples"]
                tot = TASKS * len(SEEDS)
                dec_rate = round(agg["decided"] / tot * 100, 1)
                wrong_rate = round(agg["wrong"] / tot * 100, 1)
                print(f"{label:14}{n:>3}{f:>3} {attack:18}{dec_rate:>7.1f}{wrong_rate:>8.1f}  "
                      f"{ex[0]['round0_votes'] if ex else '-'}")
                rows.append({"semantics": label, "n": n, "f": f, "attack": attack,
                             "decision_rate": dec_rate, "wrong_commit_rate": wrong_rate,
                             "n_tasks": tot, "examples": ex[:3]})
    out = os.path.join(ROOT, "experiments", "results", "mbpp_subboundary_verification.json")
    with io.open(out, "w", encoding="utf-8") as fh:
        json.dump({"p_model": P_MODEL, "tasks_per_seed": TASKS, "seeds": SEEDS,
                   "rows": rows}, fh, ensure_ascii=False, indent=2)
    print(f"\n写出: {out}")
    print("MBPP_SUBBOUNDARY_DONE")


if __name__ == "__main__":
    main()
