# 复现指南（Reproduction Guide）

> 语言 / Language：**简体中文** ｜ [English](REPRODUCTION.md)
>
> 本文件是 [REPRODUCTION.md](REPRODUCTION.md) 的中文存档。

> **一键入口（推荐）**：本文档是「表/图 → 脚本 → 命令 → 产物」的完整对照表，
> 适合需要精确控制单条命令时查阅。日常复现建议直接用仓库根的 `reproduce.sh`：
>
> ```bash
> ./reproduce.sh doctor     # 先体检：本机能复现到哪一步
> ./reproduce.sh verify     # 8 审计 + 5 组负向测试（纯 CPU，约 1 分钟）
> ./reproduce.sh all        # datasets + figures + verify
> ```
>
> 判定语义：`REPRODUCE_OK` / `REPRODUCE_OK_PARTIAL` / `REPRODUCE_FAILED`，
> 退出码 0 / 0 / 1。"未验证"不等于"通过"。

本文档给出**论文中每一个表格与图表的数据来源、生成脚本、运行命令与预期产物**。
所有路径相对仓库根目录；所有命令可在仓库根直接执行（脚本自定位，无需 `cd`）。

---

## 0. 流水线总览

```
                    start_vllm_seq.sh  (2×A800，4 个 vLLM 实例)
                              │
        ┌─────────────────────┼──────────────────────┬────────────────────┐
        │                     │                      │                    │
   full_bft_sweep.py    multi_model_compare_    large_scale_         correctness
   {gsm8k,mbpp,mmlu}      ablation_v2/v3.py      experiment.py        _50x3_log.txt
        │                 multi_model_multiseed.py  (DeepSeek API)      │
        │                 mbpp_debate_fix.py            │         parse_correctness_log.py
        ▼                        ▼                      ▼               ▼
  aggregate_full_sweep.py   merge_3seed.py     deepseek_{math,       correctness_50t_
        │                        │              knowledge,code}_      3s_run1_from_log.json
        ▼                        ▼              fixed_20.json               │
  full_bft_sweep_          multi_model_3seed_        │            run_pairing_mcnemar.py
  aggregated.json          aggregated.json           │                      │
        │                        │                   │                      ▼
        └────────────┬───────────┴───────────────────┴──────────────►  run_pairing_mcnemar.json
                     ▼
            papers/generate_figures.py
                     ▼
            papers/figures/*.pdf  （LaTeX 直接 \includegraphics）
```

**数据目录约定**：所有中间与最终结果都落在 `experiments/results/`。
可用环境变量 `A2A_RESULTS_DIR` / `A2A_DATASET_DIR` 覆盖。

---

## 1. 环境准备

```bash
pip install -r requirements.txt

export A2A_MODEL_DIR=/path/to/models        # 默认 /autodl-fs/data/models
export A2A_PY=$(which python)               # 默认 /root/miniconda3/bin/python

A2A_VERBOSE=1 bash -c 'source experiments/env/env.sh'   # 打印解析结果，确认路径
```

### 1.1 数据集

```bash
python experiments/env/download_datasets.py
```

预期产物（`experiments/datasets/`）：

| 文件 | 条数 | 论文使用 | 说明 |
|------|------|----------|------|
| `gsm8k_test.json` | 1,319 | ✅ | GSM8K test split，答案含 `####` 终结标记 |
| `mbpp_test.json` | 500 | ✅ | MBPP，每题含非空 `code` 与 `test_list` |
| `mmlu_3subjects.json` | 312 | ✅ | abstract_algebra 100 + college_mathematics 100 + machine_learning 112 |
| `humaneval_full.json` | 164 | ❌ | 可加载但未进入论文数据链 |

> `mmlu_4subjects.json`（312 条、与 `mmlu_3subjects.json` **字节完全相同**、文件名误导、
> 无任何脚本引用）已于 **2026-09-17 清理中删除**；同一轮次还修掉了它污染的
> `dataset_summary.json`（旧 `total_tasks: 2607` 把该副本与未使用的 HumanEval
> 一并计入；论文实际使用量为 **2,131**）。详见 `docs/audit/DATA_SOURCE_AUDIT.md` §十四。

> `dataset_summary.json` 已由脚本自动生成并记录上述警告，无需手工维护。

### 1.2 模型权重

四个模型（FP16 合计约 78 GB）：

```
Llama-3.1-8B-Instruct  DeepSeek-V2-Lite-Chat  InternLM3-8B-Instruct  Qwen2.5-7B-Instruct
```

### 1.3 启动 vLLM（2 张 80GB 卡）

```bash
bash experiments/env/start_vllm_seq.sh      # 推荐：逐个启动 + 健康检查
# 或 bash experiments/env/start_vllm.sh     # 并行启动，更快但可能争抢显存
```

| GPU | 模型 | 端口 | name | util |
|-----|------|------|------|------|
| 0 | Llama-3.1-8B-Instruct | 8000 | `llama` | 0.30 |
| 0 | InternLM3-8B-Instruct | 8001 | `internlm` | 0.30 |
| 1 | DeepSeek-V2-Lite-Chat | 8002 | `deepseek` | 0.50 |
| 1 | Qwen2.5-7B-Instruct | 8003 | `qwen` | 0.28 |

全部就绪时脚本打印 `ALL_4_VLLM_READY`。**必须 2 张卡**：单卡 80GB 装不下 78 GB 权重
加 KV cache；`multi_model_vllm.py` 中有 `device_count() < 2` 的保护性断言。

冒烟测试：

```bash
python experiments/env/probe.py        # 与四个实例各通一次，检查返回是否符合预期
python experiments/env/quick_test.py   # 快速连通性
python experiments/env/smoke_code.py   # 代码任务的少量端到端
```

---

## 2. 表格 → 数据来源 → 命令

### Pipeline A — 容错扫描（主实验）

覆盖 `tab:baseline`、`tab:bft`、`tab:mmlu_sweep`、`tab:attacks`（+ `tab:performance`、
`tab:complexity` 的实测轮数/调用数/时延列）。

| 步骤 | 命令 | 产物 |
|------|------|------|
| 1 | `python experiments/reproduce/full_bft_sweep.py gsm8k` | `results/full_bft_sweep_gsm8k.json` |
| 1 | `python experiments/reproduce/full_bft_sweep.py mbpp` | `results/full_bft_sweep_mbpp.json` |
| 1 | `python experiments/reproduce/full_bft_sweep.py mmlu` | `results/full_bft_sweep_mmlu.json` |
| 2 | `python experiments/reproduce/aggregate_full_sweep.py` | `results/full_bft_sweep_aggregated.json` |

规模：**5 个种子 × 50 任务 = 250 任务/单元**，种子 `{42,43,44,45,46}`，
合计 7,750 次共识任务。

后台批量执行（等价于依次跑三个数据集）：

```bash
bash experiments/env/run_sweeps.sh
```

校验：

```bash
python experiments/verification/audit_table_numbers.py   # 其中 tab:baseline/bft/mmlu/attacks 段
```

### Pipeline B — 消融与基线对比

覆盖 `tab:ablation`、`tab:hetero_compare`。

| 步骤 | 命令 | 产物 |
|------|------|------|
| 1 | `python experiments/reproduce/multi_model_compare_ablation_v2.py` | `results/multi_model_compare_ablation_v2.json` (GSM8K, seed 42) |
| 1 | `python experiments/reproduce/multi_model_compare_ablation_v3.py` | `results/multi_model_compare_ablation_v3.json` (MBPP, seed 42) |
| 1 | `python experiments/reproduce/multi_model_multiseed.py` | `results/multi_model_multiseed.json` (seeds 43, 44) |
| 1 | `python experiments/reproduce/mbpp_debate_fix.py` | `results/mbpp_debate_fix.json` (LLM-Debate 代码修正式生成) |
| 2 | `python experiments/reproduce/merge_3seed.py` | `results/multi_model_3seed_aggregated.json` |

规模：**3 个种子 × 30 任务 = 90 任务/单元**，种子 `{42,43,44}`。

> **注意**：`mbpp_debate_fix.py` 必须跑完再执行 `merge_3seed.py` —— 后者用它的结果
> 替换 `multi_model_compare_ablation_v3.json` 中的 LLM-Debate 行（修复其代码任务上
> 不合理的生成预算）。

> `merge_final.py` 是更早的"两领域合并"版本，产出
> `multi_model_compare_ablation_final.json`；最终表格用的是 `merge_3seed.py`。
> 二者已于 **2026-09-17 一并删除**（`_final.json` 零读取方，`merge_final.py` 的
> 产出物无消费者）。现行链路只有 `merge_3seed.py`。

### Pipeline C — 多领域验证（真实 DeepSeek API）

覆盖 `tab:real_llm`。

```bash
export DEEPSEEK_API_KEY=sk-...        # 必须；脚本不再内置密钥
python experiments/reproduce/large_scale_experiment.py
```

产物：`results/deepseek_{math,knowledge,code}_fixed_20.json`

| 领域 | 数据集 | 任务/配置 |
|------|--------|-----------|
| math | GSM8K | 40 |
| knowledge | MMLU | 40 |
| code | MBPP | 40 |

18 配置 × 40 任务 = 720 次真实 API 任务。报告：`results/large_scale_experiment_report.md`。

> 该流水线**不使用 vLLM**，只需要 API key 与网络。

### Pipeline D — n=8 对抗边界与配对检验

覆盖 `tab:n8_scaling`、`tab:a2a_sim_comparison` 的 Δ 与 McNemar 配对检验。

| 步骤 | 命令 | 产物 |
|------|------|------|
| 1 | （原始运行日志） | `results/correctness_50x3_log.txt` |
| 2 | `python experiments/reproduce/parse_correctness_log.py` | `results/correctness_50t_3s_run1_from_log.json` |
| 3 | `python experiments/reproduce/run_pairing_mcnemar.py` | `results/run_pairing_mcnemar.json` |

`run_pairing_mcnemar.py` 对两次 n=8 运行做**逐任务配对**比较（同一任务抽样），
输出配对 McNemar 检验结果。

### Pipeline E — 成本基准（可选，非论文数据链）

```bash
python experiments/reproduce/performance_test.py
# → results/performance_test_results.json
```

`tab:performance` / `tab:complexity` 中的**实测轮数、调用数、时延**来自
Pipeline A 的聚合结果（`aggregate_full_sweep.py` 的 `avg_rounds` / `avg_calls` /
`avg_time` 指标），而非本脚本。本脚本是独立的成本基准，其输出**不在论文数据链上**。

### Pipeline F — 声誉追踪器测量性消融

支撑 `fig:reputation`（由"示意"改为"实测"）与 `tab:rep_ablation`。

```bash
# 阶段 1（线上，需 4 个 vLLM 实例就绪）：跑协议并完整记录每一轮每一张票
python experiments/reproduce/reputation_ablation.py --tasks 20

# 阶段 2（离线，纯 CPU，零 LLM 调用）：从缓存投票流重放
python experiments/reproduce/reputation_ablation.py --replay-only
```

| 步骤 | 命令 | 产物 |
|------|------|------|
| 1 | `python experiments/reproduce/reputation_ablation.py --tasks 20` | `results/reputation_vote_stream.json`（投票流）+ `results/reputation_ablation.json`（四档结果） |
| 2 | `python experiments/reproduce/reputation_ablation.py --replay-only` | 同上，可无限次复现 |
| 3 | `python experiments/reproduce/render_reputation_report.py` | `results/reputation_ablation_report.md`（含任务级列：误罚任务 / 触发任务） |
| 4 | `python experiments/verification/audit_reputation_fidelity.py` | 保真度比对：`FIDELITY_OK`，升级罚 5180 / 5180 |
| 5 | `python experiments/verification/verify_mbpp_subboundary.py` | `results/mbpp_subboundary_verification.json`（离线复现越界错误提交，零 LLM 调用） |

> **重放口径（2026-09-17 修正）**：`ok` 谓词必须写成析取
> `(v == 'accept' and c) or (v == 'reject' and not c)`，与 `deepseek_worker.py:975-980`
> 一致。写成 `(v == 'accept') == c` 会把"对错误提案弃权"算成投对，只在 ABSTAIN 上分歧。
> 修正后正文数字由 $1{,}217$ of $1{,}305$ 变为 **$1{,}186$ of $1{,}305$**；
> 四档重放决策序列与线上记录仍逐字段一致。详见 `docs/AUDIT.md` §3.6.1。

**为什么不是"开/关声誉比接受率"**：论文 §4.3 与附录声明声誉分数**不进入计票规则**
（式 `commit` 聚合的是原始票数），因此声誉**不可能**改变任何 commit 决策——做那个对比
在数学上是恒等式，属定理推论而非实验发现。脚本改为测量**追踪器本身报告了什么**：

| 编号 | 测量对象 |
|------|----------|
| M1 | 决策指标（与论文 `tab:ablation` 对应单元对照，确认协议路径未变） |
| M2 | 四档罚则的触发分布（按"验证者真值 × 该票客观上是否正确"切分） |
| M3 | 拜占庭识别性能：把"触发激进罚（ρ≥0.7，−0.25）"当作检测器，算 P/R/F1 |
| M4 | **误罚率**：激进罚落在"诚实验证者且该票客观上正确"上的比例 |
| M5 | `c` 的来源对比：算法 1 要求 c = 提案是否真的正确；发布实现用
`_estimate_correctness`（格式检查）。用 oracle c 与 released c 各重放一次量化差距 |

四档重放 = `{oracle, released} × {persistent, fresh}`。每次重放都会断言
**重放出的决策序列与线上记录逐字段一致**（`decision_consistent` 必须为 True）——
这既是正确性校验，也是"决策不受声誉影响"这一论断的**可验证证据**。

脚本支持 `-h` 查看用法；线上阶段开跑前会做端点预检，避免空跑。

---

## 3. 图表 → 生成方式

```bash
python papers/generate_figures.py
```

产物写入 `papers/figures/`（PDF 供 LaTeX 使用，PNG 供预览；PNG 被 `.gitignore` 忽略）。

| 论文图表 | 文件 | 数据来源 |
|----------|------|----------|
| `fig:attack_resistance` | `attack_resistance.pdf` | `results/full_bft_sweep_aggregated.json` |
| `fig:performance_comparison` | `performance_comparison.pdf` | 同上 + `multi_model_3seed_aggregated.json` |
| `fig:architecture` | `architecture.pdf` | 纯代码绘制（示意图） |
| `fig:consensus_flow` | `consensus_flow.pdf` | 纯代码绘制（协议流程） |
| `fig:reputation` | `reputation_mechanism.pdf` | 纯代码绘制（声誉规则） |

> 论文实际 `\includegraphics` 的图只有 5 张：`consensus_flow` / `architecture` /
> `performance_comparison` / `reputation_mechanism` / `attack_resistance`。
> 早期产物 `acceptance_rates.*`、`fault_tolerance_surface.*`（后者还是用
> `honest_ratio * 95` 合成出来的"接受率"，与真机测量无关）以及一批
> `correctness_*.png` / `n8_scaling_results.png` 已于 **2026-09-17 删除**，
> 对应的绘图函数（`load_experiment_data` / `plot_acceptance_rates` /
> `plot_fault_tolerance_surface`）同步从 `papers/generate_figures.py` 移除。
> 移除后重出图件与移除前**逐像素一致**（5/5，最大通道差 0），确认删除是惰性的。

> 三张示意图完全由代码生成，与协议实现中使用的阈值规则**同源**；若改动了
> `experiments/src/a2a_bft/deepseek_worker.py` 的阈值公式，必须重跑本脚本并复核这三张图。

---

## 4. 编译论文

```bash
cd papers
pdflatex iclr2027_main && bibtex iclr2027_main && pdflatex iclr2027_main && pdflatex iclr2027_main
```

> **唯一提交文件**：**官方提交文件是 `papers/iclr2027_main.tex`**
> （使用官方 ICLR 2027 样式 `iclr2027_conference.sty`，与 `media.iclr.cc` 的官方包逐字节一致）。
> 早期草稿分叉 `papers/iclr2026_main.tex`（使用已损坏的 `arxiv.sty`）已在 2026-09-15
> 整理中删除，仓库内**不再有**任何 iclr2026 源文件，不存在再编辑错文件的风险。

---

## 5. 一键验收

> 已在两个平台实测同一结果 **15 通过 / 0 失败**（`REPRODUCE_OK`）：Windows + Python 3.13
> 与 Linux + Python 3.12（CUDA 12.8、vLLM 0.11.0、2×A800）。注意 `verify` 需要它所用的
> 解释器能 import `matplotlib`——机器上装了多个 Python 时用 `A2A_PY=/path/to/python` 指定；
> 缺 matplotlib 时图指纹审计会**报失败**而不是静默跳过。

```bash
# 1) 审计
python experiments/verification/audit_table_numbers.py      # 期望：348 项，0 问题
python experiments/verification/audit_figures.py            # 期望：124 项，0 问题
python experiments/verification/audit_theory_numerics.py    # 期望：全部 OK
python experiments/verification/audit_prose_ranges.py       # 期望：无数值不一致
python experiments/verification/audit_paths.py              # 期望：0 问题，四类计数均 > 0
python experiments/verification/audit_revision_layer.py     # 期望：52 项，0 问题

# 1b) 保真度与离线复现（零 LLM 调用）
python experiments/verification/audit_reputation_fidelity.py  # 期望：FIDELITY_OK，5180/5180
python experiments/verification/verify_mbpp_subboundary.py    # 期望：MBPP_SUBBOUNDARY_DONE
python experiments/verification/audit_decision_neutrality.py  # 期望：DECISION_NEUTRALITY_OK，9 项
                                                              # （从原始票重算 phi + 复现决策 + 变异测试）

# 2) 审计自身有效性（注入缺陷，必须被捕获）
python experiments/verification/negative_test_tables.py     # 期望：5/5
python experiments/verification/negative_test_figures.py    # 期望：6/6
python experiments/verification/negative_test_theory.py     # 期望：3/3
python experiments/verification/negative_test_paths.py      # 期望：5/5
python experiments/verification/negative_test_revision.py   # 期望：8/8
```

若负向测试**未全部捕获**，说明审计失效，其"全绿"结论不可信——此时不要采信第 1 步。

> **`audit_paths.py` 为什么必须在这里**：它检查的是"交付脚本里的路径还指不指得对"。
> 目录重组后曾有 3 个脚本因为数据目录/项目根由**脚本自身位置**推导而静默失效
> （其中 2 个是 `tab:n8_scaling` 与 McNemar 的数据来源），而当时的验收只看了
> `sys.path`，所以"全绿"。移动、重命名任何脚本之后，请务必先跑这一项。
> 详见 [`AUDIT.md` §2/§3.5](AUDIT.md)。

---

## 6. 常见问题

**Q：只有 1 张 GPU，能跑吗？**
不能完整跑。四个模型 FP16 合计约 78 GB，单张 80GB 卡放不下（还要留 KV cache）。
可以降级：只部署 2 个模型做小规模连通性验证，但论文数据无法复现。

**Q：`import openai` 失败会影响审计吗？**
不会。`openai` 是函数内惰性导入（`deepseek_worker.py:112`、`multi_model_vllm.py:231`），
协议库、审计脚本与负向测试都不需要它。

**Q：脚本移动位置后 import 失败？**
不应发生。所有 Python 脚本向上查找 `.a2a_project_root` 标记文件定位项目根，
shell 脚本通过 `experiments/env/env.sh` 自定位。若真的失败，先确认
`.a2a_project_root` 未被删除。

**Q：结果文件在哪里？**
全部在 `experiments/results/`。2026-09-15 之前散落在 `experiments/` 顶层的模拟期
结果曾归入 `experiments/results/archive_simulation_era/`，该目录已于 **2026-09-17
连同其余模拟期/被取代产物一并删除**（35 项 / 1.75 MB），备份在
`A2A_cleanup_backup_20260917.tar.gz`，清单在
`docs/cleanup/cleanup_manifest_20260917.txt`。当前目录内**不含任何模拟数据**。
