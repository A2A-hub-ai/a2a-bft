# A2A-BFT

**Byzantine Fault-Tolerant Consensus for Agent-to-Agent Protocols**

> Language: **English** | [简体中文](README.zh-CN.md)

A2A-BFT adds a consensus layer to Agent-to-Agent (A2A) protocols: under
heterogeneous multi-model deployment, a group of LLM agents reaches
**semantic consensus** on the same task while tolerating Byzantine participants
(prompt poisoning, collusion, strategic refusal) and soft-fault participants.

Submitted to ICLR 2027. Paper source: `papers/iclr2027_main.tex`.

---

## 1. Core idea

Three-phase semantic consensus: **Propose → Validate → Commit**

| Mechanism | Definition |
|------|------|
| Fault model | `n ≥ 3f + s + 1` (f = Byzantine, s = soft-fault) |
| Vote score | `φ(π) = \|ACCEPT\| − 0.5·\|REJECT\|` (counting, not weighted) |
| Dynamic thresholds | `θ_accept = n − 1 − 2f − s`, `θ_reject = −(n − 1 − f)·0.5` |
| Decision | `φ ≥ θ_accept` → ACCEPT; `φ ≤ θ_reject` → REJECT; otherwise PENDING (next round, view change) |
| Reputation | `reject_ratio ≥ 70%` triggers a penalty of `−0.25` per round |

**Agreement theorem (Theorem 5.1)**: the threshold gap
`gap = θ_accept − θ_reject = 1.5(n−1) − 2.5f − s`
equals `gap = 2f + 0.5s` on the safety boundary. Byzantine participants can shift
a single replica's φ by at most `1.5f` through vote flipping. Since `gap > 1.5f`,
two honest replicas **cannot** reach opposite terminal decisions (the only
possible divergence is ACCEPT versus PENDING). This gap is precisely the
absorber for equivocation.

---

## 2. Repository layout

```
.
├── papers/                     Paper (submission-relevant files only)
│   ├── iclr2027_main.tex       ★ Paper source
│   ├── references.bib          Bibliography
│   ├── generate_figures.py     Generator for the 5 paper figures
│   ├── figures/                Figures (PDF) + .figsource.json content fingerprints
│   ├── iclr2027_conference.*   Official style files (byte-identical to media.iclr.cc)
│   └── iclr-2027-style-files/  Original official style package (incl. download zip)
│
├── experiments/                Experiments: code + data + results
│   ├── src/                    ★ Core library (standard library only, 33 exported symbols)
│   │   ├── a2a_bft/            deepseek_worker.py consensus engine / baselines.py baselines
│   │   ├── a2a_bft/legacy/     Archived early implementation
│   │   └── block_a2a_integration/
│   ├── reproduce/              ★ Scripts generating the paper data (sole source of tables/figures)
│   ├── env/                    ★ Environment setup and vLLM deployment (env.sh self-locating vars)
│   ├── verification/           ★ Audits and negative tests (numbers/figures/theory/paths/revisions)
│   ├── results/                Experiment results (source of every number in the paper)
│   ├── datasets/               Benchmark datasets (GSM8K / MBPP / MMLU)
│   └── legacy/                 Archived historical experiment scripts
│
├── docs/
│   ├── REPRODUCTION.md         ★ Table/figure → script → command → artifact
│   ├── AUDIT.md                ★ Audit ledger
│   ├── audit/                  Data-source audit, PAT triage
│   ├── revisions/              Archived revision-period patch scripts
│   └── cleanup/                Cleanup lists and packaging scripts
│
├── reproduce.sh                ★ One-command reproduction entry point (see §3.0)
├── Makefile                    Thin wrapper around reproduce.sh (make verify / make doctor)
├── .a2a_project_root           Project-root marker (**do not delete**; scripts rely on it)
└── requirements.txt
```

> **Portability**: there is **no hard-coded machine path** anywhere in the
> repository. Python scripts locate the project root by searching upward for the
> `.a2a_project_root` marker; shell scripts self-locate through
> `experiments/env/env.sh`. Changing machine, directory, or username requires no
> code edits.

---

## 3. Getting started

### 3.0 One-command reproduction (recommended entry point)

`reproduce.sh` at the repository root is the **single entry point** — no need to
read documentation to pick commands, and no need to `cd`:

```bash
./reproduce.sh              # default = verify: 8 audits + 5 negative-test groups (CPU only)
./reproduce.sh doctor       # run this first: how far this machine can reproduce, and what is missing
./reproduce.sh figures      # regenerate figures from experiments/results/ and recheck figure-table consistency
./reproduce.sh all          # doctor + datasets + figures + verify
```

| Stage | Needs GPU | Notes |
|------|----------|------|
| `doctor` | No | Environment check: interpreter, dependencies, data/result/figure counts, GPU count |
| `verify` | No (needs matplotlib) | 8 audits + 5 negative-test groups; prints `REPRODUCE_OK` / `REPRODUCE_FAILED` |
| `figures` | No (needs matplotlib) | Regenerate the 5 figures + recheck content fingerprints |
| `datasets` | No | Download GSM8K / MBPP / MMLU and verify record counts |
| `install` | No | `pip install -r requirements.txt` |
| `full` | **Yes** (2×80GB) | All experiments; **aborts outright** when prerequisites are unmet — it never silently starts |

`verify` needs matplotlib because the figure-layer negative tests regenerate
figures in order to prove the freshness check is not vacuous. Install it via
`pip install -r requirements.txt` (or `./reproduce.sh install`).

Verdict semantics (important): audit scripts print
`REPRODUCE_OK` / `REPRODUCE_OK_PARTIAL` / `REPRODUCE_FAILED` with exit codes
0 / 0 / 1. **"Not verified" is not "passed"** — if a layer cannot run because a
dependency is missing, the verdict defaults to failure. Only an explicit
`A2A_ALLOW_SKIP_FIGURES=1` downgrades that layer to `SKIP`, and it is recorded in
the final verdict (`REPRODUCE_OK_PARTIAL`).

> ⚠️ **Do not run this script in parallel.** The negative tests temporarily
> rewrite `papers/iclr2027_main.tex` and then restore it byte-for-byte (they
> inject known defects to prove the audits really do catch them). Under
> parallelism the audits read the injected state and raise false alarms, and two
> negative scripts backing up/restoring concurrently overwrite each other. The
> script guards against this with a lock file, strict serialization, and an
> end-of-run hash comparison.

### 3.1 Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The core library `experiments/src/a2a_bft/` **depends only on the standard
library**, so "the protocol logic itself" can be imported and unit-tested with no
GPU and no third-party package. The dependencies above are only needed for real
LLM inference and plotting.

### 3.2 Download data and models

```bash
python experiments/env/download_datasets.py          # GSM8K / MBPP / MMLU
A2A_MODEL_DIR=/path/to/models python experiments/env/download_models.py
```

### 3.3 Launch 4 heterogeneous vLLM instances (2×80GB GPU required)

```bash
export A2A_MODEL_DIR=/path/to/models        # default /autodl-fs/data/models
bash experiments/env/start_vllm_seq.sh      # start one by one, waiting on health checks
```

| GPU | Model | Port | served-model-name | gpu-memory-utilization |
|-----|------|------|-------------------|------------------------|
| 0 | Llama-3.1-8B-Instruct | 8000 | `llama` | 0.30 |
| 0 | InternLM3-8B-Instruct | 8001 | `internlm` | 0.30 |
| 1 | DeepSeek-V2-Lite-Chat | 8002 | `deepseek` | 0.50 |
| 1 | Qwen2.5-7B-Instruct | 8003 | `qwen` | 0.28 |

**Why two GPUs are mandatory**: the four models total roughly 78 GB in FP16
weights, and a single 80GB card must additionally leave room for KV cache and
activations — it does not fit. The script also carries a protective assertion
requiring `device_count() >= 2`. The bottleneck is **total weight size**, not a
single instance's `gpu-memory-utilization`.

### 3.4 Run a minimal smoke test

```bash
A2A_VERBOSE=1 bash -c 'source experiments/env/env.sh'   # print the resolved paths
python experiments/env/smoke_code.py                   # connectivity check on a few tasks
```

The full data-generation pipeline is documented in
**[docs/REPRODUCTION.md](docs/REPRODUCTION.md)**.

---

## 4. Reproducibility and auditing

Every number in this repository can be **independently recomputed** rather than
merely "looking right". `experiments/verification/` contains two kinds of tools:

- **Audit scripts (8)**: recompute every number in the paper's prose, tables, and
  figures from the raw data in `experiments/results/`. They also cover the path
  resolution layer, the revision layer, and decision neutrality.
- **Negative tests (5)**: actively inject known defects into the repository to
  confirm the audits **really do catch them** (32/32 caught).
  > For the exact item counts per script, rely on the **live output** of
  > `./reproduce.sh verify` (that output is produced by the scripts themselves and
  > is never hard-coded). If a number stated here or in any document disagrees
  > with the live output, the live output is authoritative.
  Without this step, an "all green" audit cannot be distinguished from an audit
  that simply checks nothing.

```bash
python experiments/verification/audit_table_numbers.py     # 349 items: table numbers
python experiments/verification/audit_figures.py           # 124 items: figures + caption disclosure + fingerprint freshness
python experiments/verification/audit_prose_ranges.py      # prose ranges vs. tables
python experiments/verification/audit_theory_numerics.py   # theory formulas instantiated numerically + implementation consistency
python experiments/verification/audit_revision_layer.py    # 52 items: revision-layer algebra + textual self-consistency
python experiments/verification/audit_decision_neutrality.py
python experiments/verification/audit_reputation_fidelity.py
python experiments/verification/audit_paths.py             # path resolution layer (incl. read-open existence, §6 document command paths)

python experiments/verification/negative_test_tables.py    # 5/5
python experiments/verification/negative_test_figures.py   # 8/8
python experiments/verification/negative_test_theory.py    # 3/3
python experiments/verification/negative_test_paths.py     # 8/8
python experiments/verification/negative_test_revision.py  # 8/8
```

> The 13 commands above are equivalent to `./reproduce.sh verify` (one command,
> serial, with an overall verdict).

> The path layer exists because of a real incident: after a directory
> reorganization, a script computed its data directory as
> "the script's own location/results" and therefore pointed at a non-existent
> directory once moved — **and the acceptance check at the time only inspected
> `sys.path`, so "all green" concealed the fact that it could no longer run**.
> After moving or renaming any script, run `audit_paths.py` and
> `negative_test_paths.py` first.

See **[docs/AUDIT.md](docs/AUDIT.md)** for details.

> Note: the submission-compliance checklist (`SUBMISSION_CHECKLIST.md`) contains
> submission-identifying information. It is **double-blind material** and is not
> released in this anonymous repository, hence it is not linked here.

---

## 5. Experiment scale

| Experiment | Configuration | Scale | Data file |
|------|------|------|----------|
| Fault-tolerance sweep (main) | 3 datasets × 10 configs × 5 seeds × 50 tasks | 7,750 consensus runs | `full_bft_sweep_aggregated.json` |
| Ablations + baseline comparison | 2 domains × multiple methods × 3 seeds × 30 tasks | 4,320 | `multi_model_3seed_aggregated.json` |
| Multi-domain validation (real API) | 18 configs × 40 tasks | 770 | `deepseek_{math,knowledge,code}_fixed_20.json` |

**Every number comes from real LLM inference; there are no simulated workers.**
Sampling seeds: fault-tolerance sweep `{42,43,44,45,46}`; ablations and baselines
`{42,43,44}`. The same configuration reuses an identical task set across seeds to
support paired comparisons.

---

## 6. Hardware and software environment

- **GPU**: 2 × NVIDIA A800-SXM4-80GB (512GB host memory)
- **Software**: CUDA 12.8, PyTorch 2.8.0, vLLM 0.11.0, transformers 4.56.2, Python 3.13
- **Decoding**: temperature 0, max_tokens 512
- **Models**: Llama-3.1-8B-Instruct, DeepSeek-V2-Lite-Chat, InternLM3-8B-Instruct, Qwen2.5-7B-Instruct

---

## 7. Citation

```bibtex
@inproceedings{a2abft2027,
  title     = {Byzantine Fault-Tolerant Consensus for Agent-to-Agent Protocols},
  booktitle = {International Conference on Learning Representations (ICLR)},
  year      = {2027}
}
```
