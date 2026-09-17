# experiments/ —— 实验模块

按**功能**而非按时间组织。每个子目录职责单一：

| 目录 | 职责 | 能否重跑 |
|------|------|----------|
| `reproduce/` | **论文数据的生成脚本**。表格与图表的唯一来源 | ✅ 需要 GPU / API |
| `env/` | 环境搭建、模型与数据集下载、vLLM 部署与冒烟测试 | ✅ |
| `verification/` | 审计脚本与负向测试 | ✅ 不需要 GPU |
| `results/` | 实验结果（含日志） | — 产物 |
| `datasets/` | 基准数据集 | — 产物 |
| `legacy/` | 历史实验脚本存档 | ⚠️ 保留供追溯，多数已不可直接运行 |

---

## reproduce/ —— 论文数据链

| 脚本 | 输入 | 输出 | 对应论文 |
|------|------|------|----------|
| `multi_model_vllm.py` | 4 个 vLLM 实例 | （被其他脚本 import 的库） | 全部 |
| `full_bft_sweep.py` | 数据集 + vLLM | `full_bft_sweep_{gsm8k,mbpp,mmlu}.json` | `tab:baseline/bft/mmlu_sweep/attacks` |
| `aggregate_full_sweep.py` | 上述三个文件 | `full_bft_sweep_aggregated.json` | 同上 + `tab:performance/complexity` 实测列 |
| `multi_model_compare_ablation_v2.py` | GSM8K, seed 42 | `multi_model_compare_ablation_v2.json` | `tab:ablation` / `tab:hetero_compare` |
| `multi_model_compare_ablation_v3.py` | MBPP, seed 42 | `multi_model_compare_ablation_v3.json` | 同上 |
| `multi_model_multiseed.py` | seeds 43, 44 | `multi_model_multiseed.json` | 同上 |
| `mbpp_debate_fix.py` | MBPP | `mbpp_debate_fix.json` | 修复 LLM-Debate 代码行 |
| `merge_3seed.py` | 上述四个 | `multi_model_3seed_aggregated.json` | `tab:ablation` / `tab:hetero_compare` |
| ~~`merge_final.py`~~ | — | — | 早期两领域合并版，已被 `merge_3seed.py` 取代，2026-09-17 删除 |
| `large_scale_experiment.py` | DeepSeek API | `deepseek_{math,knowledge,code}_fixed_20.json` | `tab:real_llm` |
| `parse_correctness_log.py` | `correctness_50x3_log.txt` | `correctness_50t_3s_run1_from_log.json` | `tab:n8_scaling` |
| `run_pairing_mcnemar.py` | 上述 + 计数日志 | `run_pairing_mcnemar.json` | 配对 McNemar 检验 |
| `performance_test.py` | vLLM | `performance_test_results.json` | （独立成本基准，不在论文数据链上） |
| `reputation_ablation.py` | 4 个 vLLM 实例 | `reputation_vote_stream.json` + `reputation_ablation.json` | `fig:reputation` 实测轨迹 / `tab:rep_ablation` |

> 执行顺序与命令见 [`../docs/REPRODUCTION.md`](../docs/REPRODUCTION.md)。

`reputation_ablation.py` 是**两阶段**脚本：阶段 1 在真实部署上跑协议并记录投票流（需 GPU），
阶段 2 从缓存的投票流离线重放（纯 CPU、零 LLM 调用）。因此阶段 2 可以无限次复现，
这也是"决策不受声誉影响"这一论断**可被独立验证**的原因：每次重放都会断言
重放出的决策序列与线上记录逐字段一致。用 `--replay-only` 只跑阶段 2，`-h` 看用法。

---

## env/ —— 环境与部署

### 自定位变量

**`env.sh`** 是所有启动脚本的公共入口，把原先硬编码的 AutoDL 路径改为
"脚本自定位 + 环境变量可覆盖"：

```bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `A2A_ROOT` | 由 `env.sh` 位置向上两级推出 | 项目根 |
| `A2A_RESULTS` | `<root>/experiments/results` | 结果目录 |
| `A2A_DATASETS` | `<root>/experiments/datasets` | 数据集目录 |
| `A2A_LOGDIR` | `<results>/logs` | 日志目录 |
| `A2A_MODEL_DIR` | `/autodl-fs/data/models` | 模型权重目录 |
| `A2A_PY` / `A2A_PIP` | `/root/miniconda3/bin/python` / `pip` | 解释器 |

设 `A2A_VERBOSE=1` 可打印解析结果。

### 脚本清单

| 脚本 | 用途 |
|------|------|
| `install_vllm011.sh` / `install_vllm011b.sh` | 安装 vLLM 0.11.0（b 版固定 transformers 4.56.2） |
| `start_vllm.sh` | 并行启动 4 个 vLLM 实例 |
| `start_vllm_seq.sh` | **推荐**：逐个启动 + 健康检查，全部就绪后打印 `ALL_4_VLLM_READY` |
| `restart_failed.sh` | 只重启 OOM 失败的 llama(8000) / deepseek(8002) |
| `run_sweeps.sh` | 后台并发跑三个数据集的容错扫描 |
| `run_compare.sh` | 等待现有实验结束后跑消融对比 |
| `run_probe.sh` / `run_quick.sh` | 运行 `probe.py` / `quick_test.py` 并落日志 |
| `run_experiment.sh` | 早期的一体化启动脚本 |
| `run_on_autodl.sh` | 远端 AutoDL 部署（host/port/密码均改为环境变量） |

### Python 脚本

| 脚本 | 用途 |
|------|------|
| `download_datasets.py` | 下载 GSM8K / MBPP / MMLU 并校验，写 `dataset_summary.json` |
| `download_models.py` | 下载 4 个模型权重 |
| `ssh_autodl.py` | **非交互式**连接 AutoDL GPU（paramiko 密码认证），可执行远端命令、上传/下载。凭据只从 `A2A_SSH_*` 环境变量读取，不落盘 |
| `probe.py` | 与四个 vLLM 实例各通一次，检查输出是否符合预期 |
| `quick_test.py` | 快速连通性 |
| `smoke_code.py` / `smoke_sweep.py` | 代码任务 / 扫描流程的少量端到端冒烟 |
| `test_extract_idem.py` | 幂等性测试（同一输入重复提取答案应一致） |

---

## verification/ —— 审计与负向测试

| 脚本 | 内容 | 期望 |
|------|------|------|
| `audit_table_numbers.py` | 表格数值逐项重算 | 348 项，0 问题 |
| `audit_figures.py` | 图表来源、题注披露、新鲜度 | 123 项，0 问题 |
| `audit_theory_numerics.py` | 理论公式数值实例化 + 交付代码阈值扫描 | 全部 OK |
| `audit_prose_ranges.py` | 正文区间与表格一致性 | 无数值不一致 |
| `audit_paths.py` | **L9** 路径解析层：数据目录常量与 `sys.path` 目标是否指向真实位置 | 0 问题，四类计数均 > 0 |
| `audit_reputation_fidelity.py` | 声誉追踪器 vs `deepseek_worker.py:982-1002` 逐轮 `r_i` 比对（含 suspect 升级罚） | 12000 步 0 不一致，`FIDELITY_OK` |
| `negative_test_tables.py` | 向表格审计注入 5 个缺陷 | 5/5 捕获 |
| `negative_test_figures.py` | 向图表审计注入 6 个缺陷 | 6/6 捕获 |
| `negative_test_theory.py` | 向代码/理论扫描注入 3 个缺陷 | 3/3 捕获 |
| `negative_test_paths.py` | 向 L9 注入 4 个路径缺陷 + 1 个防空转用例 | 5/5 捕获 |

**负向测试未全部捕获时，审计的"全绿"不可采信。** 详见
[`../docs/AUDIT.md`](../docs/AUDIT.md)。

> `audit_paths.py` 出过一次很有代表性的教训：它的初版用 `exec` 逐条执行顶层语句
> 来取路径常量的值，结果把 `mbpp_debate_fix.py` 的实验主体也执行了，真实打出了
> API 请求。现在改成纯 AST 符号求值（不执行任何额代码），并识别本仓库中
> 三种"向上查找项目根"的写法——只认一种会让另外两种被误算成"脚本目录"，
> 一次产生十几条假阳性。**审计脚本本身也是代码，必须像被测对象一样被审查。**

---

## results/ —— 结果目录

| 文件 | 内容 |
|------|------|
| `full_bft_sweep_aggregated.json` | 容错扫描聚合（5 种子 × 50 任务） |
| `multi_model_3seed_aggregated.json` | 消融与基线对比聚合（3 种子 × 30 任务） |
| `correctness_50t_3s_run1_from_log.json` | n=8 边界扫描 |
| `deepseek_{math,knowledge,code}_fixed_20.json` | 多领域验证（真实 API） |
| `run_pairing_mcnemar.json` | 配对 McNemar 检验 |
| `logs/` | 运行日志（`compare_ablation.log` / `compare_v3.log` / `multiseed.log`） |
| ~~`archive_simulation_era/`~~ | 模拟期结果归档；**2026-09-17 已整体删除**（指纹：`avg_time` 40–80 µs，真实 LLM 不可能微秒级）。备份见 `A2A_cleanup_backup_20260917.tar.gz` |

---

## datasets/ —— 数据集

| 文件 | 条数 | 论文使用 |
|------|------|----------|
| `gsm8k_test.json` | 1,319 | ✅ |
| `mbpp_test.json` | 500 | ✅ |
| `mmlu_3subjects.json` | 312 | ✅ |
| `humaneval_full.json` | 164 | ❌ 下载但未进入数据链 |
| `dataset_summary.json` | — | 自动生成的数据集计数摘要（`paper_total_tasks` = 2,131） |

> `mmlu_4subjects.json`（312 条、与上表字节级重复、名字误导、无脚本引用）已于
> **2026-09-17 删除**。

---

## legacy/ —— 历史存档

早期实验脚本。**保留目的是可追溯**（论文修改过程中对照过这些实现），
不是可运行的入口。其中多数使用 DeepSeek API 的早期调用方式，或已被
`reproduce/` 中的版本取代。

引用的服务器专用一次性脚本（`judge_test.py` 等）已在本轮整理中按清理清单移除。
