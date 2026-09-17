"""
下载真实benchmark数据集用于A2A-BFT实验
包含：
A. 标准benchmark数据集 (GSM8K, MMLU, MBPP)
B. 完整HumanEval数据集 (164个任务)
"""

import json
import os
from pathlib import Path

# 使用国内镜像
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 数据集保存目录
DATA_DIR = Path(__file__).resolve().parent.parent / "datasets"
DATA_DIR.mkdir(exist_ok=True)

print("=" * 60)
print("A2A-BFT 实验数据集下载")
print("=" * 60)
print(f"保存目录: {DATA_DIR.absolute()}")
print()

from datasets import load_dataset

# ========================================
# A. 标准benchmark数据集
# ========================================

print("【A】下载标准benchmark数据集...")
print("-" * 40)

# 1. GSM8K (数学推理)
print("\n1. GSM8K (小学数学推理数据集)...")
try:
    gsm8k = load_dataset("openai/gsm8k", "main", split="test")
    print(f"   GSM8K测试集: {len(gsm8k)} 个问题")

    gsm8k_data = []
    for item in gsm8k:
        question = item["question"]
        answer = item["answer"]
        gsm8k_data.append({
            "id": f"gsm8k_{len(gsm8k_data)+1:04d}",
            "type": "math",
            "question": question,
            "answer": answer,
            "difficulty": "medium"
        })

    gsm8k_path = DATA_DIR / "gsm8k_test.json"
    with open(gsm8k_path, "w", encoding="utf-8") as f:
        json.dump(gsm8k_data, f, ensure_ascii=False, indent=2)
    print(f"   ✅ 已保存: {gsm8k_path}")
except Exception as e:
    print(f"   ⚠️ GSM8K下载失败: {e}")
    gsm8k_data = []

# 2. MMLU (知识问答)
print("\n2. MMLU (知识问答数据集, 3个核心科目)...")
mmlu_subjects = ["abstract_algebra", "college_mathematics", "machine_learning"]
mmlu_data = []
for subject in mmlu_subjects:
    try:
        ds = load_dataset("cais/mmlu", subject, split="test")
        for item in ds:
            choices = item["choices"]
            answer_idx = item["answer"]
            question_text = item["question"].strip()
            mmlu_data.append({
                "id": f"mmlu_{subject}_{len(mmlu_data)+1:04d}",
                "type": "knowledge",
                "subject": subject,
                "question": question_text,
                "choices": choices,
                "answer": choices[answer_idx] if answer_idx < len(choices) else "",
                "difficulty": "medium"
            })
        print(f"   {subject}: {len([x for x in mmlu_data if x['subject']==subject])} 题")
    except Exception as e:
        print(f"   {subject}: ⚠️ 失败 - {str(e)[:50]}")

mmlu_path = DATA_DIR / "mmlu_3subjects.json"
with open(mmlu_path, "w", encoding="utf-8") as f:
    json.dump(mmlu_data, f, ensure_ascii=False, indent=2)
print(f"   ✅ MMLU共 {len(mmlu_data)} 题已保存")

# 3. MBPP (编程)
print("\n3. MBPP (编程数据集, 全部500题)...")
try:
    mbpp = load_dataset("mbpp", split="test")
    print(f"   MBPP测试集: {len(mbpp)} 个任务")

    mbpp_data = []
    for item in mbpp:
        mbpp_data.append({
            "id": f"mbpp_{len(mbpp_data)+1:04d}",
            "type": "code",
            "description": item.get("text", ""),
            "code": item.get("code", ""),
            "test_list": item.get("test_list", []),
            "difficulty": "medium"
        })

    mbpp_path = DATA_DIR / "mbpp_test.json"
    with open(mbpp_path, "w", encoding="utf-8") as f:
        json.dump(mbpp_data, f, ensure_ascii=False, indent=2)
    print(f"   ✅ 已保存 {len(mbpp_data)} 题")
except Exception as e:
    print(f"   ⚠️ MBPP下载失败: {e}")
    mbpp_data = []

# ========================================
# B. 完整HumanEval数据集 (164个任务)
# ========================================

print("\n" + "=" * 60)
print("【B】下载完整HumanEval数据集 (164个任务)...")
print("=" * 60)

try:
    humaneval = load_dataset("codeparrot/humaneval", split="test")
    print(f"   HumanEval测试集: {len(humaneval)} 个任务")

    humaneval_data = []
    for item in humaneval:
        humaneval_data.append({
            "id": f"humaneval_{item['task_id']:03d}",
            "type": "code",
            "prompt": item["prompt"],
            "canonical_solution": item["canonical_solution"],
            "test": item["test"],
            "entry_point": item["entry_point"],
            "difficulty": "medium"
        })

    humaneval_path = DATA_DIR / "humaneval_full.json"
    with open(humaneval_path, "w", encoding="utf-8") as f:
        json.dump(humaneval_data, f, ensure_ascii=False, indent=2)
    print(f"   ✅ 已保存完整HumanEval ({len(humaneval_data)} 题)")
except Exception as e:
    print(f"   ⚠️ HumanEval下载失败: {e}")
    humaneval_data = []

# ========================================
# 汇总
# ========================================

print("\n" + "=" * 60)
print("数据集下载汇总")
print("=" * 60)
print(f"目录: {DATA_DIR.absolute()}")
print()

# 声明式注册表：只统计下面明确列出的文件，不再 glob 整个目录。
# 历史缺陷：原实现是 ``DATA_DIR.glob("*.json")`` 求和，于是任何多余文件都会
# 静默计入"实验任务总数"——当时多出的 mmlu_4subjects.json（312 条冗余副本）
# 与未被实验使用的 humaneval_full.json（164 条）把总数从 2,131 抬到 2,607。
# 清单写死在本处，新增数据集必须显式登记，避免同类污染复发。
DATASET_REGISTRY = [
    ("gsm8k",     "gsm8k_test.json",      True),
    ("mmlu",      "mmlu_3subjects.json",  True),
    ("mbpp",      "mbpp_test.json",       True),
    ("humaneval", "humaneval_full.json",  False),   # 已下载但论文实验链未使用
]

counts, paper_total, all_total = {}, 0, 0
for name, fname, used in DATASET_REGISTRY:
    path = DATA_DIR / fname
    if not path.exists():
        counts[name] = 0
        print(f"  {fname}: 缺失")
        continue
    with open(path, encoding="utf-8") as fp:
        data = json.load(fp)
    counts[name] = len(data) if isinstance(data, list) else 0
    all_total += counts[name]
    if used:
        paper_total += counts[name]
    print(f"  {fname}: {counts[name]} 条数据{'（论文使用）' if used else '（未使用）'}")

print()
print(f"论文使用的三个数据集合计: {paper_total} 条实验任务")
print(f"目录内全部数据集（含未使用）: {all_total} 条")
print("=" * 60)

# 生成数据集摘要
summary = {
    "paper_used_datasets": ["gsm8k", "mbpp", "mmlu"],
    "paper_total_tasks": paper_total,
    "all_datasets_total_tasks": all_total,
    "datasets": {name: counts[name] for name, _, _ in DATASET_REGISTRY},
    "unused": {name: counts[name] for name, _, used in DATASET_REGISTRY if not used},
}

with open(DATA_DIR / "dataset_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print("\n✅ 数据集摘要已保存")
