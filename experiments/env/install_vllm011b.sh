#!/bin/bash
# vLLM 0.11.0 安装（锁定 transformers==4.56.2，避免与 torch 2.8.0 冲突引发回溯）
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
LOG="$A2A_LOGDIR/vllm011b_install.log"
PIP="$A2A_PIP"

{
echo "=== 开始安装 vLLM 0.11.0 (transformers==4.56.2) $(date '+%F %T') ==="
$PIP install --progress-bar off --timeout 90 --retries 5 \
  "vllm==0.11.0" "transformers==4.56.2"
RC=$?
echo "===VLLM_INSTALL_EXIT=$RC==="
echo "--- pip show vllm ---"
$PIP show vllm 2>/dev/null | head -3
echo "--- pip show transformers ---"
$PIP show transformers 2>/dev/null | grep -E '^Version'
echo "--- torch 校验 ---"
"$A2A_PY" -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),torch.cuda.device_count())" 2>&1 | tail -1
echo "===ALL DONE==="
} > $LOG 2>&1
