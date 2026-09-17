# The Audit System (AUDIT)

> Language: **English** | [简体中文](AUDIT.zh-CN.md)

This repository subjects **every number in the paper to a recomputation-based
check**. This document explains which layers the audit is divided into, what each
layer checks, and why the audit itself is not vacuous.

> **About the item counts appearing in this document ("349 items", "8/8", ...)**
> They change as cases are added or removed, so writing them into documentation
> invites staleness — and because pass/fail is decided by exit codes alone, a
> stale number can go unnoticed for a long time (this actually happened:
> `reproduce.sh`'s label was stuck at "6 injected path defects" while the script
> had already grown to 8).
> **The authoritative count is always the live output of `./reproduce.sh verify`**:
> it is read by `extract_count()` from each script's actual output and is never
> hard-coded. If a number here or in the README disagrees with that live output,
> **the live output wins**, and the disagreeing number should be fixed.

---

## 1. Why audit at all

The easiest place in a paper to make a mistake — and the hardest place to notice
one — is not the algorithm but **the gap between a number and the source it claims
to come from**: table values copied by hand, ranges eyeballed, caption sample
sizes inconsistent with the prose, threshold formulas in code differing from
those in the paper. Such problems are usually invisible when "reading through",
because **every individual number looks reasonable**.

Hence the repository's verification principle: **anything that can be recomputed
from the raw data must not be trusted as transcription.**

---

## 2. The nine-layer audit model

| Layer | Name | What it checks |
|----|------|--------|
| L1 | Table numbers | Every number in the paper's tables vs. recomputation from `experiments/results/` |
| L2 | Formula algebra | Whether columns derived by formula (e.g. the fault-tolerance column) are algebraically equivalent to the theorem |
| L3 | External fidelity and mechanism delivery | Whether cited external-method data is attributed; whether claimed mechanisms are actually implemented |
| L4 | Prose ranges | Whether numeric ranges, percentages, and sample sizes in the abstract/prose/conclusion match the tables |
| L5 | Methodological promises + theorem assumption completeness | Whether promised experimental conditions (seed count, task count) were actually executed; whether the theorem's assumptions cover what the conclusion needs |
| L5b | **Theorem provability** | Whether the conclusion follows from the assumptions (whether behaviours the assumptions permit are enough to falsify it) |
| L6 | Provenance | Whether the chain data file → generating script → paper location is closed |
| L7 | Figure layer | Figure data sources, caption disclosure (e.g. n=90), freshness of PDFs vs. generating script |
| L8 | **Promise surface and delivered-code layer** | Whether the deliverable actually satisfies what "All source code / reproducibility statement" promises |
| L9 | **Path resolution layer** | Whether every path constant in the delivered scripts (data directory, `sys.path` target) points at a real location |

> L5b, L8, and L9 are the last three layers added to this project's audit: L5b
> governs "does the theory hold", L8 governs "does the deliverable keep its
> promises", and **L9 governs "does the deliverable still run"**.

### Why L9 exists

The 2026-09-15 directory reorganization moved scripts. Afterwards:

- `experiments/reproduce/parse_correctness_log.py` and `run_pairing_mcnemar.py`
  located their data directory via `os.path.join(HERE, "results", ...)`. While the
  scripts sat under `experiments/`, HERE happened to be the parent of the results
  directory; after moving into `experiments/reproduce/`, HERE changed and the path
  pointed at a **non-existent** `experiments/reproduce/results/`. These two scripts
  are exactly the data sources for the paper's `tab:n8_scaling` and the McNemar
  paired test — following the reproduction guide to Pipeline D fails outright.
- `docs/cleanup/build_cleanup_list.py` located the project root with
  `ROOT = dirname(abspath(__file__))`; after moving into `docs/cleanup/`, ROOT
  became `docs/cleanup`, `add()` matched nothing, and the deletion manifest was
  **always empty and never raised an error**.

The acceptance check at the time only verified `sys.path` insertion targets and
**did not cover the "data directory constant" class at all**, so "all green"
concealed three scripts that could no longer run. L9 closes that blind spot.

---

## 3. Audit scripts

### 3.1 `audit_table_numbers.py` — 349 items

| Function | Coverage |
|------|----------|
| `check_baseline()` | `tab:baseline` |
| `check_bft()` | `tab:bft` |
| `check_mmlu()` | `tab:mmlu_sweep` |
| `check_ablation()` | `tab:ablation` |
| `check_compare()` | `tab:hetero_compare` |
| `check_n8()` | `tab:n8_scaling` |
| `check_ttest()` | Paired t-test statistics (recomputed from raw data) |
| `check_attack_ranges()` | `tab:attacks` ranges = min/max of the source rows |
| `check_real_llm()` | `tab:real_llm` (incl. conservation of submitted / completed / API-failed counts) |
| `check_complexity()` | `tab:complexity` fault-tolerance column equivalent to the theorem; round-count column matching measured min–max |
| `check_a2a_sim()` | `tab:a2a_sim_comparison` Δ arithmetic and external-data attribution |
| `check_promises()` | **L8**: whether the hardware/scale promises in the reproducibility statement match the main text and appendix |

Data sources: `full_bft_sweep_aggregated.json`,
`multi_model_3seed_aggregated.json`,
`correctness_50t_3s_run1_from_log.json`,
`deepseek_{math,knowledge,code}_fixed_20.json`.

### 3.2 `audit_figures.py` — 124 items

- **Existence** and **freshness** of the five figures (content-fingerprint basis:
  `figures/.figsource.json` records the generating script's logical fingerprint
  and the md5 of each data file; changing a comment does not falsely report
  staleness, changing data always does)
- Sample-size disclosure in figure and table captions (e.g. n=90 must appear)
- Point-by-point comparison of figure data points against the aggregate JSON

Covers all 5 paper figures (`consensus_flow`, `architecture`,
`reputation_mechanism`, `performance_comparison`, `attack_resistance`).

### 3.3 `audit_theory_numerics.py`

- §6 **Agreement margin**: for all configurations with `n ≤ 20` inside the safety
  boundary, verify `gap ≥ 2f + 0.5s` and `gap > 1.5f` (the Byzantine vote-flip
  bound)
- §7 **Executable probe**: call the reference implementation's
  `ConsensusLayer._commit` directly and check, over 5 `(n, f, s, A, R)` cases,
  that its decisions match the paper's rule (including
  `(4,0,0,A=2,R=1) → PENDING`)
- §8 **Delivered-code threshold sweep**: recursively scan every `.py` under `src/`
  and confirm no writing contradicts the paper's threshold rule

### 3.4 `audit_prose_ranges.py`

Consistency of numeric ranges in the prose/abstract against the tables, and
whether "cells not shown in a table" are appropriately qualified (avoiding
"coverage read as 100%").

### 3.5 `audit_paths.py` (L9) — file class 38 / dir class 121 / smoke 163 / `sys.path` 64 / `open()` 8 / doc commands 152 (as of this revision)

> These counts change as files are added or removed and are **not fixed values**:
> the script itself prints the current measured numbers, and the criterion is
> "every counter > 0 and problem count = 0", not "the numbers equal some historic
> value". When editing this line, take the numbers from `audit_paths.py`'s actual
> output.

| Section | Check |
|----|------|
| §1 | The **parent directory** of every path constant inside the project must exist (a path used for writing may point at a not-yet-existing file, but its directory must already exist) |
| §2 | **Smoke fingerprint**: whether a path is **derived from the script's own location** as `<script dir>/<data dir name>/` — a code directory never hosts a data directory |
| §3 | Every directory inserted into `sys.path` must exist |
| §4 | Diagnostics: CWD-dependent relative path constants, AutoDL-side POSIX paths (not judged as failures) |
| §5 | Data files opened for **reading** via `open()` must actually exist (added 2026-09-17) |
| §6 | `python\|bash <path>` commands given in documentation/scripts must point at scripts that actually exist (added 2026-09-17) |

> **Where §6 came from**: a reproducer does not read source code, they copy
> commands out of `README.md` / `REPRODUCTION.md`. After the round-19 directory
> reorganization, **5 places in the packaged documentation still gave old paths**
> (placing an audit script under `experiments/` when it had moved to
> `experiments/verification/`), and copying them yields
> `No such file or directory`. Yet §1–§5 all scan `.py` only and are completely
> blind to this class.
> §6 covers `.md / .sh / .txt`; `docs/reviews/` is excluded as a historical
> snapshot of "the state at the time".
>
> Note: the explanatory text of this section itself must not contain a
> **literally executable dead command** — §6 will flag a command quoted as a
> counter-example as dead too (observed: this section's first draft was caught by
> §6). When describing historical defects, use descriptive wording rather than
> pasting the raw command line.

Deciding "derived from the script's own location" looks at the **derivation
source**, not at mere name coincidence: in `papers/generate_figures.py`,
`ROOT/papers/figures` happens to equal "script dir/figures", but it is derived
from the project root, which is correct; the real defect is deriving from the
script's own directory. Confusing the two produces false positives.

The implementation carries three hard constraints (each bought with a real
incident — see the module docstring of `audit_paths.py`):

1. **Never `exec`.** An early version used `exec` to evaluate top-level statements
   one by one to extract constant values, and ended up executing
   `mbpp_debate_fix.py`'s experiment body too — issuing real API requests and
   hanging the process. It now performs pure-AST **symbolic evaluation**,
   recognising only `os.path.*`, string concatenation, f-strings, `Path / "x"`,
   and `os.environ.get` defaults; anything else evaluates to UNKNOWN.
2. **Recognise the three idioms for "search upward for the project root"**
   (`X = dirname(X)` inside a `while`; `if exists(_cur/marker): X = _cur; break`
   inside `while True`; `def _find_root(start) → return cur` followed by
   `ROOT = _find_root(__file__)`). Recognising only one of them made the other two
   count as "script directory", producing 4–12 false positives at a time.
3. **Guard against vacuity.** The file-class / dir-class / smoke / `sys.path`
   counters each have their own counter, and any of them being 0 fails the audit.

### 3.6 `audit_reputation_fidelity.py` — fidelity comparison

`ReputationTracker` in `experiments/reproduce/reputation_ablation.py` claims to
be "a faithful implementation of the paper's Algorithm 1". **A claim cannot
certify itself**, so this audit **copies line by line** the penalty fragment at
`src/a2a_bft/deepseek_worker.py:982-1002` into an independent
`released_update()`, then compares the two round by round over `r_i` on the
**same random vote sequence**.

| Item | Value |
|----|-----|
| Comparison steps | 12000 (300 sequences × 40 steps) |
| Steps in disagreement | 0 |
| Escalated-penalty triggers (reference / this implementation) | 5180 / 5180 |

Conclusion: the tracker faithfully replicates the released implementation,
**including** that extra `max(0.3, r - 0.2)` when the suspect counter reaches its
threshold. This turns an internal contradiction in the paper into a decidable
question: §4.3 says the reference implementation "escalates penalties for
persistent misbehaviour", while the appendix says the suspect counter is
"warnings only; penalties are fixed per tier". **The code supports the former**,
and the measured `escalated` count is the only authoritative figure.

> This audit also exposed a bug in itself: `self.suspect` was initially declared
> and read but never incremented, so `0 >= 3` was always false and the escalated
> penalty never fired — i.e. the "faithful implementation" was quietly missing an
> entire penalty rule. **Fidelity must be established against an independent
> implementation, never by reading the code.**

#### 3.6.1 The vote alphabet must include ABSTAIN (corrected 2026-09-17)

The escalated-trigger count in the table above was once `7123 / 7123`. Changing
it to **`5180 / 5180`** was not an implementation change but a **change in the
random vote alphabet**: the original audit drew only `accept` / `reject`, whereas
the real online vote stream (`reputation_vote_stream.json`, 2{,}461 votes)
contains **148 ABSTAIN votes** (`ABSTAIN/False` 104 + `ABSTAIN/True` 44). With
abstentions included, the "reward branch" resets on more rounds, the escalation
counter shifts later, and the absolute count drops while the two sides remain
**round-by-round identical**.

The same correction fixed a **semantic trap that only surfaces on abstentions**:
`reputation_ablation.py` previously used

```python
ok = (v == 'accept') == c        # wrong
```

while the released implementation (`deepseek_worker.py:975-980`) uses a
disjunction:

```python
ok = ((v == 'accept') and c) or ((v == 'reject') and (not c))   # correct
```

The two are exactly equivalent on `accept` / `reject` and **diverge only on
ABSTAIN**: when `c = False` (a wrong proposal), `(v == 'accept') == c` counts
**ABSTAIN as "voted correctly"**, potentially earning a `+0.1` reward. The
paper's Algorithm 1 originally had exactly this wrong form. The code, the paper's
Algorithm 1, and the explanation in §4.4 were all corrected, and the entire
reputation table was **re-measured** under the corrected semantics (main text now
says "$1{,}186$ of $1{,}305$", previously $1{,}217$ of $1{,}305$).

> The lesson is the same as §3.6 but sharper: a fidelity audit must compare not
> only the **penalty rules** but also the **vote alphabet and ground-truth
> definition**. An audit covering only two vote values is blind to the question
> "does abstention count as voting correctly".

### 3.7 `verify_mbpp_subboundary.py` — offline reproduction of the out-of-bound wrong commit

The paper reports that in the execution-verification domain (MBPP), the
**out-of-bound configurations** ($n{=}5, f{=}2$) produce $5.6$–$9.6\%$ wrong
commits, while in-bound configurations are uniformly $0.0\%$. These numbers were
once challenged as "mathematically impossible in the code domain" (an execution
verifier should block any wrong code). To turn "possible/impossible" from an
assertion into a reproducible fact, this script **calls no LLM at all** and
rebuilds both paths locally:

- `A2ABFT` (strict semantics): Byzantine validators vote by the code-domain rules;
- `A2ABFSybil` (replicating the Sybil layer of `full_bft_sweep.py`): Byzantine
  validators vote REJECT / ACCEPT with 75% / 25% probability.

Both paths make the "proposal" return the dataset's reference solution with
`P_MODEL = 0.70` and a tampered solution otherwise, measuring:

| Path | n=5, f=2 wrong commits | n=6, f=2 wrong commits |
|------|------------------|------------------|
| A2ABFT (strict) | 0.3% | 0.3% |
| A2ABFSybil (sweep definition) | 3.8% | 0.3% |

(In the same run `A2ABFSybil` gives 0.7% under a `random` attack, i.e. the effect
requires **targeted** Byzantine voting and is not random noise.)

Conclusion: the mechanism is not "code execution being bypassed" but **a few
Byzantine ACCEPT votes under multi-model cross-validation, added to honest
REJECT/abstain votes**, reaching $\phi \geq \theta_{accept}$ once the threshold
collapses to $\theta_{accept} \leq 1$. For the algebra see the paper's Property 4
condition $7f + 3s + 3 \geq 3n$ (soft faults abstaining, i.e. the worst-case
definition of Theorem 5.1; if soft faults vote REJECT together with the honest
ones it degrades to $7f + 2s + 3 \geq 3n$). For $n{=}5$ this is $17 \geq 15$
(out-of-bound possible), for $n{=}6$ it is $17 \geq 18$ (impossible), matching
the table above.

> Round-13 correction: the paper originally gave only $7f + 2s + 3 \geq 3n$
> **without stating the soft faults' voting behaviour**. That form implicitly
> assumes "soft faults REJECT together with the honest ones", which is
> inconsistent with Theorem 5.1's worst-case abstention assumption; for $s>0$ it
> misclassifies 238 out-of-bound configurations as "impossible" (e.g.
> $n{=}5,f{=}1,s{=}2$). The 7 configurations in the paper's experimental grid are
> judged identically under both definitions, so no reported conclusion changes.

---

### 3.8 `audit_revision_layer.py` — revision layer (52 items)

**Why a separate layer**: the 2026-09-17 PAT triage injected 45 new passages and
42 compressions into the paper. That batch of text was born under the pressure of
the 9-page limit and produced by 6 scripts over several rounds; two of its
algebraic conditions (the closed form for soft-fault false positives in
Appendix A.2, and Property 4's out-of-bound condition) are **entirely new
mathematical propositions** — they have no corresponding data file, so L1/L4/L6/L7
are **naturally immune** to them and only L2 can find errors.

The script has three parts:

| Part | Content | Items |
|------|------|--------|
| **A** | L2 algebra: rederive every new formula in exact `Fraction` arithmetic, and exhaustively verify over $n\le30$, $f\le11$, $s\le11$, $p\in\{0,0.05,\dots,1\}$ that "the paper's closed form" and "deciding directly from the $\phi$ definition" are strictly equivalent | 18 |
| **B** | Revised-text self-consistency: multi-replica consistency of the out-of-bound mechanism, the soft-fault definition, the notation $V/\hat V_i/V_i$, stale values, `\label`↔`\ref`, domain mapping, `\small`, hard claims | 22 |
| **C** | Compression regression: parse the 5 compression scripts from the revision period with `ast`, extract the **95** keywords from their "these key numbers must be preserved" assertions, and check that the current `.tex` still contains all of them | 2 |

**Key design of part A**: the early implementation scanned for the "out-of-bound
condition" **inside** the boundary ($3f+s+1 \le n$), whereas the out-of-bound
discussion happens precisely **outside** it — a wrong range means the check never
reaches the real counterexamples. Fixing the range to scan outside exposed 238
configurations the old form had missed.

**Key design of part B**: a **negative lookahead** distinguishes
`n{-}1{-}f{-}s$ honest` (soft faults abstain, correct) from `n{-}1{-}f$ honest`
(soft faults counted as honest, conflicting with the theorem's assumption). Using
`\b` word boundaries for this check also matches the former, producing false
positives.

**Key design of part C**: the keyword assertions in the compression scripts were
verified only once, at run time; this check extracts them and turns them into a
**regression test** — if any later patch loses information that was deliberately
preserved during compression, this raises the alarm.

Companion negative test: `negative_test_revision.py` (8/8).

---

### 3.9 `audit_decision_neutrality.py` — decision neutrality (9 items)

**Why a separate layer**: §6.6 of the paper and Appendix A.7 once claimed that
the reputation tracker's decision neutrality was "verified rather than merely
asserted". But the check it relied on lived in `reputation_ablation.py` and looked
like this:

```python
stats['decisions'].append((key, rec['task_idx'], rec['decision']))   # value == rec['decision']
by_dec  = {(k, t): d for k, t, d in stats['decisions']}
rec_dec = {..., r['decision'] for r in records}                      # value == rec['decision']
consistent = all(by_dec.get(k) == v for k, v in rec_dec.items())
```

**Both sides come from the same source and it is always True** — entirely
independent of `c_source` and `persistence`. That "verification" has zero
resolving power, and the `verified` written on its basis is unsupported. **This is
the third time this project has fallen into the same class of trap: checking 0
items (or checking something always true) while printing "pass".**

The script replaces it with a falsifiable three-tier test (and puts the
always-true check itself on the audit's own chopping block):

| Item | Content | Result |
|----|------|------|
| **D1** | Recompute $\phi = \lvert\text{ACCEPT}\rvert - 0.5\lvert\text{REJECT}\rvert$ from the raw votes and compare it round by round against the recorded $\phi$. If votes had ever been weighed by reputation (e.g. `score += effective_weight * reputation` as in `consensus_unified._compute_vote_score`), the recomputed value would necessarily diverge from the record | 457/457 rounds match |
| **D2a/D2b** | Replay the protocol state machine (confirm / view change / pending) using the recorded $\phi/\theta$ and compare against the online primary advance sequence, final decision, and round count | 120/120 records match |
| **D3** | Mutation test: inject three counterfactual weightings (REJECT weighted 0.5, Byzantine 0.3, soft-fault 0.3) | $\phi$ changes in 421/288/189 rounds, flipping 5/2/2 decisions |
| **D4a–c** | Static reachability: the decision section must not contain reputation/weight identifiers; `_get_reputation_weights` has zero call sites; the reads of `self._reputation` are only logging and dead code | all pass |
| **D5** | Reproduce the old check itself and confirm it still reports "consistent" after the decisions are **entirely** tampered with | confirmed always-true |
| **D6** | Mutation test of D2b itself: tampering with one decision must be reported as a mismatch | passes |

**D3 is the core of this script**: without it, D1/D2 might still merely "happen to
pass"; with it, the claim "**if reputation really did enter vote counting, this
check would fail**" is proven.

#### 3.9.1 A definition that must be kept distinct: 1,305 or 1,459

The paper's `$1{,}186$ of $1{,}305$` is restricted to the **four attacked cells**;
across all six cells the total is `1,316 of 1,459`. Both are true, but mixing them
makes it look like a numeric error:

| Scope | Escalated penalties | Mispenalties | Task level |
|------|-------:|-----:|--------|
| Four attacked cells ($f>0$) | 1,305 | 1,186 | 20/20 each with mispenalties |
| Two non-Byzantine cells ($f=0$) | 154 | 130 | 8/20 and 9/20 mispenalized (10 and 9 triggering tasks) |
| **All six cells** | **1,459** | **1,316** | 97/120 |

The abstract and contributions originally said "its $1{,}305$" without stating
the scope; this was amended to "in the four attacked cells".

---

## 4. Negative tests: proving the audits are not vacuous

> **An audit's credibility comes from its ability to catch injected defects.** An
> "all green" audit that has never caught anything is indistinguishable from no
> audit at all.

### `negative_test_tables.py` — 5/5

| Case | Injected defect |
|------|-----------|
| 1 | Fault-tolerance column off by one: `≤` changed to `<` (equivalent to strengthening the theorem by 1) |
| 2 | Round-count column contradicting the measurement |
| 3 | Δ arithmetic error |
| 4 | BFT value inconsistent with the JSON |
| 5 | A800 wording missing the GPU count |

### `negative_test_figures.py` — 8/8

| Case | Injected defect |
|------|-----------|
| 1 | Figure caption missing the n=90 disclosure |
| 2 | Table range tampered with |
| 3 | Sweep cell missing |
| 4 | Performance table value tampered with |
| 5 | Table caption missing the n=90 disclosure |
| 6 | Schematic PDF missing |
| 7 | Data content changed but the figure not regenerated (must trigger the freshness alarm) |
| 8 (inverse) | Only a comment appended to the generator — must **not** trigger a staleness alarm |

> Case 8 is the inverse control, and it is the failure mode of an mtime-based
> baseline: appending one comment used to produce staleness warnings for three
> figures. It must stay green under all circumstances, otherwise the guard gets
> ignored as noise.

### `negative_test_theory.py` — 3/3

| Case | Injected defect |
|------|-----------|
| 5 | `distributed_worker.py` threshold regressed to a majority rule |
| 6 | `langgraph_integration.py` threshold regressed to a majority rule |
| 7 | Reference implementation re-introduces the f=0 threshold special case |

Case 7 is especially important: it re-injects a defect that really existed
historically, and the probe reports `code=ACCEPT paper-rule=PENDING`, proving that
§7's executable probe **really does compare code against the paper** rather than
merely checking that files exist.

### `negative_test_paths.py` — 8/8

| Case | Injected defect |
|------|-----------|
| 1 | `parse_correctness_log.py` reverted to `HERE/results` (a migration break that really happened) |
| 2 | `run_pairing_mcnemar.py` likewise; this script is the data source for the McNemar paired test |
| 3 | `build_cleanup_list.py` result directory derived from the script's own location → the parent directory does not exist |
| 4 | A `sys.path` insertion target misspelled |
| 5 | Anti-vacuity: on a clean repository every check counter must be > 0 and the problem count 0 |
| 6 | §5 read-type `open()` pointing at a cleaned-up data file |
| 7 | §6 dead documentation command path (`.md` side) — writing the already-fixed old path back |
| 8 | §6 dead documentation command path (`.sh` side) |

> **Case 7 immediately caught another instance of the same defect**:
> `_doc_command_paths()` initially reused `SKIP_DIRS` for directory pruning, and
> that set contains `datasets` — so `experiments/datasets/DATASET_README.md` never
> entered the scan range at all, an injected defect produced no complaint, and
> §6's "0 problems" really meant "0 scanned". This shares a root cause with §5's
> earlier false positives from the same trap (see the comment on
> `_repo_basenames()`), so §6 now prunes only dot-directories and `__pycache__`.

Cases 1/2 also validate L9 §2: after injection the audit reports
`[smoke] …:RESULTS 数据目录挂在脚本自身目录下 …（由脚本自身位置推导（HERE）…）`.

Injection/restoration operates on **bytes** throughout (`shutil.copy2` +
`bytes.replace`). A text-mode round trip would normalize CRLF to LF, leaving the
restored file no longer byte-identical — which in git shows up as a spurious diff.

### `negative_test_revision.py` — 8/8

| Case | Injected defect |
|------|-----------|
| 1 | §6.3 out-of-bound mechanism wording reverted to "colluders push a tampered proposal" |
| 2 | Out-of-bound condition reverted to the old `7f + 2s + 3` |
| 3 | Property 4 counts soft faults as honest again (`n{-}1{-}f$ honest`) |
| 4 | §4.2 restored the over-strong claim "error decays exponentially in $m$" |
| 5 | Decision-function notation reverted to `V_i(\pi)` |
| 6 | Stale value retained (`1{,}186` → `1{,}217`) |
| 7 | Definition 3.1 loses the `s ≤ f` condition |
| 8 | A keyword preserved during compression is lost (`4{,}320` replaced everywhere) |

Negative cases accept a third element specifying the **number of replacements**
(default 1, `0` meaning replace all). Case 8 must use replace-all: `4{,}320`
appears **twice** in the paper, and replacing only one occurrence leaves it
findable in the check set, so the case would falsely pass (this was observed once
as MISSED).

---

## 5. Five hard rules

The audits and negative tests follow the rules below; violating any one of them
makes the conclusions meaningless:

1. **Failure details must differ from success details.** If a check prints
   `'clean'` on success and also `'clean'` on failure, negative tests cannot
   distinguish "caught" from "vacuous".
2. **Every new check must ship with a negative case.** Without a corresponding
   tampering test there is no proof it works.
3. **A check count of 0 must fail.** If a check silently skips because it "found
   no objects", it looks green while having checked nothing. The actual number of
   evaluations must be counted and an error raised when it is 0.
4. **A negative case's replacement must make the target string disappear
   entirely.** If the target string occurs several times in the paper, replacing
   only the first occurrence leaves it findable by the check and the case falsely
   passes — the replacement count is part of the negative case.
5. **Same-source comparison is forbidden.** If both sides of a check come from the
   same field (e.g. comparing `rec['decision']` against itself), it is always true,
   has no resolving power, and **looks green forever**. A check must recompute
   independently and must be proven by a mutation test to "fail once a defect is
   injected". See §3.9 for an instance.

> Rule 3 came from a real incident: a location-independence check used an AST that
> walked only module-level statements, while `sys.path.insert` sat inside a `for`
> loop, so it **checked 0 paths and printed "pass"**. After the fix, the check
> first counts the paths it actually evaluated.
>
> The same rule paid off again at L9: L9's first version executed all top-level
> statements of every file and thereby ran `mbpp_debate_fix.py`'s experiment body
> (real API requests). Evidently **audit scripts are code too**, and their side
> effects and blind spots must be reviewed just like the objects they test.

---

## 6. Running the audit

**One command (recommended)**:

```bash
./reproduce.sh verify     # = the 13 commands below, executed serially with an overall verdict
```

`./reproduce.sh` is the single entry point (`Makefile` is a thin wrapper); full
usage is in `README.md` §3.0. It prints
`REPRODUCE_OK` / `REPRODUCE_OK_PARTIAL` / `REPRODUCE_FAILED` with exit codes
0 / 0 / 1; "not verified" is not "passed".

**One by one**:

```bash
python experiments/verification/audit_table_numbers.py
python experiments/verification/audit_figures.py
python experiments/verification/audit_theory_numerics.py
python experiments/verification/audit_prose_ranges.py
python experiments/verification/audit_paths.py            # L9
python experiments/verification/audit_revision_layer.py   # round 13: revision layer
python experiments/verification/audit_decision_neutrality.py  # decision neutrality (zero LLM)
python experiments/verification/audit_reputation_fidelity.py  # reputation fidelity

python experiments/verification/negative_test_tables.py
python experiments/verification/negative_test_figures.py
python experiments/verification/negative_test_theory.py
python experiments/verification/negative_test_paths.py    # L9
python experiments/verification/negative_test_revision.py # round 13
```

> ⚠️ **These must run serially.** The negative tests temporarily rewrite
> `papers/iclr2027_main.tex` and restore it byte-for-byte; running them in
> parallel with the audits makes the audits read the injected state and raise
> false alarms (observed: `audit_table_numbers` reporting
> `[tab:a2a_sim] 99.9±5.8 vs data 56.7±5.8`), and two negative scripts
> backing up/restoring at once overwrite each other, leaving a half-injected paper
> file. `reproduce.sh` guards against this with a lock file + strict
> serialization + an end-of-run hash comparison.
>
> `audit_figures.py` and `negative_test_figures.py` need `matplotlib` (the former
> loads `papers/generate_figures.py` at import time); the remaining scripts depend
> only on the standard library. When the dependency is missing these two are
> judged **failed**, not skipped — "not verified" is not "passed".
>
> `audit_revision_layer.py` **parses** (does not execute) the 5 compression
> scripts under `docs/revisions/2026-09-17/` to extract their keyword assertions.
> Those scripts depend on the line numbers of their time;
> **they have already been applied — do not rerun them.**

Every script locates the project root by searching upward for
`.a2a_project_root`, **independent of its own directory**, and can be invoked from
any working directory at any depth (verified by copying the project to a
5-level-deep directory).

---

## 7. Historical audit reports

Round-by-round audit reports are kept in `docs/reviews/` (moved out of `papers/`
during the round-19 reorganization, since the submission directory keeps only
submission-relevant files), and `docs/audit/` holds the data-source ledgers:

| Report | Topic |
|------|------|
| `REVIEW_2026-09-15_round5_numeric_audit.md` | Numeric audit |
| `REVIEW_2026-09-15_round6_theory_spec_audit.md` | Theory specification |
| `REVIEW_2026-09-15_round7_reference_contribution_audit.md` | Related work and contributions |
| `REVIEW_2026-09-15_round8_scale_stats_audit.md` | Scale and statistics |
| `REVIEW_2026-09-15_round10_figure_layer_audit.md` | Figure layer (L7) |
| `REVIEW_2026-09-15_round11_algorithm_layer_audit.md` | Algorithm layer (pseudocode vs. implementation) |
| `REVIEW_2026-09-15_round12_theory_code_layer_audit.md` | Theorem provability (L5b) + delivered code (L8) |
| `REVIEW_2026-09-17_round13_revision_layer_audit.md` | **Revision layer (L2 algebra + new-text consistency)** |
| `PAT_TRIAGE_2026-09-17.md` | Item-by-item triage of ICLR PAT feedback (26 items: 22 upheld / 4 false alarms) |
| `DATA_SOURCE_AUDIT.md` | Round-by-round data-source ledger |

> The `REVIEW_*` reports are internal drafting records and are **not part of this
> anonymous release**; `docs/audit/` ships the data-source ledgers.
