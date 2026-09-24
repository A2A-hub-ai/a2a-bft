#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 13 轮审计：修订层（PAT 修正引入的新代数式 + 新文本的自洽性）。

背景：2026-09-17 的 PAT 分诊给论文注入了 45 处新文本与 42 条压缩。这批文本
从未被任何检查器触碰过，其中两个代数条件（附录 A.2 的软故障假阳性闭式与
Property 4 的越界条件）是**全新的数学命题** —— L1/L4/L6/L7 对它们天然免疫，
只有 L2（公式推导代数）能发现错误。

本脚本分两部分：
  A. L2 代数验算：用 Fraction 精确算术重推每条新式，并穷举参数空间验证
     论文给出的闭式与"从 phi 定义直接判定"严格等价。
  B. 修订文本自洽性：从 .tex 解析并核对多处的口径是否一致。

输出：已核对项数 / 问题数。任何问题都会打印 [PROBLEM] 行。
"""
import io
import os
import re
import itertools
import math
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_tex():
    cur = HERE
    for _ in range(6):
        cand = os.path.join(cur, "papers", "iclr2027_main.tex")
        if os.path.exists(cand):
            return cand
        cur = os.path.dirname(cur)
    raise FileNotFoundError("iclr2027_main.tex not found")


TEX_PATH = _find_tex()
TEX = io.open(TEX_PATH, encoding="utf-8").read()

checked = 0
problems = []


def ck(label, ok, detail=""):
    global checked
    checked += 1
    if not ok:
        problems.append(f"[PROBLEM] {label}: {detail}")


# ----------------------------------------------------------------------------
# A. L2 代数验算
# ----------------------------------------------------------------------------

def theta_acc(n, f, s):
    return n - 1 - 2 * f - s


def theta_rej(n, f, s):
    return F(-(n - 1 - f), 2)


def phi_fp(n, f, s, p):
    """软故障假阳性场景：拜占庭主，f-1 个拜占庭验证者 ACCEPT，
    s 个软故障以概率 p 误 ACCEPT（否则弃权），n-f-s 个诚实验证者 REJECT。"""
    return (f - 1) + s * p - F(1, 2) * (n - f - s)


def cond_fp_paper(n, f, s, p):
    """论文闭式：7f + 2sp + 3s < 3n"""
    return 7 * f + 2 * s * p + 3 * s < 3 * n


def cond_fp_direct(n, f, s, p):
    """从 phi 定义直接判安全：phi < theta_accept"""
    return phi_fp(n, f, s, p) < theta_acc(n, f, s)


def phi_sub_rej(n, f, s):
    """越界场景（软故障与诚实者一起 REJECT）：主未篡改但提案错，
    f 个拜占庭 ACCEPT，n-1-f 个非拜占庭 REJECT。"""
    return f - F(1, 2) * (n - 1 - f)


def phi_sub_abs(n, f, s):
    """越界场景（软故障弃权）：REJECT 数只剩 n-1-f-s。"""
    return f - F(1, 2) * (n - 1 - f - s)


def cond_sub_paper(n, f, s):
    """论文条件：7f + 2s + 3 >= 3n"""
    return 7 * f + 2 * s + 3 >= 3 * n


def cond_sub_abs(n, f, s):
    """保守条件（软故障弃权）：7f + 3s + 3 >= 3n"""
    return 7 * f + 3 * s + 3 >= 3 * n


GRID = [(n, f, s)
        for n in range(1, 31)
        for f in range(0, 12)
        for s in range(0, 12)
        if 3 * f + s + 1 <= n]          # 只看边界内的配置

PS = [F(k, 20) for k in range(0, 21)]   # p 取 0, 0.05, ..., 1

# A1: 软故障假阳性闭式与直接判据严格等价
mismatch = []
for (n, f, s) in GRID:
    for p in PS:
        if cond_fp_paper(n, f, s, p) != cond_fp_direct(n, f, s, p):
            mismatch.append((n, f, s, p))
ck("A1 闭式 7f+2sp+3s<3n 与 phi 直接判据等价",
   not mismatch, f"{len(mismatch)} 例不等价，例如 {mismatch[:3]}")

# A2: 边界 n=3f+s+1 上退化为 sp < f+1.5
mismatch = []
for f in range(0, 12):
    for s in range(0, 12):
        n = 3 * f + s + 1
        for p in PS:
            lhs = cond_fp_paper(n, f, s, p)
            rhs = (s * p < f + F(3, 2))
            if lhs != rhs:
                mismatch.append((n, f, s, p))
ck("A2 边界退化 sp<f+1.5", not mismatch,
   f"{len(mismatch)} 例不等价，例如 {mismatch[:3]}")

# A2b: 论文正文的三个实例化
ck("A2b p=1 时 s <= f+1",
   all((cond_fp_paper(3 * f + s + 1, f, s, F(1)) == (s <= f + 1))
       for f in range(0, 12) for s in range(0, 12)))
ck("A2c f=0 时退化为 sp < 1.5",
   all((cond_fp_paper(s + 1, 0, s, p) == (s * p < F(3, 2)))
       for s in range(0, 12) for p in PS))

# A3: 越界条件
mismatch = []
for (n, f, s) in GRID:
    if (phi_sub_rej(n, f, s) >= theta_acc(n, f, s)) != cond_sub_paper(n, f, s):
        mismatch.append((n, f, s))
ck("A3 越界条件 7f+2s+3>=3n 与 phi 直接判据等价（软故障投 REJECT 口径）",
   not mismatch, f"{len(mismatch)} 例不等价，例如 {mismatch[:3]}")

# A3b: 越界场景发生在边界**之外**（n < 3f+s+1），故扫描范围必须在边界外。
# 论文现在采用的是保守口径（软故障弃权，与 Theorem 5.1 的 worst-case
# soft-fault abstention 一致）：7f+3s+3 >= 3n。验证它与 phi 直接判据等价。
mismatch = []
for f in range(1, 12):
    for s in range(0, 12):
        for n in range(f + 1, 3 * f + s + 1):
            if (phi_sub_abs(n, f, s) >= theta_acc(n, f, s)) != cond_sub_abs(n, f, s):
                mismatch.append((n, f, s))
ck("A3b 保守越界条件 7f+3s+3>=3n 与 phi 直接判据等价（边界外）",
   not mismatch, f"{len(mismatch)} 例不等价，例如 {mismatch[:3]}")

# A3b2: 旧式 7f+2s+3>=3n 的左边更小（2s < 3s），因此**更宽松**：它会把
# 一批实际可被越界的配置判为"不可能"。这些配置正是新式补上的。
residual = []
for f in range(1, 12):
    for s in range(1, 12):
        for n in range(f + 1, 3 * f + s + 1):
            if cond_sub_abs(n, f, s) and not cond_sub_paper(n, f, s):
                residual.append((n, f, s))
ck("A3b2 旧式在 s>0 时确实漏判（存在新式成立而旧式不成立的配置）",
   bool(residual), "未找到反例 —— 两式可能已等价，需复核")
print(f"     [info] 旧式漏判的边界外配置共 {len(residual)} 个，例如 {residual[:4]}")

# A3c: 论文实际实验网格不受两种口径差异影响
SWEEP_GRID = [(4, 0, 0), (4, 1, 0), (5, 0, 0), (5, 1, 1), (5, 2, 0),
              (6, 0, 0), (6, 2, 0)]
divergent = [c for c in SWEEP_GRID
             if cond_sub_paper(*c) != cond_sub_abs(*c)]
ck("A3c 两种口径在论文实验网格上给出相同判定", not divergent,
   f"判定分歧：{divergent}")

# A3d: 论文正文引用的两个实例
ck("A3d n=5,f=2 判'可越界'", cond_sub_abs(5, 2, 0), "17 >= 15 应成立")
ck("A3d2 n=6,f=2 判'不可能'", not cond_sub_abs(6, 2, 0), "17 >= 18 应不成立")

# A4: gap 公式
mismatch = []
for (n, f, s) in GRID:
    g1 = theta_acc(n, f, s) - theta_rej(n, f, s)
    g2 = F(3, 2) * (n - 1) - F(5, 2) * f - s
    if g1 != g2:
        mismatch.append((n, f, s, g1, g2))
ck("A4 gap = 1.5(n-1)-2.5f-s", not mismatch, f"{len(mismatch)} 例不符")

# A4b: 边界处 gap = 2f+0.5s 且 gap > 1.5f
bad = []
for f in range(1, 12):
    for s in range(0, 12):
        n = 3 * f + s + 1
        g = theta_acc(n, f, s) - theta_rej(n, f, s)
        if g != 2 * f + F(1, 2) * s or not (g > F(3, 2) * f):
            bad.append((n, f, s, g))
ck("A4b 边界处 gap=2f+0.5s 且 gap>1.5f", not bad, f"{len(bad)} 例不符，例如 {bad[:3]}")

# A5: Lemma 5.3 —— 全诚实 ACCEPT 时 phi >= theta_accept 等价于 f >= s
mismatch = []
for (n, f, s) in GRID:
    phi = (n - 1 - f - s) - F(1, 2) * (f + s)
    if (phi >= theta_acc(n, f, s)) != (f >= s):
        mismatch.append((n, f, s))
ck("A5 Lemma 5.3 的 f>=s 条件", not mismatch, f"{len(mismatch)} 例不符")

# A5b: 附录 A.2 的对抗性软故障式
mismatch = []
for (n, f, s) in GRID:
    phi_adv = (n - 1 - f - s) - F(1, 2) * f - F(1, 2) * s
    g1 = phi_adv
    g2 = n - 1 - F(3, 2) * f - F(3, 2) * s
    if g1 != g2:
        mismatch.append((n, f, s))
    if n == 3 * f + s + 1:
        if phi_adv != F(3, 2) * f - F(1, 2) * s:
            mismatch.append(("boundary", n, f, s))
ck("A5b phi_min^adversarial = n-1-1.5f-1.5s 及边界退化 1.5f-0.5s",
   not mismatch, f"{len(mismatch)} 例不符，例如 {mismatch[:3]}")

# A6: 二项尾和
def binom_tail(m, p_h):
    k = math.ceil(2 * m / 3)
    return sum(math.comb(m, j) * p_h ** j * (1 - p_h) ** (m - j)
               for j in range(0, k))
ck("A6 正文 P(error)≈0.028 (m=3, p_h=0.9)", abs(binom_tail(3, 0.9) - 0.028) < 5e-4,
   f"实得 {binom_tail(3, 0.9):.6f}")
# 注意方向：k=ceil(2m/3)<m，判据允许少数验证者出错，故二项尾和**大于**
# (1-p_h)^m（后者是"m 个验证者全部出错"的联合概率）。PAT 的 P2 正是据此
# 判定原式 (1-p_h)^m 低估了误差。此处断言方向必须与之一致。
ck("A6b 二项尾和 > (1-p_h)^m（k<m 允许少数出错）",
   binom_tail(3, 0.9) > (1 - 0.9) ** 3,
   f"tail={binom_tail(3,0.9):.4f} vs (1-p)^m=0.001")
ck("A6c 小 m 处非单调（tail(5)=0.0815 > tail(3)=0.0280）",
   binom_tail(5, 0.9) > binom_tail(3, 0.9),
   f"实得 m=5:{binom_tail(5,0.9):.4f} m=3:{binom_tail(3,0.9):.4f}")

# A6d: 论文 §4.2 曾断言 P(error) "decreases exponentially with m"。在
# k=ceil(2m/3) 下 k/m 随 m 振荡（m=3q -> 2/3，m=3q+2 -> 4/5），小 m 处不单调。
# 注意：非单调性是**数学事实**，改动论文不会改变它；因此这里的检查对象是
# **论文是否仍作此声称**，而不是数学性质本身。
TAIL = {m: binom_tail(m, 0.9) for m in range(1, 16)}
nonmono = [(m, TAIL[m], TAIL[m - 1]) for m in range(2, 16) if TAIL[m] > TAIL[m - 1]]
ck("A6d 非单调性确实存在（数学事实，供正文引用）", bool(nonmono),
   "未观察到非单调，k 的定义可能已变")
ck("A6e 正文不再声称 P(error) 随 m 指数下降",
   not re.search(r"decreases exponentially with \$m\$", TEX),
   "仍含 'decreases exponentially with $m$'")
print("     [info] k=ceil(2m/3) 下的 P(error)，p_h=0.9：")
print("            " + "  ".join(f"m={m}:{TAIL[m]:.4f}" for m in range(1, 10)))

# A7: 活性界
p_acc = 0.9 ** 2
ck("A7 p_h^(n-1-f-s)=0.81 (n=5,f=1,s=1)", abs(p_acc - 0.81) < 1e-12, f"{p_acc}")
ck("A7b (1-0.81)^10 ≈ 6e-8", abs((1 - p_acc) ** 10 / 6.13e-8 - 1) < 0.05,
   f"{(1-p_acc)**10:.3e}")

# A8: 论文声明"全部实验配置都在条件内" —— 用真实实验网格核对
SWEEP_CELLS = [(4, 0, 0), (4, 1, 0), (5, 0, 0), (5, 1, 1), (5, 2, 0),
               (6, 0, 0), (6, 2, 0)]
bad = [c for c in SWEEP_CELLS if not cond_fp_paper(c[0], c[1], c[2], F(1))]
ck("A8 实验网格全部满足假阳性条件（p=1 最坏）", not bad, f"违例：{bad}")
bad = [c for c in SWEEP_CELLS if not (c[1] >= c[2])]
ck("A8b 实验网格全部满足 f >= s", not bad, f"违例：{bad}")


# ----------------------------------------------------------------------------
# B. 修订文本自洽性（从 .tex 解析，不硬编码）
# ----------------------------------------------------------------------------

def grab(pattern, ctx=260):
    """返回 [(行号, 匹配片段)]"""
    out = []
    for m in re.finditer(pattern, TEX):
        ln = TEX[:m.start()].count("\n") + 1
        out.append((ln, TEX[m.start():m.start() + ctx].replace("\n", " ")))
    return out


# B1: 越界机制的四处表述必须一致
SUB_BOUNDARY_SITES = [
    (r"7f \+ 2s \+ 3 \\geq 3n", "Property 4 / 定理证明 / 附录"),
]
hits = grab(r"7f \+ 2s \+ 3 \\geq 3n")
# 修复后旧式只应作为"若软故障也 REJECT 则退化为"的附带说明出现，故只记录数量。
print(f"     [info] 旧式 7f+2s+3>=3n 剩余出现 {len(hits)} 处（行 {[h[0] for h in hits]}），"
      f"应仅为退化情形说明")
ck("B1 旧式已不再作为主条件（≤2 处）", len(hits) <= 2,
   f"{[(h[0], h[1][:70]) for h in hits]}")

# B1b: 软故障弃权口径（论文的定理假设）下的保守形式必须在正文与附录一致
hits3 = grab(r"7f \+ 3s \+ 3 \\geq 3n")
ck("B1b 保守越界条件 7f+3s+3>=3n 出现在 ≥3 处", len(hits3) >= 3,
   f"仅 {len(hits3)} 处：{[h[0] for h in hits3]}")
ck("B1c 旧式仅作为'软故障也 REJECT'的退化情形保留",
   len(hits) <= 2, f"{[(h[0], h[1][:70]) for h in hits]}")

# B2: 越界机制不得再出现"拜占庭主篡改即可零诚实支持提交"
bad_phr = grab(r"tampered proposal alone|zero honest support")
ck("B2 无'篡改提案可零诚实支持提交'的旧表述", not bad_phr,
   f"{[(h[0], h[1][:90]) for h in bad_phr]}")

# B2b: 出现 "colluders carry a tampered proposal" 即为与附录冲突
conflict = grab(r"colluders? carry a tampered")
ck("B2b §6.3 未把越界归因于'共谋者推动篡改提案'", not conflict,
   f"{[(h[0], h[1][:90]) for h in conflict]}")

# B3: Property 4 里的 REJECT 方应写 non-Byzantine（软故障也会 REJECT）
# B3: Property 4 描述 REJECT 方时，若写成 "n{-}1{-}f ... honest"（后面不接 -s）
# 就等于把软故障也当成投 REJECT，与 Theorem 5.1 的 abstention 假设冲突。
# 注意负向断言：n{-}1{-}f{-}s 才是软故障弃权口径下的正确写法。
p4 = TEX[TEX.find("Property 4: Commit Validity"):TEX.find("Property 5:")]
bad = re.findall(r"n\{-\}1\{-\}f(?!\{-\}s)[^.]{0,40}?honest", p4)
ck("B3 Property 4 的 REJECT 方未把软故障计入诚实者", not bad, f"实得 {bad}")
ck("B3b Property 4 区分 non-Byzantine 与 honest",
   "non-Byzantine validators" in p4, "未出现 non-Byzantine validators")

# B4: 软故障行为假设在越界条件处是否声明
p4_body = re.sub(r"\s+", " ", p4)
ck("B4 Property 4 越界段声明了软故障投票行为",
   bool(re.search(r"abstain|abstention|REJECT", p4_body, re.I)) and
   bool(re.search(r"soft[- ]fault", p4_body, re.I)),
   "未在同一段内同时出现 soft-fault 与关于其投票行为/弃权的说明")

# B5: Definition 3.1/3.2 的限定齐备（2026-09-22 soft fault 升为独立 Definition 3.2，
# 提取范围 = Fault Model + Soft fault 两个连续 definition 环境）
_d0 = TEX.find("\\begin{definition}[Fault Model]")
_d1 = TEX.find("\\end{definition}", TEX.find("\\begin{definition}[Soft fault]"))
d31 = TEX[_d0:_d1]
ck("B5 Definition 3.2 含 'never ACCEPTs an invalid proposal'",
   "never ACCEPTs an invalid proposal" in d31)
ck("B5c Definition 3.2 soft-fault 条目含故障语义（intermittent, non-malicious）",
   "intermittent, non-malicious" in d31)
ck("B5d Fault Model 已移除幽灵参数 p_s", "$p_s$" not in d31)
ck("B5e Fault Model 的 s 条目引用 Soft fault 定义",
   "soft-fault agents (Definition~\\ref{def:softfault})" in d31)
ck("B5b Definition 3.1/3.2 覆盖 s<=f 条件", bool(re.search(r"s \\leq f", d31)))

# B6: s<=f 在阈值/引理处同步
ck("B6 §4.3 阈值处有 s<=f 指注", bool(re.search(r"provided \$s \\leq f\$", TEX)))
ck("B6b Lemma 5.3 证明含 f>=s", bool(re.search(r"requires \$f \\geq s\$", TEX)))

# B7: 记号 V / \hat V / V_i 不得重载。
# 注意：式(1) 处在 equation 环境内，**没有 $ 包裹**，故正则不能要求 $ 前缀
# ——否则检查会静默匹配 0 处而报"通过"（实测被负向测试抓到过一次）。
n_Vi = len(re.findall(r"V_i\(", TEX))            # 裸的判定函数 V_i(\pi)
n_hat = len(re.findall(r"\\hat\{?V\}?_i?\(", TEX))  # 判定函数 \hat V_i(\pi)
n_oracle = len(re.findall(r"ground-truth oracle \$V\$|oracle \$V\$", TEX))
ck("B7 记号拆分：\\hat V_i 已用于判定函数", n_hat > 0,
   "\\hat V_i( 出现 %d 次" % n_hat)
ck("B7b 裸 V_i( 不再用作判定函数", n_Vi == 0,
   f"仍有 {n_Vi} 处 V_i(")

# B8: 数字一致性（旧值必须清零，新值必须出现）
OLD = ["1{,}217", "0.413", "0.458", "9 and 5 of 20"]
NEW = ["1{,}186", "0.337", "0.391", "10 and 9 of 20"]
for v in OLD:
    ck(f"B8 旧值已清除 {v}", v not in TEX, f"仍出现 {TEX.count(v)} 次")
for v in NEW:
    ck(f"B8b 新值存在 {v}", v in TEX)

# B9: label / ref 双向
labels = set(re.findall(r"\\label\{([^}]+)\}", TEX))
refs = set(re.findall(r"\\(?:ref|eqref|autoref)\{([^}]+)\}", TEX))
ck("B9 无悬空引用", not (refs - labels), f"{sorted(refs - labels)[:6]}")
orphan = {l for l in (labels - refs) if not l.startswith(("eq:", "alg:", "fig:", "tab:", "thm:", "lem:", "def:"))}

# B10: 四条 domain 映射必须与代码一致（MBPP=执行验证）
ck("B10 §4.2 明确 MBPP 执行验证 / GSM8K·MMLU 语义验证",
   bool(re.search(r"code generation \(MBPP\) is execution-validated while mathematics \(GSM8K\) and knowledge QA \(MMLU\) are semantically validated", TEX)))

# B11: 页限相关 —— 正文三个表都加了 \small
body = TEX[:TEX.find("\\bibliography{references}")]
tables = re.findall(r"\\begin\{table\}(.*?)\\end\{table\}", body, re.S)
small_ok = sum(1 for t in tables if "\\small" in t)
ck("B11 正文表格均带 \\small", small_ok == len(tables),
   f"{small_ok}/{len(tables)}")

# B12: 硬声明对账 —— "No simulation" 与 "never" 类绝对声明
ck("B12 'No simulation' 声明存在", "\\textbf{No simulation:}" in TEX)
ck("B12b 执行验证域 0.0 错误提交的措辞保留", "0.0 \\pm 0.0" in TEX)


# ---------------------------------------------------------------------------
# C. 压缩回归：修订期共 5 轮压缩，每轮都对"新文本必须仍含这些关键数字/符号"
#    作过断言。把它们全量提取，核对**当前** tex 仍然包含 —— 即后续补丁没有
#    把压缩当时刻意保住的信息弄丢。（只解析，不执行这些脚本。）
# ---------------------------------------------------------------------------
import ast  # noqa: E402

# 修订脚本归档位置（2026-09-17 整理：papers/revision_2026-09-17 -> docs/revisions/2026-09-17）
_REPO_ROOT = os.path.dirname(os.path.dirname(HERE))          # experiments/verification -> 项目根
REV_DIR = os.path.join(_REPO_ROOT, "docs", "revisions", "2026-09-17")
if not os.path.isdir(REV_DIR):                                # 兼容整理前的旧布局
    REV_DIR = os.path.join(os.path.dirname(TEX_PATH), "revision_2026-09-17")
kws = []
scanned = 0
if os.path.isdir(REV_DIR):
    for fn in sorted(os.listdir(REV_DIR)):
        if not (fn.startswith("_pat_compress") and fn.endswith(".py")):
            continue
        try:
            tree = ast.parse(io.open(os.path.join(REV_DIR, fn),
                                     encoding="utf-8").read())
        except SyntaxError:
            continue
        scanned += 1
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append"
                    and node.args
                    and isinstance(node.args[0], ast.Tuple)
                    and len(node.args[0].elts) >= 4
                    and isinstance(node.args[0].elts[3], ast.List)):
                continue
            for e in node.args[0].elts[3].elts:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    kws.append((fn, e.value))

ck("C0 压缩脚本被扫描到（基数 > 0）", scanned >= 4, f"仅扫描 {scanned} 个")
uniq = sorted({k for _, k in kws})
missing = [k for k in uniq if k not in TEX]
ck("C1 压缩期断言保留的关键词全部仍在", not missing,
   f"{len(missing)}/{len(uniq)} 丢失：{missing[:8]}")
print(f"     [info] 解析 {scanned} 个压缩脚本，取得保留关键词 {len(uniq)} 个（去重后）")


# ----------------------------------------------------------------------------
print("=" * 66)
print("第 13 轮 · 修订层审计（L2 代数 + 文本自洽性）")
print("=" * 66)
for p in problems:
    print(p)
print("-" * 66)
print(f"已核对项数: {checked}")
print(f"问题数: {len(problems)}")
print("REVISION_LAYER_DONE")
