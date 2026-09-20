# Reproduction Guide

> Language: **English** | [简体中文](REPRODUCTION.zh-CN.md)

> **One-command entry point (recommended)**: this document is the complete
> table/figure → script → command → artifact mapping, for when you need precise
> control over individual commands. For everyday reproduction use
> `reproduce.sh` at the repository root:
>
> ```bash
> ./reproduce.sh doctor     # check first: how far this machine can reproduce
> ./reproduce.sh verify     # 10 audits + 5 negative-test groups (CPU only, about 1 minute)
> ./reproduce.sh all        # datasets + figures + verify
> ```
>
> Verdict semantics: `REPRODUCE_OK` / `REPRODUCE_OK_PARTIAL` / `REPRODUCE_FAILED`,
> with exit codes 0 / 0 / 1. "Not verified" is not "passed".

This document gives the **data source, generating script, run command, and
expected artifact for every table and figure in the paper**. All paths are
relative to the repository root; all commands can be run directly from the
repository root (scripts self-locate, no `cd` needed).

---

## 0. Pipeline overview

```
                    start_vllm_seq.sh  (2×A800, 4 vLLM instances)
                              │
        ┌─────────────────────┼──────────────────────┬────────────────────┐
        │                     │                      │                    │
   full_bft_sweep.py    multi_model_compare_    large_scale_         correctness
   {gsm8k,mbpp,mmlu}      ablation_v2/v3.py      experiment.py        _50x3_log.txt
        │                 multi_model_multiseed.py  (DeepSeek API)      │
        │                 mbpp_debate_fix.py            │         parse_correctness_log.py
        ▼                        ▼                      ▼               ▼
  aggregate_full_sweep.py   merge_3seed.py     deepseek_{math,       correctness_50t_
        │                        │              knowledge,code}_      3s_run1_from_log.json
        ▼                        ▼              fixed_20.json               │
  full_bft_sweep_          multi_model_3seed_        │            run_pairing_mcnemar.py
  aggregated.json          aggregated.json           │                      │
        │                        │                   │                      ▼
        └────────────┬───────────┴───────────────────┴──────────────►  run_pairing_mcnemar.json
                     ▼
            papers/generate_figures.py
                     ▼
            papers/figures/*.pdf  (included directly by LaTeX via \includegraphics)
```

**Results directory convention**: all intermediate and final results land in
`experiments/results/`. Override with the environment variables
`A2A_RESULTS_DIR` / `A2A_DATASET_DIR`.

---

## 1. Environment setup

```bash
pip install -r requirements.txt

export A2A_MODEL_DIR=/path/to/models        # default /autodl-fs/data/models
export A2A_PY=$(which python)               # default /root/miniconda3/bin/python

A2A_VERBOSE=1 bash -c 'source experiments/env/env.sh'   # print the resolved paths and confirm them
```

### 1.1 Datasets

```bash
python experiments/env/download_datasets.py
```

Expected artifacts (in `experiments/datasets/`):

| File | Records | Used in paper | Notes |
|------|------|----------|------|
| `gsm8k_test.json` | 1,319 | ✅ | GSM8K test split; answers carry the `####` terminator |
| `mbpp_test.json` | 500 | ✅ | MBPP; each item has a non-empty `code` and `test_list` |
| `mmlu_3subjects.json` | 312 | ✅ | abstract_algebra 100 + college_mathematics 100 + machine_learning 112 |
| `humaneval_full.json` | 164 | ❌ | Loadable, but never enters the paper's data chain |

> `mmlu_4subjects.json` (312 records, **byte-identical** to
> `mmlu_3subjects.json`, misleadingly named, referenced by no script) was
> **deleted during the 2026-09-17 cleanup**. The same pass also fixed the
> `dataset_summary.json` it had polluted (the old `total_tasks: 2607` counted
> that duplicate together with the unused HumanEval; the paper's actual usage is
> **2,131**). See `docs/audit/DATA_SOURCE_AUDIT.md` §14.

> `dataset_summary.json` is generated automatically by the scripts and records
> the warnings above; it needs no manual maintenance.

### 1.2 Model weights

Four models (about 78 GB total in FP16):

```
Llama-3.1-8B-Instruct  DeepSeek-V2-Lite-Chat  InternLM3-8B-Instruct  Qwen2.5-7B-Instruct
```

### 1.3 Launch vLLM (2 × 80GB GPUs)

```bash
bash experiments/env/start_vllm_seq.sh      # recommended: start one by one + health checks
# or bash experiments/env/start_vllm.sh     # start in parallel, faster but may contend for VRAM
```

| GPU | Model | Port | name | util |
|-----|------|------|------|------|
| 0 | Llama-3.1-8B-Instruct | 8000 | `llama` | 0.30 |
| 0 | InternLM3-8B-Instruct | 8001 | `internlm` | 0.30 |
| 1 | DeepSeek-V2-Lite-Chat | 8002 | `deepseek` | 0.50 |
| 1 | Qwen2.5-7B-Instruct | 8003 | `qwen` | 0.28 |

When everything is ready the script prints `ALL_4_VLLM_READY`. **Two GPUs are
mandatory**: a single 80GB card cannot hold 78 GB of weights plus KV cache;
`multi_model_vllm.py` carries a protective `device_count() < 2` assertion.

Smoke tests:

```bash
python experiments/env/probe.py        # one round-trip per instance, checking the response shape
python experiments/env/quick_test.py   # quick connectivity
python experiments/env/smoke_code.py   # a few end-to-end code tasks
```

---

## 2. Tables → data source → commands

### Pipeline A — fault-tolerance sweep (main experiment)

Covers `tab:baseline`, `tab:bft`, `tab:mmlu_sweep`, `tab:attacks` (plus the
measured rounds / calls / latency columns of `tab:performance` and
`tab:complexity`).

| Step | Command | Artifact |
|------|------|------|
| 1 | `python experiments/reproduce/full_bft_sweep.py gsm8k` | `results/full_bft_sweep_gsm8k.json` |
| 1 | `python experiments/reproduce/full_bft_sweep.py mbpp` | `results/full_bft_sweep_mbpp.json` |
| 1 | `python experiments/reproduce/full_bft_sweep.py mmlu` | `results/full_bft_sweep_mmlu.json` |
| 2 | `python experiments/reproduce/aggregate_full_sweep.py` | `results/full_bft_sweep_aggregated.json` |

Scale: **5 seeds × 50 tasks = 250 tasks per cell**, seeds `{42,43,44,45,46}`,
7,750 consensus tasks in total.

Batch execution in the background (equivalent to running the three datasets in
sequence):

```bash
bash experiments/env/run_sweeps.sh
```

Verification:

```bash
python experiments/verification/audit_table_numbers.py   # the tab:baseline/bft/mmlu/attacks sections
```

### Pipeline B — ablations and baseline comparison

Covers `tab:ablation`, `tab:hetero_compare`.

| Step | Command | Artifact |
|------|------|------|
| 1 | `python experiments/reproduce/multi_model_compare_ablation_v2.py` | `results/multi_model_compare_ablation_v2.json` (GSM8K, seed 42) |
| 1 | `python experiments/reproduce/multi_model_compare_ablation_v3.py` | `results/multi_model_compare_ablation_v3.json` (MBPP, seed 42) |
| 1 | `python experiments/reproduce/multi_model_multiseed.py` | `results/multi_model_multiseed.json` (seeds 43, 44) |
| 1 | `python experiments/reproduce/mbpp_debate_fix.py` | `results/mbpp_debate_fix.json` (LLM-Debate code-repair generation) |
| 2 | `python experiments/reproduce/merge_3seed.py` | `results/multi_model_3seed_aggregated.json` |

Scale: **3 seeds × 30 tasks = 90 tasks per cell**, seeds `{42,43,44}`.

> **Note**: `mbpp_debate_fix.py` must finish before `merge_3seed.py` runs — the
> latter uses its output to replace the LLM-Debate row in
> `multi_model_compare_ablation_v3.json` (fixing that row's unreasonable
> generation budget on code tasks).

> `merge_final.py` is an earlier "two-domain merge" variant producing
> `multi_model_compare_ablation_final.json`; the final tables use
> `merge_3seed.py`. Both were **deleted on 2026-09-17** (`_final.json` had zero
> readers, and `merge_final.py`'s output had no consumer). The live chain is only
> `merge_3seed.py`.

### Pipeline C — multi-domain validation (real DeepSeek API)

Covers `tab:real_llm`.

```bash
export DEEPSEEK_API_KEY=sk-...        # required; the scripts no longer embed a key
python experiments/reproduce/large_scale_experiment.py
```

Artifacts: `results/deepseek_{math,knowledge,code}_fixed_20.json`

| Domain | Dataset | Tasks per config |
|------|--------|-----------|
| math | GSM8K | 40 |
| knowledge | MMLU | 40 |
| code | MBPP | 40 |

18 configs × 40 tasks = 720 real-API tasks. Report:
`results/large_scale_experiment_report.md`.

> This pipeline **does not use vLLM**; it only needs an API key and network access.

### Pipeline D — n=8 adversarial boundary and paired testing

Covers `tab:n8_scaling` and the Δ and McNemar paired test of
`tab:a2a_sim_comparison`.

| Step | Command | Artifact |
|------|------|------|
| 1 | (raw run log) | `results/correctness_50x3_log.txt` |
| 2 | `python experiments/reproduce/parse_correctness_log.py` | `results/correctness_50t_3s_run1_from_log.json` |
| 3 | `python experiments/reproduce/run_pairing_mcnemar.py` | `results/run_pairing_mcnemar.json` |

`run_pairing_mcnemar.py` performs a **task-by-task paired** comparison of the two
n=8 runs (same task sampling) and outputs paired McNemar test results.

### Pipeline E — cost benchmark (optional, not on the paper's data chain)

```bash
python experiments/reproduce/performance_test.py
# -> results/performance_test_results.json
```

The **measured rounds, call counts, and latencies** in `tab:performance` /
`tab:complexity` come from Pipeline A's aggregates (the `avg_rounds` /
`avg_calls` / `avg_time` metrics produced by `aggregate_full_sweep.py`), not from
this script. This script is a standalone cost benchmark whose output is **not on
the paper's data chain**.

### Pipeline F — reputation tracker measurement ablation

Supports `fig:reputation` (changed from "illustrative" to "measured") and
`tab:rep_ablation`.

```bash
# Stage 1 (online, requires all 4 vLLM instances ready): run the protocol and log every vote in every round
python experiments/reproduce/reputation_ablation.py --tasks 20

# Stage 2 (offline, CPU only, zero LLM calls): replay from the cached vote stream
python experiments/reproduce/reputation_ablation.py --replay-only
```

| Step | Command | Artifact |
|------|------|------|
| 1 | `python experiments/reproduce/reputation_ablation.py --tasks 20` | `results/reputation_vote_stream.json` (vote stream) + `results/reputation_ablation.json` (four-variant results) |
| 2 | `python experiments/reproduce/reputation_ablation.py --replay-only` | Same, reproducible any number of times |
| 3 | `python experiments/reproduce/render_reputation_report.py` | `results/reputation_ablation_report.md` (incl. task-level columns: mispenalized tasks / triggered tasks) |
| 4 | `python experiments/verification/audit_reputation_fidelity.py` | Fidelity comparison: `FIDELITY_OK`, escalated penalties 5180 / 5180 |
| 5 | `python experiments/verification/verify_mbpp_subboundary.py` | `results/mbpp_subboundary_verification.json` (offline reproduction of the out-of-bound wrong commit, zero LLM calls) |

> **Replay definition (corrected 2026-09-17)**: the `ok` predicate must be
> written as a disjunction
> `(v == 'accept' and c) or (v == 'reject' and not c)`,
> matching `deepseek_worker.py:975-980`. Writing `(v == 'accept') == c` counts
> "abstaining on a wrong proposal" as voting correctly; the two disagree only on
> ABSTAIN. After the fix, the main-text figure changes from $1{,}217$ of
> $1{,}305$ to **$1{,}186$ of $1{,}305$**; the four-variant replay decision
> sequences remain field-by-field identical to the online record. See
> `docs/AUDIT.md` §3.6.1.

**Why not "reputation on/off vs. acceptance rate"**: §4.3 of the paper and the
appendix state that reputation scores **do not enter the vote-counting rule**
(the `commit` formula aggregates raw vote counts), so reputation **cannot**
change any commit decision — that comparison is a mathematical identity, a
corollary of the theorem rather than an experimental finding. The script instead
measures **what the tracker itself reports**:

| ID | What is measured |
|------|----------|
| M1 | Decision metrics (cross-checked against the corresponding `tab:ablation` cells to confirm the protocol path is unchanged) |
| M2 | Trigger distribution of the four penalty variants (split by "verifier ground truth × whether that vote was objectively correct") |
| M3 | Byzantine detection performance: treat "triggered the aggressive penalty (ρ≥0.7, −0.25)" as a detector and compute P/R/F1 |
| M4 | **Mispenalty rate**: the share of aggressive penalties landing on "an honest verifier whose vote was objectively correct" |
| M5 | Source of `c`: Algorithm 1 requires c = whether the proposal is actually correct; the released implementation uses `_estimate_correctness` (format check). Replay once with oracle c and once with released c to quantify the gap |

Four-variant replay = `{oracle, released} × {persistent, fresh}`. Every replay
asserts that **the replayed decision sequence is field-by-field identical to the
online record** (`decision_consistent` must be True) — this is both a correctness
check and **verifiable evidence** for the claim that decisions are unaffected by
reputation.

The script supports `-h` for usage; the online stage performs an endpoint
pre-check before starting, to avoid a wasted run.

---

### Pipeline G — validation-oracle (judge) error-rate calibration

Supports the appendix's judge-calibration tables (`tab:judge_calib`, on-protocol;
`tab:judge_heldout`, held-out) and the measured false-accept rate cited next to
Corollary 1 in the main text. The appendix's safety bound is **conditional on the
oracle's miss probability**, so this pipeline measures that probability instead of
assuming it ($p_h \geq 0.9$ in the theorem's illustration; measured
$\approx 0.80$).

**Level 1 — on-protocol, offline, zero LLM calls** (CPU only; this is what the
acceptance run executes):

```bash
python experiments/verification/calibrate_judge_from_streams.py   # recompute FPR/FNR from the released vote streams
python experiments/verification/audit_judge_calibration.py        # check every calibrated number against the paper
```

**Level 2 — held-out, requires the 4 vLLM endpoints** (optional: reproduces the
held-out table from scratch; the released per-call records are already in
`results/heldout_judge_calibration.json`):

```bash
python experiments/verification/heldout_judge_calibration.py \
    --datasets experiments/datasets --out experiments/results/heldout_judge_calibration.json
```

| Step | Command | Artifact |
|------|------|------|
| 1 (offline) | `python experiments/verification/calibrate_judge_from_streams.py` | prints the on-protocol FPR/FNR (GSM8K, 241 rounds / 700 honest votes) cited in the paper's `tab:judge_calib` |
| 2 (offline) | `python experiments/verification/audit_judge_calibration.py` | `AUDIT PASS`: on-protocol aggregate, per-judge composition, and held-out rates all match the paper |
| 3 (GPU) | `python experiments/verification/heldout_judge_calibration.py --datasets experiments/datasets --out experiments/results/heldout_judge_calibration.json` | `results/heldout_judge_calibration.json`: 2,192 per-call records (150 GSM8K + 124 MMLU held-out tasks × {correct, plausible-wrong} × 4 judges) |

> **Held-out sample definition**: task indices excluded from *every* task set used
> in the paper (the full sweep, ablation, reputation, and multiseed samplings), so
> the calibration sample is disjoint from every reported experiment. Proposals are
> the ground-truth answer (measures FNR) and a deterministic plausible
> perturbation — a numeric delta on GSM8K, a wrong choice letter on MMLU (measures
> FPR) — presented with the protocol's judge prompts and verdict parsing **verbatim**.
> Unparsed verdicts map to ABSTAIN and are excluded from the rates.
>
> **Reading the result**: the aggregate false-accept rate is not a uniform oracle
> error — it is dominated by one permissive judge (DeepSeek-V2-Lite), while the
> other three reject almost all wrong GSM8K answers. The on-protocol vote streams
> decompose the same way, and the offline auditors (Steps 1–2) check that
> decomposition, so this conclusion is reproducible without a GPU.

---

## 3. Figures → how they are generated

```bash
python papers/generate_figures.py
```

Artifacts are written to `papers/figures/` (PDF for LaTeX, PNG for preview; PNG
is ignored by `.gitignore`).

| Paper figure | File | Data source |
|----------|------|----------|
| `fig:attack_resistance` | `attack_resistance.pdf` | `results/full_bft_sweep_aggregated.json` |
| `fig:performance_comparison` | `performance_comparison.pdf` | same, plus `multi_model_3seed_aggregated.json` |
| `fig:architecture` | `architecture.pdf` | drawn purely in code (schematic) |
| `fig:consensus_flow` | `consensus_flow.pdf` | drawn purely in code (protocol flow) |
| `fig:reputation` | `reputation_mechanism.pdf` | drawn purely in code (reputation rule) |

> The paper actually `\includegraphics` only 5 figures: `consensus_flow` /
> `architecture` / `performance_comparison` / `reputation_mechanism` /
> `attack_resistance`. The earlier artifacts `acceptance_rates.*` and
> `fault_tolerance_surface.*` (the latter was an "acceptance rate" synthesized as
> `honest_ratio * 95`, unrelated to the real-machine measurements) plus a batch of
> `correctness_*.png` / `n8_scaling_results.png` were **deleted on 2026-09-17**,
> and the corresponding plotting functions (`load_experiment_data` /
> `plot_acceptance_rates` / `plot_fault_tolerance_surface`) were removed from
> `papers/generate_figures.py` at the same time. After removal the regenerated
> figures were **pixel-identical** to before (5/5, maximum channel difference 0),
> confirming the deletion was inert.

> The three schematics are generated entirely in code and are **same-sourced** as
> the threshold rules used in the protocol implementation; if you change the
> threshold formulas in `experiments/src/a2a_bft/deepseek_worker.py`, you must
> rerun this script and recheck those three figures.

---

## 4. Compiling the paper

```bash
cd papers
pdflatex iclr2027_main && bibtex iclr2027_main && pdflatex iclr2027_main && pdflatex iclr2027_main
```

> **The single submission file**: **the official submission file is
> `papers/iclr2027_main.tex`** (using the official ICLR 2027 style
> `iclr2027_conference.sty`, byte-identical to the official package from
> `media.iclr.cc`). The earlier draft fork `papers/iclr2026_main.tex` (which used
> a broken `arxiv.sty`) was deleted in the 2026-09-15 reorganization; the
> repository contains **no** iclr2026 source files any more, so there is no risk
> of editing the wrong file.

---

## 5. Full acceptance run

> Verified on both platforms with the identical result **15 passed / 0 failed**
> (`REPRODUCE_OK`): Windows + Python 3.13 and Linux + Python 3.12 (CUDA 12.8,
> vLLM 0.11.0, 2×A800). Note that `verify` needs `matplotlib` importable by the
> interpreter it runs under — pick one with `A2A_PY=/path/to/python` if several
> are installed; without it the figure-fingerprint audit reports a failure
> rather than silently skipping.

```bash
# 1) Audits
python experiments/verification/audit_table_numbers.py      # 348 items, 0 problems
python experiments/verification/audit_figures.py            # 124 items, 0 problems
python experiments/verification/audit_theory_numerics.py    # all OK
python experiments/verification/audit_prose_ranges.py       # no numeric inconsistency
python experiments/verification/audit_paths.py              # 0 problems, all four counters > 0
python experiments/verification/audit_revision_layer.py     # 52 items, 0 problems

# 1b) Fidelity and offline reproduction (zero LLM calls)
python experiments/verification/audit_reputation_fidelity.py  # FIDELITY_OK, 5180/5180
python experiments/verification/verify_mbpp_subboundary.py    # MBPP_SUBBOUNDARY_DONE
python experiments/verification/audit_decision_neutrality.py  # DECISION_NEUTRALITY_OK, 9 items
                                                              # (recompute phi from raw votes + replay decisions + mutation test)
python experiments/verification/audit_judge_calibration.py    # AUDIT PASS: on-protocol, per-judge, held-out rates vs. the paper
python experiments/verification/calibrate_judge_from_streams.py  # AUDIT PASS: judge FPR/FNR recomputed from the vote streams

# 2) Audit effectiveness (inject defects; they must be caught)
python experiments/verification/negative_test_tables.py     # 5/5
python experiments/verification/negative_test_figures.py    # 8/8
python experiments/verification/negative_test_theory.py     # 3/3
python experiments/verification/negative_test_paths.py      # 8/8
python experiments/verification/negative_test_revision.py   # 8/8
```

If the negative tests do **not all catch** their injected defects, the audits are
ineffective and their "all green" result cannot be trusted — in that case do not
rely on step 1.

> **Item counts change as cases are added or removed.** The counts above
> correspond to the current test suite; the authoritative source is the **live
> output** of `./reproduce.sh verify`, which reads the numbers from each script's
> actual stdout. If a number here disagrees with the live output, the live output
> wins. (Hard-coded expectations in this document had already drifted once: the
> counts here said 348 / 123 items and 6/6 / 5/5 negative cases while the live
> output of that revision reported 349 / 124 and 8/8 / 8/8 — the table-number
> count has since moved back to 348 as table rows were consolidated.)

> **Why `audit_paths.py` must be in this list**: it checks whether the paths in
> the delivered scripts still resolve. After the directory reorganization, three
> scripts had silently broken because their data directory / project root was
> derived from **the script's own location** (two of them being the data sources
> for `tab:n8_scaling` and the McNemar test), while the acceptance check at the
> time only inspected `sys.path`, so it reported "all green". After moving or
> renaming any script, always run this check first.
> See [`AUDIT.md` §2/§3.5](AUDIT.md).

---

## 6. FAQ

**Q: I only have 1 GPU. Can I run this?**
Not fully. The four models total about 78 GB in FP16 and do not fit on a single
80GB card (which must also hold KV cache). You can degrade gracefully: deploy
only 2 models for small-scale connectivity checks, but the paper's data cannot be
reproduced that way.

**Q: Does a failing `import openai` affect the audits?**
No. `openai` is imported lazily inside functions (`deepseek_worker.py:112`,
`multi_model_vllm.py:231`), and the protocol library, audit scripts, and negative
tests do not need it.

**Q: Imports fail after moving the scripts?**
That should not happen. Every Python script locates the project root by searching
upward for the `.a2a_project_root` marker, and shell scripts self-locate through
`experiments/env/env.sh`. If it does fail, first check that `.a2a_project_root`
has not been deleted.

**Q: Where are the result files?**
All under `experiments/results/`. Simulation-era results that were scattered at
the top level of `experiments/` before 2026-09-15 were moved into
`experiments/results/archive_simulation_era/`, and that directory was **deleted on
2026-09-17** together with the remaining simulation-era and superseded artifacts
(35 entries / 1.75 MB). The backup and manifest are kept in the full working copy
(`A2A_cleanup_backup_20260917.tar.gz`,
`docs/cleanup/cleanup_manifest_20260917.txt`) and are not part of this anonymous
release. The current directory contains **no simulated data**.
