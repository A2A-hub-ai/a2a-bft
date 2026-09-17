#!/bin/bash
# 重启失败的实例：llama(8000) + deepseek(8002)
# 修复：No available memory for the cache blocks
#   -> 提高 gpu-memory-utilization，缩小 max-model-len/max-num-seqs，加 --enforce-eager
# 注意：不触碰已在运行的 internlm(8001) / qwen(8003)

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
PY="$A2A_PY"
MODELS="$A2A_MODEL_DIR"
LOGDIR="$A2A_LOGDIR"

echo "重启 llama(8000) + deepseek(8002) ..."

# GPU0: Llama-3.1-8B (port 8000)
CUDA_VISIBLE_DEVICES=0 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/Llama-3.1-8B-Instruct \
  --served-model-name llama \
  --port 8000 \
  --gpu-memory-utilization 0.42 \
  --max-model-len 2048 \
  --max-num-seqs 16 \
  --enforce-eager \
  --disable-log-requests \
  --dtype float16 \
  > $LOGDIR/vllm_llama.log 2>&1 < /dev/null &

sleep 5

# GPU1: DeepSeek-V2-Lite-Chat (port 8002)
CUDA_VISIBLE_DEVICES=1 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/DeepSeek-V2-Lite-Chat \
  --served-model-name deepseek \
  --port 8002 \
  --gpu-memory-utilization 0.58 \
  --max-model-len 2048 \
  --max-num-seqs 16 \
  --trust-remote-code \
  --enforce-eager \
  --disable-log-requests \
  --dtype float16 \
  > $LOGDIR/vllm_deepseek.log 2>&1 < /dev/null &

echo "已启动，日志: $LOGDIR/vllm_llama.log, $LOGDIR/vllm_deepseek.log"
