"""
A2A-BFT 统一实验运行器
支持主试验、对比试验、消融实验、攻击类型实验
"""

import sys
import os
import json
import time
import random
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.data_structures import (
    ExperimentConfig, ExperimentResult, SeedResult,
    Verdict, AttackType
)
from a2a_bft.experiment_configs import (
    ALL_EXPERIMENTS, get_experiment_by_name,
    generate_experiment_table
)
from a2a_bft.deepseek_worker import ConsensusLayer, BaseWorker, DeepSeekWorker
from a2a_bft.legacy.distributed_worker import DistributedWorker


class UnifiedExperimentRunner:
    """统一实验运行器"""

    def __init__(self, use_real_models: bool = False, output_dir: str = "experiments/results"):
        self.use_real_models = use_real_models
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results_log: List[Dict] = []

    def run_single_experiment(
        self,
        config: ExperimentConfig,
        seed: Optional[int] = None
    ) -> ExperimentResult:
        """运行单个实验配置"""
        # 设置随机种子
        if seed is not None:
            random.seed(seed)

        print(f"\n{'='*60}")
        print(f"实验: {config.name}")
        print(f"配置: n={config.n}, f={config.f}, s={config.s}")
        print(f"安全条件: n >= 3f+s+1 → {config.n} >= {3*config.f + config.s + 1} = {config.is_secure}")
        print(f"{'='*60}")

        # 创建workers
        workers = self._create_workers(config)

        # 初始化共识层
        consensus = ConsensusLayer(
            n=config.n,
            f=config.f,
            s=config.s,
            use_reputation="reputation" not in config.disabled_components,
            use_dynamic_threshold="dynamic_threshold" not in config.disabled_components,
            use_view_change="view_change" not in config.disabled_components,
        )

        # 运行任务
        accept_count = 0
        reject_count = 0
        manual_count = 0
        error_count = 0
        rounds = []
        times = []

        for i in range(config.num_tasks):
            task_start = time.time()

            # 生成任务
            question = self._generate_task(i, config)

            try:
                outcome = consensus.run_consensus(workers, question)
                task_time = time.time() - task_start

                decision = outcome["decision"].upper()
                if decision == "ACCEPT":
                    accept_count += 1
                elif decision == "REJECT":
                    reject_count += 1
                elif decision == "MANUAL":
                    manual_count += 1
                else:
                    error_count += 1

                rounds.append(outcome.get("round", 0))
                times.append(task_time)

                # 进度显示
                if (i + 1) % 5 == 0:
                    print(f"  进度: {i+1}/{config.num_tasks} ({(i+1)/config.num_tasks*100:.1f}%)")

            except Exception as e:
                error_count += 1
                times.append(time.time() - task_start)
                print(f"  错误: {e}")

        # 计算统计结果
        result = ExperimentResult(
            config=config,
            accept_count=accept_count,
            reject_count=reject_count,
            manual_count=manual_count,
            error_count=error_count,
            rounds=rounds,
            times=times
        )

        print(f"\n结果: 接受率={result.accept_rate:.1f}%, 平均轮次={result.avg_rounds:.2f}")

        return result

    def run_experiment_with_seeds(
        self,
        config: ExperimentConfig,
        num_seeds: int = 5
    ) -> Tuple[ExperimentResult, List[SeedResult]]:
        """运行实验（带多个随机种子）"""
        per_seed_results = []

        for seed in range(num_seeds):
            seed_result = self.run_single_experiment(config, seed=seed)
            per_seed_results.append(SeedResult(
                seed=seed,
                accept_rate=seed_result.accept_rate,
                rounds=seed_result.rounds,
                times=seed_result.times
            ))

        # 计算汇总统计
        accept_rates = [s.accept_rate for s in per_seed_results]
        avg_accept = sum(accept_rates) / len(accept_rates) if accept_rates else 0
        std_accept = (sum((r - avg_accept)**2 for r in accept_rates) / len(accept_rates))**0.5 if len(accept_rates) > 1 else 0

        # 合并所有种子结果
        total_accept = sum(r.accept_count for r in [self._seed_to_result(s, config) for s in per_seed_results])
        total_reject = sum(r.reject_count for r in [self._seed_to_result(s, config) for s in per_seed_results])
        total_tasks = sum(r.total_tasks for r in [self._seed_to_result(s, config) for s in per_seed_results])

        all_rounds = []
        all_times = []
        for s in per_seed_results:
            all_rounds.extend(s.rounds)
            all_times.extend(s.times)

        # 计算95% CI（使用Wilson score interval处理100%情况）
        ci_lower, ci_upper = self._compute_wilson_ci(total_accept, total_tasks)

        result = ExperimentResult(
            config=config,
            accept_count=total_accept,
            reject_count=total_reject,
            manual_count=0,
            error_count=0,
            rounds=all_rounds,
            times=all_times,
            per_seed_results=[s.__dict__ for s in per_seed_results]
        )

        result.std_accept = std_accept
        result.ci_95 = (ci_lower, ci_upper)

        return result, per_seed_results

    def run_all_experiments(self, experiment_type: str = "main") -> List[ExperimentResult]:
        """运行所有指定类型的实验"""
        configs = get_experiments_by_type(experiment_type)

        if not configs:
            print(f"未找到实验类型: {experiment_type}")
            return []

        all_results = []
        print(f"\n{'='*60}")
        print(f"运行实验类型: {experiment_type}")
        print(f"配置数: {len(configs)}")
        print(f"{'='*60}")

        for config in configs:
            if isinstance(config, dict):
                # 对比试验或鲁棒性实验（字典格式）
                for sub_config in config.get("configs", []):
                    result, _ = self.run_experiment_with_seeds(sub_config)
                    all_results.append(result)
            else:
                # 标准实验配置
                result, _ = self.run_experiment_with_seeds(config)
                all_results.append(result)

        return all_results

    def generate_report(
        self,
        results: List[ExperimentResult],
        output_path: Optional[str] = None
    ) -> str:
        """生成实验报告"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"experiment_report_{timestamp}.md"
        else:
            output_path = Path(output_path)

        report_lines = [
            "# A2A-BFT 实验报告",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**实验数量**: {len(results)}",
            "",
            "## 实验结果汇总",
            "",
            "| 实验名称 | 配置 | 接受率 | 平均轮次 | TPS | 95% CI |",
            "|---------|------|--------|---------|-----|--------|",
        ]

        for r in results:
            config = r.config
            ci_lower, ci_upper = r.ci_95 if hasattr(r, 'ci_95') else (0, 0)
            report_lines.append(
                f"| {config.name} | n={config.n},f={config.f},s={config.s} | "
                f"{r.accept_rate:.1f}% ± {r.std_accept:.1f}% | "
                f"{r.avg_rounds:.2f} | {r.avg_tps:.0f} | "
                f"[{ci_lower:.1f}%, {ci_upper:.1f}%] |"
            )

        report_lines.append("")
        report_lines.append("## 详细数据")
        report_lines.append("")
        report_lines.append(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))

        report_content = "\n".join(report_lines)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        print(f"\n报告已保存: {output_path}")
        return report_content

    def save_results(self, results: List[ExperimentResult], filename: str):
        """保存实验结果为JSON"""
        output_path = self.output_dir / filename
        data = {
            "timestamp": datetime.now().isoformat(),
            "experiment_type": filename.replace(".json", ""),
            "results": [r.to_dict() for r in results]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"结果已保存: {output_path}")

    # ==================== 辅助方法 ====================

    def _create_workers(self, config: ExperimentConfig) -> List[BaseWorker]:
        """根据配置创建Workers"""
        workers = []
        api_key = self.api_key or os.getenv("DEEPSEEK_API_KEY", "")

        for i in range(config.n):
            if i < config.f:
                # 拜占庭节点
                worker = DeepSeekWorker(
                    worker_id=i,
                    model="deepseek-chat",
                    api_key=api_key,
                )
                worker.is_byzantine = True
                worker.byzantine_type = config.attack_type
            elif i < config.f + config.s:
                # 软故障节点
                worker = DeepSeekWorker(
                    worker_id=i,
                    model="deepseek-chat",
                    api_key=api_key,
                )
                worker.is_soft_fault = True
            else:
                # 诚实节点
                worker = DeepSeekWorker(
                    worker_id=i,
                    model="deepseek-chat",
                    api_key=api_key,
                )
            workers.append(worker)

        return workers

    def _generate_task(self, task_id: int, config: ExperimentConfig) -> str:
        """生成测试任务"""
        task_types = [
            f"math_problem_{task_id+1}: 计算 1234 + {5678 + task_id} = ?",
            f"code_task_{task_id+1}: 实现一个函数计算斐波那契数列第{n}项",
            f"qa_task_{task_id+1}: 解释区块链共识算法的原理",
        ]
        return random.choice(task_types)

    def _compute_wilson_ci(self, successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
        """计算Wilson score interval"""
        if total == 0:
            return (0.0, 100.0)

        p_hat = successes / total

        # 处理100%接受率情况
        if p_hat == 1.0:
            # Wilson score interval上界为1.0，下界计算
            denominator = 1 + z**2 / total
            center = (p_hat + z**2 / (2 * total)) / denominator
            spread = z * ((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)**0.5 / denominator
            ci_lower = max(0, (center - spread) * 100)
            return (ci_lower, 100.0)

        if p_hat == 0.0:
            denominator = 1 + z**2 / total
            center = (p_hat + z**2 / (2 * total)) / denominator
            spread = z * ((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)**0.5 / denominator
            return (0.0, (center + spread) * 100)

        denominator = 1 + z**2 / total
        center = (p_hat + z**2 / (2 * total)) / denominator
        spread = z * ((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)**0.5 / denominator

        ci_lower = max(0, (center - spread) * 100)
        ci_upper = min(100, (center + spread) * 100)

        return (ci_lower, ci_upper)

    def _seed_to_result(self, seed_result: SeedResult, config: ExperimentConfig) -> ExperimentResult:
        """将SeedResult转换为ExperimentResult"""
        return ExperimentResult(
            config=config,
            accept_count=int(seed_result.accept_rate * config.num_tasks / 100),
            reject_count=config.num_tasks - int(seed_result.accept_rate * config.num_tasks / 100),
            manual_count=0,
            error_count=0,
            rounds=seed_result.rounds,
            times=seed_result.times
        )


def main():
    parser = argparse.ArgumentParser(description="A2A-BFT 统一实验运行器")
    parser.add_argument("--type", choices=["main", "comparison", "ablation", "attack", "scalability", "robustness"],
                        default="main", help="实验类型")
    parser.add_argument("--name", type=str, help="指定实验名称")
    parser.add_argument("--seeds", type=int, default=5, help="随机种子数量")
    parser.add_argument("--tasks", type=int, default=20, help="每个实验的任务数")
    parser.add_argument("--real-models", action="store_true", help="使用真实LLM模型")
    parser.add_argument("--output", type=str, help="输出目录")

    args = parser.parse_args()

    runner = UnifiedExperimentRunner(
        use_real_models=args.real_models,
        output_dir=args.output or "experiments/results"
    )

    if args.name:
        # 运行单个实验
        config = get_experiment_by_name(args.name)
        if config is None:
            print(f"未找到实验: {args.name}")
            return
        config.num_tasks = args.tasks
        config.num_seeds = args.seeds
        result, _ = runner.run_experiment_with_seeds(config)
        runner.save_results([result], f"{args.name}_result.json")
    else:
        # 运行一类实验
        results = runner.run_all_experiments(args.type)
        runner.save_results(results, f"{args.type}_results.json")
        runner.generate_report(results)

    # 打印汇总
    print("\n" + "="*60)
    print("实验完成")
    print("="*60)


if __name__ == "__main__":
    main()
