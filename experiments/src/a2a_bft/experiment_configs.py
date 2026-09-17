"""
A2A-BFT 统一实验配置
包含所有主试验、对比试验、消融实验、攻击类型实验的配置
"""

from typing import List, Dict
from .data_structures import ExperimentConfig


# ==================== 主试验配置 ====================
MAIN_EXPERIMENTS: List[ExperimentConfig] = [
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


# ==================== 对比试验配置 ====================
COMPARISON_EXPERIMENTS: List[Dict] = [
    # A2A-BFT vs 其他方法
    {
        "name": "comparison_n4_f1",
        "configs": [
            ExperimentConfig(name="a2a_bft", n=4, f=1, s=0, attack_type="strategic_reject"),
            ExperimentConfig(name="simple_majority", n=4, f=1, s=0, attack_type="strategic_reject"),
            ExperimentConfig(name="a2a_sim", n=4, f=1, s=0, attack_type="strategic_reject"),
        ]
    },
    {
        "name": "comparison_n5_f1_s1",
        "configs": [
            ExperimentConfig(name="a2a_bft", n=5, f=1, s=1, attack_type="strategic_reject"),
            ExperimentConfig(name="simple_majority", n=5, f=1, s=1, attack_type="strategic_reject"),
        ]
    },
]


# ==================== 消融实验配置 ====================
ABALATION_EXPERIMENTS: List[ExperimentConfig] = [
    # 完整协议作为对照
    ExperimentConfig(
        name="ablation_full_protocol",
        n=5, f=1, s=1,
        attack_type="strategic_reject",
        disabled_components=[]
    ),
    # 禁用声誉机制
    ExperimentConfig(
        name="ablation_no_reputation",
        n=5, f=1, s=1,
        attack_type="strategic_reject",
        disabled_components=["reputation"]
    ),
    # 禁用动态阈值
    ExperimentConfig(
        name="ablation_no_dynamic_threshold",
        n=5, f=1, s=1,
        attack_type="strategic_reject",
        disabled_components=["dynamic_threshold"]
    ),
    # 禁用视图切换
    ExperimentConfig(
        name="ablation_no_view_change",
        n=5, f=1, s=1,
        attack_type="strategic_reject",
        disabled_components=["view_change"]
    ),
]


# ==================== 攻击类型对比配置 ====================
ATTACK_TYPE_EXPERIMENTS: List[ExperimentConfig] = [
    ExperimentConfig(name="attack_random", n=4, f=1, s=0, attack_type="random", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_strategic_reject", n=4, f=1, s=0, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_sybil", n=4, f=1, s=0, attack_type="sybil_attack", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_backdoor", n=4, f=1, s=0, attack_type="backdoor", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_collusion", n=4, f=1, s=0, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="attack_lazy", n=4, f=1, s=0, attack_type="lazy", num_tasks=20, num_seeds=5),
]


# ==================== 规模扩展实验配置 ====================
SCALABILITY_EXPERIMENTS: List[ExperimentConfig] = [
    ExperimentConfig(name="scale_n8_f2", n=8, f=2, s=0, attack_type="strategic_reject", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="scale_n10_f3_s1", n=10, f=3, s=1, attack_type="collusion", num_tasks=20, num_seeds=5),
    ExperimentConfig(name="scale_n12_f3_s1", n=12, f=3, s=1, attack_type="random", num_tasks=20, num_seeds=5),
]


# ==================== 鲁棒性分析配置 ====================
ROBUSTNESS_EXPERIMENTS: List[Dict] = [
    # 准确率敏感性
    {
        "name": "robustness_accuracy",
        "variations": [
            {"accuracy": 0.7, "label": "low_accuracy"},
            {"accuracy": 0.8, "label": "medium_accuracy"},
            {"accuracy": 0.9, "label": "high_accuracy"},
            {"accuracy": 0.95, "label": "very_high_accuracy"},
        ],
        "base_config": {"n": 5, "f": 1, "s": 1, "attack_type": "strategic_reject"}
    },
    # 软故障率敏感性
    {
        "name": "robustness_soft_fault",
        "variations": [
            {"s": 0, "label": "no_soft_fault"},
            {"s": 1, "label": "low_soft_fault"},
            {"s": 2, "label": "medium_soft_fault"},
            {"s": 3, "label": "high_soft_fault"},
        ],
        "base_config": {"n": 7, "f": 1, "attack_type": "strategic_reject"}
    },
]


# ==================== 实验汇总 ====================
ALL_EXPERIMENTS = {
    "main": MAIN_EXPERIMENTS,
    "comparison": COMPARISON_EXPERIMENTS,
    "ablation": ABALATION_EXPERIMENTS,
    "attack": ATTACK_TYPE_EXPERIMENTS,
    "scalability": SCALABILITY_EXPERIMENTS,
    "robustness": ROBUSTNESS_EXPERIMENTS,
}


def get_experiment_by_name(name: str) -> ExperimentConfig:
    """根据名称获取实验配置"""
    for experiment_type, configs in ALL_EXPERIMENTS.items():
        for config in configs:
            if isinstance(config, ExperimentConfig) and config.name == name:
                return config
            elif isinstance(config, dict):
                for sub_config in config.get("configs", []):
                    if sub_config.name == name:
                        return sub_config
    return None


def get_experiments_by_type(experiment_type: str) -> List[ExperimentConfig]:
    """根据实验类型获取所有配置"""
    return ALL_EXPERIMENTS.get(experiment_type, [])


def generate_experiment_table() -> str:
    """生成实验表格描述"""
    table = "| 实验类型 | 配置数 | 说明 |\n|---------|--------|------|\n"
    table += "| 主试验 | {} | 基础性能验证 |n".format(len(MAIN_EXPERIMENTS))
    table += "| 对比试验 | {} | 与基线方法对比 |n".format(len(COMPARISON_EXPERIMENTS))
    table += "| 消融实验 | {} | 组件贡献分析 |n".format(len(ABALATION_EXPERIMENTS))
    table += "| 攻击类型 | {} | 攻击抵抗力测试 |n".format(len(ATTACK_TYPE_EXPERIMENTS))
    table += "| 规模扩展 | {} | 系统扩展性验证 |n".format(len(SCALABILITY_EXPERIMENTS))
    table += "| 鲁棒性 | {}组 | 参数敏感性分析 |n".format(len(ROBUSTNESS_EXPERIMENTS))
    return table


if __name__ == "__main__":
    print("=" * 60)
    print("A2A-BFT 实验配置汇总")
    print("=" * 60)
    print(generate_experiment_table())
    print()

    print("主试验配置:")
    for exp in MAIN_EXPERIMENTS:
        print(f"  - {exp.name}: n={exp.n}, f={exp.f}, s={exp.s}, attack={exp.attack_type}, "
              f"secure={exp.is_secure}")

    print()
    print("消融实验配置:")
    for exp in ABALATION_EXPERIMENTS:
        print(f"  - {exp.name}: disabled={exp.disabled_components}")
