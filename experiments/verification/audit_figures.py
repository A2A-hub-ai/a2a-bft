"""图-表一致性审计（第 10 轮新增层）

覆盖论文中三张"有数据"的图，检查它们与已审计的表格/算法是否互相矛盾：

  fig:attack_resistance      <- full_bft_sweep_aggregated.json + multi_model_3seed_aggregated.json
                                vs tab:attacks 的区间（内含性检查）
  fig:performance_comparison <- full_bft_sweep_aggregated.json
                                vs tab:performance 的逐格相等检查
  fig:reputation_mechanism   <- Algorithm 1 的三档常数（+0.1 / -0.05 floor 0.5 / -0.25 floor 0.1）

另外检查两项"跨工件披露一致性"与"新鲜度"：
  - 边界内 collusion 单元不存在于 n=250 扫描中，只存在于 n=90 对比部署；
    因此 fig:attack_resistance 的题注与 tab:attacks 的题注都必须披露 n=90。
    表已披露而图未披露 = 题注缺陷。
  - 图 PDF 的**内容指纹**必须与来源一致：`figures/.figsource.json` 记录的
    generate_figures.py 逻辑指纹与各数据文件 md5，任一与当前不符即为陈旧产物。
    （基准用内容而非 mtime —— 改一行注释不该把图判为陈旧；见下方 §3 注释）

用法: python experiments/verification/audit_figures.py
      依赖 matplotlib（导入 papers/generate_figures.py 以复用其取数逻辑）
"""
import importlib.util
import json
import os
import re
import sys

def _find_root(start):
    """向上查找项目根标记文件，使本脚本与自身所在目录无关（见 audit_table_numbers.py）。"""
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
TEX = os.path.join(PAPERS, "iclr2027_main.tex")
FIGDIR = os.path.join(PAPERS, "figures")
AGG = os.path.join(RESULTS, "full_bft_sweep_aggregated.json")
MULTI = os.path.join(RESULTS, "multi_model_3seed_aggregated.json")

problems = []
checked = 0

# ---- 复用绘图脚本自身的取数逻辑：审计"图到底画了什么"，再独立解析表格 ----
# generate_figures.py 在模块级 import matplotlib，因此本审计无法脱离 matplotlib 运行。
# 缺依赖时必须给出可操作的提示并**判失败**——图件层未被验证 ≠ 图件层通过。
_GF = os.path.join(PAPERS, "generate_figures.py")
_spec = importlib.util.spec_from_file_location("gf", _GF)
gf = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(gf)
except ImportError as e:
    sys.stderr.write(
        f"\n[audit_figures] 无法加载 {_GF}\n"
        f"  原因: 缺少依赖 {e.name}\n"
        f"  图件层因此【未被验证】（这是失败，不是跳过）。\n"
        f"  修复: python -m pip install -r requirements.txt\n"
        f"        （或单独装 matplotlib: pip install 'matplotlib>=3.7.0'）\n\n")
    sys.exit(1)

tex = open(TEX, encoding="utf-8").read()
sweep = gf._load_sweep()
multi = gf._load_multi()

ATTACKS = ["random", "strategic_reject", "sybil_attack", "collusion"]

# 各组贡献给 fig:attack_resistance 的扫描单元数（"黄金计数"）。
# _sweep_mean 对组内单元取平均，删掉一格不会变成 None、只会静默改变均值，
# 因此必须固定计数：任何增删单元都会在这里被抓住。
GOLDEN_CELLS = {
    ("gsm8k", "random", "within"): 2, ("gsm8k", "random", "below"): 1,
    ("gsm8k", "strategic_reject", "within"): 1, ("gsm8k", "strategic_reject", "below"): 1,
    ("gsm8k", "sybil_attack", "within"): 1, ("gsm8k", "sybil_attack", "below"): 0,
    ("gsm8k", "collusion", "within"): 0, ("gsm8k", "collusion", "below"): 2,
    ("mbpp", "random", "within"): 2, ("mbpp", "random", "below"): 1,
    ("mbpp", "strategic_reject", "within"): 1, ("mbpp", "strategic_reject", "below"): 1,
    ("mbpp", "sybil_attack", "within"): 1, ("mbpp", "sybil_attack", "below"): 0,
    ("mbpp", "collusion", "within"): 0, ("mbpp", "collusion", "below"): 2,
}


def get_tabular(label):
    m = re.search(r"\\label\{" + label + r"\}(.*?)\\end\{tabular\}", tex, re.S)
    return m.group(1) if m else ""


def ranges_of(label):
    """把 tab:attacks 的 4 个区间列解析为 {attack: [within_dec, within_wrong, below_dec, below_wrong]}"""
    out = {}
    for line in get_tabular(label).splitlines():
        if line.count("&") < 5:
            continue
        c = [x.strip() for x in line.rstrip("\\").split("&")]
        nm = re.sub(r"\\textbf\{|\}", "", c[0]).strip().lower()
        k = ("strategic_reject" if "strategic" in nm else
             "collusion" if "collusion" in nm else
             "sybil_attack" if "sybil" in nm else
             "random" if "random" in nm else None)
        if not k:
            continue
        pr = []
        for cc in c[2:6]:
            mm = re.match(r"^\$(\d+\.\d+)\$--\$(\d+\.\d+)\$$", cc)
            pr.append((float(mm.group(1)), float(mm.group(2))) if mm else None)
        out[k] = pr
    return out


# ---------------- fig:attack_resistance vs tab:attacks ----------------
def check_attack_figure():
    global checked
    rang = ranges_of("tab:attacks")
    if not rang:
        problems.append("[fig:attack] 无法解析 tab:attacks")
        return

    for ds in ("gsm8k", "mbpp"):
        within, below = gf._sweep_partition(sweep, ds)
        # 0) 黄金计数：组内单元数必须与预期一致
        for atk in ATTACKS:
            for grp, tag in ((within, "within"), (below, "below")):
                got = sum(1 for r in grp if r["attack"] == atk)
                checked += 1
                exp = GOLDEN_CELLS[(ds, atk, tag)]
                if got != exp:
                    problems.append(f"[fig:attack] 单元数漂移: {ds}/{atk}/{tag} 实测 {got}，预期 {exp}"
                                    "（_sweep_mean 会静默改均值）")
        for atk in ATTACKS:
            # (a) 边界内决策率 —— 必须落在 tab:attacks 的同名区间内
            v = gf._sweep_mean(within, "decision_rate", atk, ds)
            if v is None and atk == "collusion":
                v = gf._multi_get(multi, ds, 8, 2, 1, "collusion", "decision_rate")
            checked += 1
            if v is None:
                problems.append(f"[fig:attack] (a) {ds}/{atk} 无值（图会画空柱）")
            elif rang[atk][0] and not (rang[atk][0][0] - 0.06 <= v <= rang[atk][0][1] + 0.06):
                problems.append(f"[fig:attack] (a) {ds}/{atk}={v:.1f} 超出 tab:attacks 区间 {rang[atk][0]}")

            # (b) 错误提交率，边界内 / 越界
            for grp, idx, tag in ((within, 1, "within"), (below, 3, "below")):
                pr = rang[atk][idx]
                if pr is None:
                    continue
                w = gf._sweep_mean(grp, "wrong_commit_rate", atk, ds)
                if w is None and atk == "collusion" and grp is within:
                    w = gf._multi_get(multi, ds, 8, 2, 1, "collusion", "wrong_commit_rate")
                checked += 1
                if w is None:
                    problems.append(f"[fig:attack] (b) {ds}/{atk}/{tag} 无值（图会画空柱）")
                elif not (pr[0] - 0.06 <= w <= pr[1] + 0.06):
                    problems.append(f"[fig:attack] (b) {ds}/{atk}/{tag}={w:.1f} 超出区间 {pr}")


# ---------------- fig:performance_comparison vs tab:performance ----------------
FIG_PICKS = [(4, 0, 0, "baseline"), (4, 1, 0, "random"), (4, 1, 0, "strategic_reject"),
             (5, 1, 1, "random"), (6, 0, 0, "baseline"), (5, 2, 0, "collusion")]


def sweep_get(ds, key, n, f, s, atk):
    for r in sweep:
        if (r["dataset"], r["n"], r["f"], r["s"], r["attack"]) == (ds, n, f, s, atk):
            return r[key + "_mean"]
    return None


def parse_performance_table():
    """从 tex 解析 tab:performance，而不是在脚本里硬编码——否则审计的是脚本自己。"""
    rows = {}
    cur = None
    for line in get_tabular("tab:performance").splitlines():
        if "&" not in line or "\\\\" not in line:
            continue
        if line.strip().startswith(("\\toprule", "\\midrule", "\\bottomrule")):
            continue
        c = [x.strip() for x in line.rstrip("\\").split("&")]
        if len(c) < 5:
            continue
        if c[0]:
            mm = re.search(r"n=(\d+),\s*f=(\d+),\s*s=(\d+)", c[0])
            if not mm:
                continue
            atk = ("strategic_reject" if "Strat" in c[0] else
                   "collusion" if "Collusion" in c[0] else "baseline")
            cur = (int(mm.group(1)), int(mm.group(2)), int(mm.group(3)), atk)
        if cur is None:
            continue
        ds = c[1].strip().lower()
        if ds not in ("gsm8k", "mbpp"):
            continue
        def val(s):
            s = s.replace("$", "").replace("s", "").replace("\\dag", "")
            return float(s)
        rows[(ds, cur)] = (val(c[2]), val(c[3]), val(c[4]))
    return rows


def check_performance_figure():
    global checked
    # 1) 图自身完整性：6 个 pick x 2 数据集 x 3 指标 必须齐全
    for ds in ("gsm8k", "mbpp"):
        for p in FIG_PICKS:
            for key in ("avg_time", "avg_calls", "avg_rounds"):
                checked += 1
                if sweep_get(ds, key, *p) is None:
                    problems.append(f"[fig:perf] 缺失 {ds} n={p[0]},f={p[1]},s={p[2]},{p[3]} / {key}")

    # 2) 与 tab:performance 的共有配置逐格相等（表值来自 tex）
    paper = parse_performance_table()
    if not paper:
        problems.append("[fig:perf] 无法解析 tab:performance")
        return
    for (ds, cfg), exp in paper.items():
        if cfg not in FIG_PICKS:
            continue
        for key, e in zip(("avg_time", "avg_calls", "avg_rounds"), exp):
            v = sweep_get(ds, key, *cfg)
            checked += 1
            if v is None:
                problems.append(f"[fig:perf] vs tab:performance: {ds} {cfg}/{key} 无值")
            elif abs(round(v, 1) - e) > 0.06:
                problems.append(f"[fig:perf] vs tab:performance: {ds} {cfg}/{key} "
                                f"图/数据={round(v, 1)} 表={e}")
    # 3) 表中的每个配置都必须在图里出现，否则两工件覆盖面不一致
    for (ds, cfg) in paper:
        checked += 1
        if cfg not in FIG_PICKS:
            problems.append(f"[fig:perf] tab:performance 的 {ds} {cfg} 未出现在图中")


# ---------------- fig:reputation_mechanism vs Algorithm 1 ----------------
REP_TIERS = ["-0.25", "-0.05", "+0.1", "0.7", "max(r, 0.3)", "floor 0.5", "floor 0.1"]


def check_reputation_figure():
    """算法常数的一致性靠源码文本比对（图为示意图，无数据可重算）。

    R11 起算法为四档（+0.1 / -0.05 floor 0.5 / -0.25 floor 0.1 / -0.02 中性漂移），
    且图中不得再出现未实现的选择权重（R10-1 收窄后的披露对等要求）。
    """
    global checked
    m = re.search(r"\\label\{alg:reputation\}(.*?)\\end\{algorithmic\}", tex, re.S)
    if not m:
        problems.append("[fig:reputation] 找不到 Algorithm 1")
        return
    algo = m.group(1)
    for tok in ("0.25", "0.05", "0.1", "0.7", "0.5", "0.02"):
        checked += 1
        if tok not in algo:
            problems.append(f"[fig:reputation] Algorithm 1 未出现常数 {tok}，与图不一致")
    # 中性漂移分支与实现逐行一致性的关键标记
    checked += 1
    if "text{ok}" not in algo:
        problems.append("[fig:reputation] Algorithm 1 未按实现使用 'ok'（按提案质量判投票正确性）")
    # 选择权重是"已披露但未实现"的设计扩展（R10-1），不得画进 Algorithm 1 规则图
    gen_src = open(os.path.join(PAPERS, "generate_figures.py"), encoding="utf-8").read()
    checked += 1
    if "Selection weight" in gen_src:
        problems.append("[fig:reputation] 绘图脚本仍把未实现的选择权重画进 Algorithm 1 规则图")
    # 选择权重的 floor 只应出现在正文公式与图中，不应被当作算法步骤
    checked += 1
    if "max(r_i, 0.3)" not in tex:
        problems.append("[fig:reputation] 正文缺少 max(r_i, 0.3) 选择权重公式（图中有）")


def _balanced(tex, open_idx):
    """open_idx 指向 '{'，返回配平花括号内的内容（忽略 \\{ 转义）。"""
    depth = 0
    i = open_idx
    while i < len(tex):
        ch = tex[i]
        escaped = i > 0 and tex[i - 1] == "\\"
        if ch == "{" and not escaped:
            depth += 1
        elif ch == "}" and not escaped:
            depth -= 1
            if depth == 0:
                return tex[open_idx + 1:i]
        i += 1
    return None


def caption_for_label(tex, label):
    """取得 \\label{label} 之前**紧邻**的 \\caption{...} 正文。

    早先的实现用"label 前 900 字符窗口"匹配披露关键词，属启发式：只要窗口内
    任何位置出现 n=90 形状的 token（例如相邻表格的题注）就会静默通过。这里改为
    解析真正的 caption（配平花括号），并要求 caption 与 label 之间不夹其它内容。
    返回 (正文, None) 或 (None, 原因)。
    """
    m = re.search(r"\\label\{" + re.escape(label) + r"\}", tex)
    if not m:
        return None, "找不到 label"
    idx = tex.rfind(r"\caption{", 0, m.start())
    if idx < 0:
        return None, "label 之前没有 caption"
    body = _balanced(tex, idx + len(r"\caption"))
    if body is None:
        return None, "caption 花括号不配平"
    end = idx + len(r"\caption") + len(body) + 2   # '{' + body + '}'
    between = tex[end:m.start()]
    if between.strip():
        return None, f"caption 与 label 之间夹有其它内容: {between.strip()[:60]!r}"
    return body, None


# ---------------- 跨工件披露一致性 + 新鲜度 ----------------
def check_disclosure_and_freshness():
    global checked
    # 1) 边界内 collusion 不可能来自 n=250 扫描
    checked += 1
    in_sweep = [r for r in sweep
                if r["attack"] == "collusion" and r["n"] >= 3 * r["f"] + r["s"] + 1]
    if in_sweep:
        problems.append(f"[disclosure] n=250 扫描中出现了 {len(in_sweep)} 个边界内 collusion 单元，"
                        "题注中『来自 n=90 部署』的说法需复核")

    # 2) 图题注与表题注都必须披露 n=90 来源（在各自的 caption 正文内，非窗口）
    for label in ("fig:attack_resistance", "tab:attacks"):
        checked += 1
        body, why = caption_for_label(tex, label)
        if body is None:
            problems.append(f"[disclosure] 无法取得 {label} 的题注：{why}")
            continue
        if not re.search(r"n\{?=\}?90|\$n\{=}90", body):
            problems.append(f"[disclosure] {label} 的题注未披露边界内 collusion 来自 n=90 部署")

    # 3) 新鲜度：**内容级**判定，基准是 papers/figures/.figsource.json 里记录的
    #    (generate_figures.py 的逻辑指纹, 各数据文件 md5) —— 由生成脚本在出图时写入。
    #    2026-09-17 由 mtime 改为内容指纹，原因：mtime 会把「只改注释/文档串」判为陈旧
    #    （实测修一处 docstring 后 3 张图误报）。误报多了守卫就会被无视，而它要防的
    #    R16-1 形态（数据重新生成、图没重出）本质是**内容变化**，不是时间戳变化。
    #    守卫本身必须可被推翻：缺指纹文件即判失败，不允许静默降级为"不检查"。
    STAMP = os.path.join(FIGDIR, ".figsource.json")
    GEN = os.path.join(PAPERS, "generate_figures.py")
    checked += 1
    if not os.path.exists(STAMP):
        problems.append("[freshness] 缺少 .figsource.json 内容指纹 —— 新鲜度守卫无法判定；"
                        "请重跑 papers/generate_figures.py")
    elif not hasattr(gf, "_logic_sha1"):
        problems.append("[freshness] generate_figures.py 未提供 _logic_sha1，指纹不可计算")
    else:
        stamp = json.load(open(STAMP, encoding="utf-8"))
        cur_logic = gf._logic_sha1(GEN)
        if stamp.get("generator_logic_sha1") != cur_logic:
            problems.append(
                "[freshness] generate_figures.py 的逻辑已变（指纹 "
                f"{str(stamp.get('generator_logic_sha1'))[:8]} -> {cur_logic[:8]}），图未重出")
        for f, deps in gf.FIGURE_DEPS.items():
            checked += 1
            if not os.path.exists(os.path.join(FIGDIR, f)):
                problems.append(f"[freshness] 缺少 {f}")
                continue
            for d in deps:
                rec = (stamp.get("data_md5") or {}).get(d)
                cur = gf._md5(os.path.join(RESULTS, d))
                if rec != cur:
                    problems.append(
                        f"[freshness] {f} 所依赖的 {d} 内容已变（{str(rec)[:8]} -> "
                        f"{cur[:8]}），图未重出，可能为陈旧产物")


if __name__ == "__main__":
    check_attack_figure()
    check_performance_figure()
    check_reputation_figure()
    check_disclosure_and_freshness()

    print(f"\n已核对项数: {checked}")
    print("问题数:", len(problems))
    for p in problems:
        print("  ", p)
    sys.exit(1 if problems else 0)
