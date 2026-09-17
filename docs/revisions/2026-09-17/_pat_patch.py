# -*- coding: utf-8 -*-
"""按 PAT 反馈逐条修正 iclr2027_main.tex（每条均带命中数断言）。"""
import io
import sys

PATH = "iclr2027_main.tex"
t = io.open(PATH, encoding="utf-8").read()
orig = t
applied = []


FAILS = []


def rep(old, new, n=1, tag=""):
    """替换并校验命中数。命中数不符时记录失败但继续，便于一轮看到全部偏差。"""
    global t
    c = t.count(old)
    if c != n:
        FAILS.append((tag, n, c, old[:200]))
        return
    t = t.replace(old, new)
    applied.append(tag)


# ============ 1. 声誉数字（ok 谓词修正后的重放结果） ============
rep("$1{,}217$", "$1{,}186$", 6, "N1 误罚计数 1217→1186")
rep(r"($1{,}217/1{,}305$ mis-attributed", r"($1{,}186/1{,}305$ mis-attributed", 1, "N1b 斜杠形式 1217/1305")
rep("$0.413$", "$0.337$", 2, "N2 GSM8K 共谋 r_hon 0.413→0.337")
rep("$0.301$", "$0.300$", 2, "N3 MBPP 共谋 r_hon 0.301→0.300")
rep("$0.458$", "$0.391$", 2, "N4 fresh 档 r_hon 0.458→0.391")
rep(r"GSM8K $f{=}0$ (no attack) & 66 & 44 & 0.667 & --- & --- & 1.000 & 0.609\,/\,--- \\",
    r"GSM8K $f{=}0$ (no attack) & 66 & 42 & 0.636 & --- & --- & 1.000 & 0.587\,/\,--- \\",
    1, "T1 表格 f=0 行")
rep(r"GSM8K $f{=}1$ strat.\ rej. & 164 & 120 & 0.732 & 0.232 & 1.000 & 0.824 & 0.467\,/\,0.300 \\",
    r"GSM8K $f{=}1$ strat.\ rej. & 164 & 116 & 0.707 & 0.232 & 1.000 & 0.832 & 0.436\,/\,0.300 \\",
    1, "T2 表格 GSM8K SR 行")
rep(r"GSM8K $f{=}2$ collusion & 373 & 370 & \textbf{0.992} & \textbf{0.000} & \textbf{0.000} & 0.844 & \textbf{0.413\,/\,0.427} \\",
    r"GSM8K $f{=}2$ collusion & 373 & 355 & \textbf{0.952} & \textbf{0.000} & \textbf{0.000} & 0.856 & \textbf{0.337\,/\,0.427} \\",
    1, "T3 表格 GSM8K 共谋行")
rep(r"MBPP $f{=}1$ strat.\ rej. & 200 & 161 & 0.805 & 0.195 & 1.000 & 0.842 & 0.351\,/\,0.332 \\",
    r"MBPP $f{=}1$ strat.\ rej. & 200 & 155 & 0.775 & 0.195 & 1.000 & 0.843 & 0.338\,/\,0.332 \\",
    1, "T4 表格 MBPP SR 行")
rep(r"MBPP $f{=}2$ collusion & 568 & 566 & \textbf{0.996} & \textbf{0.000} & \textbf{0.000} & 0.887 & \textbf{0.301\,/\,0.412} \\",
    r"MBPP $f{=}2$ collusion & 568 & 560 & \textbf{0.986} & \textbf{0.000} & \textbf{0.000} & 0.888 & \textbf{0.300\,/\,0.412} \\",
    1, "T5 表格 MBPP 共谋行")
rep("in 9 and 5 of 20 tasks respectively", "in 10 and 9 of 20 tasks respectively", 1, "N5 无攻击细胞任务数")

# ============ 2. 定义 3.1：软故障在无效提案上的行为 ============
rep(r"""    \item $f$: maximum number of Byzantine (malicious) agents, which may vote arbitrarily including equivocation, coordination, or selective rejection
    \item $s$: maximum number of soft-fault (unreliable) agents, which vote independently with probability $p_s \in [0.5, 0.9]$ of producing ACCEPT on valid proposals and may ABSTAIN or vote REJECT stochastically
    \item Safety condition: $n \geq 3f + s + 1$""",
    r"""    \item $f$: maximum number of Byzantine (malicious) agents, which may vote arbitrarily, including equivocation, coordination, or selective rejection.
    \item $s$: maximum number of soft-fault (unreliable) agents, which vote independently with probability $p_s \in [0.5, 0.9]$ of producing ACCEPT on valid proposals, may ABSTAIN or vote REJECT stochastically, and \emph{do not ACCEPT invalid proposals} (zero false-positive rate on invalid proposals; the relaxation is quantified in Appendix~\ref{app:softfault}).
    \item Safety condition: $n \geq 3f + s + 1$, with $s \leq f$ when soft faults vote REJECT rather than abstaining (Appendix~\ref{app:softfault}).""",
    1, "D1 定义 3.1")

# ============ 3. §3.1 能力分符号 / §3.3 去掉未使用的难度等级 ============
rep(r"a capability score reflecting its domain expertise, a reputation score $r_i \in [0.1, 1.0]$",
    r"a capability score $g_i$ reflecting its domain expertise, a reputation score $r_i \in [0.1, 1.0]$",
    1, "D2 能力分符号")
rep(r"with a verifiable solution space $\mathcal{S}$, a difficulty level $d(T) \in [0, 1]$, and a ground-truth verification function",
    r"with a verifiable solution space $\mathcal{S}$ and a ground-truth verification function",
    1, "D3 删除未使用的难度等级 d(T)")

# ============ 4. §4.2 验证函数记号 / 二项尾和 / p_h 定义 / 弃权机制 ============
rep(r"Formally, $V(T, s) = 1$ iff $s$ matches the ground truth (or an equivalent formulation) for \emph{deterministic tasks} (mathematics, logic puzzles), which is algorithmic and error-free; for \emph{semantic tasks} (code generation, knowledge QA), $V(T, s) = 1$ iff",
    r"Formally, writing $\hat{V}$ for the validator's empirical check---kept distinct from the ground-truth oracle $V$ of Section~\ref{sec:task}---we have $\hat{V}(T, s) = 1$ iff $s$ matches the ground truth (or an equivalent formulation) in the \emph{execution-validated} domain, where the check is algorithmic and error-free; in the \emph{semantically validated} domain (free-form reasoning and multiple-choice QA, where no exact test exists), $\hat{V}(T, s) = 1$ iff",
    1, "D4 验证函数记号与任务域映射")
rep(r"with $k = \lceil 2m/3 \rceil$, reducing the individual verifier error from $1 - p_h$ to $(1 - p_h)^{m}$ via concentration.",
    r"with $k = \lceil 2m/3 \rceil$; the individual verifier error then falls from $1-p_h$ to the binomial tail $\sum_{j=0}^{k-1}\binom{m}{j}p_h^{\,j}(1-p_h)^{m-j}$ (not to $(1-p_h)^m$, which would require unanimity), where $p_h$ is the probability that an honest validator correctly accepts a valid proposal.",
    1, "D5 二项尾和与 p_h 定义")
rep(r"In our heterogeneous experiments each validator instantiates this check with a \emph{single} self-model judge ($m{=}1$)",
    r"In our heterogeneous experiments the domains map as follows: code generation (MBPP) is execution-validated, while mathematics (GSM8K) and knowledge QA (MMLU) are semantically validated, each validator instantiating the check with a \emph{single} self-model judge ($m{=}1$)",
    1, "D6 实验域映射")
rep(r"If the verification probability falls in $[0.4, 0.6]$, the validator ABSTAINS, contributing 0 to $\phi(\pi)$.",
    r"The released judge emits a discrete verdict, and ABSTAIN is reserved for an explicit UNCERTAIN outcome (when a calibrated verification probability is available, the band $[0.4, 0.6]$ marks that same state); an ABSTAIN contributes 0 to $\phi(\pi)$.",
    1, "D7 弃权机制可复现性")

# ============ 5. Algorithm 1 的 ok 谓词（弃权漏洞） ============
rep(r"\State $\text{ok} \gets \big(v_i = \textsc{Accept}\big) = c$",
    r"\State $\text{ok} \gets (v_i = \textsc{Accept} \wedge c) \vee (v_i = \textsc{Reject} \wedge \neg c)$ \Comment{ABSTAIN is never ``correct''}",
    1, "D8 Algorithm 1 的 ok 谓词")
rep(r"Section~\ref{sec:rep_ablation} measures how far the released trigger falls short of that intent. \textbf{Scope:} the four-model sweep runs with uniform weights",
    r"Section~\ref{sec:rep_ablation} measures how far the released trigger falls short of that intent. An ABSTAIN vote is non-affirmative: the correctness predicate of Algorithm~\ref{alg:reputation} must be read as a disjunction, since the equivalent form $(v_i = \textsc{Accept}) = c$ would score abstention on an \emph{incorrect} proposal as correct and could pay the reward for it; the released code implements the disjunction, and adopting it changes $31$ aggressive-tier events in our replay (Section~\ref{sec:rep_ablation}). \textbf{Scope:} the four-model sweep runs with uniform weights",
    1, "D9 弃权非肯定性说明")

# ============ 6. §5.2 阈值注释加 s<=f 条件 ============
rep(r"where the threshold is derived from the safety condition $n \geq 3f + s + 1$. This ensures that if all honest validators accept, the proposal passes even with $f$ Byzantine validators rejecting.",
    r"where the threshold is derived from the safety condition $n \geq 3f + s + 1$. This ensures that if all honest validators accept, the proposal passes even with $f$ Byzantine validators rejecting (and, when soft faults also reject, provided $s \leq f$; Appendix~\ref{app:softfault}).",
    1, "D10 阈值注释")

# ============ 7. §4.5 视图切换 + 附录 A.1.3（跨视图状态转移 / 自评置信度） ============
rep(r"any $2f{+}1$ quorum contains at least $f{+}1$ honest agents (at most $f$ Byzantine agents cannot establish a view), and a committed task terminates its instance.",
    r"any $2f{+}1$ confirmation quorum contains at least $f{+}1$ non-Byzantine agents (at most $f$ Byzantine agents cannot establish a view), and a committed task terminates its instance. Cross-view state transfer and the assumptions it rests on are detailed in Appendix~\ref{app:viewchange}.",
    1, "D11 §4.5 视图切换")
rep(r"(ii) any $2f+1$ confirmation quorum contains at least $f+1$ honest agents, so the at most $f$ Byzantine agents cannot establish a view unilaterally; and (iii) a committed task terminates its instance, so a later view cannot reverse a prior commitment. Note that quorum intersection of two $2f{+}1$ quorums ($\geq 4f{+}2{-}n$ agents) is not itself the load-bearing argument here, since mechanism (i) already pins the primary.",
    r"""(ii) any $2f+1$ confirmation quorum contains at least $f+1$ non-Byzantine agents (and hence at least $f{+}1{-}s$ strictly honest ones when soft-fault agents join it), so the at most $f$ Byzantine agents cannot establish a view unilaterally; and (iii) a committed task terminates its instance, so a later view cannot reverse a prior commitment. Note that quorum intersection of two $2f{+}1$ quorums ($\geq 4f{+}2{-}n$ agents) is not itself the load-bearing argument here, since mechanism (i) already pins the primary.

\textbf{Cross-view state transfer.} The protocol deliberately does not carry quorum certificates across views. A view change only rotates the primary deterministically; a committed task terminates its instance, and the new primary re-proposes (or promotes the highest-confidence pending alternative). Under partial synchrony a replica that observes $\phi \geq \theta_{accept}$ broadcasts the commit, so a slower replica either adopts that commitment or, if it times out first, enters a view in which the instance has already been terminated by the commit; the two cannot diverge because the primary of a given view number is unique, so there is never a second decision for the same instance. The load-bearing assumption is therefore that a committed task is never re-instantiated, which the reference implementation enforces by binding each task instance to its committed round. The residual exposure is the converse of this choice: a proposal that has \emph{not} yet committed is not transferred, so progress after a view change costs a repeat generation. A two-phase commit with signed commit certificates in the VIEW-CHANGE message (as in PBFT or HotStuff) would remove the assumption and preserve partially committed state, at the price of an extra message round; we regard this as the natural next step for a distributed deployment (Appendix~\ref{app:deployment}).

\textbf{Self-assessed confidence.} Alternative proposals are prioritised by the proposer's own confidence (Section~\ref{sec:altprop}), which a Byzantine agent can set to $1.0$. Priority only selects \emph{which} pending alternative is re-proposed; it never enters $\phi(\pi)$ or the thresholds, so a self-promoted proposal still has to clear the same vote count, and on execution-validated domains it still has to pass the tests. Hardening the heuristic (e.g.\ ranking by execution outcome, or dropping priority entirely) is orthogonal to the safety theorem, which depends only on vote counts.""",
    1, "D12 附录 A.1.3 展开")

# ============ 8. Property 4（越界机制）+ 端点区间 + Property 6 措辞 ============
rep(r"Below the boundary, $\theta_{accept} \leq f-1$ and a Byzantine primary plus $f-1$ colluding validators commit with zero honest support.",
    r"Below the boundary this implication fails, but not through the Byzantine primary alone: honest validators \emph{actively} reject ($-0.5$ each), so with $f{-}1$ Byzantine and $n{-}f$ honest validators a tampering Byzantine primary reaches only $\phi = (f{-}1) - 0.5(n{-}f) < \theta_{accept}$. What the collapsed threshold does permit is a wrong proposal from a primary that does \emph{not} tamper, rejected by the $n{-}1{-}f$ honest validators while all $f$ Byzantine validators vote ACCEPT: then $\phi = f - 0.5(n{-}1{-}f) \geq \theta_{accept}$ exactly when $7f + 2s + 3 \geq 3n$. For $n{=}5, f{=}2$ this reads $17 \geq 15$ (violation possible) and for $n{=}6, f{=}2$ it reads $17 \geq 18$ (violation impossible), matching the measured execution-validated wrong-commit rates of $5.6$--$9.6\%$ versus $0.0\%$ in Table~\ref{tab:bft}.",
    1, "D13 Property 4 越界机制")
rep(r"If $\phi(\pi) \in [\theta_{reject}, \theta_{accept})$, the decision is PENDING. In this case:",
    r"If $\theta_{reject} < \phi(\pi) < \theta_{accept}$, the decision is PENDING (matching Equation~\ref{eq:commit}, where $\phi \leq \theta_{reject}$ is a REJECT). In this case:",
    1, "D14 Property 5 区间")
rep(r"If $\phi(\pi)$ falls in $[\theta_{reject}, \theta_{accept})$, the decision is PENDING. After 2 consecutive PENDING rounds",
    r"If $\phi(\pi)$ falls strictly between $\theta_{reject}$ and $\theta_{accept}$, the decision is PENDING. After 2 consecutive PENDING rounds",
    1, "D15 Step 4 区间")
rep(r"Any view-change quorum of $2f+1$ confirmations contains at least $f+1$ honest agents, so the at most $f$ Byzantine agents cannot establish a view unilaterally.",
    r"Any view-change quorum of $2f+1$ confirmations contains at least $f+1$ non-Byzantine agents, so the at most $f$ Byzantine agents cannot establish a view unilaterally.",
    1, "D16 Property 6 措辞")

# ============ 9. Lemma 5.3 的 s<=f 条件 ============
rep(r"When the primary is honest, it generates a valid proposal. Each honest validator independently accepts with probability $p_h$. Since there are $(n-1-f-s)$ honest validators, the probability that all accept (ensuring $\phi \geq \theta_{accept}$) is $p_h^{(n-1-f-s)}$. \qed",
    r"When the primary is honest, it generates a valid proposal. Each honest validator independently accepts with probability $p_h$. Since there are $(n-1-f-s)$ honest validators, the probability that all accept is $p_h^{(n-1-f-s)}$. All-accept ensures $\phi \geq \theta_{accept}$ under the stated abstention behaviour of soft faults; if instead all $f$ Byzantine \emph{and} $s$ soft-fault validators vote REJECT, $\phi = (n{-}1{-}f{-}s) - 0.5(f{+}s)$ and $\phi - \theta_{accept} = 0.5(f-s)$, so the implication requires $f \geq s$ as assumed throughout (Appendix~\ref{app:softfault}). \qed",
    2, "D17 Lemma 5.3 条件（正文 L224 + 附录 L497）")

# ============ 10. 附录 A.1.2：加标签 + 软故障假阳性分析 + 注入说明 ============
rep(r"""\subsubsection{Soft Fault Adversarial Behavior}

Theorem~\ref{thm:safety} assumes soft-fault agents abstain in the worst case.""",
    r"""\subsubsection{Soft Fault Adversarial Behavior}\label{app:softfault}

Theorem~\ref{thm:safety} assumes soft-fault agents abstain in the worst case (Definition~\ref{def:fault} additionally excludes false-positive ACCEPT votes on invalid proposals, which the analysis below relaxes).""",
    1, "D18 A.1.2 标签与假设")
rep(r"Thus, the safety condition $n \geq 3f + s + 1$ is robust even against adversarial soft faults when $s \leq f$.",
    r"""Thus, the safety condition $n \geq 3f + s + 1$ is robust even against adversarial soft faults that \emph{reject} valid proposals, when $s \leq f$.

\textbf{False positives on invalid proposals.} The more dangerous direction is a soft-fault agent that ACCEPT\emph{s} an invalid proposal. Let each soft-fault agent do so with probability $p \in [0,1]$ and abstain otherwise, and let honest validators reject. With a Byzantine primary the wrong-side score is $\phi = (f{-}1) + sp - 0.5(n{-}f{-}s)$, and safety requires $\phi < \theta_{accept} = n - 1 - 2f - s$, i.e.
\begin{equation}
    7f + 2sp + 3s < 3n .
\end{equation}
Substituting the boundary condition $n = 3f + s + 1$ reduces this to the single requirement $sp < f + 1.5$: with $p = 1$ it is $s \leq f + 1$, and for $f = 0$ it becomes $sp < 1.5$, so a deployment with many unreliable agents relative to its Byzantine count must either bound their false-positive rate or enlarge $n$ to $n > (7f + 2sp + 3s)/3$. All experiments in this paper use $s \in \{0,1\}$ and $f \geq s$, comfortably inside the condition; we state it because it is the one place where the boundary $n \geq 3f + s + 1$ alone is not sufficient.

\textbf{Injection used in the evaluation.} The released soft-fault agents ABSTAIN with probability $0.3$ (and, as primary, return an empty proposal with probability $0.3$), so the experiments exercise the abstention arm---which for $s \leq f$ is the worst case for the accept threshold---together with the stochastic-REJECT arm covered analytically above. We note explicitly that the stochastic-REJECT behaviour of Definition~\ref{def:fault} is analysed rather than injected.""",
    1, "D19 假阳性分析")

# ============ 11. 附录 A.2.5 越界说明与错提交机制 ============
rep(r"Below the boundary ($f{=}2$ with $n \leq 6 < 7$) safety is violated",
    r"Below the boundary ($f{=}2$, $n{=}5,6$, where $3f{+}s{+}1 = 7 > n$) safety is violated",
    1, "D20 A.8 越界措辞")
rep(r"The real-LLM results (Table~\ref{tab:bft}) show exactly what the theorem predicts: with $\theta_{accept} = n - 1 - 2f - s \leq 1$, two colluding Byzantine validators can carry a tampered proposal to commitment on their own, and wrong-commit rates rise to",
    r"The real-LLM results (Table~\ref{tab:bft}) show exactly what the theorem predicts: with $\theta_{accept} = n - 1 - 2f - s \leq 1$ the honest majority no longer outvotes the Byzantine bloc ($f$ ACCEPT votes against $n{-}1{-}f$ honest REJECTs clear $\theta_{accept}$ whenever $7f + 2s + 3 \geq 3n$), and wrong-commit rates rise to",
    1, "D21 A.6 越界机制")

# ============ 12. 附录 A.4.3 草稿痕迹 + 升级罚语义 ============
rep(r"once a counter reaches its threshold it applies an additional $\max(0.3,\, r_i - 0.2)$ on top of the tier penalty. A step-by-step fidelity audit against the released penalty code (12{,}000 update steps, zero divergence) confirms the escalation fires, contradicting an earlier draft of this appendix that described the counters as warning-only.",
    r"once a counter reaches its threshold the score is \emph{set} to $\max(0.3,\, r_i - 0.2)$, i.e.\ a further clamped decrement of $0.2$ applied to the post-tier value (an assignment, not an additive term). A step-by-step fidelity audit against the released penalty code ($12{,}000$ update steps over all three vote types, zero divergence) confirms that the escalation fires.",
    1, "D22 A.4.3")

# ============ 13. 附录 A.3.1/A.3.3：基线语义与缺失基线的说明 ============
rep(r"\item \textbf{LLM-Debate} \citep{du2024improving}: two debate rounds with a rational update rule (agents revise toward majority-validated arguments); on MBPP, solutions already passing all tests are retained. Commits the post-debate majority answer.",
    r"""\item \textbf{LLM-Debate} \citep{du2024improving}: two debate rounds in which honest agents revise their answer after seeing the others', followed by a majority commit; the tabulated runs use \emph{no} execution oracle. The oracle-assisted variant---which retains any solution already passing all tests---is reported separately below.
\end{itemize}

\textbf{On self-refinement and multi-agent framework baselines.} Reflexion \citep{shinn2023reflexion} is a single-agent self-refinement loop and MetaGPT \citep{hong2024metagpt} a role-based software pipeline; neither defines a quorum, a fault model, or a commit rule, so neither can be placed on the wrong-commit axis without first supplying the consensus layer that is the object of study. We therefore compare against the closest aggregation-based alternatives and, to avoid under-testing the debate baseline, also run an \emph{oracle-assisted} variant that rewrites each agent's solution but keeps any solution that already passes all tests: on MBPP it still commits incorrect answers in $46.7\%$ (strategic rejection) and $56.7\%$ (collusion) of tasks, versus $26.7\%$ fault-free (\texttt{mbpp\_debate\_fix.json}). Giving the debate baseline a verification oracle therefore does not rescue an unvalidated aggregation rule, which is precisely the gap A2A-BFT closes.""",
    1, "D23 A.3.3 LLM-Debate 与缺失基线")

# ============ 14. 表 6 说明与延迟归因 ============
rep(r"LLM-Debate uses domain-appropriate budgets and retains solutions already passing all tests.",
    r"LLM-Debate uses two debate rounds with a majority commit and no execution oracle; an oracle-assisted variant is reported in Appendix~\ref{app:attacks}.",
    1, "D24 对比表说明")
rep(r"\textbf{Cost structure:} latency is dominated by LLM generation: the $n{=}4 \to n{=}6$ increase ($61.3 \to 88.4$s on GSM8K) reflects the additional validators per round, consistent with $O(n^2)$ message complexity.",
    r"\textbf{Cost structure:} latency is dominated by LLM generation, and it tracks the number of generations: the $n{=}4 \to n{=}6$ increase ($61.3 \to 88.4$s on GSM8K) accompanies $12.7 \to 20.0$ LLM calls per task, a linear growth in the validator count rather than the $O(n^2)$ message complexity.",
    1, "D25 延迟归因")

# ============ 15. 表 4 分母 + A.9 平衡报告 ============
rep(r"Code baseline ($n=4,f=0,s=0$) & 40 & \textbf{100}$^\star$ & 38.16 \\",
    r"Code baseline ($n=4,f=0,s=0$) & 40\,(12)$^\star$ & \textbf{100} & 38.16 \\",
    1, "D26 表 4 代码基线分母")
rep(r"Code BFT ($n=5,f=1,s=1$) & 40 & \textbf{100}$^\star$ & 9.01 \\",
    r"Code BFT ($n=5,f=1,s=1$) & 40\,(39)$^\star$ & \textbf{100} & 9.01 \\",
    1, "D27 表 4 代码 BFT 分母")
rep(r"$^\star$All 320 tasks were submitted to the live DeepSeek API; acceptance is computed over the $291$ that completed execution",
    r"$^\star$The ``Tasks'' column shows submitted (and, in parentheses, completed) tasks: $28$ code-baseline tasks and $1$ code-BFT task terminated in API/harness errors, and $100\%$ is computed over the completed ones. All 320 tasks were submitted to the live DeepSeek API, and acceptance is computed over the $291$ that completed execution",
    1, "D28 表 4 说明")
rep(r"\item With one Byzantine replica, A2A-Sim decides fewer tasks ($62.2\%$ vs.\ $74.4\%$) and commits wrong answers in up to $35.5\%$ of code tasks, whereas A2A-BFT never commits a wrong answer on execution-validated code ($0.0\%$).",
    r"""\item With one Byzantine replica under strategic rejection, A2A-Sim decides fewer tasks ($62.2\%$ vs.\ $74.4\%$) and commits wrong answers in up to $35.5\%$ of code tasks, whereas A2A-BFT never commits a wrong answer on execution-validated code ($0.0\%$).
    \item The collusion cell in Table~\ref{tab:hetero_compare} is the one place where the comparison does not favour us: at $n{=}8, f{=}2, s{=}1$ on GSM8K, A2A-Sim's decision rate is marginally higher ($66.7\%$ vs.\ $61.1\%$) and its wrong-commit rate marginally lower ($7.8\%$ vs.\ $10.0\%$). Both differences are within the $\pm$std of three seeds ($7.8{\pm}1.9$ vs.\ $4.5{\pm}3.9$ for wrong-commit under strategic rejection; descriptive at $n{=}3$ seeds), and neither survives pooling: what separates the methods is the code domain ($34.4$--$35.5\%$ vs.\ $0.0\%$ wrong commits) and the fact that A2A-BFT's decisions carry a proof obligation rather than a confidence threshold. Under collusion the protocol is deliberately conservative---it forgoes a decision when validation is inconclusive---which costs decision rate in exactly the cell where an unvalidated aggregator happens to agree with itself.""",
    1, "D29 A.9 平衡报告")

# ============ 16. 附录 A.10 / B.1 与实测的一致性 ============
rep(r"    \item \textbf{Incentive Compatibility:} The reputation mechanism implicitly creates incentives for honest behavior---agents with high reputation receive more influence in future rounds.",
    r"    \item \textbf{Incentive Compatibility:} The reputation mechanism is \emph{designed} to create incentives for honest behavior---agents with high reputation receive more influence in future rounds. This analysis applies to the intended design, in which the penalty falls on the deviating agent; Section~\ref{sec:rep_ablation} measures the released implementation and finds the opposite (penalties land predominantly on honest, correct votes), so the equilibrium below describes a \emph{repaired} tracker rather than the one we evaluated.",
    1, "D30 A.10 理想化限定")
rep(r"This condition is satisfied when the reputation penalty ($\Delta r = 0.25$ for aggressive misbehavior) multiplied by the consensus value exceeds any private benefit from deviation. In practice, $V_{consensus}$ is typically large in multi-agent collaboration scenarios, making honest behavior the dominant strategy.",
    r"This condition is satisfied when the reputation penalty ($\Delta r = 0.25$ for aggressive misbehavior) multiplied by the consensus value exceeds any private benefit from deviation; in practice $V_{consensus}$ is large, making honest behavior the dominant strategy. The qualification is important: under the \emph{released} tracker of Section~\ref{sec:rep_ablation}, where the aggressive tier fires on honest correct votes ($1{,}186$ of $1{,}305$) and misses colluders entirely (precision and recall $0.000$), a utility-maximising agent would instead be pushed toward accepting Byzantine proposals to keep $\rho_i$ low. The repaired trigger proposed in Section~\ref{sec:rep_ablation} is a prerequisite for the equilibrium statement, not a consequence of the current code.",
    1, "D31 A.10 均衡限定")
rep(r"The three-phase semantic consensus design balances expressiveness with formal guarantees, while the reputation mechanism addresses practical concerns about agent reliability.",
    r"The three-phase semantic consensus design balances expressiveness with formal guarantees, while a \emph{repaired} reputation framework (Section~\ref{sec:rep_ablation}) is intended to address practical concerns about agent reliability.",
    1, "D32 B.1 措辞")

# ============ 17. §2 直接点名并发工作 ============
rep(r"concurrent robust-aggregation designs for LLM agent networks offer neither view change nor such a metric",
    r"concurrent robust-aggregation designs for LLM agent networks, such as confidence-probe weighting \citep{zheng2025rethinking} and self-anchored filter-and-refine consensus \citep{lee2026robust}, offer neither view change nor such a metric",
    1, "D33 §2 并发工作点名")

# ============ 18. 部署小节加标签（供跨视图转移引用） ============
rep(r"\subsection{Practical Deployment Considerations}",
    r"\subsection{Practical Deployment Considerations}\label{app:deployment}",
    1, "D34 部署小节标签")

if FAILS:
    print(f"[ABORT] {len(FAILS)} 条未命中，文件未写入：")
    for tag, n, c, s in FAILS:
        print(f"  [FAIL] {tag}: 期望 {n} 处，实得 {c}")
        print(f"      {s}")
    sys.exit(1)

io.open(PATH, "w", encoding="utf-8", newline="").write(t)
print(f"应用 {len(applied)} 条修改，文件长度 {len(orig)} -> {len(t)} 字符")
for a in applied:
    print("  ok:", a)
