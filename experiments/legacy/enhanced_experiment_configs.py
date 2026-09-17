"""
A2A-BFT 增强版实验配置
包含更强的攻击场景和完整的对比试验
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from a2a_bft.data_structures import ExperimentConfig

# ==================== 主试验配置（增强版） ====================
MAIN_EXPERIMENTS = [
    # Baseline配置
    ExperimentConfig(name="baseline_n4", n=4, f=0, s=0, num_tasks=20, num_seeds=5),
    ExperimentConfig(name="baseline_n5", n=5, f=0, s=0, num_tasks=20, num_seeds=5),
    ExperimentConfig(name="baseline_n6", n=6, f=0, s=0, num_tasks=20, num_seeds=5),

    # BFT攻击配置（标准强度）
    ExperimentConfig(name="bft_n4_f1_strategic", n=4, f=1, s=0, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="bft_n5_f1_s1_strategic", n=5, f=1, s=1, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="bft_n5_f2_collusion", n=5, f=2, s=0, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="bft_n6_f2_collusion", n=6, f=2, s=0, attack_type="collusion", num_tasks=20, num_seeds=5),

    # BFT攻击配置（增强强度）
    ExperimentConfig(name="bft_n7_f2_s1_strategic", n=7, f=2, s=1, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="bft_n10_f3_s1_collusion", n=10, f=3, s=1, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="bft_n7_f2_collusion", n=7, f=2, s=0, attack_type="collusion", num_tasks=20, num_seeds=5),
]

# ==================== 对比试验配置 ====================
COMPARISON_EXPERIMENTS = [
    {
        "name": "comparison_n4_f1_strategic",
        "description": "n=4, f=1, strategic_reject攻击对比",
        "configs": [
            ExperimentConfig(name="a2a_bft", n=4, f=1, s=0, attack_type="strategic_reject", method="a2a_bft"),
            ExperimentConfig(name="simple_majority", n=4, f=1, s=0, attack_type="strategic_reject", method="simple_majority"),
            ExperimentConfig(name="weighted_majority", n=4, f=1, s=0, attack_type="strategic_reject", method="weighted_majority"),
            ExperimentConfig(name="a2a_sim", n=4, f=1, s=0, attack_type="strategic_reject", method="a2a_sim"),
            ExperimentConfig(name="llm_debate", n=4, f=1, s=0, attack_type="strategic_reject", method="llm_debate"),
        ]
    },
    {
        "name": "comparison_n5_f1_s1_strategic",
        "description": "n=5, f=1, s=1, strategic_reject攻击对比",
        "configs": [
            ExperimentConfig(name="a2a_bft", n=5, f=1, s=1, attack_type="strategic_reject", method="a2a_bft"),
            ExperimentConfig(name="simple_majority", n=5, f=1, s=1, attack_type="strategic_reject", method="simple_majority"),
            ExperimentConfig(name="weighted_majority", n=5, f=1, s=1, attack_type="strategic_reject", method="weighted_majority"),
            ExperimentConfig(name="a2a_sim", n=5, f=1, s=1, attack_type="strategic_reject", method="a2a_sim"),
        ]
    },
    {
        "name": "comparison_n7_f2_collusion",
        "description": "n=7, f=2, collusion攻击对比（增强强度）",
        "configs": [
            ExperimentConfig(name="a2a_bft", n=7, f=2, s=0, attack_type="collusion", method="a2a_bft"),
            ExperimentConfig(name="simple_majority", n=7, f=2, s=0, attack_type="collusion", method="simple_majority"),
            ExperimentConfig(name="weighted_majority", n=7, f=2, s=0, attack_type="collusion", method="weighted_majority"),
        ]
    },
]

# ==================== 消融实验配置（增强版） ====================
ABALATION_EXPERIMENTS = [
    # 标准强度配置
    ExperimentConfig(name="ablation_full_n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject", disabled_components=[], method="a2a_bft"),
    ExperimentConfig(name="ablation_no_rep_n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject", disabled_components=["reputation"], method="a2a_bft"),
    ExperimentConfig(name="ablation_no_dyn_threshold_n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject", disabled_components=["dynamic_threshold"], method="a2a_bft"),
    ExperimentConfig(name="ablation_no_view_change_n5_f1_s1", n=5, f=1, s=1, attack_type="strategic_reject", disabled_components=["view_change"], method="a2a_bft"),

    # 增强强度配置（n=7, f=2, s=1）
    ExperimentConfig(name="ablation_full_n7_f2_s1", n=7, f=2, s=1, attack_type="strategic_reject", disabled_components=[], method="a2a_bft"),
    ExperimentConfig(name="ablation_no_rep_n7_f2_s1", n=7, f=2, s=1, attack_type="strategic_reject", disabled_components=["reputation"], method="a2a_bft"),
    ExperimentConfig(name="ablation_no_dyn_threshold_n7_f2_s1", n=7, f=2, s=1, attack_type="strategic_reject", disabled_components=["dynamic_threshold"], method="a2a_bft"),
    ExperimentConfig(name="ablation_no_view_change_n7_f2_s1", n=7, f=2, s=1, attack_type="strategic_reject", disabled_components=["view_change"], method="a2a_bft"),
]

# ==================== 攻击类型实验配置（增强版） ====================
ATTACK_TYPE_EXPERIMENTS = [
    # 标准强度（n=4, f=1, s=0）
    ExperimentConfig(name="attack_random_n4", n=4, f=1, s=0, attack_type="random", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_strategic_reject_n4", n=4, f=1, s=0, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_sybil_n4", n=4, f=1, s=0, attack_type="sybil_attack", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_backdoor_n4", n=4, f=1, s=0, attack_type="backdoor", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_collusion_n4", n=4, f=1, s=0, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_lazy_n4", n=4, f=1, s=0, attack_type="lazy", num_tasks=20, num_seeds=5),

    # 增强强度（n=7, f=2, s=1）
    ExperimentConfig(name="attack_strategic_reject_n7_f2_s1", n=7, f=2, s=1, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_collusion_n7_f2_s1", n=7, f=2, s=1, attack_type="collusion", num_tasks=20, num_seeds=5),
]

# ==================== 规模扩展实验配置 ====================
SCALABILITY_EXPERIMENTS = [
    ExperimentConfig(name="scale_n8_f2", n=8, f=2, s=0, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="scale_n10_f3_s1", n=10, f=3, s=1, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="scale_n12_f3_s1", n=12, f=3, s=1, attack_type="random", num_tasks=20, num_seeds=5),
]

# ==================== 汇总所有实验 ====================
ALL_EXPERIMENTS = {
    "main": MAIN_EXPERIMENTS,
    "comparison": COMPARISON_EXPERIMENTS,
    "ablation": ABALATION_EXPERIMENTS,
    "attack": ATTACK_TYPE_EXPERIMENTS,
    "scalability": SCALABILITY_EXPERIMENTS,
}


def print_experiment_summary():
    """打印实验汇总"""
    print("="*80)
    print("A2A-BFT 增强版实验配置汇总")
    print("="*80)

    print("\n【主试验】")
    for exp in MAIN_EXPERIMENTS:
        print(f"  - {exp.name:<35} n={exp.n} f={exp.f} s={exp.s} attack={exp.attack_type:<20} secure={exp.is_secure}")

    print("\n【对比试验】")
    for comp in COMPARISON_EXPERIMENTS:
        print(f"\n  {comp['description']}")
        for cfg in comp['configs']:
            print(f"    - {cfg.name}")

    print("\n【消融试验】")
    for exp in ABALATION_EXPERIMENTS:
        disabled = ",".join(exp.disabled_components) if exp.disabled_components else "none"
        print(f"  - {exp.name:<40} disabled={disabled}")

    print("\n【攻击类型试验】")
    for exp in ATTACK_TYPE_EXPERIMENTS:
        print(f"  - {exp.name:<35} n={exp.n} f={exp.f} s={exp.s} attack={exp.attack_type}")


if __name__ == "__main__":
    print_experiment_summary()
