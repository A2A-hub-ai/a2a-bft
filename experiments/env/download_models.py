"""
AutoDL模型下载脚本
下载4个模型到 $A2A_DOWNLOAD_DIR（默认 <项目根>/experiments/models，可用环境变量覆盖）
"""
import os
import subprocess
import sys

MODEL_REPOS = {
    "Llama-3.1-8B-Instruct": "meta-llama/Llama-3.1-8B-Instruct",
    "InternLM3-8B-Instruct": "internlm/internlm3-8b-instruct",
    "LLaDA-8B-Instruct": "PKU-LLaDA/LLaDA-8B-Instruct",
    "DeepSeek-V2-Lite-Chat": "deepseek-ai/DeepSeek-V2-Lite"
}

BASE_DIR = os.environ.get("A2A_DOWNLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))

def download_model(name, repo):
    """下载模型"""
    path = os.path.join(BASE_DIR, name)
    if os.path.exists(path):
        print(f"[跳过] {name} 已存在: {path}")
        return True

    print(f"[下载] {name} -> {path}")
    print(f"  仓库: {repo}")

    # 使用huggingface-cli下载
    cmd = [
        sys.executable, "-m", "huggingface_hub", "download",
        "--repo_id", repo,
        "--local-dir", path,
        "--local-dir-use-symlinks", "False"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode == 0:
            print(f"  [成功] {name}")
            return True
        else:
            print(f"  [失败] {name}: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  [错误] {name}: {e}")
        return False

def main():
    os.makedirs(BASE_DIR, exist_ok=True)
    print(f"模型下载目录: {BASE_DIR}")
    print("="*60)

    success = []
    for name, repo in MODEL_REPOS.items():
        if download_model(name, repo):
            success.append(name)

    print("\n" + "="*60)
    print(f"下载完成: {len(success)}/{len(MODEL_REPOS)}")
    if success:
        print("已下载模型:", ", ".join(success))
    if len(success) < len(MODEL_REPOS):
        print("未下载:", ", ".join(set(MODEL_REPOS.keys()) - set(success)))
        print("请手动下载或使用huggingface-cli")

if __name__ == "__main__":
    main()
