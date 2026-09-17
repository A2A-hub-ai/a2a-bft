#!/usr/bin/env bash
# ============================================================================
# A2A-BFT 一键复现入口（Single Entry Point）
#
# 设计目标：把「读文档 → 逐个脚本挑命令 → 手工比对输出」压缩成一条命令。
#
#   ./reproduce.sh            # 默认 = verify（无需 GPU，一键可跑）
#   ./reproduce.sh verify     # 8 审计 + 5 负向测试（纯 CPU）
#   ./reproduce.sh doctor     # 环境体检：明确告诉你能跑到哪一步、缺什么
#   ./reproduce.sh figures    # 从 results/ 重新出图并复查图-表一致性
#   ./reproduce.sh datasets   # 下载 GSM8K / MBPP / MMLU 并校验条数
#   ./reproduce.sh install    # pip install -r requirements.txt
#   ./reproduce.sh all        # doctor + datasets + figures + verify
#   ./reproduce.sh full        # 全部实验（需 2×80GB GPU + 78GB 权重 + API key）
#   ./reproduce.sh help
#
# 可移植性：脚本自定位（靠 .a2a_project_root），不依赖调用时所在目录；
#           Linux 与 Windows(Git Bash) 均可运行，解释器可用 A2A_PY 覆盖。
#
# ⚠️ 并发禁令（2026-09-17 实测教训）
#    verify 阶段的负向测试会**临时改写** papers/iclr2027_main.tex 再还原
#    （通过注入已知缺陷来证明审计真的能捕获，而非形同虚设）。因此审计与负向
#    测试**必须串行**，绝不能 `&` 或 `xargs -P` 并行：
#      · 并行时 audit_table_numbers 读到注入态，报出假告警
#        "[tab:a2a_sim] GSM8K 基线 99.9±5.8 vs 数据 56.7±5.8"；
#      · 两个负向脚本同时备份/还原还会互相覆盖，留下"半注入"的论文文件。
#    本脚本用「锁文件 + 严格串行 + 收尾哈希比对」三重防护。
# ============================================================================
set -uo pipefail

# ---------------------------------------------------------------------------
# 0. 自定位：项目根由本脚本位置确定，并向上校验根标记文件
# ---------------------------------------------------------------------------
A2A_ROOT="${A2A_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
if [ ! -f "$A2A_ROOT/.a2a_project_root" ]; then
  echo "[reproduce] 未找到项目根标记 .a2a_project_root（当前: $A2A_ROOT）" >&2
  echo "[reproduce] 请从仓库根目录运行，或显式设置 A2A_ROOT=/path/to/repo" >&2
  exit 2
fi

# 传给 Python 解释器的路径一律用「相对项目根」的形式：
#   Git Bash/MSYS 下 A2A_ROOT 是 /d/... 形态，而解释器若是原生 Windows
#   python.exe，MSYS 的参数路径转换会把它错拼成 D:\d\...（实测报错形如
#   "can't open file 'D:\d\<仓库名>\experiments\verification\audit_paths.py'"）。
#   相对路径没有这个歧义；run_step 已先 cd 到项目根，因此相对路径总是对的。
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
# 1. 解释器探测（A2A_PY 优先；否则 python3 / python）
# ---------------------------------------------------------------------------
PY="${A2A_PY:-}"
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  PY=""
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "[reproduce] 找不到 Python 解释器；请设置 A2A_PY=/path/to/python" >&2
  exit 2
fi

# Windows/Git Bash：把 MSYS 形态（/c/...）规范成 C:/... 形态。
# 原因：A2A_PY 会被导出给 Python 脚本，而负向测试内部要用 subprocess 再拉起
# 子进程 —— subprocess 走的是 Windows CreateProcess，认不出 /c/... 这类 MSYS
# 路径，直接 FileNotFoundError(WinError 2)。C:/... 形态对 bash 与 Windows 两侧都有效。
# （2026-09-17 实测：5 个负向测试中 4 个因此失败，只有用 sys.executable 的那个正常。）
if command -v cygpath >/dev/null 2>&1; then
  _pynorm="$(cygpath -m "$PY" 2>/dev/null || true)"
  [ -n "$_pynorm" ] && PY="$_pynorm"
fi
export A2A_PY="$PY"

# ---------------------------------------------------------------------------
# 2. 小工具
# ---------------------------------------------------------------------------
C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_WARN=$'\033[33m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
if [ ! -t 1 ]; then C_OK=""; C_BAD=""; C_WARN=""; C_DIM=""; C_OFF=""; fi

PASS_N=0; FAIL_N=0; SKIP_N=0
FAILED_ITEMS=(); SKIPPED_ITEMS=()

hr() { printf '%s\n' "------------------------------------------------------------------------"; }

# 逐字节哈希（用 Python 实现，避免依赖 md5sum/sha1sum 在 Git Bash 上的差异）
#
# ⚠️ 路径必须以「相对项目根」的形式作为**参数**传给 Python：
#    MSYS 会把 /d/... 形态的参数错拼成 D:\d\...，open() 直接失败。
#    早期版本因此恒返回 "MISSING"——而 MISSING 与 MISSING 相等，
#    于是"负向测试已逐字节还原"的判定变成了一次**假通过**。
#    这里同时把失败显式写成 ERROR:...，让"读不到"不可能伪装成"读一致"。
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

# 32 位十六进制 = 有效摘要；其余（MISSING/ERROR:.../空）一律视为"无法验证"
is_hash() { printf '%s' "$1" | grep -Eq '^[0-9a-f]{32}$'; }

# 运行一个脚本并记录结果。用法: run_step "标签" "工作目录" 命令...
# 从脚本输出里抽取"核对/通过了多少项"。各脚本输出格式不统一，故按优先级试几种；
# 一种都不匹配就返回空（宁可只显示 PASS，也不要显示一个可能过期的数字）。
extract_count() {
  local out="$1" p
  # 五个负向脚本的收尾措辞各不相同（"项通过" / "项被捕获" / "项符合预期" / "捕获"），
  # 但都写成 "负向测试: N/M ..."，故按该前缀取，不依赖后半句。
  p="$(printf '%s' "$out" | grep -oE '负向测试: *[0-9]+/[0-9]+' | tail -1 | grep -oE '[0-9]+/[0-9]+' || true)"
  if [ -n "$p" ]; then printf '%s' "$p"; return; fi
  p="$(printf '%s' "$out" | grep -oE '已核对(数值|项数): *[0-9]+' | tail -1 | grep -oE '[0-9]+$' || true)"
  if [ -n "$p" ]; then printf '%s 项' "$p"; return; fi
  p="$(printf '%s' "$out" | grep -oE '[0-9]+ 项核对' | tail -1 || true)"
  if [ -n "$p" ]; then printf '%s' "$p"; return; fi
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

# 上一段的最后一行摘要（用于把关键数字带出来）
tail_summary() {
  printf '%s' "$1" | grep -E "问题数|负向测试|项|OK|PASS" | tail -1
}

require_py_module() { "$PY" -c "import $1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 3. 锁：同一时刻只允许一个复现流程（负向测试会改写仓库文件）
# ---------------------------------------------------------------------------
acquire_lock() {
  if [ -e "$LOCK" ]; then
    echo "${C_BAD}[reproduce] 已有另一个复现流程在运行（$LOCK）${C_OFF}" >&2
    echo "[reproduce] 负向测试会临时改写论文源文件，并发执行会互相破坏。" >&2
    echo "[reproduce] 若确认无进程在跑，删掉该锁文件后重试。" >&2
    exit 3
  fi
  mkdir -p "$LOCK"
  trap 'rm -rf "$LOCK"' EXIT INT TERM
}

# ===========================================================================
# 阶段 1：doctor —— 环境体检
# ===========================================================================
stage_doctor() {
  hr; echo "环境体检 (doctor)"; hr
  echo "  项目根        : $A2A_ROOT"
  echo "  解释器        : $PY"
  "$PY" -c 'import sys; print("  Python 版本   :", sys.version.split()[0])'

  local pyok
  pyok="$("$PY" -c 'import sys; print(1 if sys.version_info>=(3,10) else 0)')"
  if [ "$pyok" = "1" ]; then
    printf '  %-42s%sOK%s\n' "Python >= 3.10" "$C_OK" "$C_OFF"
  else
    printf '  %-42s%s需 >= 3.10%s\n' "Python >= 3.10" "$C_BAD" "$C_OFF"
  fi

  echo
  echo "  依赖（核心协议库仅需标准库；下表仅影响推理与绘图）:"
  local m
  for m in numpy scipy matplotlib datasets openai torch vllm transformers; do
    printf '    %-14s' "$m"
    if require_py_module "$m"; then printf '%s已安装%s\n' "$C_OK" "$C_OFF"
    else printf '%s缺失%s\n' "$C_DIM" "$C_OFF"; fi
  done

  echo
  echo "  数据与结果:"
  local d
  for d in "experiments/datasets:数据集" "experiments/results:实验结果" \
           "papers/figures:论文图件" "experiments/src:核心库"; do
    local p="${d%%:*}"; local n="${d##*:}"
    local cnt
    cnt="$(find "$A2A_ROOT/$p" -type f ! -name "*.pyc" 2>/dev/null | grep -vc "__pycache__" || echo 0)"
    printf '    %-24s %s 个文件\n' "$n" "$cnt"
  done

  echo
  echo "  硬件（仅 full 阶段需要）:"
  if command -v nvidia-smi >/dev/null 2>&1; then
    local ngpu
    ngpu="$(nvidia-smi -L 2>/dev/null | grep -c '^GPU')"
    printf '    GPU 数量      : %s' "$ngpu"
    if [ "$ngpu" -ge 2 ]; then printf '  %s(满足 2 卡要求)%s\n' "$C_OK" "$C_OFF"
    else printf '  %s(full 阶段需 2 张 80GB 卡)%s\n' "$C_WARN" "$C_OFF"; fi
    nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/      /'
  else
    printf '    GPU           : %s未检测到 nvidia-smi（不影响 verify）%s\n' "$C_DIM" "$C_OFF"
  fi

  echo
  hr
  echo "结论：verify / figures / datasets 可在本机运行；full 需 2×80GB GPU。"
  hr
}

# ===========================================================================
# 阶段 2：verify —— 8 审计 + 5 负向测试（严格串行）
# ===========================================================================
# 标签只写描述、不写计数：计数由 extract_count() 从各脚本的**实际输出**里读。
# 早先标签里写死了 "（349 项）" / "注入路径缺陷 6 项"，用例一增减标签就过期，
# 而通过/失败只由退出码判定，于是过期标签会长期无人发现（实测负向路径用例
# 已从 6 增到 8，标签仍写 6）。
AUDITS=(
  "audit_table_numbers.py|表格数值"
  "audit_figures.py|图-表一致性 + 内容指纹"
  "audit_prose_ranges.py|正文区间与表格一致"
  "audit_theory_numerics.py|理论公式数值实例化"
  "audit_revision_layer.py|修订层代数 + 文本自洽"
  "audit_decision_neutrality.py|决策中性"
  "audit_reputation_fidelity.py|声誉实现保真"
  "audit_paths.py|路径解析层"
)
NEGATIVES=(
  "negative_test_tables.py|注入表格缺陷"
  "negative_test_figures.py|注入图件缺陷"
  "negative_test_theory.py|注入理论缺陷"
  "negative_test_paths.py|注入路径缺陷"
  "negative_test_revision.py|注入修订层缺陷"
)

stage_verify() {
  acquire_lock
  hr; echo "审计 + 负向测试 (verify) —— 纯 CPU，无需 GPU"; hr

  if [ -f "$TEX" ]; then
    local h0; h0="$(file_hash "$TEX")"
    echo "论文源文件指纹（执行前）: $h0"
  else
    echo "${C_BAD}缺少 $TEX${C_OFF}" >&2
  fi
  echo

  echo "[1/2] 审计脚本（顺序执行，共 ${#AUDITS[@]} 个）"
  local item script label
  for item in "${AUDITS[@]}"; do
    script="${item%%|*}"; label="${item##*|}"
    if [ ! -f "$VERIFICATION/$script" ]; then
      printf '  %-42s%sMISSING%s\n' "$script" "$C_BAD" "$C_OFF"
      FAIL_N=$((FAIL_N + 1)); FAILED_ITEMS+=("$script 不存在")
      continue
    fi
    # audit_figures.py 在导入期就加载 papers/generate_figures.py（需要 matplotlib）。
    # 缺依赖时它不是"通过"，而是"这一层根本没被验证"——两种结果必须区分开，
    # 所以默认判失败；只有显式设置 A2A_ALLOW_SKIP_FIGURES=1 才降级为 SKIP，
    # 且 SKIP 不计入 PASS，会被写进最终结论。
    if [ "$script" = "audit_figures.py" ] && ! require_py_module matplotlib; then
      if [ "${A2A_ALLOW_SKIP_FIGURES:-0}" = "1" ]; then
        printf '  %-42s%sSKIP%s (缺 matplotlib)\n' "$label" "$C_WARN" "$C_OFF"
        SKIP_N=$((SKIP_N + 1)); SKIPPED_ITEMS+=("$label —— 图件层未被验证")
        continue
      fi
      printf '  %-42s%sFAIL%s\n' "$label" "$C_BAD" "$C_OFF"
      printf '      | 缺少 matplotlib，图件层无法验证（这不是通过）。\n'
      printf '      | 修复: %s -m pip install "matplotlib>=3.7.0"   或   ./reproduce.sh install\n' "$PY"
      printf '      | 明确放弃该层: A2A_ALLOW_SKIP_FIGURES=1 ./reproduce.sh verify\n'
      FAIL_N=$((FAIL_N + 1)); FAILED_ITEMS+=("$label 缺 matplotlib")
      continue
    fi
    run_step "$label" "$A2A_ROOT" "$PY" "$REL_VERIFICATION/$script"
  done

  echo
  echo "[2/2] 负向测试（顺序执行，共 ${#NEGATIVES[@]} 个）"
  echo "${C_DIM}  注：这些用例会临时改写 papers/iclr2027_main.tex 再还原，故不可并行。${C_OFF}"
  for item in "${NEGATIVES[@]}"; do
    script="${item%%|*}"; label="${item##*|}"
    if [ ! -f "$VERIFICATION/$script" ]; then
      printf '  %-42s%sMISSING%s\n' "$script" "$C_BAD" "$C_OFF"
      FAIL_N=$((FAIL_N + 1)); FAILED_ITEMS+=("$script 不存在")
      continue
    fi
    run_step "$label" "$A2A_ROOT" "$PY" "$REL_VERIFICATION/$script"
  done

  # ---- 收尾后置条件：负向测试必须把论文源文件逐字节还原 ----
  echo
  if [ -f "$TEX" ]; then
    local h0v="${h0:-}" h1
    h1="$(file_hash "$TEX")"
    printf '论文源文件指纹（执行后）: %s  ' "$h1"
    if ! is_hash "$h0v" || ! is_hash "$h1"; then
      # 摘要无效（读不到/被错拼）= 约束未被验证，绝不算通过
      printf '%s无法验证 ❌%s\n' "$C_BAD" "$C_OFF"
      echo "  执行前: ${h0v:-<空>}"
      echo "  执行后: $h1"
      echo "  说明: 未取到有效摘要，无法证明负向测试已还原论文源文件。"
      FAIL_N=$((FAIL_N + 1))
      FAILED_ITEMS+=("无法验证 papers/iclr2027_main.tex 是否已还原")
    elif [ "$h1" = "$h0v" ]; then
      printf '%s还原成功%s\n' "$C_OK" "$C_OFF"
    else
      printf '%s未还原 ❌%s\n' "$C_BAD" "$C_OFF"
      echo "  执行前 $h0v"
      echo "  执行后 $h1"
      FAIL_N=$((FAIL_N + 1))
      FAILED_ITEMS+=("负向测试未还原 papers/iclr2027_main.tex")
    fi
  else
    printf '%s缺少 %s，无法设置还原后置条件 ❌%s\n' "$C_BAD" "$TEX" "$C_OFF"
    FAIL_N=$((FAIL_N + 1))
    FAILED_ITEMS+=("缺少论文源文件，还原后置条件无法建立")
  fi

  echo; hr
  printf '审计+负向：%s%d 通过%s / %s%d 失败%s' \
    "$C_OK" "$PASS_N" "$C_OFF" "$C_BAD" "$FAIL_N" "$C_OFF"
  if [ "$SKIP_N" -gt 0 ]; then
    printf ' / %s%d 跳过%s' "$C_WARN" "$SKIP_N" "$C_OFF"
  fi
  printf '\n'
  if [ "$FAIL_N" -gt 0 ]; then
    echo "失败项："
    local f; for f in "${FAILED_ITEMS[@]}"; do echo "  - $f"; done
    echo "REPRODUCE_FAILED"
    hr
    return 1
  fi
  if [ "$SKIP_N" -gt 0 ]; then
    echo "${C_WARN}注意：以下检查层【未被验证】，结论不是全绿：${C_OFF}"
    local s; for s in "${SKIPPED_ITEMS[@]}"; do echo "  ! $s"; done
    echo "REPRODUCE_OK_PARTIAL"
    hr
    return 0
  fi
  echo "全部通过：论文中的每个数字都可被独立重算，且审计本身已被证明有效。"
  echo "REPRODUCE_OK"
  hr
  return 0
}

# ===========================================================================
# 阶段 3：figures —— 重新出图 + 复查
# ===========================================================================
stage_figures() {
  acquire_lock
  hr; echo "重出论文图件 (figures)"; hr
  if ! require_py_module matplotlib; then
    echo "${C_BAD}缺少 matplotlib，无法出图。${C_OFF}"
    echo "请先执行: $PY -m pip install 'matplotlib>=3.7.0'   （或 ./reproduce.sh install）"
    return 1
  fi
  run_step "重新生成 5 张图件" "$A2A_ROOT" "$PY" "$REL_PAPERS/generate_figures.py"
  run_step "图-表一致性复查" "$A2A_ROOT" "$PY" "$REL_VERIFICATION/audit_figures.py"
  echo
  if [ "$FAIL_N" -gt 0 ]; then echo "REPRODUCE_FAILED"; return 1; fi
  echo "图件已从 experiments/results/ 重新生成并通过一致性复查。"
  echo "REPRODUCE_OK"
}

# ===========================================================================
# 阶段 4：datasets
# ===========================================================================
stage_datasets() {
  hr; echo "下载数据集 (datasets)"; hr
  run_step "GSM8K / MBPP / MMLU" "$A2A_ROOT" "$PY" "$REL_ENVDIR/download_datasets.py"
  echo
  if [ "$FAIL_N" -gt 0 ]; then echo "REPRODUCE_FAILED"; return 1; fi
  echo "REPRODUCE_OK"
}

# ===========================================================================
# 阶段 5：install
# ===========================================================================
stage_install() {
  hr; echo "安装依赖 (install)"; hr
  echo "解释器: $PY"
  "$PY" -m pip install -r "$A2A_ROOT/requirements.txt"
  local rc=$?
  echo
  [ $rc -eq 0 ] && echo "REPRODUCE_OK" || echo "REPRODUCE_FAILED"
  return $rc
}

# ===========================================================================
# 阶段 6：full —— 全部实验（需 GPU，永不隐式触发）
# ===========================================================================
stage_full() {
  hr; echo "全部实验 (full) —— 前置条件检查"; hr
  local ok=1

  local ngpu=0
  if command -v nvidia-smi >/dev/null 2>&1; then
    ngpu="$(nvidia-smi -L 2>/dev/null | grep -c '^GPU')"
  fi
  printf '  %-40s' "GPU 数量 >= 2"
  if [ "$ngpu" -ge 2 ]; then printf '%sOK (%s)%s\n' "$C_OK" "$ngpu" "$C_OFF"
  else printf '%s不满足 (%s)%s\n' "$C_BAD" "$ngpu" "$C_OFF"; ok=0; fi

  printf '  %-40s' "模型权重目录 A2A_MODEL_DIR"
  if [ -n "${A2A_MODEL_DIR:-}" ] && [ -d "${A2A_MODEL_DIR:-/nonexistent}" ]; then
    printf '%sOK%s\n' "$C_OK" "$C_OFF"
  else
    printf '%s未设置或不存在：%s%s\n' "$C_BAD" "${A2A_MODEL_DIR:-<空>}" "$C_OFF"; ok=0
  fi

  printf '  %-40s' "DEEPSEEK_API_KEY（Pipeline C）"
  if [ -n "${DEEPSEEK_API_KEY:-}" ]; then printf '%s已设置%s\n' "$C_OK" "$C_OFF"
  else printf '%s未设置%s\n' "$C_WARN" "$C_OFF"; fi

  printf '  %-40s' "依赖 numpy / scipy / matplotlib"
  if require_py_module numpy && require_py_module scipy && require_py_module matplotlib; then
    printf '%sOK%s\n' "$C_OK" "$C_OFF"
  else printf '%s缺失%s\n' "$C_BAD" "$C_OFF"; ok=0; fi

  echo
  if [ "$ok" -ne 1 ]; then
    echo "${C_BAD}前置条件不满足，已中止（未执行任何实验）。${C_OFF}"
    echo "REPRODUCE_FAILED"
    return 1
  fi

  hr; echo "启动 4 个异构 vLLM 实例（2×80GB，逐个启动 + 健康检查）"; hr
  bash "$ENVDIR/start_vllm_seq.sh" || { echo "vLLM 启动失败"; echo "REPRODUCE_FAILED"; return 1; }
  run_step "连通性探测" "$A2A_ROOT" "$PY" "$REL_ENVDIR/probe.py" || true

  hr; echo "Pipeline A：容错扫描（主实验）"; hr
  local n
  for n in gsm8k mbpp mmlu; do
    run_step "full_bft_sweep.py $n" "$A2A_ROOT" "$PY" "$REL_REPRODUCE/full_bft_sweep.py" "$n"
  done
  run_step "aggregate_full_sweep.py" "$A2A_ROOT" "$PY" "$REL_REPRODUCE/aggregate_full_sweep.py"

  hr; echo "Pipeline B：消融 + 基线对比"; hr
  echo "${C_DIM}  该流水线的完整命令见 docs/REPRODUCTION.md §3（含多方法/多种子组合）。${C_OFF}"

  hr; echo "Pipeline C：真实 API 多领域验证（需 DEEPSEEK_API_KEY）"; hr
  echo "${C_DIM}  该流水线的完整命令见 docs/REPRODUCTION.md §4（含成本与限流说明）。${C_OFF}"

  hr; echo "重出图件并复查"; hr
  run_step "generate_figures.py" "$A2A_ROOT" "$PY" "$REL_PAPERS/generate_figures.py"
  run_step "audit_figures.py" "$A2A_ROOT" "$PY" "$REL_VERIFICATION/audit_figures.py"

  echo; hr
  if [ "$FAIL_N" -gt 0 ]; then
    printf '%s%d 项失败%s\n' "$C_BAD" "$FAIL_N" "$C_OFF"
    echo "REPRODUCE_FAILED"; return 1
  fi
  echo "实验完成。建议随后执行 ./reproduce.sh verify 做全量数字复核。"
  echo "REPRODUCE_OK"
}

# ===========================================================================
# 阶段 7：all
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
  # 打印文件头部的注释块（从第 2 行起，遇到第一行非注释即停），
  # 这样帮助文本与脚本头部的用法说明永远只有一份、不会各写各的。
  awk 'NR>1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print } else exit }' "${BASH_SOURCE[0]}"
}

# ---------------------------------------------------------------------------
# 入口
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
    echo "未知阶段: $1" >&2
    echo "可用: verify | doctor | figures | datasets | install | full | all | help" >&2
    exit 2
    ;;
esac
