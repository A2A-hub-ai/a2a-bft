#!/bin/bash
# 后台运行快速验证
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
cd "$A2A_ROOT"
echo "=== 开始 $(date '+%F %T') ===" > "$A2A_LOGDIR/quick_test.log"
"$A2A_PY" -u "$A2A_ENV/quick_test.py" >> "$A2A_LOGDIR/quick_test.log" 2>&1
echo "===EXIT=$?===" >> "$A2A_LOGDIR/quick_test.log"
