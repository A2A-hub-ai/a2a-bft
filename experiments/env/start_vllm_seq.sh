#!/bin/bash
# 顺序启动 4 个 vLLM 实例：一个就绪后再启动下一个，避免并发显存探测竞争
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
PY="$A2A_PY"
MODELS="$A2A_MODEL_DIR"
LOGDIR="$A2A_LOGDIR"

wait_health() {
  local port=$1 name=$2
  for i in $(seq 1 40); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:$port/health)
    if [ "$code" = "200" ]; then echo "[$name] 就绪 (port $port)"; return 0; fi
    sleep 15
  done
  echo "[$name] 超时未就绪!"; return 1
}

echo "[1/4] Llama-3.1-8B -> GPU0 (util 0.30)"
CUDA_VISIBLE_DEVICES=0 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/Llama-3.1-8B-Instruct --served-model-name llama --port 8000 \
  --gpu-memory-utilization 0.30 --max-model-len 4096 --disable-log-requests --dtype float16 \
  > $LOGDIR/vllm_llama.log 2>&1 < /dev/null &
wait_health 8000 llama || exit 1

echo "[2/4] InternLM3-8B -> GPU0 (util 0.30)"
CUDA_VISIBLE_DEVICES=0 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/InternLM3-8B-Instruct --served-model-name internlm --port 8001 \
  --gpu-memory-utilization 0.30 --max-model-len 4096 --trust-remote-code \
  --disable-log-requests --dtype float16 \
  > $LOGDIR/vllm_internlm.log 2>&1 < /dev/null &
wait_health 8001 internlm || exit 1

echo "[3/4] DeepSeek-V2-Lite -> GPU1 (util 0.50)"
CUDA_VISIBLE_DEVICES=1 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/DeepSeek-V2-Lite-Chat --served-model-name deepseek --port 8002 \
  --gpu-memory-utilization 0.50 --max-model-len 4096 --trust-remote-code \
  --disable-log-requests --dtype float16 \
  > $LOGDIR/vllm_deepseek.log 2>&1 < /dev/null &
wait_health 8002 deepseek || exit 1

echo "[4/4] Qwen2.5-7B -> GPU1 (util 0.28)"
CUDA_VISIBLE_DEVICES=1 setsid $PY -m vllm.entrypoints.openai.api_server \
  --model $MODELS/Qwen2.5-7B-Instruct --served-model-name qwen --port 8003 \
  --gpu-memory-utilization 0.28 --max-model-len 4096 --disable-log-requests --dtype float16 \
  > $LOGDIR/vllm_qwen.log 2>&1 < /dev/null &
wait_health 8003 qwen || exit 1

echo "ALL_4_VLLM_READY"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
