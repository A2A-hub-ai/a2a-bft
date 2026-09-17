# -*- coding: utf-8 -*-
"""第三轮：正文压回 9 页。

要点：§6.1 的 Reproducibility 段把实验细节移入文末的 Reproducibility Statement
（ICLR 2027 规定该声明不计入页数），正文只留结论性摘要 + 指针。
其余为措辞压缩，全部数字保留。
"""
import io
import sys

PATH = "iclr2027_main.tex"
lines = io.open(PATH, encoding="utf-8", newline="").read().split("\n")
orig_n = len(lines)

EDITS = []

# ---------- L48 摘要：进一步压缩 ----------
EDITS.append((
    48,
    "Agent-to-Agent (A2A) protocols let autonomous agents collaborate",
    "Agent-to-Agent (A2A) protocols let autonomous agents collaborate on complex tasks, but reliable consensus in heterogeneous agent networks remains a fundamental challenge once Byzantine failures and soft faults are admitted. We propose \\textbf{A2A-BFT}, a Byzantine fault-tolerant consensus extension for A2A protocols: a three-phase semantic consensus protocol (Propose--Validate--Commit) with attack-adaptive decision thresholds and a reputation tracker provably excluded from the vote-counting rule. We prove safety and liveness under $n \\geq 3f + s + 1$ ($f$ Byzantine, $s$ soft faults) and evaluate entirely on real LLM inference: a 7{,}750-task fault sweep with four heterogeneous open-source models ($n{=}250$ per cell) spanning mathematical reasoning, code generation, and knowledge QA. On execution-validated code tasks the protocol \\emph{never} commits a wrong answer within the safety boundary ($0.0 \\pm 0.0\\%$ under every attack), while sub-boundary settings violate safety up to $72.4\\%$ on GSM8K and $90.0\\%$ on knowledge QA, confirming $3f{+}s{+}1$ as a tight operating condition; on semantically validated tasks, safety composes with the validation oracle. Under collusion, unvalidated majority-voting and debate baselines commit incorrect answers in $16.7$--$63.4\\%$ of tasks \\emph{within} the boundary. Ablations identify view change as the core liveness component---removing it collapses decisions from $74.4\\%$ to $4.5\\%$ under strategic rejection---and dynamic thresholds as the safeguard against attack-induced deadlock. A measured audit shows the released reputation tracker to be decision-neutral but mis-specified as a deterrent: $1{,}186$ of its $1{,}305$ aggressive penalties land on honest validators whose vote was objectively correct.",
    ["7{,}750", "1{,}186", "1{,}305", "74.4", "4.5", "16.7", "63.4", "72.4", "90.0", "0.0", "3f + s + 1"],
))

# ---------- L69 相关工作：压缩 ----------
EDITS.append((
    69,
    "\\textbf{Multi-agent consensus with LLMs.}",
    "\\textbf{Multi-agent consensus with LLMs.} Debate- and voting-based aggregation improves answer quality but offers no guarantee against committed wrong answers under Byzantine agents: our experiments show $16.7$--$63.4\\%$ wrong-commit rates for such baselines. Self-aggregation frameworks such as A2A-Sim add confidence filtering but no validation stage. A2A-BFT complements this line with a validated three-phase consensus with view change and reputation: to our knowledge, the first protocol to couple Byzantine fault tolerance for agent-to-agent task consensus with an execution-validated safety metric (wrong-commit rate); concurrent robust-aggregation designs for LLM agent networks, such as confidence-probe weighting \\citep{zheng2025rethinking} and self-anchored filter-and-refine consensus \\citep{lee2026robust}, offer neither (extended discussion: Appendix~\\ref{app:extrelated}).",
    ["16.7", "63.4", "zheng2025rethinking", "lee2026robust"],
))

# ---------- L215 活性证明：压缩措辞（数字与结论不变） ----------
EDITS.append((
    215,
    "The primary rotates round-robin",
    "The primary rotates round-robin, so an honest agent becomes primary within every $f+1$ rounds. With an honest primary, a sufficient event for acceptance is that all $(n-1-f-s)$ honest validators accept, so Lemma~\\ref{lem:acceptance} lower-bounds the single-round acceptance probability by $p_h^{(n-1-f-s)} = 0.81$ for $n{=}5, f{=}1, s{=}1$ (with $p_h = 0.9$). If the decision is PENDING, the view-change protocol (requiring $2f+1$ confirmations, more than the $f$ Byzantine agents) rotates the primary within $f+1$ further rounds. Under partial synchrony, after GST the probability of no acceptance within $k$ rounds is bounded by $(1 - p_h^{(n-1-f-s)})^k$ (approximately $6 \\times 10^{-8}$ for $k{=}10$), so termination occurs with probability approaching 1. The excluded case---sustained rejection of all honest proposals---is mitigated stochastically rather than eliminated: view change denies a fixed primary and reputation penalties (where enabled) tax persistent rejecters, which is why Theorem~\\ref{thm:liveness} is probabilistic rather than deterministic. Full proof in Appendix~\\ref{app:proofs}. \\qed",
    ["0.81", "6 \\times 10^{-8}", "2f+1", "p_h"],
))

# ---------- L250 §6.1：细节移入不计页数的 Reproducibility Statement ----------
EDITS.append((
    250,
    "\\textbf{Reproducibility:} All protocol-level fault-tolerance experiments",
    "\\textbf{Reproducibility:} All protocol-level fault-tolerance experiments share one heterogeneous four-model deployment with 5 seeds and 50 tasks per (configuration, seed, dataset), i.e., $n{=}250$ per cell (7{,}750 tasks over 31 cells); task sets are drawn per seed by a seeded shuffle over GSM8K \\citep{gsm8k}, MBPP \\citep{mbpp}, and MMLU \\citep{mmlu} and reused across configurations for paired comparison, while ablation and baseline comparisons use 3 seeds with $n{=}90$ per cell. \\textbf{No simulation:} every reported number comes from real LLM inference ($7{,}750$ fault sweep + $4{,}320$ ablation/baseline + $770$ API tasks); models, hardware, injection, and the reputation measurement are specified in the Reproducibility Statement and Appendix~\\ref{app:attacks}.",
    ["7{,}750", "31 cells", "4{,}320", "770", "n{=}250", "n{=}90"],
))

# ---------- L314 消融结论：压缩措辞 ----------
EDITS.append((
    314,
    "The ablation yields four consistent findings.",
    "The ablation yields four consistent findings. \\textbf{(i) View change is the core liveness component:} removing it collapses decisions from $74.4 \\pm 8.4\\%$ to $4.5 \\pm 3.9\\%$ (GSM8K, strategic rejection) and to $0\\%$ (MBPP, both attacks)---blocked rounds never rotate the primary, confirming Theorem~\\ref{thm:liveness} in a real system. \\textbf{(ii) Semantic validation is the prerequisite for heterogeneous consensus:} under naive exact-match comparison, heterogeneous replicas almost never agree byte-for-byte, so valid proposals are rejected indefinitely and the code domain deadlocks ($0$--$1.1\\%$ decisions)---Validate must be semantic, not syntactic. \\textbf{(iii) Dynamic thresholds prevent attack-induced deadlock:} a fixed majority threshold drives every strategic-rejection round on GSM8K into the pending region ($0.0 \\pm 0.0\\%$, all seeds), whereas attack-adaptive thresholds restore $74.4 \\pm 8.4\\%$. \\textbf{(iv) Safety is preserved:} at most $10.0 \\pm 3.3\\%$ wrong commits on GSM8K and \\emph{never} on MBPP (pooled $95\\%$ Wilson interval $[0.0, 4.1]\\%$ at $n{=}90$)---on execution-validated domains every committed solution passes all test assertions by construction.",
    ["74.4", "8.4", "4.5", "3.9", "1.1", "10.0", "3.3", "4.1", "n{=}90"],
))

# ---------- L341 Reproducibility Statement：承接从 §6.1 移出的细节（不计页数） ----------
EDITS.append((
    341,
    "All source code, experimental data, and model configurations",
    "All source code, experimental data, and model configurations are available at \\url{https://github.com/anonymous/a2a-bft} (anonymized for review). Section~\\ref{sec:setup} summarises the setup; in full, all protocol-level fault-tolerance runs use the same heterogeneous four-model deployment with 5 seeds ($\\{42,\\dots,46\\}$) and 50 tasks per (configuration, seed, dataset) ($n{=}250$ per cell; 7{,}750 tasks over 31 cells), with task sets drawn per seed by a seeded shuffle over GSM8K, MBPP, and MMLU and reused across configurations for paired comparison, while ablation and baseline comparisons use 3 seeds ($\\{42,43,44\\}$) with $n{=}90$ per cell. The four models (Llama-3.1-8B, DeepSeek-V2-Lite, InternLM3-8B, Qwen2.5-7B; Instruct/Chat variants) are served by vLLM $0.11$ (temperature $0$, max\\_tokens $512$) on two NVIDIA A800-SXM4-80GB GPUs (CUDA 12.8, PyTorch 2.8.0). No simulated workers are used anywhere: every reported number comes from real LLM inference---7{,}750-task fault sweep; $4{,}320$ ablation/baseline tasks ($48$ cells $\\times$ $90$); and $770$ API tasks ($320$ multi-domain validation, Table~\\ref{tab:real_llm}, and $450$ adversarial-boundary scaling, Table~\\ref{tab:n8_scaling}). The reputation-tracker measurement of Section~\\ref{sec:rep_ablation} additionally releases the fully instrumented vote streams (\\texttt{reputation\\_vote\\_stream.json}) for 120 consensus tasks ($6$ cells $\\times$ $20$), the two-phase measurement-and-replay script, and the fidelity audit against the released penalty code, so that every reported tracker quantity can be recomputed offline without any LLM calls; those quantities are event counts, reported without a variance.",
    ["7{,}750", "4{,}320", "770", "vLLM", "A800", "120", "48"],
))

FAILS = []
before = after = 0
for idx, prefix, new, must in EDITS:
    old = lines[idx - 1]
    before += len(old)
    after += len(new)
    if not old.startswith(prefix):
        FAILS.append((idx, "前缀不符", old[:110]))
        continue
    missing = [m for m in must if m not in new]
    if missing:
        FAILS.append((idx, f"缺少关键内容 {missing}", new[:110]))
        continue
    lines[idx - 1] = new

if FAILS:
    print(f"[ABORT] {len(FAILS)} 条未通过，文件未写入：")
    for idx, why, s in FAILS:
        print(f"  [FAIL] L{idx}: {why}\n      {s}")
    sys.exit(1)

io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(lines))
print(f"完成 {len(EDITS)} 条编辑，行数 {orig_n} -> {len(lines)}")
print(f"正文侧字符 {before} -> {after}（净 {after-before:+d}；其中 Reproducibility Statement 承接了细节）")
