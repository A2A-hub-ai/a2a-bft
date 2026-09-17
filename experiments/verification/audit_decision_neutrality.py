# -*- coding: utf-8 -*-
"""决策中性审计：把"声誉追踪器不进入决策"从**空转断言**变成**可证伪检验**。

为什么需要这个审计
--------------------------------------------------------------------------------
论文 §6.6 与附录 A.7 写：

    "In all four the replayed decisions match the online record, verifying
     decision-neutrality rather than asserting it."   （iclr2027_main.tex:330）
    "the tracker is genuinely decision-neutral---this is now *verified* rather
     than merely asserted, since all four replays reproduce the online decisions
     exactly."                                        （iclr2027_main.tex:786）

但 `experiments/reproduce/reputation_ablation.py:394` 记录的"重放决策"就是
`rec['decision']` 本身，而 `summarize()`(L464-467) 拿它与 `rec['decision']` 比对：

    stats['decisions'].append((key, rec['task_idx'], rec['decision']))   # L394
    by_dec  = {(k, t): d for k, t, d in stats['decisions']}              # 值 == rec['decision']
    rec_dec = {..., r['decision'] for r in records}                      # 值 == rec['decision']
    consistent = all(by_dec.get(k) == v for k, v in rec_dec.items())     # 恒真

两侧同源 ⇒ `consistent` 与 c_source、persistence 全然无关，**永远为 True**。
即：这条"验证"没有任何分辨力，论文据此写的 "verified" 缺乏支撑。

本审计改用投票流中已存的**原始票**与阈值，做三层真正可证伪的检验：

  D1  从原始票重算 phi = |ACCEPT| - 0.5|REJECT|，与线上记录的 phi 逐轮比对。
      —— 若计票曾按声誉加权（如 `consensus_unified._compute_vote_score`
         的 score += weight * reputation），重算值必然偏离记录值。
  D2  用记录的 phi/theta 复现协议状态机（view change / pending / confirm），
      与线上的 primary 推进序列、最终 decision、轮数逐项比对。
      —— 这才是"决策由计票规则唯一决定"的检验。
  D3  变异测试：向 phi 注入三种反事实权重，确认 phi 与决策**确实会变**。
      —— 证明 D1/D2 不是空转：若注入权重后一切不变，说明检验无分辨力。
  D4  静态可达性：论文所用实现的决策段不得出现声誉/权重标识，且
      `_get_reputation_weights` 必须零调用点（即 rho 在结构上不可达决策）。
  D5  复现现有 `consistent` 校验的恒真性：把决策全部篡改后它仍判 True。

用法::

    python experiments/verification/audit_decision_neutrality.py
"""
import io
import os
import re
import sys
import json
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while not os.path.exists(os.path.join(_ROOT, ".a2a_project_root")) and os.path.dirname(_ROOT) != _ROOT:
    _ROOT = os.path.dirname(_ROOT)

RESULTS = os.path.join(_ROOT, "experiments", "results")
VOTE_LOG = os.path.join(RESULTS, "reputation_vote_stream.json")
REPRO = os.path.join(_ROOT, "experiments", "reproduce")
SRC = os.path.join(_ROOT, "experiments", "src", "a2a_bft")

checks = []          # (name, ok, detail)
problems = []


def ck(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    if not ok:
        problems.append(f"{name}: {detail}")


def read(p):
    return io.open(p, encoding="utf-8", errors="ignore", newline="").read()


# ---------------------------------------------------------------------------
# D1/D2：从原始票重算 phi，并复现状态机
# ---------------------------------------------------------------------------
def recompute_phi(rd, weight=None):
    """从原始票重算计票分数。

    weight(vote_record) -> float  为可选的票权（默认恒 1，即论文的纯计数制）。
    """
    phi = 0.0
    for v in rd["votes"]:
        w = 1.0 if weight is None else weight(v)
        if v["vote"] == "ACCEPT":
            phi += w
        elif v["vote"] == "REJECT":
            phi -= 0.5 * w
        # ABSTAIN 记 0（与发布实现一致：既不计入 ACCEPT 也不计入 REJECT）
    return phi


def redecide(rec, phi_of_round=None, max_rounds=6):
    """按 multi_model_compare_ablation_v3.A2ABFT.run (L166-198) 复现状态机。

    返回 (decision, rounds, primary_trace, pending_trace)。
    phi_of_round: 可选覆盖，用于变异测试。
    """
    n = rec["n"]
    idx = 0
    pending = 0
    primary_trace = []
    pending_trace = []
    rounds_detail = rec["rounds_detail"]
    for rd in rounds_detail:
        primary_trace.append(idx)
        pending_trace.append(pending)
        if rd.get("proposal_empty"):
            idx = (idx + 1) % n          # use_view_change=True
            continue
        phi = rd["phi"] if phi_of_round is None else phi_of_round(rd)
        if phi >= rd["theta_accept"]:
            return "ACCEPT", rd["round"], primary_trace, pending_trace
        if phi <= rd["theta_reject"] or pending >= 1:
            idx = (idx + 1) % n
            pending = 0
        else:
            pending += 1
    return "PENDING", rounds_detail[-1]["round"] if rounds_detail else 0, primary_trace, pending_trace


def main():
    if not os.path.exists(VOTE_LOG):
        print(f"[FAIL] 找不到投票流 {VOTE_LOG}")
        sys.exit(1)
    recs = json.load(io.open(VOTE_LOG, encoding="utf-8"))["records"]
    print(f"投票流: {len(recs)} 条记录")
    print(f"决策分布: {dict(Counter(r['decision'] for r in recs))}")
    print()

    # ---- D1: phi 是否等于纯计数 ----
    phi_rounds = 0
    phi_bad = []
    for rec in recs:
        for rd in rec["rounds_detail"]:
            if rd.get("proposal_empty") or "phi" not in rd:
                continue
            phi_rounds += 1
            exp = recompute_phi(rd)
            if abs(exp - rd["phi"]) > 1e-9:
                phi_bad.append((rec["dataset"], rec["n"], rec["f"], rd["round"],
                                rd["phi"], exp))
    ck("D1 线上 phi 等于纯计数 |ACCEPT| - 0.5|REJECT|（无权重）",
       phi_rounds > 0 and not phi_bad,
       f"共 {phi_rounds} 轮，{len(phi_bad)} 轮偏离；例如 {phi_bad[:3]}")
    print(f"  [info] D1 覆盖 {phi_rounds} 个有提案轮次的 phi 重算")

    # ---- D2a: primary 推进序列 ----
    prim_bad = []
    for rec in recs:
        _, _, tr, _ = redecide(rec)
        rec_tr = [rd["primary"] for rd in rec["rounds_detail"]]
        if tr != rec_tr:
            prim_bad.append((rec["dataset"], rec["task_idx"], tr[:8], rec_tr[:8]))
    ck("D2a 复现的 primary 推进序列与线上一致", not prim_bad,
       f"{len(prim_bad)} 条不符；例如 {prim_bad[:2]}")

    # ---- D2b: 决策 ----
    dec_bad = []
    for rec in recs:
        d, r, _, _ = redecide(rec)
        if d != rec["decision"]:
            dec_bad.append((rec["dataset"], rec["task_idx"], rec["decision"], d))
        if r != rec["rounds"]:
            dec_bad.append((rec["dataset"], rec["task_idx"], f"rounds {rec['rounds']}", f"rounds {r}"))
    ck("D2b 复现决策（含轮数）与线上记录逐条一致", not dec_bad,
       f"{len(dec_bad)} 条不符；例如 {dec_bad[:3]}")
    print(f"  [info] D2b 独立复现 {len(recs)} 条决策，非空转校验")

    # ---- D3: 变异测试 ----
    variants = {
        "REJECT 权重 0.5": lambda v: 0.5 if v["vote"] == "REJECT" else 1.0,
        "拜占庭验证者权重 0.3": lambda v: 0.3 if v.get("is_byzantine") else 1.0,
        "软故障验证者权重 0.3": lambda v: 0.3 if v.get("is_soft_fault") else 1.0,
    }
    total_flip = 0
    for vname, wf in variants.items():
        phi_changed = 0
        flip = 0
        for rec in recs:
            for rd in rec["rounds_detail"]:
                if rd.get("proposal_empty") or "phi" not in rd:
                    continue
                if abs(recompute_phi(rd, wf) - rd["phi"]) > 1e-9:
                    phi_changed += 1
            d_mut, _, _, _ = redecide(rec, phi_of_round=lambda rd, wf=wf: recompute_phi(rd, wf))
            if d_mut != rec["decision"]:
                flip += 1
        total_flip += flip
        print(f"  [variant] {vname:<22} phi 改变 {phi_changed} 轮，决策翻转 {flip} 条")
    ck("D3 变异测试：注入权重会改变 phi 与决策（证明 D1/D2 有分辨力）",
       total_flip > 0,
       "注入三种权重后决策均无变化 —— D1/D2 可能是空转检查")

    # ---- D6: D2b 自身的分辨力（篡改一条决策必须被捕获）----
    if recs:
        probe = dict(recs[0])
        probe["decision"] = "TAMPERED"
        d_p, _, _, _ = redecide(probe)
        ck("D6 变异测试：篡改一条记录的决策，D2b 的比对必须判为不符",
           d_p != probe["decision"], "篡改后重算结果仍等于篡改值 —— D2b 无分辨力")

    # ---- D4: 静态可达性 ----
    # 逐行扫描取 A2ABFT.run 的方法体（用非贪婪正则会被模块级函数截断，见 D4a 旧版误报）
    v3lines = read(os.path.join(REPRO, "multi_model_compare_ablation_v3.py")).splitlines()
    start = next((i for i, l in enumerate(v3lines)
                  if l.startswith("    def run(self, workers, task)")), None)
    seg = []
    if start is not None:
        for l in v3lines[start:]:
            if l.strip() and not l.startswith("    "):     # 回到模块级即结束
                break
            if seg and l.startswith("    def "):           # 下一个方法
                break
            seg.append(l)
    body = "\n".join(seg)
    hits = re.findall(r"reputation|weight|声望|权重", body, re.I)
    ck("D4a 论文所用实现的决策段不含 reputation/weight 标识",
       bool(seg) and not hits,
       f"决策段 {len(seg)} 行，命中 {hits}")

    callers = []
    self_path = os.path.abspath(__file__)
    for base in (SRC, os.path.join(_ROOT, "experiments")):
        for dp, _, fns in os.walk(base):
            if "__pycache__" in dp:
                continue
            for fn in fns:
                if not fn.endswith(".py"):
                    continue
                p = os.path.join(dp, fn)
                if os.path.abspath(p) == self_path:      # 检查器不得把自己当检查对象
                    continue
                for i, ln in enumerate(read(p).splitlines(), 1):
                    if "_get_reputation_weights" in ln and "def " not in ln:
                        callers.append(f"{os.path.relpath(p, _ROOT)}:{i} {ln.strip()[:70]}")
    ck("D4b _get_reputation_weights 零调用点（rho 无读者，结构上不可达决策）",
       not callers, f"发现调用点：{callers}")

    # self._reputation 的出现点分类：写入 / 日志 / 死代码返回值 / 真读取
    dwlines = read(os.path.join(SRC, "deepseek_worker.py")).splitlines()
    dstart = next((i for i, l in enumerate(dwlines)
                   if l.strip().startswith("def _get_reputation_weights")), None)
    dbody = set(range(dstart, dstart + 5)) if dstart is not None else set()
    reads = []
    for i, ln in enumerate(dwlines):
        if not re.search(r"self\._reputation\b", ln):
            continue
        lhs_write = re.match(r"\s*self\._reputation\s*\[[^\]]*\]\s*=", ln) or \
                    re.match(r"\s*self\._reputation\s*=", ln)
        if lhs_write or "print(" in ln or i in dbody:
            continue
        reads.append((i + 1, ln.strip()[:80]))
    ck("D4c self._reputation 的读取点仅为日志/死代码（无决策路径读者）",
       not reads, f"疑似真读取：{reads}")

    # ---- D5: 现有校验的恒真性 ----
    # 复现 reputation_ablation.py:394 与 464-467：两侧都从同一份 records 派生
    def legacy_consistent(decision_map):
        by_dec = dict(decision_map)
        rec_dec = dict(decision_map)
        return all(by_dec.get(k) == v for k, v in rec_dec.items())

    orig_map = {f"{r['dataset']}|{r['task_idx']}": r["decision"] for r in recs}
    tamper_map = {k: "TAMPERED" for k in orig_map}
    ck("D5 复现：旧校验在同源输入下恒真（决策全篡改后仍判一致）",
       legacy_consistent(orig_map) and legacy_consistent(tamper_map),
       "旧校验在篡改后变 False —— 需重新评估其有效性")

    # ---- 汇总 ----
    print()
    print("=" * 78)
    n_ok = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f"[{'OK  ' if ok else 'PROB'}] {name}")
        if not ok:
            print(f"        {detail}")
    print("=" * 78)
    print(f"决策中性审计：{len(checks)} 项核对，{len(problems)} 项问题")
    if problems:
        for p in problems:
            print("  -", p)
        print("DECISION_NEUTRALITY_PROBLEMS")
    else:
        print("DECISION_NEUTRALITY_OK")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
