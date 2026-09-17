"""
多模型A2A-BFT实验
支持DeepSeek-V2-Lite, InternLM3-8B, LLaDA-8B, Llama-3.1-8B, Qwen2.5-72B
"""

import sys
import os
import json
import time
import random
from datetime import datetime
from typing import List, Dict, Tuple
from dataclasses import dataclass

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import DeepSeekWorker, ConsensusLayer
from a2a_bft.legacy.distributed_worker import MultiGPUDistributedSystem, WorkerConfig


# 模型配置
MODEL_CONFIGS = {
    "DeepSeek-V2-Lite-Chat": {
        "path": "E:/models/DeepSeek-V2-Lite-Chat",
        "size": "16B",
        "type": "对话",
        "gpu": 0
    },
    "InternLM3-8B-Instruct": {
        "path": "E:/models/InternLM3-8B-Instruct",
        "size": "8B",
        "type": "指令",
        "gpu": 1
    },
    "LLaDA-8B-Instruct": {
        "path": "E:/models/LLaDA-8B-Instruct",
        "size": "8B",
        "type": "指令",
        "gpu": 2
    },
    "Llama-3.1-8B-Instruct": {
        "path": "E:/models/Llama-3.1-8B-Instruct",
        "size": "8B",
        "type": "指令",
        "gpu": 3
    },
    "Qwen2.5-72B-Instruct-AWQ": {
        "path": "E:/models/Qwen2.5-72B-Instruct-AWQ",
        "size": "72B",
        "type": "指令",
        "gpu": 4  # 需要多卡或A800 80GB
    }
}

# 实验配置
EXPERIMENT_CONFIGS = [
    # 对照组
    {"n": 4, "f": 0, "s": 0, "models": None, "desc": "Baseline n=4"},
    {"n": 5, "f": 0, "s": 0, "models": None, "desc": "Baseline n=5"},
    {"n": 6, "f": 0, "s": 0, "models": None, "desc": "Baseline n=6"},
    # BFT攻击
    {"n": 4, "f": 1, "s": 0, "attack": "random", "models": None, "desc": "BFT random n=4"},
    {"n": 4, "f": 1, "s": 0, "attack": "strategic_reject", "models": None, "desc": "BFT strategic_reject n=4"},
    {"n": 5, "f": 1, "s": 1, "attack": "random", "models": None, "desc": "BFT random n=5,s=1"},
    {"n": 5, "f": 1, "s": 1, "attack": "strategic_reject", "models": None, "desc": "BFT strategic_reject n=5,s=1"},
    {"n": 5, "f": 2, "s": 0, "attack": "collusion", "models": None, "desc": "BFT collusion n=5"},
    {"n": 6, "f": 2, "s": 0, "attack": "collusion", "models": None, "desc": "BFT collusion n=6"},
]


def check_gpu_memory():
    """检查GPU内存可用性"""
    import torch
    if not torch.cuda.is_available():
        print("警告: 未检测到CUDA设备，将使用CPU模拟")
        return False

    print("\nGPU内存状态:")
    for i in range(torch.cuda.device_count()):
        mem_total = torch.cuda.get_device_properties(i).total_mem / 1024**3
        mem_free = torch.cuda.memory_reserved(i) / 1024**2
        print(f"  GPU {i}: {mem_total:.1f}GB total, ~{mem_free:.1f}MB reserved")

    # 72B模型需要至少80GB显存
    a800_available = any(
        torch.cuda.get_device_properties(i).total_mem >= 80 * 1024**3
        for i in range(torch.cuda.device_count())
    )

    if a800_available:
        print("\n✅ 检测到A800 80GB GPU，支持72B模型")
        return True
    else:
        print("\n⚠️ 未检测到80GB GPU，72B模型将降级到8B模拟")
        return False


def create_workers_with_models(
    n: int,
    f: int,
    s: int,
    attack_type: str = "random",
    models: List[str] = None
) -> List[DeepSeekWorker]:
    """使用真实模型创建Workers"""
    workers = []

    # 选择模型列表
    if models is None:
        # 默认使用所有可用模型
        available_models = list(MODEL_CONFIGS.keys())[:n]
    else:
        available_models = models[:n]

    # 补齐模型（如果不够）
    while len(available_models) < n:
        available_models.append(list(MODEL_CONFIGS.keys())[0])

    for i in range(n):
        model_name = available_models[i]
        model_config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["Llama-3.1-8B-Instruct"])

        # 检查模型路径是否存在
        model_path = model_config["path"]
        if not os.path.exists(model_path):
            print(f"  警告: 模型 {model_name} 路径不存在，使用模拟模式")
            accuracy = 0.9 if not (i < f or (i >= f and i < f + s)) else 0.3
            worker = DeepSeekWorker(
                worker_id=i,
                accuracy=accuracy,
                byzantine_type=attack_type if i < f else None,
                api_key=None
            )
        else:
            # 真实模型模式（需要API Key或本地推理）
            worker = DeepSeekWorker(
                worker_id=i,
                model=model_name,
                accuracy=0.9,  # 真实模型accuracy设为高值
                api_key=None  # 使用本地模型
            )

        # 设置拜占庭/软故障
        if i < f:
            worker.is_byzantine = True
            worker.byzantine_type = attack_type
        elif i < f + s:
            worker.is_soft_fault = True
            worker.accuracy = 0.6
        else:
            worker.accuracy = 0.9

        workers.append(worker)

    return workers


def run_multi_model_experiment(
    n: int,
    f: int,
    s: int,
    attack_type: str = "random",
    num_tasks: int = 50,
    use_real_models: bool = True
) -> Dict:
    """运行多模型实验"""
    print(f"\n{'='*80}")
    print(f"实验配置: n={n}, f={f}, s={s}, attack={attack_type}")
    print(f"模型模式: {'真实LLM' if use_real_models else '模拟模式'}")
    print(f"任务数: {num_tasks}")
    print(f"{'='*80}")

    # 创建workers
    workers = create_workers_with_models(n, f, s, attack_type)

    # 初始化共识层
    consensus = ConsensusLayer(n=n, f=f, s=s)

    # 运行实验
    results = {
        "accept": 0,
        "reject": 0,
        "manual": 0,
        "error": 0,
        "rounds": [],
        "times": [],
        "model_results": {}
    }

    start_time = time.time()

    for i in range(num_tasks):
        question = f"math_problem_{i+1}: 计算 1234 + 5678 = ?"

        try:
            task_start = time.time()
            outcome = consensus.run_consensus(workers, question)
            task_time = time.time() - task_start

            decision = outcome["decision"].upper()
            if decision == "ACCEPT":
                results["accept"] += 1
            elif decision == "REJECT":
                results["reject"] += 1
            elif decision == "MANUAL":
                results["manual"] += 1
            else:
                results["error"] += 1

            results["rounds"].append(outcome.get("round", 0))
            results["times"].append(task_time)

            # 记录每个模型的投票
            for worker in workers:
                model_name = getattr(worker, 'model', 'simulated')
                if model_name not in results["model_results"]:
                    results["model_results"][model_name] = {"votes": []}
                results["model_results"][model_name]["votes"].append(decision)

            # 进度显示
            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{num_tasks} ({(i+1)/num_tasks*100:.1f}%)")

        except Exception as e:
            results["error"] += 1
            print(f"  错误: {e}")

    total_time = time.time() - start_time
    total_tasks = results["accept"] + results["reject"] + results["manual"] + results["error"]

    results["accept_rate"] = results["accept"] / total_tasks * 100 if total_tasks > 0 else 0
    results["avg_time_ms"] = sum(results["times"]) / len(results["times"]) * 1000 if results["times"] else 0
    results["avg_rounds"] = sum(results["rounds"]) / len(results["rounds"]) if results["rounds"] else 0
    results["total_time_s"] = total_time
    results["tps"] = total_tasks / total_time if total_time > 0 else 0

    return results


def run_all_experiments(use_real_models: bool = True):
    """运行所有实验配置"""
    all_results = []

    for config in EXPERIMENT_CONFIGS:
        print(f"\n[{config['desc']}]")
        result = run_multi_model_experiment(
            n=config["n"],
            f=config["f"],
            s=config.get("s", 0),
            attack_type=config.get("attack", "random"),
            num_tasks=50,
            use_real_models=use_real_models
        )
        result["config"] = config
        all_results.append(result)

    return all_results


def print_summary(results: List[Dict]):
    """打印汇总"""
    print(f"\n{'='*80}")
    print("实验汇总")
    print(f"{'='*80}")
    print(f"{'配置':<35} {'接受率':<10} {'平均轮次':<10} {'TPS':<10} {'耗时(s)':<10}")
    print("-"*80)

    for r in results:
        config = r.get("config", {})
        desc = config.get("desc", "N/A")
        accept_rate = r.get("accept_rate", 0)
        avg_rounds = r.get("avg_rounds", 0)
        tps = r.get("tps", 0)
        total_time = r.get("total_time_s", 0)

        print(f"{desc:<35} {accept_rate:>6.1f}%    {avg_rounds:>8.2f}   {tps:>8.1f}   {total_time:>8.1f}")

    print(f"{'='*80}")


def save_results(all_results: List[Dict], output_path: str = "experiments/multi_model_results.json"):
    """保存结果"""
    output = {
        "timestamp": datetime.now().isoformat(),
        "experiment_type": "multi_model",
        "results": all_results
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n结果已保存: {output_path}")


if __name__ == "__main__":
    print("="*80)
    print("A2A-BFT 多模型实验")
    print("="*80)

    # 检查GPU
    has_a800 = check_gpu_memory()

    # 确定是否使用真实模型
    use_real = has_a800 and os.getenv("USE_REAL_MODELS", "0") == "1"
    print(f"\n使用真实模型: {use_real}")

    # 运行实验
    results = run_all_experiments(use_real_models=use_real)

    # 打印汇总
    print_summary(results)

    # 保存结果
    save_results(results)
