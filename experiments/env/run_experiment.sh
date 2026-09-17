#!/bin/bash
# AutoDL实验运行脚本

set -e

# 激活conda环境
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
# 原脚本在此激活 conda base；现由 A2A_PY 指定解释器

# 安装依赖
echo "安装依赖..."
pip install -q transformers accelerate torch huggingface_hub

# 创建目录
mkdir -p "$A2A_MODEL_DIR" 2>/dev/null || true
mkdir -p "$A2A_RESULTS"

# 检查并下载数据集
if [ ! -f "$A2A_DATASETS/gsm8k_test.json" ]; then
    echo "警告: 数据集未找到，请先同步代码"
fi

# 运行实验
echo "开始4模型异构实验..."
"$A2A_PY" "$A2A_LEGACY/multi_model_experiment.py"

echo "实验完成"
