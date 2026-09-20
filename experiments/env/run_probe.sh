#!/bin/bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
cd "$A2A_ROOT"
echo "=== 开始 $(date '+%F %T') ===" > "$A2A_LOGDIR/probe.log"
"$A2A_PY" -u "$A2A_ENV/probe.py" >> "$A2A_LOGDIR/probe.log" 2>&1
echo "===EXIT=$?===" >> "$A2A_LOGDIR/probe.log"
