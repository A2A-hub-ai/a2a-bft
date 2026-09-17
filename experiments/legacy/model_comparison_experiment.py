"""
A2A-BFT 多模型对比实验
支持在AutoDL GPU环境运行真实LLM推理实验
"""

import sys
import os
import time
import json
import random
import torch
from datetime import datetime
from typing import List, Dict

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import ConsensusLayer
from a2a_bft.legacy.distributed_worker import (
    DistributedWorker,
    WorkerConfig,
    MultiGPUDistributedSystem
)

# 模型路径配置（原为硬编码 /autodl-fs/data/models，可用环境变量 A2A_MODEL_DIR 覆盖）
A2A_MODELS = os.environ.get("A2A_MODEL_DIR", "/autodl-fs/data/models")
AUTO_DL_MODELS = {
    _name: os.path.join(A2A_MODELS, _name)
    for _name in (
        "DeepSeek-V2-Lite-Chat",
        "InternLM3-8B-Instruct",
        "LLaDA-8B-Instruct",
        "Llama-3.1-8B-Instruct",
        "Qwen2.5-72B-Instruct-AWQ",
    )
}

# 实验配置
EXPERIMENT_CONFIGS = [
    # 基线实验
    {"n": 4, "f": 0, "s": 0, "byzantine_type": None, "label": "Baseline n=4"},
    {"n": 5, "f": 0, "s": 0, "byzantine_type": None, "label": "Baseline n=5"},
    {"n": 6, "f": 0, "s": 0, "byzantine_type": None, "label": "Baseline n=6"},
    # BFT实验
    {"n": 4, "f": 1, "s": 0, "byzantine_type": "strategic_reject", "label": "BFT n=4,f=1"},
    {"n": 5, "f": 1, "s": 1, "byzantine_type": "strategic_reject", "label": "BFT n=5,f=1,s=1"},
    {"n": 5, "f": 2, "s": 0, "byzantine_type": "collusion", "label": "BFT n=5,f=2,collusion"},
    {"n": 6, "f": 2, "s": 0, "byzantine_type": "collusion", "label": "BFT n=6,f=2,collusion"},
]


def load_model(model_name: str, gpu_id: int):
    """加载模型到指定GPU"""
    model_path = AUTO_DL_MODELS.get(model_name)
    if not model_path or not os.path.exists(model_path):
        print(f"  [ERROR] Model {model_name} not found at {model_path}")
        return None

    try:
        # 延迟导入，避免在未配置GPU时出错
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        print(f"  [INFO] Loading {model_name} on GPU {gpu_id}...")
        device = f"cuda:{gpu_id}"

        # 加载tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

        # 加载模型（使用半精度）
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map=f"cuda:{gpu_id}",
            trust_remote_code=True
        )
        model.eval()

        print(f"  [SUCCESS] {model_name} loaded on GPU {gpu_id}")
        return {
            "model": model,
            "tokenizer": tokenizer,
            "gpu_id": gpu_id
        }
    except Exception as e:
        print(f"  [ERROR] Failed to load {model_name}: {e}")
        return None


def generate_response(model_data: Dict, prompt: str, max_tokens: int = 512) -> Dict:
    """生成模型响应"""
    model = model_data["model"]
    tokenizer = model_data["tokenizer"]
    gpu_id = model_data["gpu_id"]

    try:
        inputs = tokenizer(prompt, return_tensors="pt").to(f"cuda:{gpu_id}")

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=0.7,
                top_p=0.9,
                do_sample=True
            )

        # 解码响应
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)

        # 提取关键信息
        confidence = estimate_confidence(response)
        verdict = classify_response(response)

        return {
            "response": response,
            "confidence": confidence,
            "verdict": verdict,
            "model": model_data.get("model_name", "unknown"),
            "gpu_id": gpu_id,
            "success": True
        }
    except Exception as e:
        return {
            "response": f"ERROR: {str(e)}",
            "confidence": 0.1,
            "verdict": "ABSTAIN",
            "model": model_data.get("model_name", "unknown"),
            "gpu_id": gpu_id,
            "success": False
        }


def estimate_confidence(response: str) -> float:
    """估计响应置信度"""
    if not response or len(response) < 10:
        return 0.1

    # 基于响应长度和质量
    length_score = min(len(response) / 500, 1.0)
    has_structure = response.count('\n') > 2
    has_code = '```' in response or 'def ' in response

    confidence = 0.5 + 0.3 * length_score + 0.1 * (1 if has_structure else 0) + 0.1 * (1 if has_code else 0)
    return min(max(confidence, 0.1), 1.0)


def classify_response(response: str) -> str:
    """分类响应"""
    response_lower = response.lower()

    if "error" in response_lower or "无法回答" in response:
        return "ERROR"
    elif "correct" in response_lower or "正确" in response:
        return "ACCEPT"
    elif "reject" in response_lower or "拒绝" in response:
        return "REJECT"
    else:
        return "ABSTAIN"


def run_single_experiment(
    n: int, f: int, s: int,
    byzantine_type: str,
    model_names: List[str],
    num_tasks: int = 20,
    use_real_models: bool = False
) -> Dict:
    """运行单个实验配置"""
    print(f"\n{'='*70}")
    print(f"实验配置: n={n}, f={f}, s={s}, 拜占庭类型={byzantine_type}")
    print(f"使用模型: {', '.join(model_names)}")
    print(f"{'='*70}")

    # 创建共识层
    consensus = ConsensusLayer(n=n, f=f, s=s)

    # 创建workers
    workers = []
    byzantine_count = 0
    soft_fault_count = 0

    for i in range(n):
        # 选择模型
        model_idx = i % len(model_names)
        model_name = model_names[model_idx]

        if byzantine_count < f:
            # 拜占庭节点
            worker = DistributedWorker(
                config=WorkerConfig(
                    worker_id=i,
                    model_name=model_name,
                    gpu_id=i,
                    is_byzantine=True,
                    byzantine_type=byzantine_type or "random",
                    accuracy=0.3
                ),
                use_real_model=use_real_models
            )
            byzantine_count += 1
        elif soft_fault_count < s:
            # 软故障节点
            worker = DistributedWorker(
                config=WorkerConfig(
                    worker_id=i,
                    model_name=model_name,
                    gpu_id=i,
                    is_byzantine=False,
                    accuracy=0.6
                ),
                use_real_model=use_real_models
            )
            soft_fault_count += 1
        else:
            # 诚实节点
            worker = DistributedWorker(
                config=WorkerConfig(
                    worker_id=i,
                    model_name=model_name,
                    gpu_id=i,
                    is_byzantine=False,
                    accuracy=0.9
                ),
                use_real_model=use_real_models
            )
        workers.append(worker)

    # 初始化模型（如果在AutoDL上）
    if use_real_models and torch.cuda.is_available():
        print("\n[INFO] 初始化真实模型...")
        for worker in workers:
            worker.load_model()

    # 运行实验
    results = {
        'accept': 0,
        'reject': 0,
        'manual': 0,
        'error': 0,
        'rounds': [],
        'times': [],
        'task_results': []
    }

    for i in range(num_tasks):
        question = f"test_problem_{i}"
        start_time = time.time()

        try:
            outcome = consensus.run_consensus(workers, question)
            elapsed = time.time() - start_time

            decision = outcome.get('decision', 'ERROR').upper()
            rounds = outcome.get('round', 0)

            if decision == 'ACCEPT':
                results['accept'] += 1
            elif decision == 'REJECT':
                results['reject'] += 1
            elif decision == 'MANUAL':
                results['manual'] += 1
            else:
                results['error'] += 1

            results['rounds'].append(rounds)
            results['times'].append(elapsed)

            status = "✅" if decision == 'ACCEPT' else "❌" if decision == 'REJECT' else "⚠️"
            print(f"  [任务 {i+1}/{num_tasks}] {status} {decision} ({rounds}轮, {elapsed:.2f}s)")

        except Exception as e:
            results['error'] += 1
            print(f"  [任务 {i+1}/{num_tasks}] ❌ ERROR: {e}")

    # 计算统计
    total = results['accept'] + results['reject'] + results['manual'] + results['error']
    results['accept_rate'] = results['accept'] / total * 100 if total > 0 else 0
    results['avg_rounds'] = sum(results['rounds']) / len(results['rounds']) if results['rounds'] else 0
    results['avg_time'] = sum(results['times']) / len(results['times']) if results['times'] else 0

    return results


def run_all_experiments(use_real_models: bool = False):
    """运行所有实验配置"""
    print("="*70)
    print("A2A-BFT 多模型对比实验")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if use_real_models:
        print("模式: 真实LLM推理")
    else:
        print("模式: 模拟推理")
    print("="*70)

    all_results = []

    for config in EXPERIMENT_CONFIGS:
        # 使用所有模型
        model_names = list(AUTO_DL_MODELS.keys())

        # 运行实验
        result = run_single_experiment(
            n=config['n'],
            f=config['f'],
            s=config['s'],
            byzantine_type=config['byzantine_type'],
            model_names=model_names,
            num_tasks=20,
            use_real_models=use_real_models
        )

        config['results'] = result
        all_results.append(config)

        # 打印结果
        print(f"\n{'='*70}")
        print(f"结果: {config['label']}")
        print(f"  接受率: {result['accept_rate']:.1f}%")
        print(f"  平均轮次: {result['avg_rounds']:.2f}")
        print(f"  平均时间: {result['avg_time']:.2f}s")
        print(f"{'='*70}")

    # 保存结果
    output = {
        'timestamp': datetime.now().isoformat(),
        'mode': 'real_model' if use_real_models else 'simulation',
        'experiments': all_results
    }

    output_path = 'experiments/multi_model_results.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n结果保存到: {output_path}")
    return all_results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='A2A-BFT 多模型对比实验')
    parser.add_argument('--real-models', action='store_true', help='使用真实LLM模型')
    parser.add_argument('--num-tasks', type=int, default=20, help='每个实验的任务数')
    parser.add_argument('--model', type=str, default=None, help='指定模型（默认使用所有模型）')

    args = parser.parse_args()

    # 检查GPU
    use_real_models = args.real_models and torch.cuda.is_available()
    if use_real_models:
        print(f"检测到 {torch.cuda.device_count()} 个GPU")
        for i in range(torch.cuda.device_count()):
            print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
    else:
        print("使用模拟模式（无GPU或--real-models未指定）")

    # 运行实验
    run_all_experiments(use_real_models=use_real_models)
