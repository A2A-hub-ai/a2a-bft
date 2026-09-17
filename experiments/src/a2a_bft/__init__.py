"""
A2A-BFT 包初始化
"""

# 统一数据结构
from .data_structures import (
    Verdict,
    AttackType,
    ExperimentType,
    Proposal,
    Vote,
    ConsensusOutcome,
    ExperimentConfig,
    ExperimentResult,
    SeedResult,
)

# 统一实验配置
from .experiment_configs import (
    ALL_EXPERIMENTS,
    MAIN_EXPERIMENTS,
    COMPARISON_EXPERIMENTS,
    ABALATION_EXPERIMENTS,
    ATTACK_TYPE_EXPERIMENTS,
    SCALABILITY_EXPERIMENTS,
    ROBUSTNESS_EXPERIMENTS,
    get_experiment_by_name,
    get_experiments_by_type,
    generate_experiment_table,
)

# 共识层
from .deepseek_worker import (
    BaseWorker,
    SimulatedWorker,
    DeepSeekWorker,
    ConsensusLayer,
)

# 统一共识层（支持消融实验）
from .consensus_unified import (
    ConsensusLayer as UnifiedConsensusLayer,
    BaselineConsensus,
    run_comparison_experiment,
)

# 基线方法
from .baselines import (
    SimpleMajority,
    WeightedMajority,
    A2ASimSimulation,
    LLMDebateSimulation,
    get_baseline_methods,
    run_comparison_all_methods,
)

# 注意：早期实现（consensus / distributed_worker / langgraph_*）已归档到
# a2a_bft.legacy。它们未参与论文中的任何实验，且曾存在与论文公式不符的阈值实现，
# 因此不再作为本包的公开 API 导出。需要追溯时可用：
#   from a2a_bft.legacy.distributed_worker import DistributedWorker

# 网络模块
from .agent_network import AgentNetwork

__version__ = "1.0.0"
__all__ = [
    # 数据结构
    "Verdict",
    "AttackType",
    "ExperimentType",
    "Proposal",
    "Vote",
    "ConsensusOutcome",
    "ExperimentConfig",
    "ExperimentResult",
    "SeedResult",
    # 实验配置
    "ALL_EXPERIMENTS",
    "MAIN_EXPERIMENTS",
    "COMPARISON_EXPERIMENTS",
    "ABALATION_EXPERIMENTS",
    "ATTACK_TYPE_EXPERIMENTS",
    "SCALABILITY_EXPERIMENTS",
    "ROBUSTNESS_EXPERIMENTS",
    "get_experiment_by_name",
    "get_experiments_by_type",
    "generate_experiment_table",
    # 共识层
    "BaseWorker",
    "SimulatedWorker",
    "DeepSeekWorker",
    "ConsensusLayer",
    # 统一共识层
    "UnifiedConsensusLayer",
    "BaselineConsensus",
    "run_comparison_experiment",
    # 基线方法
    "SimpleMajority",
    "WeightedMajority",
    "A2ASimSimulation",
    "LLMDebateSimulation",
    "get_baseline_methods",
    "run_comparison_all_methods",
    # 网络
    "AgentNetwork",
]
