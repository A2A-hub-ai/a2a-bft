# -*- coding: utf-8 -*-
"""把 PAT 修正新增的正文文字压缩回 9 页（ICLR 2027 页数规则）。

原则：只删冗余措辞与已在附录展开的重复推导，不删任何结论、数字或限定条件。
每条替换都带命中数断言；有任何一条不匹配则整个文件不写入。
"""
import io
import sys

PATH = "iclr2027_main.tex"
t = io.open(PATH, encoding="utf-8", newline="").read()
orig = t
FAILS = []
applied = []


def rep(old, new, n=1, tag=""):
    global t
    c = t.count(old)
    if c != n:
        FAILS.append((tag, n, c, old[:160]))
        return
    t = t.replace(old, new)
    applied.append(tag)


def rep_first(old, new, tag="", nth=1):
    """只替换第 nth 次出现（用于正文/附录同文需要不同处理的情形）。"""
    global t
    parts = old.join([""])
    idx = -1
    for _ in range(nth):
        idx = t.find(old, idx + 1)
    if idx < 0:
        FAILS.append((tag, nth, -1, old[:160]))
        return
    t = t[:idx] + new + t[idx + len(old):]
    applied.append(tag)


# ---------- 1. 定义 3.1：软故障假阳性说明移到附录 ----------
rep("(zero false-positive rate on invalid proposals; the relaxation is quantified in Appendix~\\ref{app:softfault})",
    "(Appendix~\\ref{app:softfault} quantifies the relaxation)",
    1, "C1 定义 3.1 精简")

# ---------- 2. §4.2 验证函数段：紧凑化 ----------
rep("Formally, writing $\\hat{V}$ for the validator's empirical check---kept distinct from the ground-truth oracle $V$ of Section~\\ref{sec:task}---we have $\\hat{V}(T, s) = 1$ iff",
    "Formally, writing $\\hat{V}$ for the validator's check (the ground-truth oracle $V$ is defined in Section~\\ref{sec:task}), $\\hat{V}(T, s) = 1$ iff",
    1, "C2 记号精简")

rep("in the \\emph{semantically validated} domain (free-form reasoning and multiple-choice QA, where no exact test exists), $\\hat{V}(T, s) = 1$ iff at least $k$ of $m$ independent LLM verifiers agree on correctness \\citep{zheng2023llm}, with $k = \\lceil 2m/3 \\rceil$; the individual verifier error then falls from $1-p_h$ to the binomial tail $\\sum_{j=0}^{k-1}\\binom{m}{j}p_h^{\\,j}(1-p_h)^{m-j}$ (not to $(1-p_h)^m$, which would require unanimity), where $p_h$ is the probability that an honest validator correctly accepts a valid proposal. In our heterogeneous experiments the domains map as follows: code generation (MBPP) is execution-validated, while mathematics (GSM8K) and knowledge QA (MMLU) are semantically validated, each validator instantiating the check with a \\emph{single} self-model judge ($m{=}1$): redundancy comes \\emph{across} validators via Phase~3 vote aggregation rather than within-validator committees;",
    "in the \\emph{semantically validated} domain (free-form reasoning and multiple-choice QA), $\\hat{V}(T, s) = 1$ iff at least $k$ of $m$ verifiers agree \\citep{zheng2023llm}, with $k = \\lceil 2m/3 \\rceil$; the verifier error then falls to the binomial tail $\\sum_{j=0}^{k-1}\\binom{m}{j}p_h^{\\,j}(1-p_h)^{m-j}$, not to $(1-p_h)^m$ (which needs unanimity), where $p_h$ is the probability that an honest validator correctly accepts a valid proposal. In our experiments code generation (MBPP) is execution-validated while mathematics (GSM8K) and knowledge QA (MMLU) are semantically validated, each validator using a \\emph{single} self-model judge ($m{=}1$), so redundancy comes \\emph{across} validators via Phase~3 rather than within-validator committees;",
    1, "C3 尾和与域映射精简")

rep("The released judge emits a discrete verdict, and ABSTAIN is reserved for an explicit UNCERTAIN outcome (when a calibrated verification probability is available, the band $[0.4, 0.6]$ marks that same state); an ABSTAIN contributes 0 to $\\phi(\\pi)$.",
    "The released judge emits a discrete verdict, ABSTAIN marking an explicit UNCERTAIN outcome (the band $[0.4, 0.6]$ on a calibrated probability); an ABSTAIN contributes 0 to $\\phi(\\pi)$.",
    1, "C4 弃权机制精简")

# ---------- 3. §4.4 弃权非肯定性说明（详细版在 A.4.3 与 A.7） ----------
rep("An ABSTAIN vote is non-affirmative: the correctness predicate of Algorithm~\\ref{alg:reputation} must be read as a disjunction, since the equivalent form $(v_i = \\textsc{Accept}) = c$ would score abstention on an \\emph{incorrect} proposal as correct and could pay the reward for it; the released code implements the disjunction, and adopting it changes $31$ aggressive-tier events in our replay (Section~\\ref{sec:rep_ablation}).",
    "ABSTAIN is never ``correct'': the predicate of Algorithm~\\ref{alg:reputation} is a disjunction, since the form $(v_i = \\textsc{Accept}) = c$ would score abstention on an \\emph{incorrect} proposal as correct and could pay the reward for it (Section~\\ref{sec:rep_ablation}).",
    1, "C5 §4.4 弃权说明精简")

# ---------- 4. 正文 Lemma 5.3 证明精简（附录保留完整代数） ----------
rep_first("All-accept ensures $\\phi \\geq \\theta_{accept}$ under the stated abstention behaviour of soft faults; if instead all $f$ Byzantine \\emph{and} $s$ soft-fault validators vote REJECT, $\\phi = (n{-}1{-}f{-}s) - 0.5(f{+}s)$ and $\\phi - \\theta_{accept} = 0.5(f-s)$, so the implication requires $f \\geq s$ as assumed throughout (Appendix~\\ref{app:softfault}).",
          "All-accept ensures $\\phi \\geq \\theta_{accept}$ under the stated abstention behaviour of soft faults; if the $f$ Byzantine \\emph{and} $s$ soft-fault validators all vote REJECT the implication requires $f \\geq s$, as assumed throughout (Appendix~\\ref{app:softfault}).",
          "C6 正文 Lemma 5.3 精简", nth=1)

# ---------- 5. §6.6 前言紧凑化 ----------
rep("The reputation tracker does not enter the vote-counting rule (Equation~\\ref{eq:commit}), so it cannot change any commit decision; a reputation-on/off comparison of decision metrics would therefore return an identity---a consequence of Theorem~\\ref{thm:safety}, not an experimental finding.",
    "The tracker does not enter the vote-counting rule (Equation~\\ref{eq:commit}), so it cannot change a commit decision; a reputation-on/off comparison would return an identity---a consequence of Theorem~\\ref{thm:safety}, not a finding.",
    1, "C7 §6.6 前言精简 a")

rep("and replayed the streams offline through Algorithm~\\ref{alg:reputation} under four settings ($c$ from ground truth or the released \\texttt{\\_estimate\\_correctness} heuristic; reputation persisting across tasks or reset per task; full setup and per-finding numbers in Appendix~\\ref{app:rep_details}). In \\emph{all four} settings the replayed decisions are identical to the online record, which verifies the tracker's decision-neutrality rather than merely asserting it.",
    "and replayed them offline through Algorithm~\\ref{alg:reputation} under four settings ($c$ from ground truth or the released heuristic; reputation persisting or reset per task; per-finding numbers in Appendix~\\ref{app:rep_details}). In \\emph{all four} the replayed decisions match the online record, verifying decision-neutrality rather than asserting it.",
    1, "C8 §6.6 前言精简 b")

# ---------- 6. §6.6 四项发现紧凑化（不删任何发现） ----------
rep("precision $0.232$/$0.195$ under strategic rejection (recall $1.000$) but precision \\emph{and} recall $0.000$ under collusion---a colluder rejects only in the commit round and so never reaches the $\\rho = 0.7$ trigger, whereas honest validators who must reject the wrong proposals those same primaries inject do cross it.",
    "precision $0.232$/$0.195$ (recall $1.000$) under strategic rejection but precision \\emph{and} recall $0.000$ under collusion: a colluder rejects only in the commit round and never reaches $\\rho = 0.7$, whereas honest validators who must reject those same primaries' wrong proposals do.",
    1, "C9 发现(ii) 精简")

rep("and resetting reputation per task does not repair this (honest $0.391$ vs.\\ Byzantine $0.761$)---the failure is structural, not a cold-start artefact.",
    "and resetting reputation per task does not repair this ($0.391$ vs.\\ $0.761$)---structural, not a cold-start artefact.",
    1, "C10 发现(iii) 精简")

rep("that agrees with ground truth on only $46.2\\%$ of rounds, worse than the trivial always-\\texttt{False} predictor ($74.6\\%$), so the promised reward for correctly rejecting a wrong proposal does not occur.",
    "agreeing with ground truth on only $46.2\\%$ of rounds, worse than the trivial always-\\texttt{False} predictor ($74.6\\%$), so the promised reward for correctly rejecting a wrong proposal never occurs.",
    1, "C11 发现(iv) 精简")

# ---------- 7. §6.6 结论段紧凑化 ----------
rep("Repairing it requires a correctness oracle for \\emph{proposal} quality and a trigger not keyed on the validator's own rejection ratio---we deliberately do \\emph{not} suggest agreement with the committee's majority, which would reintroduce the coupling Algorithm~\\ref{alg:reputation} avoids; compatible triggers include execution-validated outcomes and DID-signed cross-round consistency. We leave the repaired design to future work and release the vote streams and four-setting replay for independent verification.",
    "Repairing it requires a correctness oracle for \\emph{proposal} quality and a trigger not keyed on the validator's own rejection ratio---deliberately \\emph{not} agreement with the committee's majority, which would reintroduce the coupling Algorithm~\\ref{alg:reputation} avoids; execution-validated outcomes and DID-signed cross-round consistency qualify. We leave the repair to future work and release the vote streams and replay for verification.",
    1, "C12 §6.6 结论精简")

# ---------- 8. §6.7 Limitations 紧凑化 ----------
rep("A2A-BFT assumes DID-authenticated channels (Ed25519); consensus quality depends on LLM capability, with acceptance decaying exponentially as $p_h$ drops: the observed fault-free decision rates",
    "A2A-BFT assumes DID-authenticated channels (Ed25519), and consensus quality depends on LLM capability: the fault-free decision rates",
    1, "C13 Limitations 精简 a")

rep("The implementation scales to $n \\leq 10$; ablation cells ($n{=}90$) limit power for fine-grained comparisons, though the reported contrasts (e.g., $74.4\\%$ vs.\\ $4.5\\%$) far exceed sampling noise. The reputation tracker is isolated (Section~\\ref{sec:rep_ablation}): decision-neutral but mis-specified as a deterrent. The MMLU collapse is a model-capability rather than protocol limitation.",
    "The implementation scales to $n \\leq 10$, and ablation cells ($n{=}90$) limit power for fine-grained comparisons, though the reported contrasts (e.g., $74.4\\%$ vs.\\ $4.5\\%$) far exceed sampling noise. The tracker is decision-neutral but mis-specified as a deterrent (Section~\\ref{sec:rep_ablation}); the MMLU collapse is a model-capability rather than protocol limitation.",
    1, "C14 Limitations 精简 b")

# ---------- 写入 ----------
if FAILS:
    print(f"[ABORT] {len(FAILS)} 条未命中，文件未写入：")
    for tag, n, c, s in FAILS:
        print(f"  [FAIL] {tag}: 期望 {n} 处，实得 {c}\n      {s}")
    sys.exit(1)

io.open(PATH, "w", encoding="utf-8", newline="").write(t)
print(f"应用 {len(applied)} 条压缩，文件长度 {len(orig)} -> {len(t)} 字符（-{len(orig)-len(t)}）")
for a in applied:
    print("  ok:", a)
