# -*- coding: utf-8 -*-
"""第五轮：结论段也完整落在第 9 页（再回收约 350 字符）。

全部为措辞压缩：把已由附录/不计页数的声明承接的实现细节移出正文，
任何结论、数字与限定条件都不删。
"""
import io
import sys

PATH = "iclr2027_main.tex"
lines = io.open(PATH, encoding="utf-8", newline="").read().split("\n")

EDITS = []

# L176 §4.4：实现细节交给附录 A.4.3；Scope 句与首句合并
EDITS.append((
    176,
    "The reputation score is an incentive and accountability signal",
    "The reputation score is an incentive and accountability signal, not an input to the vote-counting rule: Equation~\\ref{eq:commit} aggregates raw vote \\emph{counts}, so reputation cannot alter a commit decision---the sweep runs with uniform weights ($w_i{=}1$) and contains no reputation logic in its consensus path (Section~\\ref{sec:experiments}), so no reported decision depends on this component. The reference implementation maintains per-agent scores, a 10-round voting history, and suspect counters, and escalates penalties for persistent misbehaviour (Algorithm~\\ref{alg:reputation}); weighting validator selection and excluding persistent offenders are specified extensions the released code does \\emph{not} realise, and no deployment here subsamples validators. The tiered structure (aggressive $-0.25$ for persistent rejecters, reward $+0.1$ for correct votes, mild $-0.05$ for honest mistakes, neutral drift $-0.02$) is \\emph{intended} to provide graduated deterrence against strategic rejection; Section~\\ref{sec:rep_ablation} measures how far the released trigger falls short of that intent. ABSTAIN is never ``correct'': the predicate of Algorithm~\\ref{alg:reputation} is a disjunction, since the form $(v_i = \\textsc{Accept}) = c$ would score abstention on an \\emph{incorrect} proposal as correct and could pay the reward for it (Section~\\ref{sec:rep_ablation}).",
    ["0.25", "0.1", "0.05", "0.02", "Accept", "w_i{=}1"],
    "L176 声誉小节压缩",
))

# L121 §4.2：压缩重复表述
EDITS.append((
    121,
    "Verification involves re-computing the solution",
    "Verification re-computes the solution and compares results. Formally, writing $\\hat{V}$ for the validator's check (the ground-truth oracle $V$ is defined in Section~\\ref{sec:task}), $\\hat{V}(T, s) = 1$ iff $s$ matches the ground truth (or an equivalent formulation) in the \\emph{execution-validated} domain, where the check is error-free; in the \\emph{semantically validated} domain (free-form reasoning and multiple-choice QA), $\\hat{V}(T, s) = 1$ iff at least $k$ of $m$ verifiers agree \\citep{zheng2023llm}, with $k = \\lceil 2m/3 \\rceil$; the verifier error then falls to the binomial tail $\\sum_{j=0}^{k-1}\\binom{m}{j}p_h^{\\,j}(1-p_h)^{m-j}$ rather than $(1-p_h)^m$, where $p_h$ is the probability that an honest validator correctly accepts a valid proposal. In our experiments code generation (MBPP) is execution-validated while mathematics (GSM8K) and knowledge QA (MMLU) are semantically validated, each validator using a \\emph{single} self-model judge ($m{=}1$), so redundancy comes \\emph{across} validators via Phase~3 rather than within-validator committees; a mild self-preference bias is possible when a validator shares the primary's model, though one-model-per-replica makes this rare. The released judge emits a discrete verdict, ABSTAIN marking an explicit UNCERTAIN outcome (the band $[0.4, 0.6]$ on a calibrated probability); an ABSTAIN contributes 0 to $\\phi(\\pi)$.",
    ["0.4", "0.6", "k = \\lceil 2m/3 \\rceil", "p_h"],
    "L121 验证段压缩",
))

# L250 §6.1：3 seeds/n=90 细节交给声明
EDITS.append((
    250,
    "\\textbf{Reproducibility:} All protocol-level fault-tolerance experiments",
    "\\textbf{Reproducibility:} All protocol-level fault-tolerance experiments share one heterogeneous four-model deployment with 5 seeds and 50 tasks per (configuration, seed, dataset), i.e., $n{=}250$ per cell (7{,}750 tasks over 31 cells); task sets are drawn per seed by a seeded shuffle over GSM8K \\citep{gsm8k}, MBPP \\citep{mbpp}, and MMLU \\citep{mmlu} and reused across configurations for paired comparison. \\textbf{No simulation:} every reported number comes from real LLM inference ($7{,}750$ fault sweep + $4{,}320$ ablation/baseline + $770$ API tasks); seeds, models, hardware, injection, and the reputation measurement are specified in the Reproducibility Statement and Appendix~\\ref{app:attacks}.",
    ["7{,}750", "31 cells", "4{,}320", "770", "n{=}250"],
    "L250 §6.1 压缩",
))

# L314 消融：压缩措辞
EDITS.append((
    314,
    "The ablation yields four consistent findings.",
    "The ablation yields four consistent findings. \\textbf{(i) View change is the core liveness component:} removing it collapses decisions from $74.4 \\pm 8.4\\%$ to $4.5 \\pm 3.9\\%$ (GSM8K, strategic rejection) and to $0\\%$ (MBPP, both attacks)---blocked rounds never rotate the primary, confirming Theorem~\\ref{thm:liveness}. \\textbf{(ii) Semantic validation is the prerequisite for heterogeneous consensus:} under naive exact-match comparison, heterogeneous replicas almost never agree byte-for-byte, so valid proposals are rejected indefinitely and the code domain deadlocks ($0$--$1.1\\%$ decisions)---Validate must be semantic, not syntactic. \\textbf{(iii) Dynamic thresholds prevent attack-induced deadlock:} a fixed majority threshold drives every strategic-rejection round on GSM8K into the pending region ($0.0 \\pm 0.0\\%$, all seeds), whereas attack-adaptive thresholds restore $74.4 \\pm 8.4\\%$. \\textbf{(iv) Safety is preserved:} at most $10.0 \\pm 3.3\\%$ wrong commits on GSM8K and \\emph{never} on MBPP (pooled $95\\%$ Wilson interval $[0.0, 4.1]\\%$ at $n{=}90$)---on execution-validated domains every committed solution passes all test assertions by construction.",
    ["74.4", "4.5", "1.1", "10.0", "4.1", "n{=}90"],
    "L314 消融段压缩",
))

# L335 结论：收尾句压缩
EDITS.append((
    335,
    "We presented A2A-BFT",
    "We presented A2A-BFT, a Byzantine fault-tolerant consensus protocol for Agent-to-Agent collaboration with provable safety and liveness under $n \\geq 3f + s + 1$. A fully real-LLM evaluation (7{,}750-task four-model fault sweep, $n{=}250$/cell, plus ablation and baseline studies) shows liveness under every evaluated attack and safety that binds where the theory predicts: zero wrong commits on execution-validated tasks within the boundary, violations below it, and oracle-bounded wrong commits on semantic tasks. Implications, privacy, and related work: Appendix~\\ref{sec:discussion}.",
    ["7{,}750", "n{=}250", "3f + s + 1"],
    "L335 结论收尾压缩",
))

FAILS = []
before = after = 0
for idx, prefix, new, must, tag in EDITS:
    old = lines[idx - 1]
    before += len(old)
    after += len(new)
    if not old.startswith(prefix):
        FAILS.append((tag, f"L{idx} 前缀不符", old[:110]))
        continue
    missing = [m for m in must if m not in new]
    if missing:
        FAILS.append((tag, f"L{idx} 缺少关键内容 {missing}", new[:110]))
        continue
    lines[idx - 1] = new

if FAILS:
    print(f"[ABORT] {len(FAILS)} 条未通过，文件未写入：")
    for tag, why, s in FAILS:
        print(f"  [FAIL] {tag}: {why}\n      {s}")
    sys.exit(1)

io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(lines))
print(f"完成 {len(EDITS)} 条，涉改行字符 {before} -> {after}（{after-before:+d}）")
