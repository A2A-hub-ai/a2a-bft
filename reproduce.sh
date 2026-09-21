#!/usr/bin/env bash
# ============================================================================
# A2A-BFT one-command reproduction entry point
#
# Design goal: collapse "read the docs -> pick scripts one by one -> diff outputs by hand"
#
#   ./reproduce.sh            # default = verify (no GPU needed)
#   ./reproduce.sh verify     # 6 data-only audits + 2 negative-test groups (artifact mode,
#                             #   no paper source); +4 paper cross-check audits and +3
#                             #   paper-injection negative tests when papers/ is present
#   ./reproduce.sh doctor     # environment check: how far you can get, and what is missing
#   ./reproduce.sh figures    # regenerate figures from results/ and recheck consistency
#   ./reproduce.sh datasets   # download GSM8K / MBPP / MMLU and verify record counts
#   ./reproduce.sh install    # pip install -r requirements.txt
#   ./reproduce.sh all        # doctor + datasets + figures + verify
#   ./reproduce.sh full        # all experiments (needs 2x80GB GPU + 78GB weights + API key)
#   ./reproduce.sh help
#
# Portability: the script self-locates via .a2a_project_root and ignores the caller's cwd;
#           runs on Linux and Windows (Git Bash); override the interpreter with A2A_PY.
#
# ⚠️ DO NOT RUN IN PARALLEL (measured lesson, 2026-09-17)
#    The verify-stage negative tests TEMPORARILY REWRITE papers/iclr2027_main.tex and then
#    restore it (they inject known defects to prove the audits really catch them, rather than
#    merely existing). Audits and negative tests MUST therefore be serial - never `&` or
#    `xargs -P`: concurrently, audit_table_numbers reads the injected state and raises the
#    false alarm "[tab:a2a_sim] GSM8K baseline 99.9±5.8 vs data 56.7±5.8", and two negative
#    scripts backing up/restoring at once overwrite each other, leaving a half-injected paper.
#    This script guards against that with a lock file + strict serialization + an end-of-run hash check.
# ============================================================================
set -uo pipefail

# ---------------------------------------------------------------------------
# 0. Self-location: the project root is derived from this script's location and verified upward
# ---------------------------------------------------------------------------
A2A_ROOT="${A2A_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ ! -f "$A2A_ROOT/.a2a_project_root" ]; then
  echo "[reproduce] project-root marker .a2a_project_root not found (current: $A2A_ROOT)" >&2
  echo "[reproduce] run it from the repository root, or set A2A_ROOT=/path/to/repo explicitly" >&2
  exit 2
fi

# Paths handed to the Python interpreter are ALWAYS project-root-relative:
#   under Git Bash/MSYS, A2A_ROOT has the form /d/..., and if the interpreter is a native
#   Windows python.exe, MSYS argument-path conversion mangles it into D:\d\... (observed as
#   "can't open file 'D:\d\<repo>\experiments\verification\audit_paths.py'").
#   Relative paths carry no such ambiguity; run_step cds to the project root first, so they always resolve.
REL_VERIFICATION="experiments/verification"
REL_REPRODUCE="experiments/reproduce"
REL_ENVDIR="experiments/env"
REL_PAPERS="papers"

VERIFICATION="$A2A_ROOT/$REL_VERIFICATION"
REPRODUCE="$A2A_ROOT/$REL_REPRODUCE"
ENVDIR="$A2A_ROOT/$REL_ENVDIR"
PAPERS="$A2A_ROOT/$REL_PAPERS"
TEX="$PAPERS/iclr2027_main.tex"
LOCK="$A2A_ROOT/.a2a_repro.lock"

# ---------------------------------------------------------------------------
# 1. Interpreter detection (A2A_PY first; otherwise python3 / python)
# ---------------------------------------------------------------------------
PY="${A2A_PY:-}"
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  PY=""
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "[reproduce] no Python interpreter found; set A2A_PY=/path/to/python" >&2
  exit 2
fi

# Windows/Git Bash: normalize the MSYS form (/c/...) into the C:/... form.
# Why: A2A_PY is exported to the Python scripts, and the negative tests spawn further
# subprocesses - subprocess goes through Windows CreateProcess, which does not recognise
# MSYS paths like /c/... and raises FileNotFoundError(WinError 2). The C:/... form works on both.
# (Measured 2026-09-17: 4 of the 5 negative tests failed for this reason; only the one using
if command -v cygpath >/dev/null 2>&1; then
  _pynorm="$(cygpath -m "$PY" 2>/dev/null || true)"
  [ -n "$_pynorm" ] && PY="$_pynorm"
fi
export A2A_PY="$PY"

# ---------------------------------------------------------------------------
# 2. Small helpers
# ---------------------------------------------------------------------------
C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_WARN=$'\033[33m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
if [ ! -t 1 ]; then C_OK=""; C_BAD=""; C_WARN=""; C_DIM=""; C_OFF=""; fi

PASS_N=0; FAIL_N=0; SKIP_N=0
FAILED_ITEMS=(); SKIPPED_ITEMS=()

hr() { printf '%s\n' "------------------------------------------------------------------------"; }

# Byte-exact hashing (done in Python to avoid md5sum/sha1sum differences under Git Bash)
#
# ⚠️ The path MUST be passed to Python as an ARGUMENT in project-root-relative form:
#    MSYS mangles /d/... style arguments into D:\d\..., so open() fails outright.
#    An earlier version therefore always returned "MISSING" - and MISSING == MISSING,
#    which silently turned "the negative tests restored the file byte-for-byte" into a FALSE PASS.
#    Failures are now written explicitly as ERROR:... so "unreadable" can never pass as "identical".
file_hash() {
  (
    cd "$A2A_ROOT" || exit 1
    "$PY" - "${1#"$A2A_ROOT"/}" <<'PYEOF'
import hashlib, sys
try:
    data = open(sys.argv[1], 'rb').read()
except OSError as e:
    print("ERROR:%s" % e)
else:
    print(hashlib.md5(data).hexdigest())
PYEOF
  )
}

# 32 hex digits = valid digest; anything else (MISSING / ERROR:... / empty) means "cannot verify"
is_hash() { printf '%s' "$1" | grep -Eq '^[0-9a-f]{32}$'; }

# Run one script and record the result. Usage: run_step "label" "workdir" command...
# Extract "how many items were checked/passed" from the script output. Formats differ between
# scripts, so several patterns are tried in priority order; if none match, return empty (better to
extract_count() {
  local out="$1" p
  # The five negative scripts close with different wordings ("items passed" / "items caught" /
  # "items as expected" / "caught"), but all print "负向测试: N/M ...", so key on that prefix only.
  p="$(printf '%s' "$out" | grep -oE '负向测试: *[0-9]+/[0-9]+' | tail -1 | grep -oE '[0-9]+/[0-9]+' || true)"
  if [ -n "$p" ]; then printf '%s' "$p"; return; fi
  p="$(printf '%s' "$out" | grep -oE '已核对(数值|项数): *[0-9]+' | tail -1 | grep -oE '[0-9]+$' || true)"
  if [ -n "$p" ]; then printf '%s items' "$p"; return; fi
  p="$(printf '%s' "$out" | grep -oE '[0-9]+ 项核对' | tail -1 | grep -oE '^[0-9]+' || true)"
  if [ -n "$p" ]; then printf '%s items' "$p"; return; fi
  printf ''
}

run_step() {
  local label="$1"; shift
  local cwd="$1"; shift
  printf '  %-42s' "$label"
  local out rc
  out="$(cd "$cwd" && "$@" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    PASS_N=$((PASS_N + 1))
    local cnt; cnt="$(extract_count "$out")"
    if [ -n "$cnt" ]; then
      printf '%sPASS%s  %s\n' "$C_OK" "$C_OFF" "$cnt"
    else
      printf '%sPASS%s\n' "$C_OK" "$C_OFF"
    fi
  else
    FAIL_N=$((FAIL_N + 1)); FAILED_ITEMS+=("$label (rc=$rc)")
    printf '%sFAIL%s\n' "$C_BAD" "$C_OFF"
    printf '%s' "$out" | tail -12 | sed 's/^/      | /'
    printf '\n'
  fi
}

# Last summary line of the block above (used to surface the key numbers)
tail_summary() {
  printf '%s' "$1" | grep -E "问题数|负向测试|项|OK|PASS" | tail -1
}

require_py_module() { "$PY" -c "import $1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 3. Lock: only one reproduction run at a time (the negative tests rewrite repository files)
# ---------------------------------------------------------------------------
acquire_lock() {
  if [ -e "$LOCK" ]; then
    echo "${C_BAD}[reproduce] another reproduction run is already active ($LOCK)${C_OFF}" >&2
    echo "[reproduce] the negative tests temporarily rewrite the paper source; concurrent runs corrupt each other." >&2
    echo "[reproduce] if you are sure nothing is running, delete the lock file and retry." >&2
    exit 3
  fi
  mkdir -p "$LOCK"
  trap 'rm -rf "$LOCK"' EXIT INT TERM
}

# ===========================================================================
# Stage 1: doctor - environment check
# ===========================================================================
stage_doctor() {
  hr; echo "Environment check (doctor)"; hr
  echo "  project root  : $A2A_ROOT"
  echo "  interpreter   : $PY"
  "$PY" -c 'import sys; print("  Python version:", sys.version.split()[0])'

  local pyok
  pyok="$("$PY" -c 'import sys; print(1 if sys.version_info>=(3,10) else 0)')"
  if [ "$pyok" = "1" ]; then
    printf '  %-42s%sOK%s\n' "Python >= 3.10" "$C_OK" "$C_OFF"
  else
    printf '  %-42s%sneeds >= 3.10%s\n' "Python >= 3.10" "$C_BAD" "$C_OFF"
  fi

  echo
  echo "  dependencies (core protocol library needs stdlib only; the rest affect inference/plotting):"
  local m
  for m in numpy scipy matplotlib datasets openai torch vllm transformers; do
    printf '    %-14s' "$m"
    if require_py_module "$m"; then printf '%sinstalled%s\n' "$C_OK" "$C_OFF"
    else printf '%smissing%s\n' "$C_DIM" "$C_OFF"; fi
  done

  echo
  echo "  data and results:"
  local d
  for d in "experiments/datasets:datasets" "experiments/results:results" \
           "experiments/src:core library"; do
    local p="${d%%:*}"; local n="${d##*:}"
    local cnt
    cnt="$(find "$A2A_ROOT/$p" -type f ! -name "*.pyc" 2>/dev/null | grep -vc "__pycache__" || echo 0)"
    printf '    %-24s %s files\n' "$n" "$cnt"
  done

  echo
  echo "  hardware (needed only by the full stage):"
  if command -v nvidia-smi >/dev/null 2>&1; then
    local ngpu
    ngpu="$(nvidia-smi -L 2>/dev/null | grep -c '^GPU')"
    printf '    GPU count     : %s' "$ngpu"
    if [ "$ngpu" -ge 2 ]; then printf '  %s(meets the 2-GPU requirement)%s\n' "$C_OK" "$C_OFF"
    else printf '  %s(full stage needs 2x 80GB GPUs)%s\n' "$C_WARN" "$C_OFF"; fi
    nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/      /'
  else
    printf '    GPU           : %sno nvidia-smi detected (does not affect verify)%s\n' "$C_DIM" "$C_OFF"
  fi

  echo
  hr
  echo "Verdict: verify / figures / datasets can run on this machine; full needs 2x80GB GPUs."
  hr
}

# ===========================================================================
# Stage 2: verify - audits + negative-test groups (strictly serial; paper cross-check
#             layers auto-SKIP when papers/ is absent, e.g. in the public artifact)
# ===========================================================================
# Labels carry descriptions only, never counts: extract_count() reads counts from each script's
# ACTUAL output. Earlier labels hard-coded "(349 items)" / "6 injected path defects"; whenever
# cases were added or removed the label went stale, and because pass/fail is decided solely by
# exit codes a stale label stayed unnoticed for a long time (the negative path cases grew from 6 to 8
AUDITS=(
  "audit_table_numbers.py|table numbers|P"
  "audit_figures.py|figure-table consistency + fingerprints|P"
  "audit_prose_ranges.py|prose ranges vs. tables|P"
  "audit_theory_numerics.py|theory formulas instantiated numerically|"
  "audit_revision_layer.py|revision-layer algebra + text consistency|P"
  "audit_decision_neutrality.py|decision neutrality|"
  "audit_reputation_fidelity.py|reputation fidelity|"
  "audit_judge_calibration.py|judge-calibration numbers vs. released records|"
  "calibrate_judge_from_streams.py|judge FPR/FNR recomputed from vote streams|"
  "audit_paths.py|path resolution layer|"
)
NEGATIVES=(
  "negative_test_tables.py|inject table defect|P"
  "negative_test_figures.py|inject figure defect|P"
  "negative_test_theory.py|inject theory defect|"
  "negative_test_paths.py|inject path defect|"
  "negative_test_revision.py|inject revision-layer defect|P"
)

stage_verify() {
  acquire_lock
  hr; echo "Audits + negative tests (verify) - CPU only, no GPU required"; hr

  local PAPER_MISSING=0
  if [ -f "$TEX" ]; then
    local h0; h0="$(file_hash "$TEX")"
    echo "paper source fingerprint (before): $h0"
  else
    PAPER_MISSING=1
    echo "${C_WARN}paper source (papers/iclr2027_main.tex) not present in this artifact.${C_OFF}"
    echo "${C_DIM}  the paper-vs-data cross-check layers below will be SKIPped;${C_OFF}"
    echo "${C_DIM}  all data-only layers still run in full.${C_OFF}"
  fi
  echo

  echo "[1/2] audit scripts (run serially, ${#AUDITS[@]} total)"
  local item script label needs_paper
  for item in "${AUDITS[@]}"; do
    script="$(echo "$item" | cut -d'|' -f1)"; label="$(echo "$item" | cut -d'|' -f2)"
    needs_paper="$(echo "$item" | cut -d'|' -f3)"
    if [ "$needs_paper" = "P" ] && [ "$PAPER_MISSING" = "1" ]; then
      printf '  %-42s%sSKIP%s (paper source not included in this artifact)\n' "$label" "$C_WARN" "$C_OFF"
      SKIP_N=$((SKIP_N + 1)); SKIPPED_ITEMS+=("$label -- paper cross-check layer NOT verified (no paper source)")
      continue
    fi
    if [ ! -f "$VERIFICATION/$script" ]; then
      printf '  %-42s%sMISSING%s\n' "$script" "$C_BAD" "$C_OFF"
      FAIL_N=$((FAIL_N + 1)); FAILED_ITEMS+=("$script not found")
      continue
    fi
    # audit_figures.py loads papers/generate_figures.py at import time (needs matplotlib).
    # With the dependency missing this is not a "pass" but "this layer was never verified" -
    # the two must stay distinct, so the default verdict is FAILURE; only an explicit
    # A2A_ALLOW_SKIP_FIGURES=1 downgrades it to SKIP, which never counts as PASS and is recorded in the verdict.
    if [ "$script" = "audit_figures.py" ] && ! require_py_module matplotlib; then
      if [ "${A2A_ALLOW_SKIP_FIGURES:-0}" = "1" ]; then
        printf '  %-42s%sSKIP%s (matplotlib missing)\n' "$label" "$C_WARN" "$C_OFF"
        SKIP_N=$((SKIP_N + 1)); SKIPPED_ITEMS+=("$label -- figure layer NOT verified")
        continue
      fi
      printf '  %-42s%sFAIL%s\n' "$label" "$C_BAD" "$C_OFF"
      printf '      | matplotlib missing; the figure layer cannot be verified (this is NOT a pass).\n'
      printf '      | fix:   %s -m pip install "matplotlib>=3.7.0"   or   ./reproduce.sh install\n' "$PY"
      printf '      | give up on that layer explicitly: A2A_ALLOW_SKIP_FIGURES=1 ./reproduce.sh verify\n'
      FAIL_N=$((FAIL_N + 1)); FAILED_ITEMS+=("$label missing matplotlib")
      continue
    fi
    run_step "$label" "$A2A_ROOT" "$PY" "$REL_VERIFICATION/$script"
  done

  echo
  echo "[2/2] negative tests (run serially, ${#NEGATIVES[@]} total)"
  if [ "$PAPER_MISSING" = "1" ]; then
    echo "${C_DIM}  note: paper-injection cases are SKIPped in this artifact (no paper source); the remaining cases run serially.${C_OFF}"
  else
    echo "${C_DIM}  note: these cases temporarily rewrite papers/iclr2027_main.tex and restore it, so they cannot run in parallel.${C_OFF}"
  fi
  for item in "${NEGATIVES[@]}"; do
    script="$(echo "$item" | cut -d'|' -f1)"; label="$(echo "$item" | cut -d'|' -f2)"
    needs_paper="$(echo "$item" | cut -d'|' -f3)"
    if [ "$needs_paper" = "P" ] && [ "$PAPER_MISSING" = "1" ]; then
      printf '  %-42s%sSKIP%s (paper source not included in this artifact)\n' "$label" "$C_WARN" "$C_OFF"
      SKIP_N=$((SKIP_N + 1)); SKIPPED_ITEMS+=("$label -- paper-injection layer NOT verified (no paper source)")
      continue
    fi
    if [ ! -f "$VERIFICATION/$script" ]; then
      printf '  %-42s%sMISSING%s\n' "$script" "$C_BAD" "$C_OFF"
      FAIL_N=$((FAIL_N + 1)); FAILED_ITEMS+=("$script not found")
      continue
    fi
    run_step "$label" "$A2A_ROOT" "$PY" "$REL_VERIFICATION/$script"
  done

  # ---- end-of-run postcondition: the negative tests must restore the paper source byte-for-byte ----
  echo
  if [ "$PAPER_MISSING" = "1" ]; then
    printf '%snot applicable%s: no paper source in this artifact, no restore postcondition to check.\n' "$C_DIM" "$C_OFF"
  elif [ -f "$TEX" ]; then
    local h0v="${h0:-}" h1
    h1="$(file_hash "$TEX")"
    printf 'paper source fingerprint (after):  %s  ' "$h1"
    if ! is_hash "$h0v" || ! is_hash "$h1"; then
      # An invalid digest (unreadable / mangled) = the constraint was never verified, so it must never count as a pass
      printf '%sCANNOT VERIFY ❌%s\n' "$C_BAD" "$C_OFF"
      echo "  before: ${h0v:-<empty>}"
      echo "  after:  $h1"
      echo "  note:   no valid digest was obtained, so it cannot be proven that the negative tests restored it."
      FAIL_N=$((FAIL_N + 1))
      FAILED_ITEMS+=("cannot verify whether papers/iclr2027_main.tex was restored")
    elif [ "$h1" = "$h0v" ]; then
      printf '%srestored OK%s\n' "$C_OK" "$C_OFF"
    else
      printf '%sNOT RESTORED ❌%s\n' "$C_BAD" "$C_OFF"
      echo "  before $h0v"
      echo "  after  $h1"
      FAIL_N=$((FAIL_N + 1))
      FAILED_ITEMS+=("the negative tests did not restore papers/iclr2027_main.tex")
    fi
  else
    printf '%smissing %s; the restore postcondition cannot be established ❌%s\n' "$C_BAD" "$TEX" "$C_OFF"
    FAIL_N=$((FAIL_N + 1))
    FAILED_ITEMS+=("paper source missing; the restore postcondition cannot be established")
  fi

  echo; hr
  printf 'audits+negative: %s%d passed%s / %s%d failed%s' \
    "$C_OK" "$PASS_N" "$C_OFF" "$C_BAD" "$FAIL_N" "$C_OFF"
  if [ "$SKIP_N" -gt 0 ]; then
    printf ' / %s%d skipped%s' "$C_WARN" "$SKIP_N" "$C_OFF"
  fi
  printf '\n'
  if [ "$FAIL_N" -gt 0 ]; then
    echo "failed items:"
    local f; for f in "${FAILED_ITEMS[@]}"; do echo "  - $f"; done
    echo "REPRODUCE_FAILED"
    hr
    return 1
  fi
  if [ "$SKIP_N" -gt 0 ]; then
    echo "${C_WARN}warning: the following check layers [were NOT verified]; the verdict is not all-green:${C_OFF}"
    local s; for s in "${SKIPPED_ITEMS[@]}"; do echo "  ! $s"; done
    echo "REPRODUCE_OK_PARTIAL"
    hr
    return 0
  fi
  echo "All passed: every number in the released records is independently recomputable, and the audits are proven effective."
  if [ "$PAPER_MISSING" = "1" ]; then
    echo "${C_DIM}note: paper-vs-data cross-check layers were skipped (paper source ships separately with the manuscript).${C_OFF}"
  fi
  echo "REPRODUCE_OK"
  hr
  return 0
}

# ===========================================================================
# Stage 3: figures - regenerate and recheck
# ===========================================================================
stage_figures() {
  acquire_lock
  hr; echo "Regenerate paper figures (figures)"; hr
  if [ ! -f "$PAPERS/generate_figures.py" ]; then
    echo "${C_WARN}papers/generate_figures.py not present in this artifact; the figures stage needs the paper source.${C_OFF}"
    echo "${C_DIM}figure regeneration runs in the full project; the released figure PDFs ship with the manuscript.${C_OFF}"
    return 0
  fi
  if ! require_py_module matplotlib; then
    echo "${C_BAD}matplotlib missing; cannot generate figures.${C_OFF}"
    echo "run this first: $PY -m pip install 'matplotlib>=3.7.0'   (or ./reproduce.sh install)"
    return 1
  fi
  run_step "regenerate the 5 figures" "$A2A_ROOT" "$PY" "$REL_PAPERS/generate_figures.py"
  run_step "figure-table consistency recheck" "$A2A_ROOT" "$PY" "$REL_VERIFICATION/audit_figures.py"
  echo
  if [ "$FAIL_N" -gt 0 ]; then echo "REPRODUCE_FAILED"; return 1; fi
  echo "Figures were regenerated from experiments/results/ and passed the consistency recheck."
  echo "REPRODUCE_OK"
}

# ===========================================================================
# Stage 4: datasets
# ===========================================================================
stage_datasets() {
  hr; echo "Download datasets (datasets)"; hr
  run_step "GSM8K / MBPP / MMLU" "$A2A_ROOT" "$PY" "$REL_ENVDIR/download_datasets.py"
  echo
  if [ "$FAIL_N" -gt 0 ]; then echo "REPRODUCE_FAILED"; return 1; fi
  echo "REPRODUCE_OK"
}

# ===========================================================================
# Stage 5: install
# ===========================================================================
stage_install() {
  hr; echo "Install dependencies (install)"; hr
  echo "interpreter: $PY"
  "$PY" -m pip install -r "$A2A_ROOT/requirements.txt"
  local rc=$?
  echo
  [ $rc -eq 0 ] && echo "REPRODUCE_OK" || echo "REPRODUCE_FAILED"
  return $rc
}

# ===========================================================================
# Stage 6: full - all experiments (needs GPU; never triggered implicitly)
# ===========================================================================
stage_full() {
  hr; echo "All experiments (full) - prerequisite check"; hr
  local ok=1

  local ngpu=0
  if command -v nvidia-smi >/dev/null 2>&1; then
    ngpu="$(nvidia-smi -L 2>/dev/null | grep -c '^GPU')"
  fi
  printf '  %-40s' "GPU count >= 2"
  if [ "$ngpu" -ge 2 ]; then printf '%sOK (%s)%s\n' "$C_OK" "$ngpu" "$C_OFF"
  else printf '%sNOT met (%s)%s\n' "$C_BAD" "$ngpu" "$C_OFF"; ok=0; fi

  printf '  %-40s' "model weight dir A2A_MODEL_DIR"
  if [ -n "${A2A_MODEL_DIR:-}" ] && [ -d "${A2A_MODEL_DIR:-/nonexistent}" ]; then
    printf '%sOK%s\n' "$C_OK" "$C_OFF"
  else
    printf '%snot set or does not exist: %s%s\n' "$C_BAD" "${A2A_MODEL_DIR:-<empty>}" "$C_OFF"; ok=0
  fi

  printf '  %-40s' "DEEPSEEK_API_KEY（Pipeline C）"
  if [ -n "${DEEPSEEK_API_KEY:-}" ]; then printf '%sset%s\n' "$C_OK" "$C_OFF"
  else printf '%snot set%s\n' "$C_WARN" "$C_OFF"; fi

  printf '  %-40s' "dependencies numpy / scipy / matplotlib"
  if require_py_module numpy && require_py_module scipy && require_py_module matplotlib; then
    printf '%sOK%s\n' "$C_OK" "$C_OFF"
  else printf '%smissing%s\n' "$C_BAD" "$C_OFF"; ok=0; fi

  echo
  if [ "$ok" -ne 1 ]; then
    echo "${C_BAD}prerequisites unmet; aborted (no experiment was executed).${C_OFF}"
    echo "REPRODUCE_FAILED"
    return 1
  fi

  hr; echo "Start the 4 heterogeneous vLLM instances (2x80GB, one by one + health checks)"; hr
  bash "$ENVDIR/start_vllm_seq.sh" || { echo "vLLM failed to start"; echo "REPRODUCE_FAILED"; return 1; }
  run_step "connectivity probe" "$A2A_ROOT" "$PY" "$REL_ENVDIR/probe.py" || true

  hr; echo "Pipeline A: fault-tolerance sweep (main experiment)"; hr
  local n
  for n in gsm8k mbpp mmlu; do
    run_step "full_bft_sweep.py $n" "$A2A_ROOT" "$PY" "$REL_REPRODUCE/full_bft_sweep.py" "$n"
  done
  run_step "aggregate_full_sweep.py" "$A2A_ROOT" "$PY" "$REL_REPRODUCE/aggregate_full_sweep.py"

  hr; echo "Pipeline B: ablations + baseline comparison"; hr
  echo "${C_DIM}  full commands for this pipeline: docs/REPRODUCTION.md section 3 (multi-method / multi-seed combos).${C_OFF}"

  hr; echo "Pipeline C: real-API multi-domain validation (needs DEEPSEEK_API_KEY)"; hr
  echo "${C_DIM}  full commands for this pipeline: docs/REPRODUCTION.md section 4 (cost and rate-limit notes).${C_OFF}"

  hr; echo "Regenerate figures and recheck"; hr
  run_step "generate_figures.py" "$A2A_ROOT" "$PY" "$REL_PAPERS/generate_figures.py"
  run_step "audit_figures.py" "$A2A_ROOT" "$PY" "$REL_VERIFICATION/audit_figures.py"

  echo; hr
  if [ "$FAIL_N" -gt 0 ]; then
    printf '%s%d items failed%s\n' "$C_BAD" "$FAIL_N" "$C_OFF"
    echo "REPRODUCE_FAILED"; return 1
  fi
  echo "Experiments finished. Run ./reproduce.sh verify afterwards for a full numeric recheck."
  echo "REPRODUCE_OK"
}

# ===========================================================================
# Stage 7: all
# ===========================================================================
stage_all() {
  stage_doctor || return 1
  echo
  if [ ! -f "$A2A_ROOT/experiments/datasets/gsm8k_test.json" ]; then
    stage_datasets || return 1
    echo
  fi
  stage_figures || return 1
  echo
  stage_verify || return 1
}

usage() {
  # Print the header comment block (from line 2 up to the first non-comment line),
  # so the help text and the header usage notes exist in exactly one place and cannot drift apart.
  awk 'NR>1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print } else exit }' "${BASH_SOURCE[0]}"
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
case "${1:-verify}" in
  verify)   stage_verify ;;
  doctor)   stage_doctor ;;
  figures)  stage_figures ;;
  datasets) stage_datasets ;;
  install)  stage_install ;;
  full)     stage_full ;;
  all)      stage_all ;;
  help|-h|--help) usage ;;
  *)
    echo "unknown stage: $1" >&2
    echo "available: verify | doctor | figures | datasets | install | full | all | help" >&2
    exit 2
    ;;
esac
