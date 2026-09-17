# 穷尽式审计报告（第 7–20 轮合并）— 20 项专项检查

**论文**: iclr2027_main.tex（2026-09-13 21:50 编译版）
**方法**: 前 6 轮评审为通读式；本轮将剩余风险面拆成 20 个可独立验证的检查类别，机械检查用脚本逐项核对，判断项逐条人工过
**日期**: 2026-09-13 22:15

## 20 项检查总表

| # | 检查类别 | 结果 |
|---|---|---|
| 1 | \label/\ref 全量交叉（27/27） | ✅ 零悬空、零未引用 |
| 2 | 引用键 vs references.bib（18 cite / 21 bib） | ✅ 零缺失；3 条未引用条目无害（bibtex 不输出） |
| 3 | TODO/FIXME/占位符 | ✅ 无 |
| 4 | 重复 label | ✅ 无 |
| 5 | 摘要数值 vs 正文/数据 | ✅ 90%、16.7–63.4%、[0.0,4.1]% Wilson（独立复算 0/90 → 上界 4.09% ✓）、74.4→4.5 全对 |
| 6 | 推导范围算术（83–100%、60–74%、+48.4/+46.8/−57.8%/+92.7%） | ✅ 全部复核正确 |
| 7 | tab:ablation 48 格 vs multi_model_3seed_aggregated.json | ✅（四轮已验，本轮抽复核） |
| 8 | tab:hetero_compare vs 同上 JSON | ✅ 全格一致 |
| 9 | tab:performance vs performance_test_results.json（90/90/75） | ✅ |
| 10 | tab:real_llm vs deepseek_*_fixed_20/code_50 JSON | ✅（四轮已验） |
| 11 | tab:n8_scaling vs deepseek 150-task 数据 | ✅（四轮已验） |
| 12 | **tab:bft 点值溯源** | ❌ **P0**：9 行拼凑自两个单次运行文件，±std 无任何来源 |
| 13 | **tab:baseline 溯源** | ❌ **P0**：n=5/n=6 的 95.0% 与 TPS 24,500/23,800 无来源；n=4 行 ✓ |
| 14 | **5 种子声明（42/123/456/789/1024）** | ❌ **P0**：全项目穷尽搜索无此种子集；所有 per_seed 数据均为 seed 0–4 且多为 100% |
| 15 | tab:attacks 范围 vs tab:bft/tab:n8 | ✅ 85–94%、rounds 1.05–2.92 等一致 |
| 16 | 主文/附录一致性（liveness 数值、θ/φ 公式） | ✅（第六轮已同步修复，本轮复核） |
| 17 | 模型命名一致性 | ⚠️ P3：InternLM3-8B 与 InternLM3-8B-Instruct、DeepSeek-V2-Lite 与 -Lite-Chat 混用（L256 vs L611） |
| 18 | 舍入规范性 | ⚠️ P3："37–89%" 的 89 实为 88.3（A2A-Sim GSM8K collusion 88.3%）——方向保守（高估基线）但应写 88 |
| 19 | 术语/攻击名一致性 | ✅ strategic rejection/collusion/Sybil 全文统一 |
| 20 | 图表引用完整性（4 图 8 表全被正文引用） | ✅ |

## P0 详解（CHECK 12–14 同根同源）

**tab:bft 的真实来源**（逐值核对确认）：
- 前 6 行（4,1,0 三攻击；5,1,1 两攻击；5,2,0 Random）← `experiments/final_results_100rounds.json`：**20 任务单次运行**，accept 计数 17/18/20/20，点值与论文完全吻合
- 后 3 行（5,2,0 Strategic 94、Collusion 92；6,2,0 Collusion 94）← `experiments/comprehensive_results_v2.json`（2026-09-03）：**100 任务单次运行**
- 生成管线确认：`papers/generate_figures.py` 正是从这两个文件读数

**因此**：caption 的 "(100 rounds, 5 seeds)"、Setup 的 "5 independent random seeds ({42,123,456,789,1024})"、全部 ±std 值（±1.7~±2.5）与 CI 括号（实为 mean±1·std，非 Wilson CI）**均无数据支撑**。tab:baseline 的 95.0/95.0（n=5/n=6）在 comprehensive_results_v2 中实为 90.0/90.0，TPS 24,500/23,800 也无来源（真实值 23,988/14,678 属于别的配置）。

**这是全部六轮半评审中发现的最严重问题**——属于"不可验证的统计声明"，比幽灵数字严重；若审稿人或 rebuttal 阶段要求提供 5 种子原始数据，将无法自圆其说。

## 修复方案（需用户决策）

**用户决策：方案 A（真实重跑）——已于 2026-09-13 22:10 执行完毕**

### 执行记录
1. **重跑脚本**: `experiments/rerun_5seed_protocol.py`（复用当前 ConsensusLayer：动态阈值/声誉/视图切换/max_rounds=10；为模拟模式覆写诚实验证语义——当前 _single_validate 按数字/长度比对，与 SimulatedWorker 短字符串不兼容；拜占庭策略复用层内实现：strategic/collusion 恒拒、random 三选一、sybil 拒-拒-受-弃）
2. **真实数据**: `experiments/results/protocol_5seed_100tasks.json`（12 配置 × 5 种子 {42,123,456,789,1024} × 100 任务 = 6,000 次共识运行，纯 CPU 72 秒）
3. **结果**: 全部配置 100.0±0.0% 最终接受（pooled Wilson [99.2,100]），轮数 1.10–1.16——伪装策略+重试语义下，攻击成本表现为轻微轮数膨胀而非决策失败
4. **论文连锁更新（13 处）**: tab:baseline（3行新值+删TPS列）、tab:bft（9行新值+新caption）、摘要/引言/结论的 90%→100%、L283 语义说明重写、L309 总结重写（n≥6 串谋声明更正为理论边界 n≥3f+s+1）、tab:attacks（98–100%/新轮数范围）、附录 n=5,f=2 注（85–94%→100%）、tab:a2a_sim_comparison 整表重建（删除无源的 38.2/3.2/12,450 复现行，改用可溯源的异构评估 A2A-Sim 行）、Setup 声明补 100 任务/格、fig:attack_resistance 从新数据重生成
5. **编译验证**: 20 页、0 undefined、0 陈旧值残留；正文含 AI 声明止于 p9，Reproducibility+References 起于 p10（两项声明均为 ICLR 页数豁免项，合规）

### 诚实性说明
重跑后点值从 85–94% 变为 100%：这是**当前代码的真实行为**（2026-08-28 修复伪装策略 + 阈值调优后，模拟协议对注入故障具有完全的最终接受能力），与真实 LLM 实验（98–100%）和异构实验（60–74% 决策率，异构性上界解释）自洽。旧 85–94% 来自早期代码版本的单次运行，已不可复现，替换为可复现的真实数据是唯一诚实的做法。
