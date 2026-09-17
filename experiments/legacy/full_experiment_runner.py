"""
A2A-BFT 完整实验运行器
整合所有实验类型：主试验、对比试验、消融实验、攻击类型、规模扩展、鲁棒性分析
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
from dataclasses import dataclass, field
from enum import Enum

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

# 导入统一数据结构
from a2a_bft.data_structures import (
    ExperimentConfig, ExperimentResult, SeedResult,
    Verdict, AttackType
)
from a2a_bft.deepseek_worker import ConsensusLayer, BaseWorker, DeepSeekWorker
from a2a_bft.baselines import (
    SimpleMajority, WeightedMajority,
    A2ASimSimulation, LLMDebateSimulation,
    get_baseline_methods, run_comparison_all_methods
)


# ==================== 实验配置 ====================

class ExperimentType(Enum):
    MAIN = "main"
    COMPARISON = "comparison"
    ABLATION = "ablation"
    ATTACK = "attack"
    SCALABILITY = "scalability"
    ROBUSTNESS = "robustness"


# 主试验配置
MAIN_EXPERIMENTS = [
    # Baseline配置
    ExperimentConfig(name="baseline_n4", n=4, f=0, s=0, num_tasks=20, num_seeds=5),
    ExperimentConfig(name="baseline_n5", n=5, f=0, s=0, num_tasks=20, num_seeds=5),
    ExperimentConfig(name="baseline_n6", n=6, f=0, s=0, num_tasks=20, num_seeds=5),
    # BFT攻击配置
    ExperimentConfig(name="bft_n4_f1_strategic", n=4, f=1, s=0, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="bft_n5_f1_s1_strategic", n=5, f=1, s=1, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="bft_n5_f2_collusion", n=5, f=2, s=0, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="bft_n6_f2_collusion", n=6, f=2, s=0, attack_type="collusion", num_tasks=20, num_seeds=5),
]

# 对比试验配置
COMPARISON_EXPERIMENTS = [
    {
        "name": "comparison_n4_f1",
        "description": "n=4, f=1, strategic_reject攻击对比",
        "configs": [
            ExperimentConfig(name="a2a_bft_n4_f1", n=4, f=1, s=0, attack_type="strategic_reject", method="a2a_bft"),
            ExperimentConfig(name="simple_majority_n4_f1", n=4, f=1, s=0, attack_type="strategic_reject", method="simple_majority"),
            ExperimentConfig(name="weighted_majority_n4_f1", n=4, f=1, s=0, attack_type="strategic_reject", method="weighted_majority"),
            ExperimentConfig(name="a2a_sim_n4_f1", n=4, f=1, s=0, attack_type="strategic_reject", method="a2a_sim"),
            ExperimentConfig(name="llm_debate_n4_f1", n=4, f=1, s=0, attack_type="strategic_reject", method="llm_debate"),
        ]
    },
    {
        "name": "comparison_n5_f1_s1",
        "description": "n=5, f=1, s=1, strategic_reject攻击对比",
        "configs": [
            ExperimentConfig(name="a2a_bft_n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject", method="a2a_bft"),
            ExperimentConfig(name="simple_majority_n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject", method="simple_majority"),
            ExperimentConfig(name="weighted_majority_n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject", method="weighted_majority"),
            ExperimentConfig(name="a2a_sim_n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject", method="a2a_sim"),
        ]
    },
    {
        "name": "comparison_n7_f2",
        "description": "n=7, f=2, collusion攻击对比（增强强度）",
        "configs": [
            ExperimentConfig(name="a2a_bft_n7_f2", n=7, f=2, s=0, attack_type="collusion", method="a2a_bft"),
            ExperimentConfig(name="simple_majority_n7_f2", n=7, f=2, s=0, attack_type="collusion", method="simple_majority"),
            ExperimentConfig(name="weighted_majority_n7_f2", n=7, f=2, s=0, attack_type="collusion", method="weighted_majority"),
        ]
    },
]

# 消融实验配置
ABALATION_EXPERIMENTS = [
    ExperimentConfig(name="full_protocol", n=5, f=1, s=1, attack_type="strategic_reject", disabled_components=[]),
    ExperimentConfig(name="no_reputation", n=5, f=1, s=1, attack_type="strategic_reject", disabled_components=["reputation"]),
    ExperimentConfig(name="no_dynamic_threshold", n=5, f=1, s=1, attack_type="strategic_reject", disabled_components=["dynamic_threshold"]),
    ExperimentConfig(name="no_view_change", n=5, f=1, s=1, attack_type="strategic_reject", disabled_components=["view_change"]),
]

# 攻击类型实验配置
ATTACK_TYPE_EXPERIMENTS = [
    ExperimentConfig(name="attack_random", n=4, f=1, s=0, attack_type="random", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_strategic_reject", n=4, f=1, s=0, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_sybil", n=4, f=1, s=0, attack_type="sybil_attack", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_backdoor", n=4, f=1, s=0, attack_type="backdoor", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_collusion", n=4, f=1, s=0, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_lazy", n=4, f=1, s=0, attack_type="lazy", num_tasks=20, num_seeds=5),
]

# 规模扩展实验配置
SCALABILITY_EXPERIMENTS = [
    ExperimentConfig(name="scale_n8_f2", n=8, f=2, s=0, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="scale_n10_f3_s1", n=10, f=3, s=1, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="scale_n12_f3_s1", n=12, f=3, s=1, attack_type="random", num_tasks=20, num_seeds=5),
]


# ==================== 实验运行器 ====================

class UnifiedExperimentRunner:
    """统一实验运行器"""

    def __init__(self, output_dir: str = "experiments/results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results_log: List[Dict] = []

    def run_experiment(
        self,
        config: ExperimentConfig,
        num_seeds: int = 5,
        use_real_models: bool = False
    ) -> Tuple[ExperimentResult, List[SeedResult]]:
        """运行单个实验配置（带多个随机种子）"""
        per_seed_results = []

        print(f"\n{'='*60}")
        print(f"实验: {config.name}")
        print(f"配置: n={config.n}, f={config.f}, s={config.s}")
        print(f"攻击: {config.attack_type}")
        print(f"安全条件: n >= 3f+s+1 = {3*config.f + config.s + 1}, 当前n={config.n}, 满足={config.n >= 3*config.f + config.s + 1}")
        print(f"{'='*60}")

        for seed in range(num_seeds):
            seed_result = self._run_single_seed(config, seed, use_real_models)
            per_seed_results.append(seed_result)

            print(f"  Seed {seed}: 接受率={seed_result.accept_rate:.1f}%, 平均轮次={seed_result.avg_rounds:.2f}")

        # 计算汇总统计
        accept_rates = [s.accept_rate for s in per_seed_results]
        avg_accept = sum(accept_rates) / len(accept_rates) if accept_rates else 0
        std_accept = (sum((r - avg_accept)**2 for r in accept_rates) / len(accept_rates))**0.5 if len(accept_rates) > 1 else 0

        # 合并所有种子结果
        total_accept = sum(s.accept_rate * config.num_tasks / 100 for s in per_seed_results)
        total_tasks = num_seeds * config.num_tasks

        all_rounds = []
        all_times = []
        for s in per_seed_results:
            all_rounds.extend(s.rounds)
            all_times.extend(s.times)

        # 计算95% CI
        ci_lower, ci_upper = self._compute_wilson_ci(int(total_accept), total_tasks)

        # 创建汇总结果
        result = ExperimentResult(
            config=config,
            accept_count=int(total_accept),
            reject_count=total_tasks - int(total_accept),
            manual_count=0,
            error_count=0,
            rounds=all_rounds,
            times=all_times,
            per_seed_results=[s.__dict__ for s in per_seed_results]
        )

        # 添加统计信息
        result.std_accept = std_accept
        result.ci_95 = (ci_lower, ci_upper)
        result.avg_accept_rate = avg_accept

        print(f"\n汇总结果: 接受率={avg_accept:.1f}% ± {std_accept:.1f}%, 95% CI=[{ci_lower:.1f}%, {ci_upper:.1f}%]")

        return result, per_seed_results

    def _run_single_seed(
        self,
        config: ExperimentConfig,
        seed: int,
        use_real_models: bool = False
    ) -> SeedResult:
        """运行单个随机种子的实验"""
        random.seed(seed)

        # 创建workers
        workers = self._create_workers(config)

        # 初始化共识层
        consensus = ConsensusLayer(
            n=config.n,
            f=config.f,
            s=config.s,
            # 消融实验参数（通过disabled_components控制）
            use_reputation="reputation" not in config.disabled_components,
            use_dynamic_threshold="dynamic_threshold" not in config.disabled_components,
            use_view_change="view_change" not in config.disabled_components,
            theta_accept=None,  # 使用动态阈值
            theta_reject=None,
        )

        # 运行任务
        accept_count = 0
        rounds = []
        times = []

        for i in range(config.num_tasks):
            task_start = time.time()

            # 生成任务
            question = self._generate_task(i, config)

            try:
                outcome = consensus.run_consensus(workers, question)
                task_time = time.time() - task_start

                if outcome["decision"] == "ACCEPT":
                    accept_count += 1

                rounds.append(outcome.get("round", 0))
                times.append(task_time)

            except Exception as e:
                times.append(time.time() - task_start)
                print(f"  错误: {e}")

        accept_rate = accept_count / config.num_tasks * 100 if config.num_tasks > 0 else 0

        return SeedResult(
            seed=seed,
            accept_rate=accept_rate,
            rounds=rounds,
            times=times
        )

    def _create_workers(self, config: ExperimentConfig, api_key: str = None) -> List[BaseWorker]:
        """根据配置创建Workers（使用真实DeepSeek LLM）"""
        workers = []
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")

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
            f"code_task_{task_id+1}: 实现一个函数计算斐波那契数列第{task_id+1}项",
            f"qa_task_{task_id+1}: 解释区块链共识算法的原理",
        ]
        return random.choice(task_types)

    def _compute_wilson_ci(self, successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
        """计算Wilson score interval"""
        if total == 0:
            return (0.0, 100.0)

        p_hat = successes / total

        # 处理边界情况
        if p_hat == 1.0:
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

    def run_all_experiments(self, experiment_type: str = "main") -> List[ExperimentResult]:
        """运行所有指定类型的实验"""
        if experiment_type == "main":
            configs = MAIN_EXPERIMENTS
        elif experiment_type == "comparison":
            # 对比试验：运行A2A-BFT和所有基线方法
            return self._run_comparison_experiments()
        elif experiment_type == "ablation":
            configs = ABALATION_EXPERIMENTS
        elif experiment_type == "attack":
            configs = ATTACK_TYPE_EXPERIMENTS
        elif experiment_type == "scalability":
            configs = SCALABILITY_EXPERIMENTS
        else:
            print(f"未知实验类型: {experiment_type}")
            return []

        all_results = []
        print(f"\n{'='*60}")
        print(f"运行实验类型: {experiment_type}")
        print(f"配置数: {len(configs)}")
        print(f"{'='*60}")

        for config in configs:
            result, _ = self.run_experiment(config)
            all_results.append(result)

        return all_results

    def _run_comparison_experiments(self) -> List[ExperimentResult]:
        """运行对比试验：A2A-BFT vs 基线方法"""
        all_results = []

        print(f"\n{'='*60}")
        print(f"运行对比试验")
        print(f"{'='*60}")

        for comp in COMPARISON_EXPERIMENTS:
            print(f"\n【对比组: {comp['description']}】")

            # 运行A2A-BFT
            a2a_bft_config = next((c for c in comp['configs'] if c.method == "a2a_bft"), None)
            if a2a_bft_config:
                print(f"\n  运行 A2A-BFT...")
                a2a_result, _ = self.run_experiment(a2a_bft_config)
                all_results.append(a2a_result)

            # 运行基线方法
            for config in comp['configs']:
                if config.method == "a2a_bft":
                    continue  # 已运行

                print(f"\n  运行 {config.method}...")
                baseline_result = self._run_baseline_experiment(config)
                all_results.append(baseline_result)

        return all_results

    def _run_baseline_experiment(self, config: ExperimentConfig) -> ExperimentResult:
        """运行基线方法实验"""
        from a2a_bft.baselines import get_baseline_methods

        # 获取基线方法
        method_name = config.method
        methods = get_baseline_methods([method_name])
        if not methods:
            raise ValueError(f"未知方法: {method_name}")
        baseline = methods[0]

        per_seed_results = []

        print(f"\n{'='*60}")
        print(f"对比试验: {config.name} ({method_name})")
        print(f"配置: n={config.n}, f={config.f}, s={config.s}")
        print(f"攻击: {config.attack_type}")
        print(f"{'='*60}")

        for seed in range(5):
            random.seed(seed)
            workers = self._create_workers(config)

            accept_count = 0
            rounds = []
            times = []

            for i in range(config.num_tasks):
                task_start = time.time()
                question = self._generate_task(i, config)

                try:
                    outcome = baseline.consensus(workers, question)
                    task_time = time.time() - task_start

                    if outcome["decision"] == "ACCEPT":
                        accept_count += 1

                    rounds.append(1)  # 基线方法单轮
                    times.append(task_time)

                except Exception as e:
                    times.append(time.time() - task_start)
                    print(f"  错误: {e}")

            accept_rate = accept_count / config.num_tasks * 100 if config.num_tasks > 0 else 0
            per_seed_results.append(SeedResult(
                seed=seed,
                accept_rate=accept_rate,
                rounds=rounds,
                times=times
            ))
            print(f"  Seed {seed}: 接受率={accept_rate:.1f}%")

        # 计算汇总
        accept_rates = [s.accept_rate for s in per_seed_results]
        avg_accept = sum(accept_rates) / len(accept_rates) if accept_rates else 0
        std_accept = (sum((r - avg_accept)**2 for r in accept_rates) / len(accept_rates))**0.5 if len(accept_rates) > 1 else 0

        total_accept = sum(s.accept_rate * config.num_tasks / 100 for s in per_seed_results)
        total_tasks = 5 * config.num_tasks

        all_rounds = []
        all_times = []
        for s in per_seed_results:
            all_rounds.extend(s.rounds)
            all_times.extend(s.times)

        ci_lower, ci_upper = self._compute_wilson_ci(int(total_accept), total_tasks)

        result = ExperimentResult(
            config=config,
            accept_count=int(total_accept),
            reject_count=total_tasks - int(total_accept),
            manual_count=0,
            error_count=0,
            rounds=all_rounds,
            times=all_times,
            per_seed_results=[s.__dict__ for s in per_seed_results]
        )

        result.std_accept = std_accept
        result.ci_95 = (ci_lower, ci_upper)
        result.avg_accept_rate = avg_accept

        print(f"\n汇总: {config.method} 接受率={avg_accept:.1f}% ± {std_accept:.1f}%, 95% CI=[{ci_lower:.1f}%, {ci_upper:.1f}%]")

        return result

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

        print(f"\n结果已保存: {output_path}")
        return output_path

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
            "| 实验名称 | 配置 | 安全 | 接受率 | 平均轮次 | TPS | 95% CI |",
            "|---------|------|------|--------|---------|-----|--------|",
        ]

        for r in results:
            config = r.config
            ci_lower, ci_upper = r.ci_95 if hasattr(r, 'ci_95') else (0, 0)
            avg_accept = r.avg_accept_rate if hasattr(r, 'avg_accept_rate') else r.accept_rate
            std_accept = r.std_accept if hasattr(r, 'std_accept') else 0
            report_lines.append(
                f"| {config.name} | n={config.n},f={config.f},s={config.s} | "
                f"{'✅' if config.is_secure else '⚠️'} | "
                f"{avg_accept:.1f}% ± {std_accept:.1f}% | "
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


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description="A2A-BFT 统一实验运行器")
    parser.add_argument("--type", choices=["main", "comparison", "ablation", "attack", "scalability"],
                        default="main", help="实验类型")
    parser.add_argument("--name", type=str, help="指定实验名称")
    parser.add_argument("--seeds", type=int, default=5, help="随机种子数量")
    parser.add_argument("--tasks", type=int, default=20, help="每个实验的任务数")
    parser.add_argument("--output", type=str, default="experiments/results", help="输出目录")
    parser.add_argument("--report", action="store_true", help="生成Markdown报告")

    args = parser.parse_args()

    runner = UnifiedExperimentRunner(output_dir=args.output)

    if args.name:
        # 运行单个实验
        all_configs = MAIN_EXPERIMENTS + ABALATION_EXPERIMENTS + ATTACK_TYPE_EXPERIMENTS
        config = next((c for c in all_configs if c.name == args.name), None)
        if config is None:
            print(f"未找到实验: {args.name}")
            print("可用实验:")
            for c in all_configs:
                print(f"  - {c.name}")
            return
        config.num_tasks = args.tasks
        config.num_seeds = args.seeds
        result, _ = runner.run_experiment(config)
        runner.save_results([result], f"{args.name}_result.json")
    else:
        # 运行一类实验
        results = runner.run_all_experiments(args.type)
        filename = f"{args.type}_results.json"
        runner.save_results(results, filename)

        if args.report:
            runner.generate_report(results)

    # 打印汇总
    print("\n" + "="*60)
    print("实验完成")
    print("="*60)


if __name__ == "__main__":
    main()
