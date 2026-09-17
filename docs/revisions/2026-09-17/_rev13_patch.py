#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 13 轮（修订层）补丁：修复 PAT 修订自身引入的 5 处缺陷。

每条改动都带命中数断言：任何一条不匹配即整体放弃写入，论文保持原样。
"""
import io
import sys

PATH = "iclr2027_main.tex"
t = io.open(PATH, encoding="utf-8", newline="").read()
orig = t
applied = []
fail = []


def rep(old, new, n, tag):
    global t
    c = t.count(old)
    if c != n:
        fail.append(f"[FAIL] {tag}: 期望 {n} 处，实得 {c}\n   {old[:130]}")
        return
    t = t.replace(old, new)
    applied.append(tag)


# ---------------------------------------------------------------------------
# R13-1（P1）：§6.3 把越界归因于"共谋者推动篡改提案"，与修正后的机制冲突
# ---------------------------------------------------------------------------
rep(
    r"where $\theta_{accept} = 0$ lets two colluders carry a tampered proposal alone.",
    r"where $\theta_{accept} = 0$ lets two Byzantine ACCEPTs offset the honest REJECTs of a "
    r"non-tampering primary's wrong proposal.",
    1, "R13-1 §6.3 越界机制措辞")

# ---------------------------------------------------------------------------
# R13-2（P3）：越界条件未声明软故障投票行为；保守口径应为 7f+3s+3>=3n
# 同步三处：定理证明梗概（正文）、Property 4（附录）、边界分析（附录）
# ---------------------------------------------------------------------------
rep(
    r"rejected by $n{-}1{-}f$ honest validators against $f$ Byzantine ACCEPTs, clears "
    r"$\theta_{accept}$ exactly when $7f + 2s + 3 \geq 3n$",
    r"rejected by $n{-}1{-}f{-}s$ honest validators (soft faults abstaining, the worst case) "
    r"against $f$ Byzantine ACCEPTs, clears $\theta_{accept}$ exactly when $7f + 3s + 3 \geq 3n$",
    1, "R13-2a §5.1 定理证明梗概")

rep(
    r"rejected by the $n{-}1{-}f$ honest validators while all $f$ Byzantine validators vote "
    r"ACCEPT: then $\phi = f - 0.5(n{-}1{-}f) \geq \theta_{accept}$ exactly when "
    r"$7f + 2s + 3 \geq 3n$.",
    r"rejected by the $n{-}1{-}f{-}s$ honest validators (the worst case, with soft faults "
    r"abstaining) while all $f$ Byzantine validators vote ACCEPT: then "
    r"$\phi = f - 0.5(n{-}1{-}f{-}s) \geq \theta_{accept}$ exactly when $7f + 3s + 3 \geq 3n$; "
    r"if soft faults REJECT alongside the honest validators the constant weakens to "
    r"$7f + 2s + 3 \geq 3n$.",
    1, "R13-2b Property 4 越界段")

rep(
    r"($f$ ACCEPT votes against $n{-}1{-}f$ honest REJECTs clear $\theta_{accept}$ whenever "
    r"$7f + 2s + 3 \geq 3n$)",
    r"($f$ ACCEPT votes against $n{-}1{-}f{-}s$ honest REJECTs, soft faults abstaining, clear "
    r"$\theta_{accept}$ whenever $7f + 3s + 3 \geq 3n$)",
    1, "R13-2c 附录 A.2.5 边界分析")

# ---------------------------------------------------------------------------
# R13-3（P3）：Property 4 用 "honest" 描述 REJECT 方（R12 已修 Property 6，此漏）
# ---------------------------------------------------------------------------
rep(
    r"but not through the Byzantine primary alone: honest validators \emph{actively} reject "
    r"($-0.5$ each), so with $f{-}1$ Byzantine and $n{-}f$ honest validators",
    r"but not through the Byzantine primary alone: non-Byzantine validators \emph{actively} "
    r"reject ($-0.5$ each), so with $f{-}1$ Byzantine and $n{-}f$ non-Byzantine validators",
    1, "R13-3 Property 4 honest->non-Byzantine")

# ---------------------------------------------------------------------------
# R13-4（P3）：§4.2 断言二项尾和 "decreases exponentially with m"
# k=ceil(2m/3) 的取整使小 m 非单调（0.028@m=3 但 0.0815@m=5）
# ---------------------------------------------------------------------------
rep(
    r"The error probability for semantic tasks, $P(\text{error}) = \sum_{j=0}^{k-1} \binom{m}{j} "
    r"p_h^j (1-p_h)^{m-j}$, decreases exponentially with $m$ (e.g., $P(\text{error}) \approx 0.028$ "
    r"for $p_h = 0.9$, $m = 3$); deploying $m > 1$ verifiers per validator is a deployment-time "
    r"option that trades additional inference cost for lower verification error.",
    r"This tail decays exponentially only once $k/m$ is held fixed: the ceiling in "
    r"$k = \lceil 2m/3\rceil$ makes small-$m$ choices non-monotone ($0.028$ at $m{=}3$ but "
    r"$0.0815$ at $m{=}5$ for $p_h = 0.9$), so deployments should pick $m$ as a multiple of "
    r"three; otherwise $m > 1$ trades additional inference cost for lower verification error.",
    1, "R13-4 §4.2 尾和单调性")

# ---------------------------------------------------------------------------
# R13-5（P3）：记号重载 —— 判定函数 V_i(\pi) 与真值 oracle V、检查 \hat V 并列
# 统一为 \hat V_i（验证者 i 的检查），消除 (1) 式与 §4.2 引入的 \hat V 分裂
# ---------------------------------------------------------------------------
rep(
    r"    V_i(\pi) = \begin{cases}",
    r"    \hat{V}_i(\pi) = \begin{cases}",
    1, "R13-5a 式(1) 判定函数记号")

rep(
    r"$vote_i = (V_i(\pi), signature_i)$",
    r"$vote_i = (\hat{V}_i(\pi), signature_i)$",
    1, "R13-5b 票定义记号")

rep(
    r"writing $\hat{V}$ for the validator's check",
    r"writing $\hat{V}_i$ for validator $i$'s check",
    1, "R13-5c §4.2 \hat V 下标")

# ---------------------------------------------------------------------------

if fail:
    print("补丁未应用，论文保持原样：")
    for f in fail:
        print(f)
    sys.exit(1)

io.open(PATH, "w", encoding="utf-8", newline="").write(t)
print(f"应用 {len(applied)} 条修改，文件长度 {len(orig)} -> {len(t)} 字符（净 {len(t)-len(orig):+d}）")
for a in applied:
    print("  ok:", a)
