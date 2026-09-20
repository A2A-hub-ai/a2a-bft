#!/bin/bash
# A2A-BFT 实验环境变量（2026-09-15 代码整理）
#
# 背景：以下脚本原先把 AutoDL 的工作目录 /root/autodl-tmp 和模型盘
#       /autodl-fs/data/models 写死在各处，换机器或换目录后立即失效。
#       本文件把两者改为「脚本自定位 + 环境变量可覆盖」。
#
# 用法（在 experiments/env/ 下的脚本开头）：
#   source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
#
# 可覆盖的变量：
#   A2A_ROOT       项目根（默认由本文件位置向上两级推出）
#   A2A_RESULTS    结果目录（默认 <root>/experiments/results）
#   A2A_DATASETS   数据集目录（默认 <root>/experiments/datasets）
#   A2A_LOGDIR     日志目录（默认 <results>/logs）
#   A2A_MODEL_DIR  模型权重目录（默认 /autodl-fs/data/models）
#   A2A_PY         运行实验的 Python 解释器（默认 /root/miniconda3/bin/python）
#   A2A_PIP        对应的 pip 路径

A2A_ROOT="${A2A_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
A2A_EXPERIMENTS="$A2A_ROOT/experiments"
A2A_REPRODUCE="$A2A_EXPERIMENTS/reproduce"
A2A_LEGACY="$A2A_EXPERIMENTS/legacy"
A2A_ENV="$A2A_EXPERIMENTS/env"
A2A_RESULTS="${A2A_RESULTS:-$A2A_EXPERIMENTS/results}"
A2A_DATASETS="${A2A_DATASETS:-$A2A_EXPERIMENTS/datasets}"
A2A_LOGDIR="${A2A_LOGDIR:-$A2A_RESULTS/logs}"
A2A_MODEL_DIR="${A2A_MODEL_DIR:-/autodl-fs/data/models}"
A2A_PY="${A2A_PY:-/root/miniconda3/bin/python}"
A2A_PIP="${A2A_PIP:-/root/miniconda3/bin/pip}"

export A2A_ROOT A2A_EXPERIMENTS A2A_REPRODUCE A2A_LEGACY A2A_ENV
export A2A_RESULTS A2A_DATASETS A2A_LOGDIR A2A_MODEL_DIR A2A_PY A2A_PIP

mkdir -p "$A2A_RESULTS" "$A2A_LOGDIR" 2>/dev/null

# 便捷提示：设置 A2A_VERBOSE=1 可打印解析结果
if [ -n "$A2A_VERBOSE" ]; then
  echo "[env.sh] A2A_ROOT      = $A2A_ROOT"
  echo "[env.sh] A2A_REPRODUCE = $A2A_REPRODUCE"
  echo "[env.sh] A2A_RESULTS   = $A2A_RESULTS"
  echo "[env.sh] A2A_DATASETS  = $A2A_DATASETS"
  echo "[env.sh] A2A_LOGDIR    = $A2A_LOGDIR"
  echo "[env.sh] A2A_MODEL_DIR = $A2A_MODEL_DIR"
  echo "[env.sh] A2A_PY        = $A2A_PY"
fi
