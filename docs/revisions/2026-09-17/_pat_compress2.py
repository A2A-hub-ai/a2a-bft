# -*- coding: utf-8 -*-
"""第二轮：把正文压回 9 页（ICLR 2027 页数规则）。

方式：整行替换（不改行数，索引稳定）。每条编辑都：
  1) 断言该行以预期前缀开头（防止行号漂移后改错地方）；
  2) 断言新文本仍包含全部关键数字（防止压缩时丢掉数据）。
只在全部通过后才写文件。
"""
import io
import sys

PATH = "iclr2027_main.tex"
lines = io.open(PATH, encoding="utf-8", newline="").read().split("\n")
orig_n = len(lines)

# (行号, 前缀断言, 新文本, 必须保留的数字/符号)
EDITS = []

# ---------- L48 摘要：压缩开篇与末句 ----------
EDITS.append((
    48,
    "The emergence of Agent-to-Agent (A2A) protocols enables",
    "Agent-to-Agent (A2A) protocols let autonomous agents collaborate on complex tasks, but reliable consensus in heterogeneous agent networks remains a fundamental challenge once Byzantine failures and soft faults are admitted. We propose \\textbf{A2A-BFT}, a Byzantine fault-tolerant consensus extension for A2A protocols: a three-phase semantic consensus protocol (Propose--Validate--Commit) with attack-adaptive decision thresholds and a reputation tracker that is provably excluded from the vote-counting rule. We prove safety and liveness under $n \\geq 3f + s + 1$ ($f$ Byzantine, $s$ soft faults) and evaluate entirely on real LLM inference: a 7{,}750-task fault sweep with four heterogeneous open-source models ($n{=}250$ per cell) spanning mathematical reasoning, code generation, and knowledge QA. On execution-validated code tasks the protocol \\emph{never} commits a wrong answer within the safety boundary ($0.0 \\pm 0.0\\%$ under every attack), while sub-boundary settings violate safety up to $72.4\\%$ on GSM8K and $90.0\\%$ on knowledge QA, confirming that $3f{+}s{+}1$ is a tight operating condition; on semantically validated tasks, safety composes with the validation oracle. Under collusion, unvalidated majority-voting and debate baselines commit incorrect answers in $16.7$--$63.4\\%$ of tasks \\emph{within} the boundary. Ablations identify view change as the core liveness component---removing it collapses decisions from $74.4\\%$ to $4.5\\%$ under strategic rejection---and dynamic thresholds as the safeguard against attack-induced deadlock. A measured audit shows the released reputation tracker to be decision-neutral but mis-specified as a deterrent: $1{,}186$ of its $1{,}305$ aggressive penalties land on honest validators whose vote was objectively correct.",
    ["7{,}750", "1{,}186", "1{,}305", "74.4", "4.5", "16.7", "63.4", "72.4", "90.0", "0.0", "3f + s + 1"],
))

# ---------- L63 贡献段：去掉重复的“Our contributions are”展开 ----------
EDITS.append((
    63,
    "\\textbf{Our Approach:} We propose A2A-BFT, a Byzantine fault-tolerant consensus extension with three innovations",
    "\\textbf{Our Approach:} We propose A2A-BFT, a Byzantine fault-tolerant consensus extension with three innovations: (i) a three-phase semantic consensus (Propose-Validate-Commit) tailored to LLM-based reasoning tasks; (ii) attack-adaptive decision thresholds together with a reputation tracker that is provably excluded from the vote-counting rule; and (iii) formal safety and liveness guarantees under partial synchrony with the fault model $n \\geq 3f + s + 1$. We formalize the A2A consensus problem with provable guarantees, prove safety and liveness under $n \\geq 3f + s + 1$, and validate the protocol entirely on real four-model LLM deployments (7{,}750-task fault sweep, $n{=}250$ per cell), showing that (a) execution-validated consensus is mechanically safe within the boundary and that safety violations occur only where the theorem says they may ($3f{+}s{+}1$ violated), and (b) on semantically validated tasks, wrong commits under attack are bounded by the validation oracle's error rate---safety composes with the oracle. We additionally isolate the reputation tracker---a component the theorem excludes from every decision---by direct measurement: replaying instrumented vote streams shows it decision-neutral (as the theorem requires) but, as released, directing $1{,}186$ of its $1{,}305$ aggressive penalties at honest validators whose votes were objectively correct, because the $\\rho_i$-keyed trigger cannot distinguish principled dissent from misbehaviour.",
    ["7{,}750", "1{,}186", "1{,}305", "3f + s + 1"],
))

# ---------- L176 声誉小节：删去与首句重复的清理句 + 压缩 Scope ----------
EDITS.append((
    176,
    "The reputation score is an incentive and accountability signal",
    "The reputation score is an incentive and accountability signal, not an input to the vote-counting rule: Equation~\\ref{eq:commit} aggregates raw vote \\emph{counts}, so reputation cannot alter a commit decision. The reference implementation maintains per-agent scores, a 10-round voting history, and suspect counters, and escalates penalties for persistent misbehaviour (Algorithm~\\ref{alg:reputation}); weighting validator selection and excluding persistent offenders are specified design extensions that the released code does \\emph{not} realise, and no deployment here subsamples validators, so no reported result depends on them. The tiered structure (aggressive $-0.25$ for persistent rejecters, reward $+0.1$ for correct votes, mild $-0.05$ for honest mistakes, neutral drift $-0.02$) is \\emph{intended} to provide graduated deterrence against strategic rejection; Section~\\ref{sec:rep_ablation} measures how far the released trigger falls short of that intent. ABSTAIN is never ``correct'': the predicate of Algorithm~\\ref{alg:reputation} is a disjunction, since the form $(v_i = \\textsc{Accept}) = c$ would score abstention on an \\emph{incorrect} proposal as correct and could pay the reward for it (Section~\\ref{sec:rep_ablation}). \\textbf{Scope:} the sweep runs with uniform weights ($w_i{=}1$) and its consensus path contains no reputation logic (Section~\\ref{sec:experiments}), so no reported decision depends on this component.",
    ["0.25", "0.1", "0.05", "0.02", "Accept"],
))

# ---------- L204 主文安全证明：修正越界机制（原句称“零诚实支持”，与附录不一致） ----------
EDITS.append((
    204,
    "(i) Honest replicas share the same honest votes",
    "(i) Honest replicas share the same honest votes, so scores differ only through Byzantine vote equivocation, which the threshold gap provably absorbs ($\\theta_{accept}-\\theta_{reject} \\geq 2f+0.5s > 1.5f$; Appendix~\\ref{app:proofs}); opposite terminal decisions are therefore impossible, and ACCEPT-vs-PENDING divergence resolves through the commit broadcast or view change. Proposals carry the primary's DID signature, and conflicting signed proposals from one primary trigger a view change that voids the round, so equivocation cannot yield two concurrent acceptances. (ii) Byzantine validators number at most $f-1$ when the primary is Byzantine ($f$ otherwise) and contribute $+1$ each, so commitment requires at least $\\theta_{accept}-(f{-}1) = n{-}3f{-}s \\geq 1$ honest ACCEPT votes when the primary is Byzantine, and $\\theta_{accept}-f = n{-}1{-}3f{-}s \\geq 0$ otherwise. Within the boundary, then, a wrong proposal cannot be committed through Byzantine votes alone---it needs an honest validation error or a wrong honest-primary proposal, both bounded by oracle reliability $p_h$ (Section~6). Below the boundary the implication fails instead through the honest validators' own REJECTs: a non-tampering primary's wrong proposal, rejected by $n{-}1{-}f$ honest validators against $f$ Byzantine ACCEPTs, clears $\\theta_{accept}$ exactly when $7f + 2s + 3 \\geq 3n$, matching Table~\\ref{tab:bft}. Full proof in Appendix~\\ref{app:proofs}. \\qed",
    ["2f+0.5s", "n{-}3f{-}s", "7f + 2s + 3", "3n"],
))

# ---------- L250 可复现性段：去掉与末尾声明/附录重复的表述 ----------
EDITS.append((
    250,
    "\\textbf{Reproducibility:} All protocol-level fault-tolerance experiments",
    "\\textbf{Reproducibility:} All protocol-level fault-tolerance experiments (Tables~\\ref{tab:baseline}, \\ref{tab:bft}, and \\ref{tab:mmlu_sweep}; summarised in Table~\\ref{tab:attacks}) share one heterogeneous four-model deployment with 5 seeds ($\\{42,\\dots,46\\}$) and 50 tasks per (configuration, seed, dataset), i.e., $n{=}250$ per cell (7{,}750 tasks over 31 cells); task sets are drawn per seed by a seeded shuffle over GSM8K \\citep{gsm8k}, MBPP \\citep{mbpp}, and MMLU \\citep{mmlu}, reused across configurations for paired comparison, and fault injection is specified in Appendix~\\ref{app:attacks}. Ablation and baseline comparisons (Tables~\\ref{tab:ablation}, \\ref{tab:hetero_compare}) use 3 seeds ($\\{42, 43, 44\\}$) with $n{=}90$ per cell. The four models (Llama-3.1-8B, DeepSeek-V2-Lite, InternLM3-8B, Qwen2.5-7B; Instruct/Chat variants) are served by vLLM \\citep{vllm} $0.11$ (temperature $0$, max\\_tokens $512$) on two NVIDIA A800-SXM4-80GB GPUs (CUDA 12.8, PyTorch 2.8.0); code and data at \\url{https://github.com/anonymous/a2a-bft} (anonymized). \\textbf{No simulation:} every number comes from real LLM inference ($7{,}750$ fault sweep + $4{,}320$ ablation/baseline [$48$ cells $\\times$ $90$] + $770$ API tasks [$320$ multi-domain validation, Table~\\ref{tab:real_llm}; $450$ adversarial-boundary scaling, Table~\\ref{tab:n8_scaling}]), with Section~\\ref{sec:rep_ablation} adding $120$ consensus tasks ($6$ cells $\\times$ $20$) whose vote streams are replayed offline; no simulated workers are used anywhere, and the reputation quantities are event counts reported without a variance.",
    ["7{,}750", "31 cells", "4{,}320", "770", "48", "90", "0.11", "120"],
))

# ---------- L307 同构 DeepSeek 验证段：压缩 ----------
EDITS.append((
    307,
    "As a complementary check we validated the protocol",
    "As a complementary check we validated the protocol with real DeepSeek-V2-Lite outputs over 320 tasks spanning GSM8K, MMLU, and MBPP. These runs use a \\emph{homogeneous} single-model deployment, so honest validators agree far more often than in the heterogeneous sweep; the resulting $100\\%$ acceptance across all eight configurations, under strategic rejection and collusion alike, is therefore an \\emph{upper bound} on decision rates rather than a contradiction of the $55$--$74\\%$ heterogeneous results. At the boundary configuration $n{=}8, f{=}2, s{=}1$ (150 GSM8K tasks per configuration, real DeepSeek API), the protocol maintains $98$--$100\\%$ consensus under both attacks across two independent runs, with answer correctness within $2$ points of the fault-free baseline ($92.0$--$92.7\\%$ vs.\\ $94.0\\%$), and the round-count gap versus fault-free ($1.03$ vs.\\ $2.89$--$2.92$) confirms genuine attack resistance (Welch $t = -13.1$ and $-13.9$, $p < 10^{-26}$; reproduced at $1.04$ vs.\\ $2.38$--$2.43$, McNemar exact $p = 0.25$). Details: Appendix~\\ref{app:realllm}; scaling and MMLU sweeps: Appendix~\\ref{app:additional}.",
    ["320", "100", "98", "92.0", "92.7", "94.0", "1.03", "2.89", "13.1", "13.9", "1.04", "0.25"],
))

# ---------- L323/L325/L327 声誉实测：正文保留全部发现，细节留在附录 A.7 ----------
EDITS.append((
    323,
    "The tracker does not enter the vote-counting rule",
    "The tracker does not enter the vote-counting rule (Equation~\\ref{eq:commit}), so it cannot change a commit decision---a consequence of Theorem~\\ref{thm:safety}, not a finding. We instead measure \\emph{what the tracker reports}: we logged every validation vote from the four-model deployment (120 runs, 457 scored proposal rounds, 2{,}461 validation events) and replayed them offline through Algorithm~\\ref{alg:reputation} under four settings ($c$ from ground truth or the released heuristic; reputation persisting or reset per task; Appendix~\\ref{app:rep_details}). In \\emph{all four} the replayed decisions match the online record, verifying decision-neutrality rather than asserting it.",
    ["120", "457", "2{,}461"],
))
EDITS.append((
    325,
    "The measured behaviour is negative.",
    "The measured behaviour is negative. \\textbf{(i) The aggressive tier fires on honest, correct votes:} across the four attacked cells, $1{,}186$ of $1{,}305$ aggressive penalties ($\\rho_i \\geq 0.7$) landed on an honest validator whose vote was \\emph{objectively correct}---the behaviour Section~\\ref{sec:reputation} specifies should be rewarded---and \\emph{all 20 tasks} in each attacked cell produced at least one mis-penalty. \\textbf{(ii) As a Byzantine detector the tier fails:} precision $0.232$/$0.195$ (recall $1.000$) under strategic rejection but precision \\emph{and} recall $0.000$ under collusion: a colluder rejects only in the commit round and never reaches $\\rho = 0.7$, whereas honest validators rejecting those same primaries' wrong proposals do. \\textbf{(iii) The score ordering inverts:} honest validators finish \\emph{below} Byzantine ones in both collusion cells ($0.337$ vs.\\ $0.427$ on GSM8K; $0.300$ vs.\\ $0.412$ on MBPP), and resetting reputation per task does not repair this ($0.391$ vs.\\ $0.761$)---structural, not a cold-start artefact. \\textbf{(iv) The released $c$ carries negative information:} \\texttt{\\_estimate\\_correctness} is a per-domain constant (always \\texttt{False} on GSM8K, \\texttt{True} on MBPP) agreeing with ground truth on only $46.2\\%$ of rounds, worse than the trivial always-\\texttt{False} predictor ($74.6\\%$), so the promised reward for correctly rejecting a wrong proposal never occurs.",
    ["1{,}186", "1{,}305", "0.7", "0.232", "0.195", "0.000", "0.337", "0.427", "0.300", "0.412", "0.391", "0.761", "46.2", "74.6"],
))
EDITS.append((
    327,
    "This failure mode is known to the trust literature",
    "This failure mode is known to the trust literature \\citep{josang2002beta,josang2007survey,kamvar2003eigentrust}; what we add is its scale in a real LLM consensus deployment and evidence that it is structural. Because no reported safety or liveness \\emph{number} depends on the tracker, the quantitative results stand, but the deterrent listed in Appendix~\\ref{app:attack_resistance} should be read as specified rather than realised. Repairing it requires a correctness oracle for \\emph{proposal} quality and a trigger not keyed on the validator's own rejection ratio---deliberately \\emph{not} agreement with the committee's majority, which would reintroduce the coupling Algorithm~\\ref{alg:reputation} avoids; execution-validated outcomes and DID-signed cross-round consistency qualify. We release the vote streams and replay so a repaired trigger can be measured the same way.",
    ["josang2002beta", "josang2007survey", "kamvar2003eigentrust"],
))

# ---------- 执行 ----------
FAILS = []
before = 0
after = 0
for idx, prefix, new, must in EDITS:
    old = lines[idx - 1]
    before += len(old)
    after += len(new)
    if not old.startswith(prefix):
        FAILS.append((idx, "前缀不符", old[:110]))
        continue
    missing = [m for m in must if m not in new]
    if missing:
        FAILS.append((idx, f"新文本缺少关键数字 {missing}", new[:110]))
        continue
    lines[idx - 1] = new

if FAILS:
    print(f"[ABORT] {len(FAILS)} 条编辑未通过，文件未写入：")
    for idx, why, s in FAILS:
        print(f"  [FAIL] L{idx}: {why}\n      {s}")
    sys.exit(1)

out = "\n".join(lines)
io.open(PATH, "w", encoding="utf-8", newline="").write(out)
print(f"完成 {len(EDITS)} 条整行压缩，行数 {orig_n} -> {len(lines)}（不变）")
print(f"被压缩行总字符 {before} -> {after}（-{before-after}）")
