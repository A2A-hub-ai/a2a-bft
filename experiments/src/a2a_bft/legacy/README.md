# legacy —— 早期实现（归档，不参与论文实验）

本目录存放 A2A-BFT 项目早期迭代中产生、但**未参与论文任何实验**的实现。
保留它们是为了可追溯（审稿人或后续维护者可能想核对演化过程），但**不应作为协议的参考实现使用**。

## 归档原因

| 模块 | 状态 | 归档原因 |
|---|---|---|
| `consensus.py` | **完全未被引用** | 全仓库无任何 import。早期共识层实现，已被 `deepseek_worker.py` 取代 |
| `langgraph_consensus.py` | **完全未被引用** | 全仓库无任何 import。LangGraph 集成实验期的中间产物 |
| `langgraph_integration.py` | **完全未被引用** | 全仓库无任何 import。论文正文从未提及 LangGraph |
| `distributed_worker.py` | 仅被 3 个已归档实验脚本引用 | HF transformers 多 GPU 路径，已由 `experiments/reproduce/multi_model_vllm.py`（vLLM 版）取代 |

## ⚠️ 重要：阈值实现的历史差异

`distributed_worker.py` 与 `langgraph_integration.py` 曾使用

```python
theta_accept = (n_total - self.f) * 0.5      # 计数多数式，非论文公式
```

这与论文的计分投票规则不符（论文为 `θ_accept = n − 2f − s`，且完全忽略 `s` 与 `−2f` 项）。
该差异已于 2026-09-15 修复（见 `docs/reviews/REVIEW_2026-09-15_round12_theory_code_layer_audit.md` §四）。

**论文的全部已报告结果不受此影响**：数据由
`experiments/reproduce/multi_model_vllm.py` 产出，该文件自始至终使用正确公式。

修改归档模块时请勿回退此修复。`experiments/verification/audit_theory_numerics.py` 第 8 节会**递归扫描本目录**，
任何回归都会导致审计报错。

## 使用方式

```python
from a2a_bft.legacy.distributed_worker import DistributedWorker, MultiGPUDistributedSystem
```

这些模块已从 `a2a_bft` 的公开 API 中移除（`__init__.py` 不再导出）。

## 模型路径（2026-09-15 可移植性整理）

`distributed_worker.py` 与 `langgraph_integration.py` 原先把模型目录硬编码为
`/autodl-fs/data/models/<模型名>`，换机器即失效。现改为：

```python
_models_dir = os.environ.get("A2A_MODEL_DIR", "/autodl-fs/data/models")
model_paths = {_name: os.path.join(_models_dir, _name) for _name in (...)}
```

默认值与原先一致（在 AutoDL 上行为不变），但可通过环境变量 `A2A_MODEL_DIR` 覆盖。
`experiments/legacy/model_comparison_experiment.py` 做了同样处理。

