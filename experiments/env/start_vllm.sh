#!/bin/bash
# 启动 4 个 vLLM 实例（2×A800-80GB）
# GPU0: Llama-3.1-8B + InternLM3-8B
# GPU1: DeepSeek-V2-Lite + Qwen2.5-7B

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
PY="$A2A_PY"
MODELS="$A2A_MODEL_DIR"
LOGDIR="$A2A_LOGDIR"

echo "启动 4 个 vLLM 实例..."

# GPU0: Llama-3.1-8B (port 8000)
CUDA_VISIBLE_DEVICES=0 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/Llama-3.1-8B-Instruct \
  --served-model-name llama \
  --port 8000 \
  --gpu-memory-utilization 0.28 \
  --max-model-len 4096 \
  --disable-log-requests \
  --dtype float16 \
  > $LOGDIR/vllm_llama.log 2>&1 < /dev/null &

sleep 3

# GPU0: InternLM3-8B (port 8001)
CUDA_VISIBLE_DEVICES=0 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/InternLM3-8B-Instruct \
  --served-model-name internlm \
  --port 8001 \
  --gpu-memory-utilization 0.28 \
  --max-model-len 4096 \
  --trust-remote-code \
  --disable-log-requests \
  --dtype float16 \
  > $LOGDIR/vllm_internlm.log 2>&1 < /dev/null &

sleep 3

# GPU1: DeepSeek-V2-Lite-Chat (port 8002)
CUDA_VISIBLE_DEVICES=1 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/DeepSeek-V2-Lite-Chat \
  --served-model-name deepseek \
  --port 8002 \
  --gpu-memory-utilization 0.50 \
  --max-model-len 4096 \
  --trust-remote-code \
  --disable-log-requests \
  --dtype float16 \
  > $LOGDIR/vllm_deepseek.log 2>&1 < /dev/null &

sleep 3

# GPU1: Qwen2.5-7B-Instruct (port 8003)
CUDA_VISIBLE_DEVICES=1 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/Qwen2.5-7B-Instruct \
  --served-model-name qwen \
  --port 8003 \
  --gpu-memory-utilization 0.28 \
  --max-model-len 4096 \
  --disable-log-requests \
  --dtype float16 \
  > $LOGDIR/vllm_qwen.log 2>&1 < /dev/null &

echo "4 个 vLLM 实例已启动，正在加载模型..."
echo "日志: $LOGDIR/vllm_*.log"
