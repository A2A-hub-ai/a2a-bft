"""
A2A-BFT 统一数据结构定义
消除重复定义，提供统一接口
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union
from enum import Enum
import hashlib
import time


class Verdict(Enum):
    """投票结果枚举"""
    ACCEPT = "accept"
    REJECT = "reject"
    ABSTAIN = "abstain"


class AttackType(Enum):
    """拜占庭攻击类型"""
    NONE = None
    RANDOM = "random"
    STRATEGIC_REJECT = "strategic_reject"
    SYBIL_ATTACK = "sybil_attack"
    BACKDOOR = "backdoor"
    COLLUSION = "collusion"
    LAZY = "lazy"
    COMPLIANT = "compliant"


class ExperimentType(Enum):
    """实验类型"""
    MAIN = "main"
    COMPARISON = "comparison"
    ABLATION = "ablation"
    ROBUSTNESS = "robustness"
    ATTACK = "attack"


@dataclass
class Proposal:
    """任务提案"""
    task_id: str
    proposer_id: int
    result: str
    confidence: float
    trace: List[str] = field(default_factory=list)
    signature: str = ""
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """计算提案哈希"""
        content = f"{self.task_id}{self.proposer_id}{self.result}{self.confidence}{self.timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Vote:
    """验证投票"""
    validator_id: int
    proposal_hash: str
    verdict: Verdict
    confidence: float
    evidence: Dict[str, float] = field(default_factory=dict)
    signature: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def effective_weight(self) -> float:
        """计算有效权重"""
        if self.verdict == Verdict.ACCEPT:
            return self.confidence
        elif self.verdict == Verdict.REJECT:
            return -self.confidence
        else:
            return 0.0


@dataclass
class ConsensusOutcome:
    """共识结果"""
    task_id: str
    decision: Verdict
    rounds: int
    votes: List[Vote]
    total_score: float
    accept_threshold: float
    reject_threshold: float
    timestamp: float = field(default_factory=time.time)
    trace: List[str] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        return self.decision == Verdict.ACCEPT

    @property
    def is_rejected(self) -> bool:
        return self.decision == Verdict.REJECT


@dataclass
class ExperimentConfig:
    """实验配置"""
    name: str
    n: int  # 总节点数
    f: int  # 拜占庭节点数
    s: int  # 软故障节点数
    attack_type: Optional[str] = None
    num_tasks: int = 20
    num_seeds: int = 5
    use_real_models: bool = False
    disabled_components: List[str] = field(default_factory=list)
    method: Optional[str] = None  # 方法名称（用于对比实验）

    @property
    def is_secure(self) -> bool:
        """检查配置是否满足安全条件 n >= 3f + s + 1"""
        return self.n >= 3 * self.f + self.s + 1

    @property
    def theta_accept(self) -> float:
        """动态接受阈值"""
        n_validators = self.n - 1  # 排除proposer
        return n_validators - 2 * self.f - self.s

    @property
    def theta_reject(self) -> float:
        """动态拒绝阈值"""
        n_validators = self.n - 1
        return -(n_validators - self.f) * 0.5

    @property
    def label(self) -> str:
        """生成实验标签"""
        if self.attack_type:
            return f"n={self.n},f={self.f},s={self.s},{self.attack_type}"
        return f"n={self.n},f={self.f},s={self.s}"


@dataclass
class ExperimentResult:
    """实验结果"""
    config: ExperimentConfig
    accept_count: int
    reject_count: int
    manual_count: int
    error_count: int
    rounds: List[int]
    times: List[float]
    per_seed_results: List[Dict] = field(default_factory=list)

    @property
    def total_tasks(self) -> int:
        return self.accept_count + self.reject_count + self.manual_count + self.error_count

    @property
    def accept_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.accept_count / self.total_tasks * 100

    @property
    def reject_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.reject_count / self.total_tasks * 100

    @property
    def avg_rounds(self) -> float:
        if not self.rounds:
            return 0.0
        return sum(self.rounds) / len(self.rounds)

    @property
    def avg_time_ms(self) -> float:
        if not self.times:
            return 0.0
        return sum(self.times) / len(self.times) * 1000

    @property
    def avg_tps(self) -> float:
        total_time = sum(self.times)
        if total_time == 0:
            return 0.0
        return self.total_tasks / total_time

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "config": {
                "name": self.config.name,
                "n": self.config.n,
                "f": self.config.f,
                "s": self.config.s,
                "attack_type": self.config.attack_type,
                "is_secure": self.config.is_secure,
            },
            "results": {
                "accept_count": self.accept_count,
                "reject_count": self.reject_count,
                "manual_count": self.manual_count,
                "error_count": self.error_count,
                "total_tasks": self.total_tasks,
                "accept_rate": round(self.accept_rate, 2),
                "reject_rate": round(self.reject_rate, 2),
                "avg_rounds": round(self.avg_rounds, 2),
                "avg_time_ms": round(self.avg_time_ms, 2),
                "avg_tps": round(self.avg_tps, 2),
            },
            "per_seed": self.per_seed_results,
        }


@dataclass
class SeedResult:
    """单个随机种子的结果"""
    seed: int
    accept_rate: float
    rounds: List[int]
    times: List[float]

    @property
    def avg_rounds(self) -> float:
        if not self.rounds:
            return 0.0
        return sum(self.rounds) / len(self.rounds)

    @property
    def avg_time_ms(self) -> float:
        if not self.times:
            return 0.0
        return sum(self.times) / len(self.times) * 1000
