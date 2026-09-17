#!/bin/bash
# AutoDL GPU服务器连接和实验运行脚本
# 使用方法: bash run_on_autodl.sh

set -e

A2A_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$A2A_ROOT"

# AutoDL连接信息
HOST="${A2A_SSH_HOST:?请设置环境变量 A2A_SSH_HOST}"
PORT="${A2A_SSH_PORT:?请设置环境变量 A2A_SSH_PORT}"
USER="${A2A_SSH_USER:-root}"
PASS="${A2A_SSH_PASS:?请先设置环境变量 A2A_SSH_PASS（原为硬编码明文密码，已移除）}"

echo "=========================================="
echo "A2A-BFT GPU 实验脚本"
echo "=========================================="

# 检查SSH连接
echo ""
echo "[1/4] 检查AutoDL连接..."
ssh -p $PORT -o ConnectTimeout=10 -o StrictHostKeyChecking=no $USER@$HOST "echo '连接成功'; nvidia-smi | head -15" 2>/dev/null || {
    echo "⚠️  AutoDL连接失败，请检查:"
    echo "   1. 服务器是否正在运行"
    echo "   2. SSH端口是否正确 ($PORT)"
    echo "   3. 密码是否正确"
    echo ""
    echo "手动连接命令:"
    echo "   ssh -p $PORT $USER@$HOST"
    exit 1
}

echo ""
echo "[2/4] 检查Python环境和依赖..."
ssh -p $PORT $USER@$HOST "python3 --version && pip list | grep -E 'torch|transformers|datasets'" || {
    echo "⚠️  Python环境检查失败"
}

echo ""
echo "[3/4] 检查模型和GPU..."
ssh -p $PORT $USER@$HOST "ls -la ~/models/ 2>/dev/null || echo '模型目录不存在，需要下载模型'; nvidia-smi"

echo ""
echo "[4/4] 上传数据集并运行实验..."
# 上传数据集
echo "上传数据集..."
scp -P $PORT -r "$A2A_ROOT/experiments/datasets" $USER@$HOST:~/A2A-BFT/datasets/ 2>/dev/null || echo "数据集上传失败，将使用服务器本地数据"

# 运行实验
echo ""
echo "开始运行GPU实验..."
ssh -p $PORT $USER@$HOST "
cd ~/A2A-BFT 2>/dev/null || mkdir -p ~/A2A-BFT && cd ~/A2A-BFT
echo '当前目录:' \$(pwd)
echo ''
echo '尝试运行真实数据集实验...'
python3 experiments/legacy/real_dataset_experiment.py 2>&1 || echo '实验运行失败，需要安装依赖'
"

echo ""
echo "=========================================="
echo "实验完成（或需要手动运行）"
echo "=========================================="
echo ""
echo "手动连接运行命令:"
echo "   ssh -p $PORT $USER@$HOST"
echo "   cd ~/A2A-BFT"
echo "   python experiments/legacy/real_dataset_experiment.py"
echo ""
