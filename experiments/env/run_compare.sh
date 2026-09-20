#!/bin/bash
# 等待当前主实验结束，再自动接力跑「对比算法 + 消融算法」
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
cd "$A2A_ROOT"
echo "等待当前实验结束... $(date '+%F %T')" > "$A2A_LOGDIR/compare_ablation.log"
while pgrep -f 'multi_model_vllm' > /dev/null 2>&1; do
  sleep 20
done
sleep 15
echo "=== 主实验已结束，开始对比+消融 $(date '+%F %T') ===" >> "$A2A_LOGDIR/compare_ablation.log"
"$A2A_PY" -u "$A2A_LEGACY/multi_model_compare_ablation.py" >> "$A2A_LOGDIR/compare_ablation.log" 2>&1
echo "===EXIT=$?===" >> "$A2A_LOGDIR/compare_ablation.log"
