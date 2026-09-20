#!/bin/bash
# 安装与现有 torch 2.8.0+cu128 完全匹配的 vLLM 0.11.0
export PIP_DISABLE_PIP_VERSION_CHECK=1
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
echo "=== 开始安装 vLLM 0.11.0 $(date +%H:%M:%S) ==="
"$A2A_PIP" install --timeout 90 --retries 5 "vllm==0.11.0"
RC=$?
echo "===VLLM_INSTALL_EXIT=$RC==="
"$A2A_PIP" show vllm 2>/dev/null | head -3
echo "=== 校验 torch 是否被改动 ==="
"$A2A_PY" -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
echo "===ALL DONE==="
