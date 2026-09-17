#!/bin/bash
# 三个数据集并行启动全量真机扫描
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
cd "$A2A_ROOT"
mkdir -p "$A2A_RESULTS"

PY="$A2A_PY"
setsid $PY "$A2A_REPRODUCE/full_bft_sweep.py" gsm8k > "$A2A_LOGDIR/sweep_gsm8k.log" 2>&1 < /dev/null &
sleep 2
setsid $PY "$A2A_REPRODUCE/full_bft_sweep.py" mbpp  > "$A2A_LOGDIR/sweep_mbpp.log"  2>&1 < /dev/null &
sleep 2
setsid $PY "$A2A_REPRODUCE/full_bft_sweep.py" mmlu  > "$A2A_LOGDIR/sweep_mmlu.log"  2>&1 < /dev/null &

echo "3 个扫描进程已启动"
ps aux | grep full_bft_sweep | grep -v grep | awk '{print $2, $13, $14}'
