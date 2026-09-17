"""逐格审计：论文表格数值 vs 原始实验 JSON

覆盖：
  tab:baseline / tab:bft / tab:mmlu_sweep   <- full_bft_sweep_aggregated.json
  tab:ablation / tab:hetero_compare         <- multi_model_3seed_aggregated.json
  tab:n8_scaling (表 6)                      <- correctness_50t_3s_run1_from_log.json
  §6.4 的轮数显著性声明 (t, p)               <- 同上（逐任务轮数）
  tab:real_llm                              <- deepseek_{math,knowledge,code}_fixed_20.json
  tab:attacks 的区间推导                     <- 上两份数据的逐格 min/max（check_attack_ranges）
  tab:complexity                            <- 定理代数推导 + tab:performance 实测轮数
  tab:a2a_sim_comparison (表 11)             <- multi_model_3seed_aggregated.json + Delta 算术（行 1 跨源不计算 Delta）
"""
import json
import re
import os
import math
import statistics as st

def _find_root(start):
    """向上查找项目根标记文件，使本脚本与自身所在目录无关。

    此前用 ``dirname(__file__)`` 推导 HERE/ROOT。一旦脚本或结果目录被移动，
    相对层级就会失效——而且往往是**静默指错**而非报错，审计可能"通过"却读到别处的文件。
    """
    cur = os.path.dirname(os.path.abspath(start))
    while True:
        if os.path.exists(os.path.join(cur, ".a2a_project_root")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise RuntimeError("未找到项目根：缺少 .a2a_project_root 标记文件")
        cur = parent


ROOT = _find_root(__file__)
EXP_DIR = os.path.join(ROOT, "experiments")
RESULTS = os.path.join(EXP_DIR, "results")
PAPERS = os.path.join(ROOT, "papers")

AGG = os.path.join(RESULTS, "full_bft_sweep_aggregated.json")
MULTI = os.path.join(RESULTS, "multi_model_3seed_aggregated.json")
N8 = os.path.join(RESULTS, "correctness_50t_3s_run1_from_log.json")
TEX = os.path.join(PAPERS, "iclr2027_main.tex")

TOL = 0.06


def load_json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------- verdict types ----------------
# ("cell", dataset, n, f, s, attack) -> from full sweep
# ("multi", dataset, n, f, s, attack, method) -> from multi_model_3seed_aggregated

_agg = load_json(AGG)
_agg_rows = _agg["rows"] if isinstance(_agg, dict) else _agg
SWEEP = {}
for r in _agg_rows:
    SWEEP[(r["dataset"], r["n"], r["f"], r["s"], r.get("attack") or "baseline")] = r

_multi = load_json(MULTI)
MULTI_MAP = {}
for r in _multi["rows"]:
    MULTI_MAP[(r["dataset"], r["n"], r["f"], r["s"], r["attack"], r["method"])] = r

tex = open(TEX, encoding="utf-8").read()

problems = []
checked = 0


def num(s):
    s = (s.replace("$", "").replace("\\pm", " ").replace("{", "").replace("}", "")
          .replace("\\mathbf", "").replace("\\dag", "").replace("\\textbf", "").strip())
    parts = s.split()
    return float(parts[0]), (float(parts[1]) if len(parts) > 1 else None)


def get_table(name):
    m = re.search(r"\\label\{" + name + r"\}(.*?)\\end\{tabular\}", tex, re.S)
    return m.group(1) if m else ""


def approx(a, b):
    return abs(a - b) <= TOL


def cmp4(label, keyname, paper_vals, expected):
    """paper_vals: list of 4 floats; expected: dict with *_mean/_std"""
    global checked
    exp = [expected["decision_rate_mean"], expected["decision_rate_std"],
           expected["wrong_commit_rate_mean"], expected["wrong_commit_rate_std"]]
    for i, (e, g) in enumerate(zip(exp, paper_vals)):
        checked += 1
        if not approx(e, g):
            problems.append(f"[{label}] {keyname} 第{i+1}值 论文={g} 数据={round(e, 2)}")


# ---------------- tab:baseline (gsm8k + mbpp) ----------------
def check_baseline():
    tab = get_table("tab:baseline")
    for line in tab.splitlines():
        if "&" not in line:
            continue
        cells = [c.strip() for c in line.rstrip("\\").split("&")]
        m = re.match(r"\$n=(\d+), f=(\d+), s=(\d+)\$", cells[0])
        if not m:
            continue
        n, f, s = map(int, m.groups())
        for ds, off in (("gsm8k", 1), ("mbpp", 3)):
            rec = SWEEP.get((ds, n, f, s, "baseline"))
            if rec is None:
                # n=5 rows are taken from the ablation-study deployment
                rec = MULTI_MAP.get((ds, n, f, s, "baseline", "A2A-BFT"))
            if rec is None:
                problems.append(f"[tab:baseline] 无数据 {ds}({n},{f},{s})")
                continue
            got = []
            for c in cells[off:off + 2]:
                if "\\pm" in c:
                    got += list(num(c))
            cmp4("tab:baseline", f"{ds}({n},{f},{s})", got,
                 {k: rec[k] for k in exp_keys()})


def exp_keys():
    return ["decision_rate_mean", "decision_rate_std",
            "wrong_commit_rate_mean", "wrong_commit_rate_std"]


# ---------------- tab:bft ----------------
def check_bft():
    tab = get_table("tab:bft")
    for line in tab.splitlines():
        if "&" not in line:
            continue
        cells = [c.strip() for c in line.rstrip("\\").split("&")]
        if len(cells) < 8 or not re.match(r"^(\*\*)?\d", re.sub(r"\\textbf\{|\}", "", cells[0])):
            continue
        n = int(re.sub(r"[^0-9]", "", cells[0]))
        f = int(re.sub(r"[^0-9]", "", cells[1]))
        s = int(re.sub(r"[^0-9]", "", cells[2]))
        atk = cells[3].lower()
        atk = ("strategic_reject" if "strat" in atk else
               "collusion" if "collusion" in atk else
               "sybil_attack" if "sybil" in atk else "random")
        for ds, off in (("gsm8k", 4), ("mbpp", 6)):
            rec = SWEEP.get((ds, n, f, s, atk))
            if rec is None:
                # fall back to the heterogeneous multi-model source
                rec2 = MULTI_MAP.get((ds, n, f, s, atk, "A2A-BFT"))
                if rec2 is not None:
                    got = []
                    for c in cells[off:off + 2]:
                        if "\\pm" in c:
                            got += list(num(c))
                    cmp4("tab:bft(multi-src)", f"{ds}({n},{f},{s},{atk})", got, rec2)
                    continue
                problems.append(f"[tab:bft] 无数据 {ds}({n},{f},{s},{atk})")
                continue
            got = []
            for c in cells[off:off + 2]:
                if "\\pm" in c:
                    got += list(num(c))
            cmp4("tab:bft", f"{ds}({n},{f},{s},{atk})", got,
                 {k: rec[k] for k in exp_keys()})


# ---------------- tab:mmlu_sweep ----------------
def check_mmlu():
    tab = get_table("tab:mmlu_sweep")
    for line in tab.splitlines():
        if "&" not in line:
            continue
        cells = [c.strip() for c in line.rstrip("\\").split("&")]
        if len(cells) < 6 or not re.match(r"^\d", cells[0]):
            continue
        n = int(re.sub(r"[^0-9]", "", cells[0]))
        f = int(re.sub(r"[^0-9]", "", cells[1]))
        s = int(re.sub(r"[^0-9]", "", cells[2]))
        atk = cells[3].lower()
        atk = ("strategic_reject" if "strat" in atk else "collusion" if "collusion" in atk
               else "sybil_attack" if "sybil" in atk else "random" if "random" in atk
               else "baseline")
        rec = SWEEP.get(("mmlu", n, f, s, atk))
        if rec is None:
            problems.append(f"[tab:mmlu] 无数据 ({n},{f},{s},{atk})")
            continue
        got = []
        for c in cells[4:6]:
            if "\\pm" in c:
                got += list(num(c))
        cmp4("tab:mmlu", f"({n},{f},{s},{atk})", got, {k: rec[k] for k in exp_keys()})


# ---------------- tab:ablation ----------------
ABL_VARIANT = {
    "full protocol": "A2A-BFT",
    "no view change": "A2A-BFT w/o 视图切换",
    "no sem. validation": "A2A-BFT w/o 语义验证",
    "fixed threshold": "A2A-BFT 固定阈值",
}
ABL_COLS = [("gsm8k", 5, 1, 1, "strategic_reject"),
            ("gsm8k", 8, 2, 1, "collusion"),
            ("mbpp", 5, 1, 1, "strategic_reject"),
            ("mbpp", 8, 2, 1, "collusion")]


def check_ablation():
    tab = get_table("tab:ablation")
    for line in tab.splitlines():
        if "&" not in line:
            continue
        cells = [c.strip() for c in line.rstrip("\\").split("&")]
        if len(cells) < 5:
            continue
        variant = re.sub(r"\\textbf\{|\}", "", cells[0]).strip().lower()
        method = ABL_VARIANT.get(variant)
        if method is None:
            continue
        for col, (ds, n, f, s, atk) in zip(cells[1:5], ABL_COLS):
            rec = MULTI_MAP.get((ds, n, f, s, atk, method))
            if rec is None:
                problems.append(f"[tab:ablation] 无数据 {method} {ds}({n},{f},{s},{atk})")
                continue
            d = num(col.split("/")[0])
            w = num(col.split("/")[1])
            cmp4("tab:ablation", f"{method} {ds}({n},{f},{s})",
                 [d[0], d[1], w[0], w[1]], rec)


# ---------------- tab:hetero_compare ----------------
CMP_METHOD = {
    "a2a-bft (ours)": "A2A-BFT",
    "simple majority": "Simple Majority",
    "weighted majority": "Weighted Majority",
    "a2a-sim": "A2A-Sim",
    "llm-debate": "LLM-Debate",
}
CMP_COLS = [("gsm8k", "strategic_reject"), ("gsm8k", "collusion"),
            ("mbpp", "strategic_reject"), ("mbpp", "collusion")]


def check_compare():
    tab = get_table("tab:hetero_compare")
    for line in tab.splitlines():
        if "&" not in line:
            continue
        cells = [c.strip() for c in line.rstrip("\\").split("&")]
        if len(cells) < 5:
            continue
        name = re.sub(r"\\textbf\{|\}", "", cells[0]).strip().lower()
        method = CMP_METHOD.get(name)
        if method is None:
            continue
        for col, (ds, atk) in zip(cells[1:5], CMP_COLS):
            rec = MULTI_MAP.get((ds, 8 if atk == "collusion" else 5,
                                 2 if atk == "collusion" else 1,
                                 1, atk, method))
            if rec is None:
                problems.append(f"[tab:hetero] 无数据 {method} {ds}/{atk}")
                continue
            parts = [p for p in col.split("/") if p]
            vals = [num(p) for p in parts]
            global checked
            for tag, got, exp in (
                ("decision", vals[0][0], rec["decision_rate_mean"]),
                ("accuracy", vals[1][0], rec["answer_accuracy_mean"]),
                ("wrongcommit", vals[2][0], rec["wrong_commit_rate_mean"]),
            ):
                checked += 1
                if not approx(exp, got):
                    problems.append(f"[tab:hetero] {method} {ds}/{atk} {tag} 论文={got} 数据={round(exp,2)}")


# ---------------- 表 6: n=8 adversarial boundary ----------------
def check_n8():
    global checked
    if not os.path.exists(N8):
        problems.append("[tab:n8_scaling] 缺少 correctness_50t_3s_run1_from_log.json（先运行 parse_correctness_log.py）")
        return
    d = load_json(N8)
    for r in d["scenarios"]:
        checked += 1
        print(f"  [n8] n={r['n']},f={r['f']},s={r['s']},{r['attack_type']}: "
              f"consensus={r['consensus_rate']}% correct={r['correctness_rate']}% "
              f"rounds={r['avg_rounds']} (tasks={r['total_tasks']})")
    by = {(r["n"], r["f"], r["s"], r["attack_type"]): r for r in d["scenarios"]}
    expect = {(8, 2, 1, "collusion"): (98.0, 92.7, 2.89),
              (8, 2, 1, "strategic_reject"): (98.0, 92.0, 2.92),
              (8, 0, 0, None): (100.0, 94.0, 1.03)}
    for k, (c, a, r) in expect.items():
        checked += 3
        got = by.get(k)
        if got is None:
            problems.append(f"[tab:n8_scaling] 无数据 {k}")
            continue
        if abs(got["consensus_rate"] - c) > 0.05:
            problems.append(f"[tab:n8_scaling] {k} consensus 论文={c} 数据={got['consensus_rate']}")
        if abs(got["correctness_rate"] - a) > 0.05:
            problems.append(f"[tab:n8_scaling] {k} correctness 论文={a} 数据={got['correctness_rate']}")
        if abs(got["avg_rounds"] - r) > 0.005:
            problems.append(f"[tab:n8_scaling] {k} rounds 论文={r} 数据={got['avg_rounds']}")


# ---------------- 轮数显著性 (§6.4: t, p) ----------------
def betacf(a, b, x, itmax=300, eps=3e-16):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1.0 + aa / c
        c = c if abs(c) > 1e-30 else 1e-30
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1.0 + aa / c
        c = c if abs(c) > 1e-30 else 1e-30
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def two_sided_p(t, df):
    x = df / (df + t * t)
    a, b = df / 2.0, 0.5
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    if x < (a + 1) / (a + b + 2):
        front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
        return front * betacf(a, b, x)
    front = math.exp(math.log(1 - x) * b + math.log(x) * a - lbeta) / b
    return front * betacf(b, a, 1 - x)


def check_ttest():
    """Recompute Welch t / p from the per-task round histogram of run 1 and
    compare against the claim written in §6.4 and the appendix."""
    global checked
    if not os.path.exists(N8):
        return
    d = load_json(N8)
    hist = {r["attack_type"]: r.get("round_histogram", {}) for r in d["scenarios"]}
    base_hist = hist.get(None, {})
    if not base_hist:
        problems.append("[ttest] 缺少 baseline 轮数直方图")
        return
    base = [float(k) for k, v in base_hist.items() for _ in range(v)]

    def welch(a, b):
        ma, mb = st.mean(a), st.mean(b)
        va, vb = st.variance(a), st.variance(b)
        na, nb = len(a), len(b)
        t = (ma - mb) / math.sqrt(va / na + vb / nb)
        df = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
        return t, df

    for atk in ("collusion", "strategic_reject"):
        h = hist.get(atk)
        if not h:
            continue
        atkdata = [float(k) for k, v in h.items() for _ in range(v)]
        t, df = welch(base, atkdata)
        p = two_sided_p(t, df)
        checked += 2
        print(f"  [ttest] {atk}: t={t:.2f} df={df:.1f} p={p:.2e}")
        if not (t < -13):
            problems.append(f"[ttest] {atk} 论文称 t<-13，实测 t={t:.2f}")
        if not (p < 1e-26):
            problems.append(f"[ttest] {atk} 论文称 p<1e-26，实测 p={p:.2e}")


# ---------------- tab:attacks (ranges over tab:bft configurations) ----------------
def check_attack_ranges():
    """tab:attacks aggregates ranges over GSM8K+MBPP cells of tab:bft only
    (MMLU is reported separately in tab:mmlu_sweep)."""
    global checked
    pool = []
    for r in _agg_rows:
        if r["dataset"] == "mmlu":
            continue
        pool.append((r["dataset"], r["n"], r["f"], r["s"], r.get("attack") or "baseline",
                     r["decision_rate_mean"], r["wrong_commit_rate_mean"]))
    for r in _multi["rows"]:
        if r["method"] != "A2A-BFT" or r["dataset"] not in ("gsm8k", "mbpp"):
            continue
        pool.append((r["dataset"], r["n"], r["f"], r["s"], r["attack"],
                     r["decision_rate_mean"], r["wrong_commit_rate_mean"]))

    tab = get_table("tab:attacks")
    for line in tab.splitlines():
        if "&" not in line:
            continue
        cells = [c.strip() for c in line.rstrip("\\").split("&")]
        if len(cells) < 6 or not re.search(r"[A-Za-z]", cells[0]):
            continue
        name = re.sub(r"\\textbf\{|\}", "", cells[0]).strip().lower()
        atk = ("strategic_reject" if "strategic" in name else
               "collusion" if "collusion" in name else
               "sybil_attack" if "sybil" in name else
               "random" if "random" in name else None)
        if atk is None:
            continue
        # pairs: (within dec, within wrong, below dec, below wrong); '--' -> None
        pairs = []
        for c in cells[2:6]:
            m = re.match(r"^\$(\d+\.\d+)\$--\$(\d+\.\d+)\$$", c)
            pairs.append((float(m.group(1)), float(m.group(2))) if m else None)
        for idx, (tag, bound) in enumerate((("within", True), ("below", False))):
            grp = [x for x in pool if x[4] == atk and ((x[1] >= 3 * x[2] + x[3] + 1) == bound)]
            for j, kind in ((0, "decision"), (1, "wrong")):
                cell = pairs[idx * 2 + j]
                checked += 1
                if cell is None:
                    if grp:
                        problems.append(f"[tab:attacks] {atk}/{tag}/{kind}: 论文为 -- 但数据有 {len(grp)} 个单元格")
                    continue
                if not grp:
                    problems.append(f"[tab:attacks] {atk}/{tag}/{kind}: 论文有区间但无数据")
                    continue
                lo = min((x[5 + j]) for x in grp)
                hi = max((x[5 + j]) for x in grp)
                if not (approx(cell[0], lo) and approx(cell[1], hi)):
                    problems.append(f"[tab:attacks] {atk}/{tag}/{kind} 论文={cell} 数据=({round(lo,1)}, {round(hi,1)})")


# ---------------- tab:real_llm (homogeneous DeepSeek API validation) ----------------
REAL_FILES = {
    "math": os.path.join(RESULTS, "deepseek_math_fixed_20.json"),
    "knowledge": os.path.join(RESULTS, "deepseek_knowledge_fixed_20.json"),
    "code": os.path.join(RESULTS, "deepseek_code_fixed_20.json"),
}

# (row label as it appears in the tex, domain, source config name, accept% over executed tasks)
REAL_ROWS = [
    ("Math baseline", "math", "baseline_n4", False),
    ("Math BFT", "math", "bft_n5_f1_s1", False),
    ("Math + Strategic Reject", "math", "attack_n5_strategic", False),
    ("Math + Collusion", "math", "attack_n6_collusion", False),
    ("Knowledge baseline", "knowledge", "knowledge_baseline_n4", False),
    ("Knowledge BFT", "knowledge", "knowledge_bft_n5_f1_s1", False),
    ("Code baseline", "code", "code_baseline_n4", True),
    ("Code BFT", "code", "code_bft_n5_f1_s1", True),
]


def check_real_llm():
    """tab:real_llm is the only table sourced from the homogeneous DeepSeek API run
    rather than the vLLM sweep, so it needs its own resolver.

    Its starred (code) rows quote acceptance over *executed* tasks, because every
    non-acceptance there is an API/harness error (`error_count`), not a protocol
    rejection; the paper states this in the table note.  This function reproduces
    both conventions and additionally re-derives the note's 320/291/29 arithmetic.
    """
    global checked
    for p in REAL_FILES.values():
        if not os.path.exists(p):
            problems.append(f"[tab:real_llm] 源文件缺失: {os.path.basename(p)}")
            return

    raw = {dom: load_json(p)["results"] for dom, p in REAL_FILES.items()}
    src = {dom: {r["config"]["name"]: r["results"] for r in rows} for dom, rows in raw.items()}

    tab = get_table("tab:real_llm")
    rows = {}
    for line in tab.splitlines():
        if "&" not in line:
            continue
        cells = [c.strip() for c in line.rstrip("\\").split("&")]
        if len(cells) < 4:
            continue
        label = re.sub(r"\\textbf\{|\}|\s*\(\$.*$", "", cells[0]).strip()
        if label:
            rows[label] = cells

    tot = exc = accsum = 0
    for label, dom, cfg, over_executed in REAL_ROWS:
        if label not in rows:
            problems.append(f"[tab:real_llm] 表中找不到行: {label}")
            continue
        cells = rows[label]
        res = src[dom].get(cfg)
        if res is None:
            problems.append(f"[tab:real_llm] {label}: 源数据缺少配置 {cfg}")
            continue

        acc_cell = re.sub(r"\$\^\\?[A-Za-z]+\$", "", cells[2])   # drop the ^\star marker
        # "Tasks" 列格式为 "40\,(12)$^\star$"：提交数，括号内为该配置实际完成的任务数
        task_cell = (cells[1].replace("$^\\star$", "").replace("$\\star$", "")
                     .replace("\\,", " "))
        m_done = re.search(r"\((\d+)\)", task_cell)
        tasks = int(re.search(r"(\d+)", task_cell).group(1))
        tasks_done = int(m_done.group(1)) if m_done else None
        acc, tsec = num(acc_cell)[0], num(cells[3])[0]

        executed = res["total_tasks"] - res["error_count"]
        denom = executed if over_executed else res["total_tasks"]
        exp_acc = 100.0 * res["accept_count"] / denom
        exp_tsec = res["avg_time_ms"] / 1000.0

        checked += 3
        tot += res["total_tasks"]
        exc += executed
        accsum += res["accept_count"]

        if tasks != res["total_tasks"]:
            problems.append(f"[tab:real_llm] {label}: Tasks 论文={tasks} 数据={res['total_tasks']}")
        if tasks_done is not None and tasks_done != executed:
            problems.append(f"[tab:real_llm] {label}: 完成任务数 论文={tasks_done} 数据={executed}")
        if not approx(acc, exp_acc):
            problems.append(f"[tab:real_llm] {label}: Accept% 论文={acc} 数据={round(exp_acc,2)} "
                            f"(accept={res['accept_count']} err={res['error_count']} denom={denom})")
        if not approx(tsec, exp_tsec):
            problems.append(f"[tab:real_llm] {label}: Time 论文={tsec} 数据={round(exp_tsec,2)}")
        if res["reject_count"] != 0:
            problems.append(f"[tab:real_llm] {label}: reject_count={res['reject_count']} != 0，"
                            "脚注「无任何配置发生协议层拒绝」不成立")

    # note arithmetic: 320 submitted, 291 executed, 29 API errors (28 code-baseline + 1 code-BFT)
    checked += 5
    err_b = src["code"]["code_baseline_n4"]["error_count"]
    err_f = src["code"]["code_bft_n5_f1_s1"]["error_count"]
    print(f"  [tab:real_llm] 提交={tot} 完成={exc} API失败={tot - exc} "
          f"(code-baseline {err_b} + code-BFT {err_f})")
    print(f"  [tab:real_llm] 完成任务接受率 = {100.0 * accsum / exc:.2f}%  (reject_count 全表 = "
          f"{sum(r['results']['reject_count'] for rows in raw.values() for r in rows)})")

    total_row = rows.get("Total")
    if total_row is None or int(num(total_row[1])[0]) != tot:
        problems.append(f"[tab:real_llm] Total 行 {total_row[1] if total_row else None} != 实测 {tot}")
    if tot != 320:
        problems.append(f"[tab:real_llm] 表/脚注称 320，实测 {tot}")
    if exc != 291:
        problems.append(f"[tab:real_llm] 脚注称 291 完成任务，实测 {exc}")
    if (tot - exc) != 29:
        problems.append(f"[tab:real_llm] 脚注称 29 次 API 失败，实测 {tot - exc}")
    if (err_b, err_f) != (28, 1):
        problems.append(f"[tab:real_llm] 脚注称 28/1 次失败，实测 {err_b}/{err_f}")


# ---------------- tab:complexity (theoretical, but two cells are data-derivable) ----------------
def check_complexity():
    """tab:complexity: 容错列必须与定理代数等价；轮数列必须等于 tab:performance 实测 min--max。"""
    global checked
    tab = get_table("tab:complexity")
    rows = [l for l in tab.splitlines() if l.count("&") >= 3]

    # 1) 从定理陈述推导等价形式（不是硬编码）：n >= 3f+s+1  <=>  3f+s <= n-1
    m = re.search(r"n\s*\\geq\s*3f\s*\+\s*s\s*\+\s*1", tex)
    checked += 1
    if not m:
        problems.append("[tab:complexity] 找不到定理的安全边界陈述 n >= 3f+s+1")
    else:
        derived = "3f + s \\leq n-1"          # 由 n >= 3f+s+1 移项得到
        got = None
        for l in rows:
            if "A2A-BFT" in l:
                got = l.split("&")[-1].strip().rstrip("\\").strip()
        checked += 1
        if got is None:
            problems.append("[tab:complexity] 找不到 A2A-BFT 行")
        elif derived not in got.replace("\\;", " "):
            # 严格不等号 < n-1 会比定理强 1（等价于 n >= 3f+s+2），属于差一错误
            problems.append(f"[tab:complexity] 容错列 '{got}' 与定理推导 '{derived}' 不等价"
                            "（原 < n-1 为差一错误）")

    # 2) 轮数列 vs tab:performance 实测 min--max
    perf = get_table("tab:performance")
    rounds = []
    for l in perf.splitlines():
        c = [x.strip() for x in l.rstrip("\\").split("&")]
        if len(c) >= 5 and c[1].strip().lower() in ("gsm8k", "mbpp"):
            v = re.match(r"^\$?(\d+\.\d+)\$?s?$", c[4].strip())
            if v:
                rounds.append(float(v.group(1)))
    checked += 1
    if not rounds:
        problems.append("[tab:complexity] 无法从 tab:performance 解析实测轮数")
    else:
        lo, hi = min(rounds), max(rounds)
        got = None
        for l in rows:
            if "A2A-BFT" in l:
                got = l.split("&")[2].strip()
        checked += 1
        if got is None or not (abs(lo - 2.6) < 0.06 and abs(hi - 4.5) < 0.06
                               and "2.6--4.5" in got):
            problems.append(f"[tab:complexity] 轮数列 '{got}' 与实测 [{lo}, {hi}] 不符"
                            "（原 1-3 与论文自身测量矛盾）")

    # 3) PBFT 行为标准结论
    checked += 1
    if not any("PBFT" in l and "O(n^2)" in l and "n/3" in l for l in rows):
        problems.append("[tab:complexity] PBFT 行缺失或缺 O(n^2)/f<n/3")


# ---------------- tab:a2a_sim_comparison (表 11) ----------------
def check_a2a_sim():
    """tab:a2a_sim_comparison: BFT/基线列必须来自异构三种子 JSON；Delta 列算术自洽；
    41.6% 为唯一外部引用值（已联网核对原文 arXiv:2603.01213）。"""
    global checked
    tab = get_table("tab:a2a_sim_comparison")
    lines = [l for l in tab.splitlines() if l.count("&") >= 3]

    def mrow(key):
        for l in lines:
            if key in l:
                return l
        return None

    def multi(ds, n, f, s, atk, method, key):
        for r in _multi["rows"]:
            if (r["dataset"] == ds and r["n"] == n and r["f"] == f and r["s"] == s
                    and r["attack"] == atk and r["method"] == method):
                return r[key + "_mean"], r[key + "_std"]
        return None, None

    # 行 1：无故障。BFT 列 = 异构基线 (5,0,0) 的 GSM8K / MBPP 决策率。
    # R15 修订后该行不再计算 Delta（跨源、不同度量，表注以 † 披露）
    l1 = mrow("no faults")
    checked += 1
    if not l1:
        problems.append("[tab:a2a_sim] 找不到无故障行")
    else:
        nums = re.findall(r"(\d+\.\d+)", l1)
        # nums: [41.6, 56.7, 5.8, 70.0, 11.5]（无 Delta 列；若出现 Delta 则视为格式回退）
        if len(nums) not in (5, 7):
            problems.append(f"[tab:a2a_sim] 无故障行解析异常: {nums}")
        elif len(nums) == 7:
            problems.append(f"[tab:a2a_sim] 无故障行仍含 Delta 列（应为跨源不计算）: {nums}")
        else:
            quoted, g_m, g_s, m_m, m_s = (float(x) for x in nums[:5])
            gm, gs = multi("gsm8k", 5, 0, 0, "baseline", "A2A-BFT", "decision_rate")
            mm, ms = multi("mbpp", 5, 0, 0, "baseline", "A2A-BFT", "decision_rate")
            checked += 3
            if gm is None or not (approx(g_m, gm) and approx(g_s, gs)):
                problems.append(f"[tab:a2a_sim] GSM8K 基线 {g_m}±{g_s} vs 数据 {gm}±{gs}")
            if mm is None or not (approx(m_m, mm) and approx(m_s, ms)):
                problems.append(f"[tab:a2a_sim] MBPP 基线 {m_m}±{m_s} vs 数据 {mm}±{ms}")
            checked += 1
            if abs(quoted - 41.6) > 0.06:
                problems.append(f"[tab:a2a_sim] 外部引用值 {quoted} != 41.6（原文 arXiv:2603.01213）")
            checked += 1
            if "\\dagger" not in l1:
                problems.append("[tab:a2a_sim] 无故障行缺 † 标注（跨源不同度量）")

    # 行 2：f=1 战略拒绝决策率
    l2 = mrow("strat")
    checked += 1
    if not l2:
        problems.append("[tab:a2a_sim] 找不到 f=1 决策率行")
    else:
        nums = [float(x) for x in re.findall(r"(\d+\.\d+)", l2)]
        if len(nums) < 5:
            problems.append(f"[tab:a2a_sim] f=1 行解析异常: {nums}")
        else:
            sim_m, sim_s, bft_m, bft_s, d = nums[:5]
            sm, ss = multi("gsm8k", 5, 1, 1, "strategic_reject", "A2A-Sim", "decision_rate")
            bm, bs = multi("gsm8k", 5, 1, 1, "strategic_reject", "A2A-BFT", "decision_rate")
            checked += 2
            if sm is None or not (approx(sim_m, sm) and approx(sim_s, ss)):
                problems.append(f"[tab:a2a_sim] A2A-Sim f=1 {sim_m}±{sim_s} vs 数据 {sm}±{ss}")
            if bm is None or not (approx(bft_m, bm) and approx(bft_s, bs)):
                problems.append(f"[tab:a2a_sim] BFT f=1 {bft_m}±{bft_s} vs 数据 {bm}±{bs}")
            checked += 1
            if not approx(d, bft_m - sim_m):
                problems.append(f"[tab:a2a_sim] f=1 Delta {d} != {round(bft_m-sim_m,1)}")

    # 行 3：f=1 错误提交区间（两域 min/max）+ Delta 端点 = 跨域最坏配对
    l3 = mrow("Wrong-commit")
    checked += 1
    if not l3:
        problems.append("[tab:a2a_sim] 找不到 wrong-commit 行")
    else:
        nums = [float(x) for x in re.findall(r"(\d+\.\d+)", l3)]
        if len(nums) < 6:
            problems.append(f"[tab:a2a_sim] wrong-commit 行解析异常: {nums}")
        else:
            sim_lo, sim_hi, bft_lo, bft_hi, d_lo, d_hi = nums[:6]
            sim_vals, bft_vals = [], []
            for ds in ("gsm8k", "mbpp"):
                w, _ = multi(ds, 5, 1, 1, "strategic_reject", "A2A-Sim", "wrong_commit_rate")
                b, _ = multi(ds, 5, 1, 1, "strategic_reject", "A2A-BFT", "wrong_commit_rate")
                if w is not None:
                    sim_vals.append(w)
                if b is not None:
                    bft_vals.append(b)
            checked += 2
            if not (sim_vals and approx(sim_lo, min(sim_vals)) and approx(sim_hi, max(sim_vals))):
                problems.append(f"[tab:a2a_sim] A2A-Sim wrong 区间 {sim_lo}--{sim_hi} vs 数据 "
                                f"({min(sim_vals) if sim_vals else None}, {max(sim_vals) if sim_vals else None})")
            if not (bft_vals and approx(bft_lo, min(bft_vals)) and approx(bft_hi, max(bft_vals))):
                problems.append(f"[tab:a2a_sim] BFT wrong 区间 {bft_lo}--{bft_hi} vs 数据 "
                                f"({min(bft_vals) if bft_vals else None}, {max(bft_vals) if bft_vals else None})")
            checked += 1
            # Delta = 各域 (Sim - BFT) 的最坏与最好配对：7.8-4.5=3.3, 35.5-0.0=35.5
            pairs = [round(s - b, 1) for s in sim_vals for b in bft_vals]
            if pairs and not (approx(d_lo, min(pairs)) and approx(d_hi, max(pairs))):
                problems.append(f"[tab:a2a_sim] wrong Delta ({d_lo}, {d_hi}) 与跨域配对 "
                                f"({min(pairs)}, {max(pairs)}) 不符")

    # 表注：41.6 必须被披露为唯一外部引用
    checked += 1
    note = tex[tex.find("tab:a2a_sim_comparison"):tex.find("tab:a2a_sim_comparison") + 2500]
    if "quoted directly" not in note or "41.6" not in note:
        problems.append("[tab:a2a_sim] 表注未披露 41.6% 为唯一外部引用值")


# ---------------- 承诺面：Reproducibility Statement 的承诺是否兑现 ----------------
PROMISED_FILES = [
    ("tab:baseline/bft/mmlu_sweep", "results/full_bft_sweep_aggregated.json"),
    ("tab:ablation/hetero_compare", "results/multi_model_3seed_aggregated.json"),
    ("tab:n8_scaling", "results/correctness_50t_3s_run1_from_log.json"),
    ("tab:real_llm (math)", "results/deepseek_math_fixed_20.json"),
    ("tab:real_llm (knowledge)", "results/deepseek_knowledge_fixed_20.json"),
    ("tab:real_llm (code)", "results/deepseek_code_fixed_20.json"),
]


def check_promises():
    """Reproducibility Statement 承诺"全部源代码/实验数据/模型配置可得"，且"§6.1 记录
    随机种子、超参数与硬件"。承诺即声明——必须逐项可验证，否则属 L3 级未兑现声明。"""
    global checked
    for label, rel in PROMISED_FILES:
        checked += 1
        if not os.path.exists(os.path.join(EXP_DIR, rel)):
            problems.append(f"[promise] 声明称数据全部可得，但 {label} 的源文件缺失: {rel}")

    tokens = {
        "5 个采样种子": r"\\\{42, 43, 44, 45, 46\\\}",
        "3 个采样种子": r"\\\{42, 43, 44\\\}",
        "temperature": r"temperature \$0\$",
        "max_tokens": r"max\\_tokens \$512\$",
        "GPU 型号": r"A800-SXM4-80GB",
        "CUDA 版本": r"CUDA 12\.8",
        "PyTorch 版本": r"PyTorch 2\.8\.0",
        "vLLM 版本": r"vLLM \\citep\{vllm\} \$0\.11\$",
        "四个模型清单": r"Llama-3\.1-8B-Instruct",
    }
    for name, pat in tokens.items():
        checked += 1
        if not re.search(pat, tex):
            problems.append(f"[promise] 承诺 §6.1 记录 {name}，但未找到")

    # R12-4：任何提及 A800 的表述都必须给出 GPU 数量。主文 Reproducibility Statement 曾
    # 只写 "on NVIDIA A800-SXM4-80GB GPUs"，数量仅见于 §6.4 与附录——只有 1 张卡的复现者
    # 会照做并失败。承诺必须自足，不能依赖读者去别处找。
    for ln, line in enumerate(tex.splitlines(), 1):
        if "A800" not in line:
            continue
        checked += 1
        if not re.search(r"[Tt]wo\s+(?:NVIDIA\s+)?A800", line):
            problems.append(f"[promise] 第 {ln} 行提及 A800 却未给出 GPU 数量：{line.strip()[:70]}")

    for stmt in ("Reproducibility Statement", "AI Use Statement"):
        checked += 1
        if stmt not in tex:
            problems.append(f"[promise] 缺少必需声明：{stmt}")


if __name__ == "__main__":
    check_baseline()
    check_bft()
    check_mmlu()
    check_ablation()
    check_compare()
    check_attack_ranges()
    check_n8()
    check_ttest()
    check_real_llm()
    check_complexity()
    check_a2a_sim()
    check_promises()

    print(f"\n已核对数值: {checked}")
    print("问题数:", len(problems))
    for p in problems:
        print("  ", p)
