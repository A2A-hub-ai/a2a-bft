"""
A2A-BFT 完整多 Agent 测试床
集成 DeepSeek LLM + A2A 通信 + 代码执行
"""

import sys
import os

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import subprocess
import json
import time
from typing import List, Dict, Tuple, Optional

from a2a_bft.deepseek_worker import DeepSeekWorker, ConsensusLayer, Verdict
from a2a_bft.agent_network import AgentNetwork, AgentNode, MessageType


class CodeExecutionAgent(DeepSeekWorker):
    """支持代码执行的 Worker"""

    CODE_FIX_PROMPT = """
你是一个代码修复专家。请修复以下 Python 代码中的 bug。

## 原始代码
```python
{code}
```

## 测试用例
```python
{test}
```

## 任务
1. 分析代码，找出 bug
2. 修复 bug
3. 确保所有测试通过
4. 输出修复后的完整代码

## 修复后的代码
```python
"""

    def __init__(self, worker_id: int, api_key: str = None, **kwargs):
        super().__init__(worker_id, api_key=api_key, **kwargs)
        self.execution_history = []

    def solve_code_task(self, code: str, test: str, task_id: str = "") -> Tuple[str, float, List[str]]:
        """执行代码修复任务"""
        trace = [
            f"received_task: {task_id}",
            f"code_length: {len(code)}",
            f"test_length: {len(test)}"
        ]

        if self.is_byzantine:
            return self._byzantine_solve(code, trace)

        if not self.client:
            return self._simulate_code_solve(code, trace)

        try:
            # 调用 DeepSeek 修复代码
            prompt = self.CODE_FIX_PROMPT.format(code=code, test=test)

            start_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的 Python 代码修复专家。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2048
            )
            elapsed = time.time() - start_time

            result = response.choices[0].message.content
            trace.append(f"llm_response_length: {len(result)}")
            trace.append(f"inference_time: {elapsed:.2f}s")

            # 执行修复后的代码
            execution_result = self._execute_code(result, test)
            trace.append(f"execution_passed: {execution_result['passed']}")

            if execution_result['passed']:
                confidence = 0.95
                trace.append("verification: passed")
            else:
                confidence = 0.3
                trace.append(f"verification: failed - {execution_result.get('error', 'unknown')}")

            return result, confidence, trace

        except Exception as e:
            trace.append(f"error: {str(e)}")
            return "ERROR", 0.0, trace

    def _execute_code(self, code: str, test: str) -> Dict:
        """执行代码并返回结果"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code + '\n' + test)
            temp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                'passed': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {'passed': False, 'error': 'timeout'}
        except Exception as e:
            return {'passed': False, 'error': str(e)}
        finally:
            os.unlink(temp_path)

    def _simulate_code_solve(self, code: str, trace: List[str]) -> Tuple[str, float, List[str]]:
        """模拟代码修复"""
        trace.append("using_simulated_response")

        if random.random() < self.accuracy:
            return f"# Fixed code\n{code}\n# All tests passed", 0.9, trace
        else:
            return f"# Buggy code (unfixed)\n{code}", 0.3, trace


def run_code_fix_experiment(
    n: int, f: int, s: int,
    api_key: str = None,
    num_tasks: int = 3
):
    """运行代码修复实验"""
    from a2a_bft.deepseek_worker import ConsensusLayer

    consensus = ConsensusLayer(n=n, f=f, s=s, task_type="code")
    workers = []

    byzantine_count = 0
    soft_fault_count = 0

    for i in range(n):
        if byzantine_count < f:
            worker = CodeExecutionAgent(i, api_key=api_key, byzantine_type="random")
            worker.is_byzantine = True
            byzantine_count += 1
        elif soft_fault_count < s:
            worker = CodeExecutionAgent(i, api_key=api_key, accuracy=0.6)
            worker.is_soft_fault = True
            soft_fault_count += 1
        else:
            worker = CodeExecutionAgent(i, api_key=api_key, accuracy=0.9)

        workers.append(worker)

    # 示例代码修复任务（HumanEval 风格）
    tasks = [
        {
            "id": "humaneval_001",
            "code": "def add(x, y):\n    return x - y",  # Bug: 应该是 +
            "test": "assert add(2, 3) == 5"
        },
        {
            "id": "humaneval_002",
            "code": "def factorial(n):\n    if n == 0:\n        return 1\n    return n * factorial(n-1)",  # 正确
            "test": "assert factorial(5) == 120"
        },
        {
            "id": "humaneval_003",
            "code": "def is_palindrome(s):\n    return s == s[::-1]",  # 正确
            "test": "assert is_palindrome('aba') == True"
        }
    ]

    print(f"\n{'='*70}")
    print(f"代码修复实验: n={n}, f={f}, s={s}")
    print(f"任务数: {num_tasks}")
    print(f"{'='*70}")

    results = {
        "accept_count": 0,
        "reject_count": 0,
        "manual_count": 0,
        "convergence_rounds": []
    }

    for i in range(min(num_tasks, len(tasks))):
        task = tasks[i]
        print(f"\n[任务 {i+1}] {task['id']}")
        print(f"原始代码: {task['code'][:50]}...")

        outcome = consensus.run_consensus(workers, task['code'])

        if outcome["decision"] == "ACCEPT":
            results["accept_count"] += 1
            results["convergence_rounds"].append(outcome["round"])
            print(f"  ✅ 接受 (轮次: {outcome['round']})")
        elif outcome["decision"] == "REJECT":
            results["reject_count"] += 1
            results["convergence_rounds"].append(outcome["round"])
            print(f"  ❌ 拒绝 (轮次: {outcome['round']})")
        else:
            results["manual_count"] += 1
            print(f"  ⚠️ 人工审核")

    # 总结
    total = results['accept_count'] + results['reject_count'] + results['manual_count']
    print(f"\n{'='*70}")
    print("实验总结")
    print(f"{'='*70}")
    print(f"Accept: {results['accept_count']} ({results['accept_count']/total*100:.1f}%)")
    print(f"Reject: {results['reject_count']} ({results['reject_count']/total*100:.1f}%)")
    print(f"Manual: {results['manual_count']} ({results['manual_count']/total*100:.1f}%)")

    if results['convergence_rounds']:
        avg = sum(results['convergence_rounds']) / len(results['convergence_rounds'])
        print(f"平均收敛轮次: {avg:.2f}")

    return results


if __name__ == "__main__":
    import random

    print("A2A-BFT 完整多 Agent 测试床")
    print("="*70)

    # 测试模拟模式
    print("\n[测试 1] 模拟模式（无 API Key）")
    run_code_fix_experiment(n=4, f=1, s=0, num_tasks=3)

    # 如果有 API Key，可以取消注释
    # print("\n[测试 2] 真实 DeepSeek API")
    # run_code_fix_experiment(
    #     n=4, f=1, s=0,
    #     api_key="sk-xxx",
    #     num_tasks=3
    # )
