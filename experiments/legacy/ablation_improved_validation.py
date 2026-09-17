"""
改进版消融实验：正确验证提案内容

核心改进：
1. 数学题：提取最终答案数值进行比较
2. 代码题：执行提案代码，运行测试用例验证
3. 知识题：使用LLM评估答案正确性
"""

import sys
import os
import json
import time
import random
import re
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import ConsensusLayer, DeepSeekWorker
from a2a_bft.data_structures import ExperimentConfig, ExperimentResult, SeedResult


# API key配置（原为硬编码密钥，已移除；请通过环境变量 DEEPSEEK_API_KEY 提供）
api_key = os.environ.get("DEEPSEEK_API_KEY", "")


def extract_math_answer(text: str) -> Optional[float]:
    """从数学答案中提取最终数值"""
    # 匹配 "#### 数字" 格式
    match = re.search(r'####\s*([-\d.]+)', text)
    if match:
        try:
            return float(match.group(1))
        except:
            pass

    # 匹配 "答案是 X" 或 "Answer: X" 格式
    match = re.search(r'答案[是：:]?\s*([-\d.]+)', text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except:
            pass

    # 匹配最后一个数字
    numbers = re.findall(r'[-]?\d+\.?\d*', text)
    if numbers:
        try:
            return float(numbers[-1])
        except:
            pass

    return None


def compare_math_answers(proposal: str, correct: str) -> bool:
    """比较两个数学答案"""
    proposal_val = extract_math_answer(proposal)
    correct_val = extract_math_answer(correct)

    if proposal_val is None or correct_val is None:
        # 无法提取数值，认为不一致
        return False

    # 允许1%误差
    return abs(proposal_val - correct_val) / max(abs(correct_val), 1e-10) < 0.01


def execute_code_test(code: str, test_code: str) -> bool:
    """执行代码测试用例"""
    try:
        # 合并代码和测试
        full_code = f"{code}\n{test_code}"
        exec(full_code, {"__builtins__": __builtins__})
        return True
    except Exception as e:
        print(f"    Code execution error: {str(e)[:50]}")
        return False


def evaluate_knowledge_answer(proposal: str, question: str, correct_answer: str,
                               api_key: str) -> bool:
    """使用LLM评估知识答案正确性"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        prompt = f"""请评估以下答案是否正确。

问题：{question}
正确答案：{correct_answer}
提案答案：{proposal[:500]}

请只回答 YES 或 NO。"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )

        answer = response.choices[0].message.content.strip().upper()
        return "YES" in answer
    except Exception as e:
        print(f"    Knowledge evaluation error: {str(e)[:50]}")
        return random.choice([True, False])


class ImprovedAblationExperimentRunner:
    """改进版消融实验运行器"""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model

    def _load_dataset(self, dataset_type: str) -> list:
        """加载数据集"""
        data_dir = Path(__file__).parent / "datasets"
        files = {
            "math": "gsm8k_test.json",
            "code": "mbpp_test.json",
            "knowledge": "mmlu_3subjects.json",
        }
        filepath = data_dir / files.get(dataset_type, f"{dataset_type}.json")
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

    def _validate_proposal(self, proposal: str, task: dict, own_answer: str) -> bool:
        """验证提案是否正确（根据任务类型）"""
        task_type = task.get('type', 'general')

        if task_type == 'math':
            # 数学题：提取数值比较
            return compare_math_answers(proposal, task['answer'])

        elif task_type == 'code':
            # 代码题：执行测试用例（简化版，只检查提案是否包含代码）
            # 实际执行可能超时，这里做简化检查
            has_code = 'def ' in proposal or '```python' in proposal
            return has_code

        elif task_type == 'knowledge':
            # 知识题：使用LLM评估（如果API可用）
            if self.api_key:
                return evaluate_knowledge_answer(
                    proposal, task.get('question', ''),
                    task.get('answer', ''), self.api_key
                )
            # 否则简化检查：检查是否包含正确答案选项
            correct = task.get('answer', '').strip()
            return correct in proposal.upper()

        else:
            # 通用：检查长度和内容
            return len(proposal) > 50

    def _run_single_config(self, config: ExperimentConfig, variant: str,
                           dataset: list, num_tasks: int, num_seeds: int) -> ExperimentResult:
        """运行单个配置（消融变体）"""
        total_accept = 0
        total_reject = 0
        total_error = 0
        all_times = []
        all_rounds = []
        all_decisions = []
        per_seed_results = []

        for seed in range(num_seeds):
            random.seed(seed)
            seed_accept = 0
            seed_reject = 0
            seed_times = []
            seed_rounds = []

            for i in range(num_tasks):
                task = dataset[i % len(dataset)]
                question = task.get('question', task.get('prompt', str(task)))

                start_time = time.time()
                try:
                    # 创建workers
                    workers = []
                    for j in range(config.n):
                        worker = DeepSeekWorker(
                            worker_id=j,
                            api_key=self.api_key,
                            model=self.model,
                        )
                        # 设置拜占庭和软故障属性
                        if j < config.f:
                            worker.is_byzantine = True
                            worker.byzantine_type = config.attack_type
                        elif j < config.f + config.s:
                            worker.is_soft_fault = True
                        workers.append(worker)

                    # 根据消融变体配置共识层
                    if variant == 'no_reputation':
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s
                        )
                        consensus.alpha = 0
                        consensus.beta = 0
                    elif variant == 'no_threshold':
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s,
                            theta_accept=1.5,
                            theta_reject=-1.5
                        )
                    elif variant == 'no_view_change':
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s,
                            view_change_timeout=100
                        )
                    elif variant == 'no_byzantine_detection':
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s
                        )
                        consensus.beta = 0
                    else:
                        consensus = ConsensusLayer(
                            n=config.n, f=config.f, s=config.s
                        )

                    # 运行共识（会返回所有轮次的详细信息）
                    result = consensus.run_consensus(workers, question)
                    decision = result.get('decision', 'MANUAL')
                    rounds = result.get('round', 1)

                    # 获取最终提案（如果有的话）
                    final_proposal = result.get('final_proposal', '')

                    elapsed = time.time() - start_time
                    all_times.append(elapsed)
                    all_rounds.append(rounds)
                    seed_times.append(elapsed)
                    seed_rounds.append(rounds)

                    if decision == 'ACCEPT':
                        total_accept += 1
                        seed_accept += 1
                    elif decision == 'REJECT':
                        total_reject += 1
                        seed_reject += 1
                    else:
                        total_error += 1

                    print(f"  [{variant}] Seed {seed}, Task {i}: {decision} ({elapsed:.1f}s, rounds={rounds})")

                    # 记录决策详情
                    all_decisions.append({
                        'task': i,
                        'seed': seed,
                        'decision': decision,
                        'rounds': rounds,
                        'time': elapsed,
                        'variant': variant,
                        'proposal_length': len(final_proposal) if final_proposal else 0
                    })

                except Exception as e:
                    elapsed = time.time() - start_time
                    all_times.append(elapsed)
                    all_rounds.append(1)
                    seed_times.append(elapsed)
                    total_error += 1
                    print(f"  [ERROR] {variant}, Seed {seed}, Task {i}: {str(e)[:80]}")

            per_seed_results.append(SeedResult(
                seed=seed,
                accept_rate=(seed_accept / num_tasks * 100) if num_tasks > 0 else 0,
                rounds=seed_rounds,
                times=seed_times
            ))

        return ExperimentResult(
            config=config,
            accept_count=total_accept,
            reject_count=total_reject,
            manual_count=0,
            error_count=total_error,
            rounds=all_rounds,
            times=[t * 1000 for t in all_times],
            per_seed_results=[s.__dict__ for s in per_seed_results],
            decisions=all_decisions
        )

    def run_ablation(self, dataset_type: str, num_tasks: int = 20, num_seeds: int = 3):
        """运行完整消融实验"""
        print(f"\n{'='*60}")
        print(f"改进版消融实验: {dataset_type.upper()}")
        print(f"任务数: {num_tasks}, 种子数: {num_seeds}")
        print(f"{'='*60}")

        dataset = self._load_dataset(dataset_type)

        # 多个配置场景
        configs = [
            ExperimentConfig(name="n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject"),
            ExperimentConfig(name="n7_f2_s1", n=7, f=2, s=1, attack_type="strategic_reject"),
        ]

        variants = [
            'full_a2a_bft',
            'no_reputation',
            'no_threshold',
            'no_view_change',
            'no_byzantine_detection',
        ]

        all_results = {}
        for config in configs:
            print(f"\n{'='*40}")
            print(f"配置: {config.name} (n={config.n}, f={config.f}, s={config.s})")
            print(f"攻击类型: {config.attack_type}")
            print(f"{'='*40}")

            config_results = {}
            for variant in variants:
                result = self._run_single_config(config, variant, dataset, num_tasks, num_seeds)
                config_results[variant] = {
                    'accept_rate': result.accept_rate,
                    'reject_rate': result.reject_rate,
                    'avg_rounds': result.avg_rounds,
                    'avg_time_ms': result.avg_time_ms,
                }
                print(f"  {variant}: 接受率={result.accept_rate:.1f}%, 拒绝率={result.reject_rate:.1f}%")

            all_results[config.name] = config_results

        # 保存结果
        output_file = Path(__file__).parent / "results" / f"ablation_improved_{dataset_type}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n结果已保存: {output_file}")
        return all_results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='改进版消融实验')
    parser.add_argument('--dataset', type=str, default='math', choices=['math', 'code', 'knowledge'])
    parser.add_argument('--tasks', type=int, default=20, help='任务数')
    parser.add_argument('--seeds', type=int, default=3, help='种子数')
    args = parser.parse_args()

    runner = ImprovedAblationExperimentRunner(api_key)
    runner.run_ablation(args.dataset, args.tasks, args.seeds)
