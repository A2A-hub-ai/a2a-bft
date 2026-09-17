"""
快速测试 DeepSeek 连接
"""

import os
import sys

# API Key 从环境变量读取（原为硬编码密钥，已移除）
if not os.environ.get("DEEPSEEK_API_KEY"):
    print("错误: 请先设置环境变量 DEEPSEEK_API_KEY")
    sys.exit(1)

print("测试 DeepSeek API 连接...")
print("="*70)

try:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com"
    )

    # 测试简单对话
    print("\n测试 1: 简单对话")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "你好，请简单自我介绍"}],
        max_tokens=50
    )
    print(f"  模型: {response.model}")
    print(f"  响应: {response.choices[0].message.content}")
    print(f"  Token 消耗: 输入={response.usage.prompt_tokens}, 输出={response.usage.completion_tokens}")

    # 测试代码生成
    print("\n测试 2: 代码生成")
    response = client.chat.completions.create(
        model="deepseek-coder",
        messages=[{"role": "user", "content": "写一个 Python 函数计算斐波那契数列"}],
        max_tokens=100
    )
    print(f"  模型: {response.model}")
    print(f"  响应: {response.choices[0].message.content[:200]}...")

    print("\n✅ API 连接成功!")
    print("\n可以使用以下命令运行完整实验:")
    print("  python experiments/legacy/deepseek_full_experiment.py")

except ImportError:
    print("❌ 需要先安装 openai 库:")
    print("   pip install openai")
except Exception as e:
    print(f"❌ 错误: {e}")
    sys.exit(1)
