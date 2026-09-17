# A2A-BFT

**Byzantine Fault-Tolerant Consensus for Agent-to-Agent Protocols**

A2A-BFT 为 Agent-to-Agent (A2A) 协议补上共识层：在异构多模型部署下，让一组
LLM 智能体对同一任务达成**语义共识**，并抵御拜占庭节点（投毒、串谋、策略性拒绝）
与软故障节点。

投稿 ICLR 2027。论文源文件：`papers/iclr2027_main.tex`。

---

## 1. 核心思想

三阶段语义共识：**Propose → Validate → Commit**

| 机制 | 内容 |
|------|------|
| 容错模型 | `n ≥ 3f + s + 1`（f = 拜占庭数，s = 软故障数） |
| 投票计分 | `φ(π) = \|ACCEPT\| − 0.5·\|REJECT\|`（计数式，非加权式） |
| 动态阈值 | `θ_accept = n − 1 − 2f − s`，`θ_reject = −(n − 1 − f)·0.5` |
| 决策 | `φ ≥ θ_accept` → ACCEPT；`φ ≤ θ_reject` → REJECT；否则 PENDING（下一轮换视图） |
| 声誉追踪 | `reject_ratio ≥ 70%` 触发惩罚 `−0.25/轮` |

**决策一致性定理（Theorem 5.1）**：阈值间隙
`gap = θ_accept − θ_reject = 1.5(n−1) − 2.5f − s`，
在安全边界上 `gap = 2f + 0.5s`；而拜占庭节点通过选票翻转至多改变一个副本的 φ 达
`1.5f`。因 `gap > 1.5f`，诚实副本**不可能**得出相反的终态决策（只可能出现
ACCEPT 与 PENDING 的分歧）。这一间隙正是等义投票（equivocation）的吸收器。

---

## 2. 目录结构

```
.
├── papers/                     论文（只放投稿相关文件）
│   ├── iclr2027_main.tex       ★ 论文源文件
│   ├── references.bib          参考文献
│   ├── SUBMISSION_CHECKLIST.md ★ 提交清单 + ICLR 2027 合规核对
│   ├── generate_figures.py     5 张论文图件的生成脚本
│   ├── figures/                图件（PDF）+ .figsource.json 内容指纹
│   ├── iclr2027_conference.*   官方样式文件（与 media.iclr.cc 逐字节一致）
│   └── iclr-2027-style-files/  官方样式包原件（含下载 zip）
│
├── experiments/                实验：代码 + 数据 + 结果
│   ├── src/                    ★ 核心库（纯标准库，导出 33 个符号）
│   │   ├── a2a_bft/            deepseek_worker.py 共识引擎 / baselines.py 基线
│   │   ├── a2a_bft/legacy/     早期实现存档
│   │   └── block_a2a_integration/
│   ├── reproduce/              ★ 论文数据的生成脚本（表格/图表的唯一来源）
│   ├── env/                    ★ 环境搭建与 vLLM 部署（含 env.sh 自定位变量）
│   ├── verification/           ★ 审计与负向测试（数值/图表/理论/路径/修订层）
│   ├── results/                实验结果（论文所有数字的来源）
│   ├── datasets/               基准数据集（GSM8K / MBPP / MMLU）
│   └── legacy/                 历史实验脚本存档
│
├── docs/
│   ├── REPRODUCTION.md         ★ 表/图 → 脚本 → 命令 → 产物
│   ├── AUDIT.md                ★ 审计总账
│   ├── audit/                  数据来源审计、PAT 分诊
│   ├── reviews/                历史评审报告（R1–R18，内部材料）
│   ├── revisions/              修订期补丁脚本存档
│   └── cleanup/                清理清单与打包脚本
│
├── reproduce.sh                ★ 一键复现入口（唯一入口，见 §3.0）
├── Makefile                    reproduce.sh 的薄封装（make verify / make doctor）
├── .a2a_project_root           项目根标记（**勿删**，脚本靠它定位）
└── requirements.txt
```

> **可移植性**：仓库内**没有任何硬编码的机器路径**。Python 脚本通过向上查找
> `.a2a_project_root` 标记文件定位项目根；shell 脚本通过 `experiments/env/env.sh`
> 自定位。换机器、换目录、换用户名都不需要改代码。

---

## 3. 快速开始

### 3.0 一键复现（推荐入口）

仓库根目录的 `reproduce.sh` 是**唯一入口**，不需要读文档挑命令、也不需要 `cd`：

```bash
./reproduce.sh              # 默认 = verify：8 个审计 + 5 组负向测试（纯 CPU，无需 GPU）
./reproduce.sh doctor       # 先跑这个：告诉你本机能复现到哪一步、缺什么
./reproduce.sh figures      # 从 experiments/results/ 重新出图并复查图-表一致性
./reproduce.sh all          # doctor + datasets + figures + verify
```

| 阶段 | 需要 GPU | 说明 |
|------|----------|------|
| `doctor` | 否 | 环境体检：解释器、依赖、数据/结果/图件计数、GPU 数量 |
| `verify` | 否 | 8 审计 + 5 组负向测试；输出 `REPRODUCE_OK` / `REPRODUCE_FAILED` |
| `figures` | 否（需 matplotlib） | 重新生成 5 张图件 + 内容指纹复查 |
| `datasets` | 否 | 下载 GSM8K / MBPP / MMLU 并校验条数 |
| `install` | 否 | `pip install -r requirements.txt` |
| `full` | **是**（2×80GB） | 全部实验；前置条件不满足时**直接中止，不隐式开跑** |

判定语义（重要）：审计脚本会打印 `REPRODUCE_OK` / `REPRODUCE_OK_PARTIAL` / `REPRODUCE_FAILED`，
退出码为 0 / 0 / 1。**"未验证"不等于"通过"**——若某层因缺依赖跑不了，默认判失败；
只有显式 `A2A_ALLOW_SKIP_FIGURES=1` 才降级为 `SKIP`，且会写进最终结论（`REPRODUCE_OK_PARTIAL`）。

> ⚠️ **不要并行执行本脚本**。负向测试会临时改写 `papers/iclr2027_main.tex` 再逐字节还原
> （靠注入已知缺陷来证明审计真的能捕获）。并行时审计会读到注入态而报假警，
> 两个负向脚本同时备份/还原还会互相覆盖。脚本已用锁文件 + 严格串行 + 收尾哈希比对防护。

### 3.1 安装依赖

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

核心库 `experiments/src/a2a_bft/` **只依赖标准库**，因此"协议逻辑本身"无需任何 GPU
或第三方包即可导入与单测；上表依赖仅用于真实 LLM 推理与绘图。

### 3.2 下载数据与模型

```bash
python experiments/env/download_datasets.py          # GSM8K / MBPP / MMLU
A2A_MODEL_DIR=/path/to/models python experiments/env/download_models.py
```

### 3.3 启动 4 个异构 vLLM 实例（需 2×80GB GPU）

```bash
export A2A_MODEL_DIR=/path/to/models        # 默认 /autodl-fs/data/models
bash experiments/env/start_vllm_seq.sh      # 逐个启动并等待健康检查
```

| GPU | 模型 | 端口 | served-model-name | gpu-memory-utilization |
|-----|------|------|-------------------|------------------------|
| 0 | Llama-3.1-8B-Instruct | 8000 | `llama` | 0.30 |
| 0 | InternLM3-8B-Instruct | 8001 | `internlm` | 0.30 |
| 1 | DeepSeek-V2-Lite-Chat | 8002 | `deepseek` | 0.50 |
| 1 | Qwen2.5-7B-Instruct | 8003 | `qwen` | 0.28 |

**为什么必须是 2 张卡**：四个模型 FP16 权重合计约 78 GB，单张 80GB 卡还要留出
KV cache 与激活，实际装不下；脚本中还有个保护性断言要求 `device_count() >= 2`。
瓶颈是**总权重大小**，不是单实例的 `gpu-memory-utilization`。

### 3.4 跑一个最小冒烟测试

```bash
A2A_VERBOSE=1 bash -c 'source experiments/env/env.sh'   # 看解析出的路径
python experiments/env/smoke_code.py                   # 少量任务的连通性验证
```

完整的数据生成流水线见 **[docs/REPRODUCTION.md](docs/REPRODUCTION.md)**。

---

## 4. 可复现性与审计

本仓库的论文数字是**可被独立重算**的，而不是"看起来对"。`experiments/verification/`
下有两套东西：

- **审计脚本（8 个）**：把论文正文/表格/图里的每个数字，与 `experiments/results/`
  里的原始数据重新算一遍；另含路径解析层、修订层与决策中性等专项检查。
- **负向测试（5 个）**：主动向仓库注入已知缺陷，确认审计**真的能捕获**（32/32 全部捕获）。
  > 各项的具体条数以 `./reproduce.sh verify` 的**实时输出**为准（该输出由脚本实际产出，不写死）；
  > 本行与文档中的数字若与之不符，以实时输出为准。
  没有这一步，审计的"全绿"无法与"根本没检查"区分。

```bash
python experiments/verification/audit_table_numbers.py     # 349 项：表格数值
python experiments/verification/audit_figures.py           # 124 项：图表 + 题注披露 + 内容指纹新鲜度
python experiments/verification/audit_prose_ranges.py      # 正文区间与表格一致性
python experiments/verification/audit_theory_numerics.py   # 理论公式数值实例化 + 实现一致性
python experiments/verification/audit_revision_layer.py    # 52 项：修订层代数 + 文本自洽
python experiments/verification/audit_decision_neutrality.py
python experiments/verification/audit_reputation_fidelity.py
python experiments/verification/audit_paths.py             # 路径解析层（含读取型 open 存在性、文档命令路径 §6）

python experiments/verification/negative_test_tables.py    # 5/5
python experiments/verification/negative_test_figures.py   # 8/8
python experiments/verification/negative_test_theory.py    # 3/3
python experiments/verification/negative_test_paths.py     # 8/8
python experiments/verification/negative_test_revision.py  # 8/8
```

> 上面 13 条命令等价于 `./reproduce.sh verify`（一条命令、串行、带总判定）。

> 路径层检查来自一次真实教训：目录重组后，有脚本因为把数据目录写成
> "脚本自身位置/results"，搬家后指向了不存在的目录——**而当时的验收只看了
> `sys.path`，于是"全绿"掩盖了它已经跑不起来**。移动或重命名任何脚本后，
> 请先跑 `audit_paths.py` + `negative_test_paths.py`。

详见 **[docs/AUDIT.md](docs/AUDIT.md)** 与 **[papers/SUBMISSION_CHECKLIST.md](papers/SUBMISSION_CHECKLIST.md)**。

---

## 5. 实验规模

| 实验 | 配置 | 规模 | 数据文件 |
|------|------|------|----------|
| 容错扫描（主） | 3 数据集 × 10 配置 × 5 种子 × 50 任务 | 7,750 次共识 | `full_bft_sweep_aggregated.json` |
| 消融 + 基线对比 | 2 领域 × 多方法 × 3 种子 × 30 任务 | 4,320 | `multi_model_3seed_aggregated.json` |
| 多领域验证（真实 API） | 18 配置 × 40 任务 | 770 | `deepseek_{math,knowledge,code}_fixed_20.json` |

**所有数字均来自真实 LLM 推理，无模拟 worker。** 采样种子：容错扫描
`{42,43,44,45,46}`；消融与基线 `{42,43,44}`。同一配置跨种子复用同一任务集，以支持配对比较。

---

## 6. 硬件与软件环境

- **GPU**：2 × NVIDIA A800-SXM4-80GB（512GB 主机内存）
- **软件**：CUDA 12.8、PyTorch 2.8.0、vLLM 0.11.0、transformers 4.56.2、Python 3.13
- **解码**：temperature 0，max_tokens 512
- **模型**：Llama-3.1-8B-Instruct、DeepSeek-V2-Lite-Chat、InternLM3-8B-Instruct、Qwen2.5-7B-Instruct

---

## 7. 文献

```bibtex
@inproceedings{a2abft2027,
  title     = {Byzantine Fault-Tolerant Consensus for Agent-to-Agent Protocols},
  booktitle = {International Conference on Learning Representations (ICLR)},
  year      = {2027}
}
```
