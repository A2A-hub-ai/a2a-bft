# -*- coding: utf-8 -*-
"""第四轮：正文压回 9 页。

1) §6.7 Limitations 由子节改为段首粗体（省去子节标题的垂直空间），内容只压缩措辞；
2) 正文三个表加 \\small，行高与附录表（\\footnotesize/\\small）保持一致；
3) 若干段落做最后一遍措辞压缩，数字全部保留。
"""
import io
import sys

PATH = "iclr2027_main.tex"
lines = io.open(PATH, encoding="utf-8", newline="").read().split("\n")
orig_n = len(lines)

EDITS = []

# ---------- 1. §6.7 Limitations 改为段首粗体 ----------
EDITS.append((329, "\\subsection{Limitations}", "", [], "删除子节标题（内容改为段首粗体）"))
EDITS.append((
    331,
    "A2A-BFT assumes DID-authenticated channels",
    "\\textbf{Limitations.} A2A-BFT assumes DID-authenticated channels (Ed25519), and consensus quality depends on LLM capability: the fault-free decision rates ($55$--$59\\%$ GSM8K, $11$--$15\\%$ MMLU) imply weaker validation reliability on semantic domains, which the lower-bound form of Lemma~\\ref{lem:acceptance} accommodates. The implementation scales to $n \\leq 10$, and ablation cells ($n{=}90$) limit power for fine-grained comparisons though the reported contrasts far exceed sampling noise; the tracker is decision-neutral but mis-specified (Section~\\ref{sec:rep_ablation}), and the MMLU collapse reflects model capability rather than the protocol. Privacy and societal considerations: Appendix~\\ref{sec:discussion}.",
    ["55", "59", "11", "15", "n{=}90", "n \\leq 10"],
    "Limitations 改为段首粗体并压缩",
))

# ---------- 2. 正文三个表加 \small ----------
for idx, tag in [(231, "表 tab:complexity 加 \\small"),
                 (259, "表 tab:baseline 加 \\small"),
                 (281, "表 tab:bft 加 \\small")]:
    EDITS.append((idx, "\\centering", "\\centering\\small", [], tag))

# ---------- 3. 最后一批措辞压缩 ----------
EDITS.append((
    303,
    "Three findings emerge.",
    "Three findings emerge. \\textbf{(i) Safety is exactly as strong as the validation oracle, and the boundary is tight.} On MBPP, every configuration within the safety boundary commits a wrong answer in $\\mathbf{0.0 \\pm 0.0\\%}$ of tasks ($n{=}250$/cell) regardless of attack, whereas all $n{=}5, f{=}2$ configurations below the boundary violate safety ($5.6$--$9.6\\%$), where $\\theta_{accept} = 0$ lets two colluders carry a tampered proposal alone. \\textbf{(ii) On semantic domains, eventual acceptance trades safety for liveness under sustained attack.} GSM8K wrong commits rise to $11.6$--$23.2\\%$ within the boundary: a Byzantine primary submits a plausible-but-wrong answer, weak 8B judges accept it with non-negligible probability, and retry semantics keep sampling until one passes validation---the system \\emph{does} decide ($74$--$91\\%$) but inherits the judge's error rate. \\textbf{(iii) Decision rates rise under attack} (up to $98\\%$ vs.\\ $59.2\\%$ fault-free): Byzantine primaries inject extra proposals that eventually clear validation, so we report wrong commits as the primary safety metric.",
    ["0.0", "5.6", "9.6", "11.6", "23.2", "74", "91", "98", "59.2"],
    "L303 结论段压缩",
))

EDITS.append((
    319,
    "Three observations follow.",
    "Three observations follow. \\textbf{First, high decision rates are not safety.} All voting- and debate-based baselines decide on every task, yet under collusion commit incorrect answers in $16.7$--$63.4\\%$: unvalidated majority voting converts Byzantine injections and honest errors into committed consensus, whereas the full protocol forgoes such decisions ($60$--$74\\%$ decision rates under attack). \\textbf{Second, unverified debate amplifies attacks:} LLM-Debate \\citep{du2024improving} is the least safe on code ($63.4 \\pm 5.8\\%$ wrong commits under collusion), because debate without a verification oracle lets Byzantine agents drag honest replicas toward corrupted solutions. \\textbf{Third, the correct-when-decided gap matters:} conditioned on committing, A2A-BFT reaches $83$--$100\\%$ answer correctness across all eight attacked scenarios versus $37$--$89\\%$ for the baselines; against A2A-Sim, our GSM8K wrong-commit rates are within noise (descriptive only at $n{=}3$ seeds), but A2A-Sim decides fewer tasks ($62.2\\%$ vs.\\ $74.4\\%$) and collapses on code ($34.4$--$35.5\\%$ against our $0.0{\\pm}0.0$).",
    ["16.7", "63.4", "60", "74", "5.8", "83", "100", "37", "89", "62.2", "74.4", "34.4", "35.5"],
    "L319 基线观察压缩",
))

EDITS.append((
    121,
    "Verification involves re-computing the solution",
    "Verification involves re-computing the solution and comparing results. Formally, writing $\\hat{V}$ for the validator's check (the ground-truth oracle $V$ is defined in Section~\\ref{sec:task}), $\\hat{V}(T, s) = 1$ iff $s$ matches the ground truth (or an equivalent formulation) in the \\emph{execution-validated} domain, where the check is error-free; in the \\emph{semantically validated} domain (free-form reasoning and multiple-choice QA), $\\hat{V}(T, s) = 1$ iff at least $k$ of $m$ verifiers agree \\citep{zheng2023llm}, with $k = \\lceil 2m/3 \\rceil$; the verifier error then falls to the binomial tail $\\sum_{j=0}^{k-1}\\binom{m}{j}p_h^{\\,j}(1-p_h)^{m-j}$, not to $(1-p_h)^m$ (which needs unanimity), where $p_h$ is the probability that an honest validator correctly accepts a valid proposal. In our experiments code generation (MBPP) is execution-validated while mathematics (GSM8K) and knowledge QA (MMLU) are semantically validated, each validator using a \\emph{single} self-model judge ($m{=}1$), so redundancy comes \\emph{across} validators via Phase~3 rather than within-validator committees; a mild self-preference bias is possible when a validator shares the primary's model, though one-model-per-replica makes this infrequent. The released judge emits a discrete verdict, ABSTAIN marking an explicit UNCERTAIN outcome (the band $[0.4, 0.6]$ on a calibrated probability); an ABSTAIN contributes 0 to $\\phi(\\pi)$.",
    ["0.4", "0.6", "k = \\lceil 2m/3 \\rceil", "p_h"],
    "L121 验证段压缩",
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
print(f"完成 {len(EDITS)} 条编辑，行数 {orig_n} -> {len(lines)}")
print(f"涉改行字符 {before} -> {after}（{after-before:+d}）")
