# 论文数据源审计：哪些内容还在用模拟数据、哪些需要真机（GPU）重跑

审计对象：`papers/iclr2027_main.tex`（ICLR 2027 官方提交版）
审计时间：2026-09-14
审计范围：全部 10 个表 + 5 张图

> **路径沿革（2026-09-17 整理）**：本文是**逐轮审计台账**，各节记录的是**当轮**的目录状态，
> 因此早期小节里的路径已不再指向现有位置。对照如下——历史叙述**予以保留**，
> 不使用新路径回填（那会篡改记录）：
>
> | 台账中的旧路径 | 现路径 |
> |----------------|--------|
> | `experiments/multi_model_autodl/` | `experiments/reproduce/` |
> | `experiments/audit_figures.py`、`experiments/negative_test_figures.py` | `experiments/verification/` 下同名文件 |
> | `src/a2a_bft/` | `experiments/src/a2a_bft/` |
> | `papers/_old_versions_20260912/`、`experiments/results/archive_simulation_era/` | 已删除（回滚备份见根目录 `A2A_cleanup_backup_2026*.tar.gz`）|
> | `experiments/results/deepseek_code_{50,100}.json` | 已删除（§十有说明与原件位置）|
>
> 台账中出现的**项数**（如"117 项""4/4 捕获"）同样是当轮值；当前值见各审计脚本输出
> 与 [papers/SUBMISSION_CHECKLIST.md](../../papers/SUBMISSION_CHECKLIST.md) §6 的验收基线。

---

## 一、结论速览

| 类别 | 数量 | 说明 |
|------|------|------|
| **真实 GPU 真机数据** | 3 表 | tab:ablation、tab:hetero_compare、tab:a2a_sim_comparison（4 模型 vLLM，2×A800） |
| **真实 LLM API 数据** | 2 表 | tab:real_llm、tab:n8_scaling（DeepSeek-V2-Lite API） |
| **⚠️ 仍是 CPU 模拟数据** | **3 表 + 2 图** | tab:baseline、tab:bft、tab:performance、fig:performance_comparison、fig:attack_resistance |
| **理论 / 示意图（无数据）** | 1 表 + 3 图 | tab:complexity、fig:consensus_flow、fig:architecture、fig:reputation |
| **混合（一半模拟一半真机）** | 1 表 | tab:attacks |

**核心结论**：需要"用真机数据替代模拟数据"的一共 **5 处**（3 表 + 2 图）。但它们目前跑的是 `SimulatedWorker`——一个**纯 CPU 类，不调用任何 GPU/LLM**。所以严格说"不需要 GPU 就能跑"，只是跑出来是模拟值。要真正摆脱模拟数据，必须改用**异构 4 模型 vLLM 真机链路**重跑，这一步才需要 GPU。

---

## 二、全表数据源清单（10 个表）

| # | 表标签 | 内容 | 数据源文件/方法 | 数据类型 | 需真机重跑？ |
|---|--------|------|----------------|---------|-------------|
| 1 | `tab:complexity` | 消息复杂度对比 | 理论分析 | 无实验数据 | ❌ 不需要 |
| 2 | `tab:baseline` | 无故障基线 n=4/5/6 | `protocol_5seed_100tasks.json`（SimulatedWorker） | **CPU 模拟** | ⚠️ **是**（若要非模拟） |
| 3 | `tab:bft` | 拜占庭攻击 9 配置 | `protocol_5seed_100tasks.json`（SimulatedWorker） | **CPU 模拟** | ⚠️ **是** |
| 4 | `tab:ablation` | 消融（4 模型异构，48 格） | `multi_model_3seed_aggregated.json` | **真实 GPU**（4 模型 vLLM） | ✅ 已真机 |
| 5 | `tab:hetero_compare` | 基线对比（异构环境） | 同上 | **真实 GPU** | ✅ 已真机 |
| 6 | `tab:n8_scaling` | n=8 对抗边界（150 任务） | DeepSeek API 实跑 | **真实 LLM API** | ✅ 已真实 |
| 7 | `tab:real_llm` | 真实 LLM 验证（540 任务） | DeepSeek API 实跑 | **真实 LLM API** | ✅ 已真实 |
| 8 | `tab:performance` | 协议层开销基准 | `performance_test_results.json`（2026-08-28，SimulatedWorker，单次跑 20 任务） | **CPU 模拟** | ⚠️ 见下注 |
| 9 | `tab:attacks` | 攻击抵抗汇总 | 派生自 `tab:bft`(模拟) + `tab:n8_scaling`(真实) | **混合** | ⚠️ 一半 |
| 10 | `tab:a2a_sim_comparison` | vs A2A-Sim | 异构 4 模型真机 + 1 行原文引用 | **真实 GPU** | ✅ 已真机 |

> **注（重要）**：`tab:performance` 测的是**共识层开销（排除 LLM 推理）**——实测耗时 40 微秒级，本质是协议编排的成本。这一项**设计上就该用模拟/CPU**，用 GPU 跑反而测不到它想测的东西（GPU 跑出来的是 LLM 推理延迟）。建议**保留模拟**，不要真机化。

---

## 三、全图数据源清单（5 张图）

| # | 图标签 | 内容 | 数据源 | 数据类型 | 需真机重跑？ |
|---|--------|------|--------|---------|-------------|
| 1 | `fig:consensus_flow` | 共识流程图 | 示意图 | 无数据 | ❌ |
| 2 | `fig:architecture` | 系统架构图 | 示意图 | 无数据 | ❌ |
| 3 | `fig:performance_comparison` | 性能对比 | `performance_test_results.json` | **CPU 模拟** | ⚠️ **是**（若要非模拟） |
| 4 | `fig:attack_resistance` | 攻击抵抗 | `protocol_5seed_100tasks.json` | **CPU 模拟** | ⚠️ **是** |
| 5 | `fig:reputation` | 声誉机制动态 | 概念示意图 | 无数据 | ❌ |

**注意**：`figures/` 目录下还有 `acceptance_rates.pdf` 和 `fault_tolerance_surface.pdf` 两个文件，但**当前正文并未 `\includegraphics` 引用**，不占页面、不影响评审，可忽略。

---

## 四、需要真机重跑的具体清单（5 处）

| 序号 | 位置 | 现数据源 | 真机化路径 |
|------|------|---------|-----------|
| 1 | `tab:baseline`（3 行） | SimulatedWorker | 异构 4 模型跑 n=4/5/6 无故障基线 |
| 2 | `tab:bft`（9 行） | SimulatedWorker | 异构 4 模型跑 9 个攻击配置 |
| 3 | `tab:attacks`（模拟那一半） | 派生自 tab:bft | 随 tab:bft 自动更新 |
| 4 | `fig:attack_resistance` | protocol_5seed_100tasks.json | 随 tab:bft 自动重绘 |
| 5 | `fig:performance_comparison` | performance_test_results.json | ⚠️ 建议保留模拟（见上注） |
| — | `tab:performance` | SimulatedWorker，单次跑 | ⚠️ 建议保留模拟（设计如此） |

实际需要真机重跑的核心是 **2 个表（tab:baseline + tab:bft）对其共享的 12 个配置**，其余是自动派生。

---

## 五、真机实验当前覆盖 vs 模拟表覆盖的差距

**异构 4 模型真机实验（`multi_model_multiseed.py`）目前只覆盖 3 个配置**：

| 已覆盖（真机） | 攻击 |
|---------------|------|
| n=5, f=0, s=0 | baseline |
| n=5, f=1, s=1 | strategic_reject |
| n=8, f=2, s=1 | collusion |

**模拟表覆盖 12 个配置**，其中 **9 个在真机链路里没有对应**：

| 缺失配置 | 攻击类型 | 是否值得真机补 |
|---------|---------|--------------|
| n=4, f=0, s=0 | baseline | 高（最简基线） |
| n=6, f=0, s=0 | baseline | 中 |
| n=4, f=1, s=0 | random / strategic_reject / sybil | **最高**（常见 BFT 配置，3 个） |
| n=5, f=1, s=1 | random | 中（补齐） |
| n=6, f=2, s=0 | collusion | 中 |
| n=5, f=2, s=0 | random / strategic_reject / collusion | 低（**低于安全边界 3f+s+1**，论文已标 † 仅作经验观察） |

---

## 六、建议的三档方案

### 方案 A｜保持现状（零成本，推荐）
论文当前**已明确标注** `Simulation vs. Real LLM`：协议级扫描用模拟隔离 LLM 噪声，真实证据由三层真机（DeepSeek API 540 任务、n=8 边界 150 任务、4 模型异构 48 格）提供。第 5、6 轮评审均已接受此框架。
- 优点：0 成本，逻辑自洽，审稿人已认可
- 风险：模拟表层若被追问"为何不用真模型"，需补充说明（现有文字已覆盖）

### 方案 B｜补关键配置（中等成本，性价比最高）
只把真机链路扩展到 **n=4, f=1 的 3 种攻击**，共 `3 配置 × 2 领域 × 3 种子 × 30 任务 = 540 任务`（约 5–8 千次 A800 推理）。这样 tab:bft 中最典型的 BFT 配置就有了真机证据，模拟表退居"全配置扫描"的辅助角色。

### 方案 C｜全量真机化（高成本）
把 9 个缺失配置全部真机化：`9 × 2 × 3 × 30 = 1620 任务`（约 1.5–2 万次推理）。tab:baseline/tab:bft 完全由真机数据支撑，模拟仅保留 tab:performance（协议开销）。

---

## 七、下一步

如需执行方案 B 或 C，我可以：
1. 扩展 `experiments/multi_model_autodl/multi_model_multiseed.py` 的 `scenarios` 列表，加入目标配置；
2. 在 AutoDL（A800）上按同一 vLLM 链路重跑，输出与现格式一致的聚合 JSON；
3. 自动重绘 `fig:attack_resistance` 并同步更新 `tab:baseline` / `tab:bft` / `tab:attacks`。

---

## 八、2026-09-15 更新（本节为准，上面第一~六节的"模拟数据"描述已过时）

上文（2026-09-14）写于"模拟 → 真机"迁移**完成之前**。截至 2026-09-15，论文中**已不存在任何 CPU 模拟数据**，所有表格均来自真实 LLM 推理。当前真实的溯源关系如下：

| 表 | 现数据源 | 类型 |
|----|---------|------|
| `tab:complexity` | 理论分析 | 无实验数据 |
| `tab:baseline` | `full_bft_sweep_aggregated.json`（n=4/6 行）+ `multi_model_3seed_aggregated.json`（n=5 行，消融部署） | 真实 GPU（4 模型 vLLM） |
| `tab:bft` | 同上双源 | 真实 GPU |
| `tab:mmlu_sweep` | `full_bft_sweep_aggregated.json` | 真实 GPU |
| `tab:ablation` | `multi_model_3seed_aggregated.json` | 真实 GPU |
| `tab:hetero_compare` | 同上 | 真实 GPU |
| `tab:real_llm` | DeepSeek API 实测（540 任务） | 真实 LLM API |
| `tab:n8_scaling` | **`correctness_50x3_log.txt`** → `correctness_50t_3s_run1_from_log.json` | 真实 LLM API |
| `tab:performance` | 真机端到端计时 | 真实 GPU |
| `tab:attacks` | 派生自 `tab:bft` + `tab:hetero_compare` | 真实 GPU |

**`tab:n8_scaling` 溯源注意事项（重要）**：该表采用 2026-09-11 01:57 那次运行的数值（98.0%/92.7%/2.89 等）。这次运行的汇总 JSON 已被同日 14:52 的重复运行覆盖（`correctness_50t_3s.json` 现为 100.0%/93.3%/2.43）。原始**逐任务日志**仍完整保留，用以下命令可重建并可复核：

```bash
python experiments/reproduce/parse_correctness_log.py     # 期望输出：Table 6 cross-check: PASS
python experiments/verification/audit_table_numbers.py    # 期望输出：问题数 0（349 项）
```

> 路径已于 2026-09-17 目录重整后更新（`parse_correctness_log.py` → `reproduce/`，
> 审计脚本 → `verification/`）；计数由 280 项随论文修订增至 349 项。
> 更省事的做法是直接跑 `./reproduce.sh verify`（一键执行全部 8 审计 + 5 负向测试）。

两个脚本共同构成"论文每个数字 → 原始产物"的可执行审计链，详见 `docs/reviews/REVIEW_2026-09-15_round5_numeric_audit.md`。

---

## 九、2026-09-15 清理：模拟数据与旧数据已物理删除

按用户指令执行"删去所有旧的数据和虚拟数据"。**共删除 157 项、34.57 MB**，项目体积 137 MB → 101 MB。

### 删除前做了两件事（重要）

1. **模拟数据识别**：模拟产物的可靠指纹是 `avg_time ≈ 0.1 ms`——真实 LLM 调用不可能毫秒级。据此确认 A 类 7 项（`main_results.json`、`ablation_results.json`、`attack_results.json`、`comparison_results.json`、`ablation_enhanced_results.json`、`real_dataset_results.json`、`archive_simulation/`）。
2. **反向依赖检查**：对每个待删文件确认"没有被任何脚本读取"。这一步拦下了 **3 个复现链文件**——`merge_3seed.py`（生成 `multi_model_3seed_aggregated.json`，即论文表 4/7 的数据源）实际读取 `multi_model_compare_ablation_v2.json`、`_v3.json`、`mbpp_debate_fix.json`，它们**看似中间产物实为必需品**，已移出删除清单。

### 删除分类

| 分类 | 项数 | 体积 | 内容 |
|------|------|------|------|
| A 模拟数据 | 7 | 0.27 MB | CPU 模拟产物（`SimulatedWorker` 时代） |
| B 旧论文版本 | 1 | 5.23 MB | `papers/_old_versions_20260912/`（33 个 iclr2026 草稿文件） |
| C 旧提交包 | 7 | 12.75 MB | 5 个 tar.gz + `submission/` + `submission_final/` |
| D 被取代的旧真实结果 | 51 | 15.97 MB | Sep 5–7 DeepSeek 批次、旧 correctness 日志、多模型中间产物、`logs/autodl_runtime/`（13 MB GPU 运维日志） |
| E 一次性脚本/日志 | 63 | 0.22 MB | 根目录 15 个 orchestrator 脚本 + 36 个 `autodl_*.py` 诊断脚本 |
| F 旧实验报告 | 28 | 0.13 MB | `experiments/*.md` 过程报告 |

### 强制保留（删除清单的硬保护项）

- **论文依赖**：`full_bft_sweep_aggregated.json`、`multi_model_3seed_aggregated.json`、`correctness_50x3_log.txt`、`correctness_count_log.txt`、`correctness_50t_3s_run1_from_log.json`、`run_pairing_mcnemar.json`、`full_bft_sweep_{gsm8k,mbpp,mmlu}.json`、`sweep_*.log`
- **`tab:real_llm` 溯源**：`deepseek_math_fixed_20.json` + `deepseek_knowledge_fixed_20.json` + `deepseek_code_fixed_20.json`（三者均为 `deepseek_real` / `deepseek-chat`，逐任务 wall-clock 为真实 API 耗时）。该表**已纳入 `audit_table_numbers.py` 覆盖范围**（`check_real_llm()`，29 项检查）。溯源缺口已于第 9 轮审计闭合，见 §十。
- **复现链中间产物**：`multi_model_compare_ablation_v2.json`、`_v3.json`、`mbpp_debate_fix.json`、`multi_model_multiseed.json`
- **主实验脚本**：`experiments/multi_model_autodl/`（含 `multi_model_vllm.py`、`merge_3seed.py` 等）
- **审计链**：`audit_table_numbers.py`、`audit_prose_ranges.py`、`audit_theory_numerics.py`、`run_pairing_mcnemar.py`、`aggregate_full_sweep.py`、`parse_correctness_log.py`
- **评审记录**：`docs/reviews/REVIEW_*.md`、`docs/reviews/editorial_decision*.md`、本文件
- `experiments/datasets/`、`src/`、`.workbuddy/`

### 回滚方式

完整备份：`A2A_cleanup_backup_20260915.tar.gz`（15.9 MB，408 条目，gzip 校验通过）。
删除清单：`cleanup_manifest_20260915.txt`（含分类）。重建脚本：`build_cleanup_list.py`。

```bash
tar -xzf A2A_cleanup_backup_20260915.tar.gz    # 就地还原全部 157 项
```

⚠️ 本项目 git 仓库**无任何提交**，所有文件未被跟踪，故删除只能靠上述备份回滚。

### 清理后回归验证（全部通过）

```
audit_table_numbers.py   -> 280 项 / 0 问题
audit_prose_ranges.py    -> 0 不符
audit_theory_numerics.py -> 0 问题
pdflatex ×2              -> 0 错误 / 0 未定义引用 / 0 超宽>5pt
分页                     -> CONCLUSION 在 p9（主文 9 页），总 23 页
```


---

## 十、第 9 轮审计：`tab:real_llm` 代码行溯源闭合（2026-09-15）

### 10.1 发现（P0）

第 8 轮结束时 `tab:real_llm` 的两行代码任务（150 任务 / 100% / 3.80s 与 150 / 100% / `--`）是全表唯一未被机器校验、且来源未定位的数据。第 9 轮定位结果：

| 项 | 内容 |
|---|---|
| 来源文件 | `experiments/results/deepseek_code_50.json`（2026-09-05T21:48，`deepseek_real`） |
| 该文件状态 | **已于第 7 轮清理中删除**（清单分类 D「旧真实结果(被取代)」第 42 行） |
| 可恢复位置 | `A2A_cleanup_backup_20260915.tar.gz` |
| 数值对应 | `baseline_n4` → 150 任务 / 100% / **3796.36 ms = 3.80 s**（脚注省略的 `--` 即 `bft_n5_f1_s1` 的 **13.89 ms**） |

### 10.2 为何该来源不可用

`deepseek_code_50.json` 的逐任务 wall-clock 分布显示共识流水线空转：

| 配置 | 任务数 | 均值 | 中位数 | 全部 < 0.1 s |
|---|---|---|---|---|
| `baseline_n4` | 150 | 3.796 s | 1.427 s | 0/150（max 265 s，真实调用） |
| `baseline_n5` | 150 | 1.844 s | 1.475 s | 0/150 |
| `bft_n5_f1_s1` | 150 | **0.014 s** | 0.013 s | **150/150** |
| `bft_n6_f2` | 150 | **0.017 s** | 0.016 s | **150/150** |
| `attack_n5_strategic` | 150 | **0.014 s** | 0.014 s | **150/150** |
| `attack_n6_collusion` | 150 | **0.016 s** | 0.016 s | **150/150** |

四个 `f>0` 配置的 **600/600 任务全部在 9–43 ms 内完成**，比单次 DeepSeek API 往返（约 500 ms 起）快一个数量级 → 整条流水线未发生 LLM 调用。论文原脚注只声明「拜占庭 **worker** 返回预定义响应、接受率列不受影响」，但接受率由**验证器**决定，验证器同样空转，故该声明不成立。这与 §6.1 的 "**No simulation** … no simulated workers are used anywhere" 直接冲突。

交叉佐证：修复后的 `deepseek_code_fixed_20.json`（同一批配置、40 任务，验证器已改为真实调用）给出 `code_baseline_n4 = 30.0%`、`code_bft_n5_f1_s1 = 97.5%`；`large_scale_experiment_report.md` 记录的 MBPP 数值亦为 30.0/97.5。

### 10.3 另一个必须记录的问题：30% 不是拒绝率

核对 `accept_count / reject_count / error_count` 的分解后确认：

| 配置 | 总任务 | 接受 | 拒绝 | **报错** | `accept_rate` |
|---|---|---|---|---|---|
| `code_baseline_n4` | 40 | 12 | 0 | **28** | 30.0% |
| `code_baseline_n5` | 40 | 27 | 0 | **13** | 67.5% |
| `code_bft_n5_f1_s1` | 40 | 39 | 0 | 1 | 97.5% |
| `code_bft_n6_f2` | 40 | 39 | 0 | 1 | 97.5% |
| `code_attack_strategic` | 40 | 39 | 0 | 1 | 97.5% |
| `code_attack_collusion` | 40 | 38 | 0 | 2 | 95.0% |

**全表 `reject_count = 0`**，所有非接受项均为 API/harness 报错。因此「BFT 97.5% vs 基线 30–67.5%」是 harness 报错率之差，而非协议决策率之差；数学与知识两域 `error = 0`、40/40 全接受。

### 10.4 处置

采用「换成真实数据行、保留三域」方案，`tab:real_llm` 改为：

- 两行代码任务改用 `deepseek_code_fixed_20.json`（40 任务/行），接受率**按成功执行计**（12/12 与 39/39），以 `$^\star$` 标注；
- 新增表注披露：320 提交 / 291 完成 / 29 次 API 失败（代码基线 28 + 代码 BFT 1），并声明**无任何配置发生协议层拒绝**；
- 代码 BFT 行得以报告真实端到端延迟 9.01 s，原 `$^\ddag$` 省略脚注作废；
- 规模数字同步：`540 → 320`（行 316、613、617、632）、`990 → 770`（行 259）、"three domains" 保持、"eight protocol configurations" 保持。

改动后 `tab:real_llm` 的 8 行全部可回溯到现存文件，且已纳入 `audit_table_numbers.py`。

### 10.5 关于已删除文件的处置决定

`deepseek_code_50.json`、`deepseek_code_100.json`、`deepseek_code_results.json` **不再恢复到工作树**，以遵守「删去所有旧的数据和虚拟数据」的清理意图；其内容、测量结果与不可用原因记录于本节，原件保留在 `A2A_cleanup_backup_20260915.tar.gz` 中可随时取回。

### 10.6 新增机器校验（`check_real_llm()`）

`audit_table_numbers.py` 新增 29 项检查，覆盖 `tab:real_llm` 全部 8 行（Tasks / Accept% / Time 三列）与表注算术（320 / 291 / 29，及 28+1 拆分），并断言全表 `reject_count == 0`。负向测试（篡改 Accept%、Time、Total、Tasks 各一处）4/4 全部被捕获，确认检查非空转。

### 10.7 第 9 轮回归验证（全部通过）

```
audit_table_numbers.py   -> 309 项 / 0 问题   （第 8 轮为 280 项）
audit_prose_ranges.py    -> 0 不符
audit_theory_numerics.py -> 0 问题
pdflatex ×2              -> 0 错误 / 0 未定义引用 / 0 超宽>5pt
分页                     -> CONCLUSION 在 p9（主文 9 页），总 23 页
```

> 注：新增表注与第 4 条 Key Finding 曾把 CONCLUSION 推到 p10；已通过压缩 Limitations 段与 §6.4 从句收回 p9。

---

## 十一、第 10 轮审计：图件层（L7）首次纳入机器校验（2026-09-15）

本节补充第三节「全图数据源清单」——该节只列了**来源**，未校验**图与已审计表格是否互相矛盾**。第 10 轮补齐。

### 11.1 图件的独立重算路径

| 图 | 数据源 | 与哪张表比对 | 比对方式 |
|---|---|---|---|
| `fig:attack_resistance` | `full_bft_sweep_aggregated.json` + `multi_model_3seed_aggregated.json` | `tab:attacks` | 柱值 ∈ 表中同名区间（±0.06） |
| `fig:performance_comparison` | `full_bft_sweep_aggregated.json` | `tab:performance` | 共有配置逐格相等；表中每个配置必须出现在图中 |
| `fig:reputation_mechanism` | 无（示意图） | `alg:reputation` | 常数文本比对（`0.25 / 0.05 / 0.1 / 0.7 / 0.5`）+ 正文必须给出 `max(r_i, 0.3)` |

**图侧取值复用 `papers/generate_figures.py` 自身的取数函数**（`_load_sweep` / `_sweep_partition` / `_sweep_mean` / `_multi_get`），确保审计看到的是图**真正会画**的值；**表侧取值从 `iclr2027_main.tex` 解析**（`parse_performance_table()`），确保审计比对的是论文工件而非脚本里的副本。

### 11.2 披露对等性

`fig:attack_resistance` 的边界内 collusion 柱（$n{=}8,f{=}2,s{=}1$）**不在 $n{=}250$ 扫描中**，只来自 $n{=}90$ 的消融/对比部署。

| 工件 | 改动前 | 改动后 |
|---|---|---|
| `tab:attacks` 题注 | 已披露 "…from Table 5, $n{=}90$ per cell" | 不变 |
| `fig:attack_resistance` 题注 | ❌ 仅称 "$n{=}250$ four-model sweep" | ✅ 补 "…which come from the $n{=}90$ ablation/comparison deployment (cf. Table 10)" |

### 11.3 绘图脚本的静默失效（已修复）

| 位置 | 原行为 | 风险 | 现状 |
|---|---|---|---|
| `plot_attack_resistance` | 只在 collusion 一个组合断言非空 | 其余组合缺值→画成空柱（视觉像 0%） | 全覆盖硬断言 |
| `plot_performance_comparison` | `if not np.isnan(v)` 静默跳过 | 图形缩水但退出码仍 0 | 改为断言，缺值即失败 |

**可复现性已验证**：加固后重出，三张数据图文本指纹与重出前完全一致（`191356765e` / `1c00c9ba25` / `a5a0cdefff`）→ 加固未改变任何输出。

### 11.4 新增机器校验

- `experiments/audit_figures.py` —— **117 项**检查，四个检查器：攻击图区间内含 / 性能图逐格相等+覆盖 / 声誉图常数 / 披露对等+新鲜度（图 PDF mtime 必须晚于数据源）。
- `experiments/negative_test_figures.py` —— 4 情形注入，**4/4 捕获**。
- 关键设计：**黄金计数**（`GOLDEN_CELLS`）。`_sweep_mean` 取组内平均，**删格只会静默改变均值、不返回 `None`**，因此必须固定每组贡献单元数，否则删格不可见。

### 11.5 第 10 轮回归验证（全部通过）

```
audit_table_numbers.py    -> 309 项 / 0 问题
audit_theory_numerics.py  -> rc=0 全 OK
audit_prose_ranges.py     -> rc=0 全 OK
audit_figures.py          -> 117 项 / 0 问题   （新增）
negative_test_figures.py  -> 4/4 捕获           （新增）
引用                      -> 24 / 24 / 24 双向一致，.bbl 相对 .bib 新鲜
交叉引用                  -> 32 / 32
pdflatex ×2               -> 0 错误 / 0 未定义 / 0 超宽>5pt
分页                      -> CONCLUSION p9（主文 9 页），REFERENCES p10，总 23 页
图件可复现性              -> 三张数据图文本指纹重出前后一致
```

> 方法学教训：图件审计首测只捕获 2/4，两个「通过」的检查其实是空转的（平均掩盖缺失；期望值硬编码在审计脚本里）。详见 `REVIEW_2026-09-15_round10_figure_layer_audit.md` §6.3。

---

## 十二、第 11 轮审计：覆盖面盘点 + 算法伪代码层（2026-09-15）

本节补充第二~三节的「全表/全图清单」——该清单只列了**来源**，未核对**每个工件是否真的被某个检查器覆盖**。第 11 轮做了一次全量覆盖面盘点。

### 12.1 覆盖面盘点结果（工件 → 检查器）

| 工件 | 机器校验 | 盘点前状态 |
|---|---|---|
| `tab:baseline` / `tab:bft` / `tab:mmlu_sweep` | `check_baseline/bft/mmlu` | ✅ |
| `tab:ablation` / `tab:hetero_compare` | `check_ablation/compare` | ✅ |
| `tab:n8_scaling` + Welch 检验 | `check_n8/ttest` | ✅ |
| `tab:real_llm` | `check_real_llm`（第 9 轮） | ✅ |
| `tab:attacks` 区间**推导** | `check_attack_ranges`（已存在，文档字符串漏写致盘点误判） | ✅ |
| `tab:performance` / `fig:attack_resistance` / `fig:reputation` | `audit_figures.py`（第 10 轮） | ✅ |
| **`tab:complexity`** | 无 | ❌ → 本轮闭合 |
| **`tab:a2a_sim_comparison`（表 11）** | 无 | ❌ → 本轮闭合 |
| **`alg:reputation` 伪代码 vs 代码逐行** | 无 | ❌ → 本轮闭合 |

### 12.2 闭合的三项

| 项 | 缺陷 | 处置 |
|---|---|---|
| `tab:complexity` 容错列 | `3f+s < n−1` ⟺ n ≥ 3f+s+**2**，比定理严格强 1 | 改 `3f+s \leq n−1`；审计从**定理陈述程序化移项推导**后比对（非硬编码） |
| `tab:complexity` 轮数列 | "Rounds 1-3" vs 自家 `tab:performance` 实测 **2.6–4.5**（无故障基线 3.20/3.30 亦 >3） | 改 `2.6--4.5$^\ast$` + 题注脚注说明与 PBFT 的 "3" 口径差异 |
| `alg:reputation` 伪代码 | 与 `deepseek_worker.py::_update_reputation` **三处不一致**，含一处语义反转（伪代码按"对齐最终决策"判定投票正确性，代码按"提案真实质量"——攻击场景下同一验证者得到相反更新） | 重写为四分支 `ok←(v_i=ACCEPT)=c`；§4.2 / §4.4 / A.6.1 / `fig:reputation_mechanism` 四处同步 |
| `tab:a2a_sim_comparison` 题注 | "the f=1 rows use…" **漏覆盖第 1 行**（56.7/70.0 既非引用值也非 f=1 行） | 改 "all remaining cells (incl. the fault-free A2A-BFT row)…" |

**外部引用 41.6% 已联网核实成立**：Berdoz, Rugli, Wattenhofer, "Can AI Agents Agree?"（arXiv:2603.01213，ETH Zurich，ICLR 2026）——无拜占庭、全配置汇总的有效共识率。行 1 的 Δ 属跨口径比较（运行级终止率 vs 任务级决策率），表注已披露不可比，记录为残余。

### 12.3 新增机器校验

- `audit_table_numbers.py` 309 → **328 项**：`check_complexity()`（定理推导 + 实测轮数）、`check_a2a_sim()`（逐值溯源 + Δ 复算 + 跨域配对端点 + 外部引用披露断言）
- `audit_figures.py` 117 → **120 项**：声誉图加入 `0.02` 常数、算法结构标记 `ok`、**图-正文披露对等**（绘图脚本不得把未实现的选择权重画进"Algorithm 1 规则"面板）
- `negative_test_tables.py`（新增）：4/4 捕获

### 12.4 第 11 轮回归验证

```
audit_table_numbers.py    -> 328 项 / 0 问题
audit_figures.py          -> 120 项 / 0 问题
audit_theory_numerics.py  -> rc=0           negative_test_figures.py -> 4/4
audit_prose_ranges.py     -> rc=0           negative_test_tables.py  -> 4/4（新增）
引用 24/24/24（41.6% 联网核实） · 交叉引用 32/32
pdflatex ×2               -> 0 错误；CONCLUSION p9，REFERENCES p10，总 23 页
```

> 方法学教训：① 覆盖面盘点是收敛的必要步骤——第 9、10 轮都在"加深"已有维度，盲区藏在"没被任何脚本提到过"的工件里；② **审计工具的覆盖声明（文档字符串）必须与代码同步**，否则盘点自身产生假阳性（`check_attack_ranges` 即此例）；③ 见 `REVIEW_2026-09-15_round11_algorithm_layer_audit.md`。

---

## 十三、第 12 轮审计：定理可证性 + 交付代码层（2026-09-15）

本节补充前十二节均未触及的两类对象：**(a) 定理陈述本身是否可证**、**(b) 论文之外但被承诺交付的代码**。二者共同点——**缺陷不表现为数字错误**，对既有的 345+123 项校验天然免疫。

### 13.1 定理可证性（Theorem 5.1(i)）

定理假设明写拜占庭可 `equivocation`，原 claim 缺钳住**各副本分数差异**的量 ⇒ 不可证。补入**阈值间隙界**：

```
gap = θ_accept − θ_reject = 1.5(n−1) − 2.5f − s
边界处 n = 3f+s+1  ⇒  gap = 2f + 0.5s
拜占庭投票拔弄对单副本 φ 的影响 ≤ 1.5f（ACCEPT +1 / REJECT −0.5 不可兼得）
f+s > 0  ⇒  gap > 1.5f  ⇒  诚实副本不可能到达相反终态
```

claim (i) 已改写为**决策一致性**形式（只可能 ACCEPT vs PENDING 分歧，由提交广播/视图切换消解），同步改定理陈述（第 208 行）、证明梗概（212）、附录 Property 2（448）、Property 5（468）。

### 13.2 交付代码与论文公式的一致性

| 文件 | 位置 | 原实现 | 判定 |
|---|---|---|---|
| `deepseek_worker.py` | `_commit` | f=0 特例 `theta_accept = n_validators * 0.5`（注释却写"与论文一致"） | **P2**，已移除 |
| `distributed_worker.py` | `MultiGPUDistributedSystem._aggregate` L416 | `theta_accept = (n_total - self.f) * 0.5` | **P3**，已对齐 |
| `langgraph_integration.py` | `LangGraphA2ABFT.run_consensus` L397 | `theta = (n_total - self.f) * 0.5` | **P3**，已对齐 |

**影响面判定**：论文数据由 `experiments/multi_model_autodl/multi_model_vllm.py` 产出（第 434 行用正确公式 `self.n - 1 - 2*self.f - self.s`，无 f=0 分支）⇒ **已报告的全部实验结果不受影响**。后两处**不在数据路径上**（论文从未提及二者；`MultiGPUDistributedSystem` 仅在本文件 `__main__` 实例化），但被包 `__init__.py` 导出、且可复现声明承诺 "All source code" **无范围限定** ⇒ 仍修正，以消除 "reference implementation" 的歧义。

### 13.3 新增机器校验

- `audit_theory_numerics.py` 新增三节：**§6 决策一致性间隙**（n≤20、f,s≤8 全部边界内配置断言 `gap ≥ 2f+0.5s` 且 `> 1.5f`）、**§7 可执行探针**（构造 `Vote` 直接调用 `ConsensusLayer._commit`，5 例断言 `代码判定 == 论文规则`——**读源码不够，必须执行**）、**§8 交付代码阈值扫描**（全部 14 处 `theta_accept` 赋值，任何 `0.5` 多数式即报错 + 两处定点回归）
- `audit_figures.py` 120 → **123 项**：**题注解析取代 900 字符窗口启发式**（原窗口内若恰有别的 `n=90` 会静默通过）；**图件清单由 2 张扩至 5 张**（论文实际用 5 张，示意类图以 `generate_figures.py` 为新鲜度基准）
- `negative_test_theory.py`（新增）：3/3 捕获——**负向 7 把已修的 f=0 特例注入回去，可执行探针报告 `code=ACCEPT paper-rule=PENDING`**，证明探针确实能抓住促使它诞生的缺陷
- `audit_table_numbers.py` 新增 `check_promises()` 的 A800 数量扫描：**所有**提及 `A800` 的行都必须给出数量（R12-4）
- `negative_test_figures.py` 4 → **6 例**（表题注缺披露、示意图 PDF 缺失）

### 13.4 两处"空转"嫌疑的实证结果

| 嫌疑 | 结论 |
|---|---|
| 图件存在性只守 2 张 | **部分成立**（覆盖缺口），已扩至 5 张 |
| 题注披露检查空转 | **证伪**——第一次实证"坐实"，复查发现删的是 `tab:bft`（290）而检查对象是 `tab:attacks`（737），**测试瞄错了对象**；重做后两张题注各自被正确捕获 |

### 13.4b R12-4（P3）：可复现声明未给出 GPU 数量

触发点是一个非审计问题（"1 卡还是 2 卡才够？"）——为回答它而清点部署资源需求时暴露的承诺面缺口。

| 项 | 内容 |
|---|---|
| 缺陷 | 主文 **Reproducibility Statement**（第 258 行）只写 "on NVIDIA A800-SXM4-80GB GPUs"，**无数量**；数量仅见于 §6.4（"two A800 GPUs"）与附录（"Two NVIDIA A800-SXM4-80GB GPUs"） |
| 后果 | 复现者读的是 Reproducibility Statement，不会去附录找硬件数量；**只有 1 张卡的人会照做并失败** |
| 为何不是小事 | 四模型 FP16 权重合计 ~78 GB（Llama 16 + InternLM 16 + Qwen 15 + DeepSeek-V2-Lite MoE 31），单卡 80 GB 仅余 2–3 GB 放 KV cache 与 CUDA 上下文；部署自身 utilization 预算合计 **1.34 > 1.00**（超 34%）；`multi_model_experiment.py:477` 另有硬检查 `device_count() < 2`。**瓶颈是权重总容量而非算力**（每实例仅 0.28–0.30）⇒ 不是"跑慢"，是"起不来" |
| 处置 | 第 258 行改为 `on **two** NVIDIA A800-SXM4-80GB GPUs`；新增全库 A800 数量扫描；`negative_test_tables.py` 负向 5 验证（CAUGHT） |

### 13.5 第 12 轮回归验证

```
audit_table_numbers.py    -> 348 项 / 0 问题
audit_figures.py          -> 123 项 / 0 问题
audit_theory_numerics.py  -> rc=0（含新增 §6/§7/§8）
audit_prose_ranges.py     -> rc=0（No numeric mismatches）
negative_test_figures.py  -> 6/6 · negative_test_tables.py -> 5/5 · negative_test_theory.py -> 3/3
pdflatex ×2               -> 0 错误；CONCLUSION p9，REFERENCES p10，总 23 页
PDF 抽查                  -> 定理小结/间隙界/四档算法/中性漂移/三处两卡表述全 FOUND；
                             three-tier、prevented in expectation 已清除
```

**机器校验总计 471 项（348 + 123），负向测试 14/14。**

> 方法学教训：① 数值审计对"命题过强"与"非数据路径代码背离"天然免疫——审计维度必须随缺陷类型扩张，而非只加深同一种；② **失败详情必须区别于成功详情**，否则检查本身就是空转；③ **实证也会瞄错对象**——断言"检查失效"前先确认改的正是该检查读取的文本；④ 可复现声明没有范围限定时，它的覆盖面就是整个交付仓库；⑤ PDF 抽查的"探不到"可能是字形编码假象（圆括号为控制符），命中的子串也可能是**正当披露句**；⑥ **"硬件规格"一项不能只写型号，必须写数量**——而暴露它的竟是一个非审计的提问。详见 `REVIEW_2026-09-15_round12_theory_code_layer_audit.md`。

---

## 十四、第 17 轮审计：数据完整性盘点 + 旧数据/模拟数据清理（2026-09-17）

本轮不是"再审一遍论文数字"（那 349 + 123 项本周已全绿），而是**审"数据目录本身"**：
仓库里还留着什么、留下的每一项是否真的指向它声称的东西、有没有"脚本看起来能用、
一跑就炸"的失效。结论是**发现 4 处真问题**，其中 1 处是审计工具自身的停摆。

### 14.1 清理结果（用户指令："删除旧的数据和模拟数据"）

删除 **35 项 / 1.75 MB**，分四类：

| 分类 | 项数 | 体积 | 内容 | 判定依据 |
|------|------|------|------|---------|
| A 模拟数据 | 16 | 0.35 MB | `results/archive_simulation_era/`（15）+ `logs/full_experiment.log` | 指纹：`avg_time` **40–80 µs**，真实 LLM 调用不可能微秒级；日志明文"模式: 模拟推理" |
| B 冗余副本 | 1 | 0.15 MB | `datasets/mmlu_4subjects.json` | 与 `mmlu_3subjects.json` **md5 完全相同**（`3b58e494…`） |
| C 被取代/零引用 | 8 | 0.72 MB | `comparison_full.log`、`comparison_math.log`（Sep 7–8 旧对比实验，20 任务×2 种子）、`correctness_50t_3s.json`、`multi_model_compare_ablation_final.json`、`merge_final.py`、4 个无引用日志 | 反向依赖检查：**零代码读取方** |
| D 孤岛图件 | 9 | 0.58 MB | `acceptance_rates.*`、`fault_tolerance_surface.*`、`correctness_*.png`×4、`n8_scaling_results.png` | 论文只 `\includegraphics` 5 张图，这 9 个既不在论文里、也无活跃函数生成 |

**硬保护项**（一律不删）：`full_bft_sweep_aggregated.json`、`multi_model_3seed_aggregated.json`、
`full_bft_sweep_{gsm8k,mbpp,mmlu}.json`、`multi_model_compare_ablation_{v2,v3}.json`、
`mbpp_debate_fix.json`、`multi_model_multiseed.json`、`correctness_*log.txt`、
`correctness_50t_3s_run1_from_log.json`、`reputation_{ablation,vote_stream}.json`、
`run_pairing_mcnemar.json`、`deepseek_*_fixed_20.json`（`tab:real_llm` 三处溯源）、
`experiments/legacy/`（文档化的历史存档，且被 `env/run_compare.sh`、`run_experiment.sh` 调用）。

> `merge_3seed.py` 读 `multi_model_compare_ablation_{v2,v3}.json` + `mbpp_debate_fix.json`
> + `multi_model_multiseed.json`——这四个**看似中间产物实为论文表 4/7 的必需输入**，
> 第 15 轮清理的教训（"看似中间产物实为必需品"）在本轮再次拦下它们。

备份 `A2A_cleanup_backup_20260917.tar.gz`（35 条目 / 0.66 MB，逐项核对齐全）·
清单 `docs/cleanup/cleanup_manifest_20260917.txt`（含每项字节数与 md5）。

### 14.2 发现并修复的 4 处真问题

| # | 问题 | 性质 | 处置 |
|---|------|------|------|
| 14-1 | `datasets/dataset_summary.json` 的 `total_tasks: 2607` **是错算** | 机器可读文件带着已知错误数字，而 `DATASET_README.md` 只写了"勿再引用"——文件本身没改 | **修根因**：`download_datasets.py` 的 `total_tasks` 原用 `glob("*.json")` 求和，任何多余文件都会静默计入（1319+164+500+312+**312 冗余副本**=2607）。改为声明式 `DATASET_REGISTRY`，新增数据集必须显式登记；摘要文件重写为 `paper_total_tasks: 2131` / `all_datasets_total_tasks: 2295` |
| 14-2 | `docs/cleanup/cleanup_manifest_20260915.txt` **是 0 字节** | 第 15 轮清理的删除清单/回滚记录为空——§九 却把它当作可回滚凭据引用，审计链断点 | **重建**：从同轮次备份包读出 378 个文件条目，按原 A–F 分类规则重新归类写入（26,407 字节）。根因已在 `build_cleanup_list.py` docstring 有记录（脚本移到 `docs/cleanup/` 后 ROOT 解析失效、清单恒为空），脚本本体已修，但它无法事后重生成 |
| 14-3 | `papers/generate_figures.py` 三个函数读**已被删除**的数据文件 | 死代码，一旦调用即 `FileNotFoundError`；其中 `plot_fault_tolerance_surface()` 更严重——它**不读任何数据**，用 `honest_ratio * 95` 合成"接受率"热力图（合成图，与真机测量无关） | 移除 `load_experiment_data` / `plot_acceptance_rates` / `plot_fault_tolerance_surface`，并清掉两个只接不用参数的伪装。`main()` 从未调用它们 |
| 14-4 | **`negative_test_tables.py` 已整体停摆**（表格层负向验证失效） | 其负向 3 的锚点 `$+15.1$ / $+28.4$ pp` 是 `tab:a2a_sim_comparison` 第 1 行的 Δ；R15 判定该行跨源不可比、移除 Δ 列后锚点消失，`assert old in s` 直接抛异常**终止整个脚本** → 负向 4/5 再没跑过。即"表格层负向测试 5/5"这一结论此前已不成立 | ① 重锚到仍存在的 f=1 Δ（`$+12.2$ pp`）；② `case()` 不再因锚点失效而中断，改记 `STALE ❌` 并继续——**锚点失效本身就是失败，必须被看见**。修复后 5/5 |

### 14.3 新增机器校验：`audit_paths.py` §5

14-3 暴露了 L9 路径层的盲区。原有四节**都看不到它**：

- §1 只看**模块级**常量——`EXPERIMENTS` 这个数据目录常量真实存在，故 §1 全绿；
- §2 冒烟指纹看"是否由脚本自身目录推导"——该常量从项目根推导，写法正确，不触发；
- 缺陷藏在**函数体内联拼接的文件名**里。

新增 **§5：读取型 `open()` 的数据文件必须真实存在**。要点：

- 只查**读模式**（`open`/`io.open`/`codecs.open`；`w/a/x/+` 跳过，输出文件尚不存在属正常）；
- 取文件名可能在第 1 参数，也可能在 `os.path.join(...)` 末位；只收不含路径分隔符、且扩展名属数据类的字面量；
- 与仓库文件名索引比对，并并入 `.gitignore` 里出现过的名字（被忽略的文件"不在仓库"是正常状态）。

**校准过程本身有教训**：首跑报 2 条假阳性（`gsm8k_test.json`、`mbpp_test.json`），
原因是索引函数照抄了本层的 `SKIP_DIRS`，而它含 `datasets`——正是数据文件的存放处。
索引只需文件名、不读内容，不该沿用"不遍历数据目录"的约束。

负向测试同步扩为 **6/6**：新增负向 6 把 `mbpp_test.json` 篡改成
`mbpp_test_DELETED.json`，确认 §5 报警；干净状态断言 §5 计数 > 0（防空转）。

### 14.4 清理是惰性的（实证）

删除后重跑 `papers/generate_figures.py`，与"清理前形态的还原副本"逐像素比对：

| 图 | 尺寸一致 | 最大通道差 |
|---|---|---|
| consensus_flow / architecture / performance_comparison / reputation_mechanism / attack_resistance | 是 | **0** |

5/5 逐像素完全一致 ⇒ 移除的函数确实从未参与任何输出。
（文件 md5 会变——matplotlib 往 PDF 里写 `CreationDate`——所以必须比像素/文本指纹，不能比文件哈希。）

### 14.5 交付包同步

`supplementary_material.zip` 原包（146 文件 / 1.03 MB）**打包了模拟期数据**
（`archive_simulation_era/` 15 项）、冗余副本 `mmlu_4subjects.json` 与已删函数产物。
已重建为 **129 文件 / 0.87 MB**，核验无模拟期/冗余/孤岛项。
若不同步重建，9-25 提交的包仍会带着模拟数据。

### 14.6 第 17 轮回归验证（全部通过）

```
audit_table_numbers.py    -> 349 项 / 0 问题
audit_figures.py          -> 123 项 / 0 问题
audit_paths.py            -> 0 问题（新增 §5：8 项读取型 open 检查）
audit_prose_ranges.py     -> 0 不符（含 K 段守卫）
audit_theory_numerics.py  -> rc=0
audit_revision_layer.py   -> 52 项 / 0 问题
audit_decision_neutrality.py -> 9 项 / 0 问题
audit_reputation_fidelity.py -> FIDELITY_OK
verify_mbpp_subboundary.py   -> 完成并重写核验 JSON
负向测试                  -> 6/6 + 6/6 + 5/5 + 3/3 + 8/8 = 28/28
pdflatex ×2               -> 0 错误 / 0 未定义引用 / 0 超宽
分页                      -> CONCLUSION p9（正文 9 页），REFERENCES + REPRODUCIBILITY 自 p10 起，总 29 页
图件惰性验证              -> 5/5 逐像素一致（最大通道差 0）
凭据自检                  -> 全仓库无明文密钥（SSH/API 走 A2A_SSH_* / DEEPSEEK_API_KEY 环境变量）
```

> 方法学教训：① **审计的目标不该只是"论文里的数字"，还包括"数据目录本身"**——本轮
> 全绿的 472 项机器校验对"脚本读一个已不存在的文件"完全免疫；② **"负向测试全过"要
> 能被推翻**——一个陈旧锚点就足以让整套负向测试静默停摆，而它此前一直显示为通过；
> ③ 锚点失效必须记为**失败**而不是异常，否则它会把同一批里的其余用例一起挡掉；
> ④ **新增检查的假阳性要当作自身缺陷查**——§5 首跑的两条误报源于照抄了不该照抄的
> `SKIP_DIRS`；⑤ 判断"删除是否安全"不能比文件哈希（PDF/PNG 内嵌时间戳），要比**像素或文本指纹**；
> ⑥ **报告"已删除"却不同步交付包**等于没删——补充材料包会原封不动把模拟数据交上去。
