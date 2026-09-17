"""
A2A-BFT 答案正确率评估实验（区分"共识达成率"与"答案正确率"）
支持三种任务类型：math (GSM8K)、knowledge (MMLU)、code (MBPP)

背景：评审发现原实验只测"共识达成率"，未测"答案正确率"（Validity）。
本脚本运行共识后，从接受的提案中提取答案，与 ground truth 比对，
报告：共识达成率 + 答案正确率（两个独立指标）。

用法：
  python correctness_eval.py --dataset gsm8k --tasks 50 --seeds 3
  python correctness_eval.py --dataset mmlu  --tasks 50 --seeds 3
  python correctness_eval.py --dataset mbpp  --tasks 30 --seeds 2
"""

import sys
import os
import re
import json
import time
import random
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.deepseek_worker import ConsensusLayer, DeepSeekWorker, _extract_choice


API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


# ==================== 任务类型相关的答案提取与比对 ====================

def extract_ground_truth(answer_text: str):
    """从 GSM8K 标准答案中提取最终数字（#### 18 -> 18.0）"""
    m = re.findall(r'####\s*([-+]?\d+(?:[.,]\d+)?)', answer_text)
    if m:
        return float(m[-1].replace(',', ''))
    nums = re.findall(r'[-+]?\d+(?:\.\d+)?', answer_text)
    if nums:
        return float(nums[-1])
    return None


def extract_llm_number(result_text: str):
    """从 LLM 输出中提取最终答案数字"""
    if not result_text:
        return None
    final_part = result_text
    for marker in ['## 最终答案', '最终答案', '答案：', 'Answer:', 'answer:']:
        idx = result_text.find(marker)
        if idx >= 0:
            final_part = result_text[idx + len(marker):]
            break
    nums = re.findall(r'[-+]?\d+(?:\.\d+)?', final_part)
    if nums:
        return float(nums[-1])
    return None


def mmlu_correct_letter(task: dict) -> str:
    """从 MMLU 任务中找出正确选项的字母（answer 是选项内容，需映射到字母）"""
    choices = task.get('choices', [])
    answer = str(task.get('answer', ''))
    for i, c in enumerate(choices):
        if str(c) == answer:
            return chr(ord('A') + i)
    return None


def build_question(task: dict, dataset_type: str) -> str:
    """构造传给 LLM 的问题字符串"""
    if dataset_type == "mmlu":
        q = task.get('question', '')
        choices = task.get('choices', [])
        letters = [chr(ord('A') + i) for i in range(len(choices))]
        opts = '\n'.join(f"{l}. {c}" for l, c in zip(letters, choices))
        return f"{q}\n\n{opts}\n\n请回答正确选项的字母（A/B/C/D）。"
    elif dataset_type == "mbpp":
        # 代码任务：给函数签名和测试用例
        desc = task.get('description', task.get('prompt', ''))
        code = task.get('code', '')
        test = task.get('test_list', [])
        test_str = '\n'.join(test[:2]) if test else ''
        return f"{desc}\n\n参考代码框架：\n{code}\n\n测试用例：\n{test_str}\n\n请完成函数实现，输出完整 Python 代码。"
    else:
        return task.get('question', task.get('problem', ''))


def is_answer_correct(llm_result: str, task: dict, dataset_type: str) -> bool:
    """判断 LLM 答案是否与 ground truth 一致（按任务类型）"""
    if dataset_type == "mmlu":
        # 选择题：提取 LLM 选项字母，与正确字母比对
        correct = mmlu_correct_letter(task)
        llm = _extract_choice(llm_result)
        if correct is None:
            return False
        return llm == correct
    elif dataset_type == "mbpp":
        # 代码任务：运行测试用例验证
        return run_code_tests(llm_result, task.get('test_list', []))
    else:
        # 数学任务：数字比对
        gt = extract_ground_truth(task.get('answer', ''))
        llm = extract_llm_number(llm_result)
        if gt is None or llm is None:
            return False
        return abs(gt - llm) < 1e-6


def run_code_tests(llm_code: str, test_list: list) -> bool:
    """运行测试用例验证代码正确性"""
    if not test_list:
        return False
    # 提取 LLM 输出中的代码（去除 markdown 代码块标记）
    code = llm_code
    m = re.search(r'```python\s*(.*?)```', llm_code, re.DOTALL)
    if m:
        code = m.group(1)
    else:
        m = re.search(r'```\s*(.*?)```', llm_code, re.DOTALL)
        if m:
            code = m.group(1)
    if not code or 'def ' not in code:
        return False

    # 构建完整测试脚本
    test_script = code + "\n\n" + "\n".join(test_list) + "\n"
    try:
        exec_globals = {}
        exec(test_script, exec_globals)
        return True
    except Exception:
        return False


# ==================== 实验运行 ====================

def load_dataset(dataset_type: str):
    data_dir = os.path.join(os.path.dirname(__file__), 'datasets')
    files = {
        "gsm8k": "gsm8k_test.json",
        "mmlu": "mmlu_3subjects.json",
        "mbpp": "mbpp_test.json",
    }
    with open(os.path.join(data_dir, files[dataset_type]), encoding='utf-8') as f:
        return json.load(f)


def run_scenario(n, f, s, attack_type, dataset, dataset_type, num_tasks, num_seeds):
    """运行单个场景，报告共识达成率 + 答案正确率"""
    print(f"\n{'='*70}")
    print(f"场景: n={n}, f={f}, s={s}, attack={attack_type}, dataset={dataset_type}")
    print(f"任务数={num_tasks}, 种子数={num_seeds}")
    print(f"{'='*70}")

    total_consensus_accept = 0
    total_correct = 0
    total_tasks = 0
    total_time = 0.0
    round_list = []

    for seed in range(num_seeds):
        random.seed(seed)
        sampled = random.sample(dataset, min(num_tasks, len(dataset)))

        for i, task in enumerate(sampled):
            question = build_question(task, dataset_type)

            workers = []
            for wid in range(n):
                worker = DeepSeekWorker(worker_id=wid, api_key=API_KEY)
                if wid < f:
                    worker.is_byzantine = True
                    worker.byzantine_type = attack_type
                elif wid < f + s:
                    worker.is_soft_fault = True
                    worker.accuracy = 0.6
                workers.append(worker)

            consensus = ConsensusLayer(n=n, f=f, s=s, task_type=dataset_type)

            t0 = time.time()
            try:
                outcome = consensus.run_consensus(workers, question)
                elapsed = time.time() - t0
                total_time += elapsed
                total_tasks += 1
                round_list.append(outcome.get("round", 0))

                decision = outcome.get("decision", "ERROR")
                if decision == "ACCEPT":
                    total_consensus_accept += 1
                    proposal = outcome.get("proposal")
                    result_text = proposal.result if proposal else ""
                    if is_answer_correct(result_text, task, dataset_type):
                        total_correct += 1

                if (i + 1) % 5 == 0 or (i + 1) == len(sampled):
                    acc = total_consensus_accept / total_tasks * 100
                    corr = total_correct / total_tasks * 100
                    print(f"  [Seed {seed}] [{i+1}/{len(sampled)}] "
                          f"共识达成={acc:.0f}% 答案正确={corr:.0f}%")
            except Exception as e:
                total_tasks += 1
                print(f"  [Seed {seed}] [{i+1}/{len(sampled)}] ERROR: {e}")

    consensus_rate = total_consensus_accept / total_tasks * 100 if total_tasks > 0 else 0
    correctness_rate = total_correct / total_tasks * 100 if total_tasks > 0 else 0

    result = {
        "n": n, "f": f, "s": s, "attack_type": attack_type,
        "total_tasks": total_tasks,
        "consensus_accept": total_consensus_accept,
        "consensus_rate": round(consensus_rate, 1),
        "correct_answers": total_correct,
        "correctness_rate": round(correctness_rate, 1),
        "avg_rounds": round(sum(round_list) / len(round_list), 2) if round_list else 0,
        "total_time_s": round(total_time, 1),
    }
    print(f"\n  => 共识达成率={consensus_rate:.1f}%  答案正确率={correctness_rate:.1f}%")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="gsm8k", choices=["gsm8k", "mmlu", "mbpp"],
                       help="数据集类型")
    parser.add_argument("--tasks", type=int, default=20, help="每种子任务数")
    parser.add_argument("--seeds", type=int, default=2, help="种子数")
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    print(f"数据集 {args.dataset} 大小: {len(dataset)} 题")

    scenarios = [
        (8, 2, 1, "collusion"),
        (8, 2, 1, "strategic_reject"),
        (8, 0, 0, None),  # baseline 无故障
    ]

    results = []
    for n, f, s, attack in scenarios:
        results.append(run_scenario(n, f, s, attack, dataset, args.dataset, args.tasks, args.seeds))

    output = {
        "timestamp": datetime.now().isoformat(),
        "experiment_type": "correctness_eval_deepseek",
        "model": "deepseek-chat",
        "dataset": args.dataset,
        "config": {"tasks_per_seed": args.tasks, "seeds": args.seeds},
        "scenarios": results,
    }
    os.makedirs("experiments/results", exist_ok=True)
    out_path = f"experiments/results/correctness_{args.dataset}_{args.tasks}t_{args.seeds}s.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"答案正确率评估结果汇总 ({args.dataset})")
    print(f"{'='*70}")
    print(f"{'场景':<32} {'共识达成率':>10} {'答案正确率':>10} {'轮数':>6}")
    print("-" * 62)
    for r in results:
        label = f"n={r['n']},f={r['f']},s={r['s']},{r['attack_type'] or 'none'}"
        print(f"{label:<32} {r['consensus_rate']:>8.1f}% {r['correctness_rate']:>8.1f}% {r['avg_rounds']:>6.2f}")
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
