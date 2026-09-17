# 审计体系说明（AUDIT）

> 语言 / Language：**简体中文** ｜ [English](AUDIT.md)
>
> 本文件是 [AUDIT.md](AUDIT.md) 的中文存档。

本仓库对论文的每一个数字都做**可重算的核验**。本文档说明审计分了哪几层、
每层查什么、如何确信审计本身不是空转。

> **关于文中出现的项数（"349 项"、"8/8" 之类）**
> 它们随用例增减而变，写进文档就有过期的风险——而判定只看退出码，
> 所以过期的数字能长期不被发现（已实测发生：`reproduce.sh` 的标签曾停留在
> "注入路径缺陷 6 项"，而脚本实际已扩到 8 项）。
> **权威计数始终是 `./reproduce.sh verify` 的实时输出**：它由 `extract_count()`
> 从各脚本的实际输出里读，不写死。本文档与 README 中的数字若与之不符，
> **以实时输出为准**，并把不一致的那一处修掉。

---

## 1. 为什么要做审计

论文里最容易出错、也最难被发现的地方不是算法，而是**数字与它声称的来源之间
的落差**：表格里的值是手抄的、区间是拍的、题注的样本量口径与正文不一致、
代码里的阈值公式与论文写的不一样。这类问题在"读一遍"时通常看不见，
因为**每个数字单独看都合理**。

因此本仓库的核验原则是：**能从原始数据重新算出来的，就不要相信抄写**。

---

## 2. 九层审计模型

| 层 | 名称 | 查什么 |
|----|------|--------|
| L1 | 表格数值 | 论文表格中的每个数字 vs `experiments/results/` 原始数据重算结果 |
| L2 | 公式代数 | 表格中由公式推导的列（如容错列）是否与定理代数等价 |
| L3 | 外部真实性与机制兑现 | 引用的外部方法数据来源是否标注；声明的机制是否真的实现 |
| L4 | 正文区间 | 摘要/正文/结论中的数值区间、百分比、样本量是否与表格一致 |
| L5 | 方法学承诺 + 定理假设完备性 | 承诺的实验条件（种子数、任务数）是否真的执行；定理假设是否覆盖结论所需条件 |
| L5b | **定理可证性** | 结论能否从假设推出（假设允许的行为是否足以否证结论） |
| L6 | 来源与出处 | 数据文件 → 生成脚本 → 论文位置的链路是否闭合 |
| L7 | 图表层 | 图的数据来源、题注披露（如 n=90）、PDF 与生成脚本的新鲜度 |
| L8 | **承诺面与交付代码层** | 论文中"All source code / 复现性声明"所承诺的内容，交付物是否真的满足 |
| L9 | **路径解析层** | 交付脚本里的每个路径常量（数据目录、`sys.path` 目标）是否指向真实位置 |

> L5b、L8、L9 是本项目审计中最后补齐的三层：前者管"理论是否成立"，
> L8 管"交付物是否兑现承诺"，**L9 管"交付物是否还能跑"**。

### 为什么会有 L9

2026-09-15 的目录重组把脚本搬了家。搬完之后：

- `experiments/reproduce/parse_correctness_log.py` 与 `run_pairing_mcnemar.py`
  用 `os.path.join(HERE, "results", ...)` 定位数据目录。脚本在 `experiments/` 下时
  HERE 正好是结果目录的父目录；搬进 `experiments/reproduce/` 后，HERE 变了，
  路径指向**不存在的** `experiments/reproduce/results/`。这两个脚本正是论文
  `tab:n8_scaling` 与 McNemar 配对检验的数据来源——按复现文档走到 Pipeline D 会直接报错。
- `docs/cleanup/build_cleanup_list.py` 用 `ROOT = dirname(abspath(__file__))`
  定位项目根，搬进 `docs/cleanup/` 后 ROOT 变成 `docs/cleanup`，
  `add()` 命中不了任何路径，删除清单**恒为空且不报错**。

当时的验收只验证了 `sys.path` 插入目标，**完全没覆盖"数据目录常量"这一类**，
于是"全绿"掩盖了三个脚本已经跑不起来。L9 就是补上这个盲区。

---

## 3. 审计脚本

### 3.1 `audit_table_numbers.py` —— 349 项

| 函数 | 覆盖对象 |
|------|----------|
| `check_baseline()` | `tab:baseline` |
| `check_bft()` | `tab:bft` |
| `check_mmlu()` | `tab:mmlu_sweep` |
| `check_ablation()` | `tab:ablation` |
| `check_compare()` | `tab:hetero_compare` |
| `check_n8()` | `tab:n8_scaling` |
| `check_ttest()` | 配对 t 检验统计量（由原始数据重算） |
| `check_attack_ranges()` | `tab:attacks` 的区间 = 来源行的 min/max |
| `check_real_llm()` | `tab:real_llm`（含提交数/完成数/API 失败数守恒） |
| `check_complexity()` | `tab:complexity` 容错列与定理等价；轮数列与实测 min–max 一致 |
| `check_a2a_sim()` | `tab:a2a_sim_comparison` 的 Δ 算术与外部数据标注 |
| `check_promises()` | **L8**：复现性声明中的硬件/规模承诺是否与正文、附录一致 |

数据源：`full_bft_sweep_aggregated.json`、`multi_model_3seed_aggregated.json`、
`correctness_50t_3s_run1_from_log.json`、`deepseek_{math,knowledge,code}_fixed_20.json`。

### 3.2 `audit_figures.py` —— 124 项

- 五张图的**存在性**与**新鲜度**（内容指纹口径：`figures/.figsource.json` 记录
  生成脚本的逻辑指纹与各数据文件 md5；改一行注释不会误报陈旧，改数据必报警）
- 图题注与表题注中的样本量披露（例如 n=90 必须出现）
- 图数据点与聚合 JSON 的逐点比对

覆盖全部 5 张论文图（`consensus_flow`、`architecture`、`reputation_mechanism`、
`performance_comparison`、`attack_resistance`）。

### 3.3 `audit_theory_numerics.py`

- §6 **决策一致性余量**：对所有 `n ≤ 20`、在安全边界内的配置，验证
  `gap ≥ 2f + 0.5s` 且 `gap > 1.5f`（Byzantine 选票翻转上限）
- §7 **可执行探针**：直接调用参考实现的 `ConsensusLayer._commit`，用 5 组
  `(n, f, s, A, R)` 检查其决策与论文规则一致（含 `(4,0,0,A=2,R=1) → PENDING`）
- §8 **交付代码阈值扫描**：递归扫描 `src/` 下所有 `.py`，确认不存在与论文阈值
  规则相矛盾的写法

### 3.4 `audit_prose_ranges.py`

正文/摘要中的数值区间与表格的一致性，以及"表格未展示的单元格"是否被恰当地
限定（避免"覆盖率被读成 100%"）。

### 3.5 `audit_paths.py`（L9）—— 文件类 37 / 目录类 119 / 冒烟 160 / `sys.path` 64 / `open()` 8 / 文档命令 79

> 这些计数随文件增删而变，**不是固定值**：脚本本身会打印当次实测值，
> 判断标准是"各项均 > 0 且问题数为 0"，不是"数字等于某个历史值"。
> 修改本行时请以 `audit_paths.py` 的实际输出为准。

| 节 | 检查 |
|----|------|
| §1 | 项目内每个路径常量的**父目录必须存在**（写文件的路径允许目标文件尚不存在，但目录必须先有） |
| §2 | **冒烟指纹**：路径是否**由脚本自身位置推导**出 `<脚本目录>/<数据目录名>/`——代码目录下不会挂数据目录 |
| §3 | 所有被插入 `sys.path` 的目录必须存在 |
| §4 | 诊断：依赖 CWD 的相对路径常量、AutoDL 侧 POSIX 路径（不判失败） |
| §5 | 读取型 `open()` 的数据文件必须真实存在（2026-09-17 新增） |
| §6 | 文档/脚本里给出的 `python\|bash <路径>` 命令必须指向真实存在的脚本（2026-09-17 新增） |

> **§6 的由来**：复现者不会读源码，只会照抄 `README.md` / `REPRODUCTION.md` 里的命令。
> 第 19 轮目录重整后，实测**包内仍有 5 处文档写着旧路径**（把审计脚本写成挂在
> `experiments/` 之下，而它已迁至 `experiments/verification/`），照抄即
> `No such file or directory`。而 §1–§5 全部只扫描 `.py`，对此完全无感。
> §6 覆盖 `.md / .sh / .txt`；`docs/reviews/` 作为"当时状态"的历史快照不参与判定。
>
> 注意：本节的说明文字本身也不能出现**字面可执行的失效命令**——§6 会把
> 文档中作为反面例子引用的命令一并判定为失效（实测：本节初稿即被 §6 拦下）。
> 描述历史缺陷时请用描述性措辞，不要粘贴原始命令行。

判"由脚本自身位置推导"看的是**推导来源**而不是**恰好同名**：
`papers/generate_figures.py` 里 `ROOT/papers/figures` 恰好等于"脚本目录/figures"，
但它由项目根推导，属正确写法；真正的缺陷是从脚本自身目录推导。二者混淆会产生假阳性。

实现上有三条硬约束（都是踩坑换来的，见 `audit_paths.py` 模块 docstring）：

1. **绝不 `exec`。** 早期版本用 `exec` 逐条执行顶层语句来取常量值，结果把
   `mbpp_debate_fix.py` 的实验主体也执行了，真实打出 API 请求并挂住进程。
   现在改为纯 AST **符号求值**，只认 `os.path.*` / 字符串拼接 / f-string /
   `Path / "x"` / `os.environ.get` 默认值这一小类表达式，求不出即 UNKNOWN。
2. **识别"向上查找项目根"的三种写法**（`while` 里 `X = dirname(X)`、
   `while True` 里 `if exists(_cur/marker): X = _cur; break`、
   `def _find_root(start) → return cur` 后 `ROOT = _find_root(__file__)`）。
   只认其中一种，另外两种会被算成"脚本目录"，一次产生 4~12 条假阳性。
3. **防空转。** 文件类/目录类/冒烟/`sys.path` 四类计数各有独立计数器，
   任一项为 0 即判失败。

### 3.6 `audit_reputation_fidelity.py` —— 保真度比对

`experiments/reproduce/reputation_ablation.py` 的 `ReputationTracker` 声称是
"论文 Algorithm 1 的忠实实现"。**声称不能自证**，所以本审计把
`src/a2a_bft/deepseek_worker.py:982-1002` 的罚则片段**逐行照搬**成独立的
`released_update()`，再让两者在**同一随机投票序列**上逐轮比对 `r_i`。

| 项 | 值 |
|----|-----|
| 比对步数 | 12000（300 条序列 × 40 步） |
| 不一致步数 | 0 |
| 升级罚触发（参考实现 / 本实现） | 5180 / 5180 |

结论：追踪器忠实复刻了发布实现，**包括** suspect 计数达阈值时那一次额外的
`max(0.3, r - 0.2)`。这直接把论文里一处内部矛盾变成了可裁决的问题：
§4.3 说参考实现 "escalates penalties for persistent misbehaviour"，而附录说
suspect 计数器 "warnings only; penalties are fixed per tier"。
**代码支持前者**，实测的 `escalated` 计数是唯一权威口径。

> 这个审计也暴露过自己的一个 bug：`self.suspect` 最初只被声明和读取、
> 从未自增，导致 `0 >= 3` 恒假、升级罚永不触发——即"忠实实现"里悄悄少了
> 一整条罚则。**保真度必须用独立实现对照，不能靠读代码确认。**

#### 3.6.1 投票字母表必须包含 ABSTAIN（2026-09-17 修正）

上面那张表的升级罚触发数一度是 `7123 / 7123`。改为 **`5180 / 5180`** 不是实现
变了，而是**随机投票字母表**变了：原审计只掷 `accept` / `reject` 两种票，而线上
真实票流（`reputation_vote_stream.json`，2{,}461 票）里有 **148 票是 ABSTAIN**
（`ABSTAIN/False` 104 + `ABSTAIN/True` 44）。加入弃权后，"奖励分支"会在更多轮被
重置，升级计数器随之后移，绝对次数下降但两边**仍然逐轮一致**。

同一轮修正还改掉了一处**只在弃权上暴露的语义陷阱**：`reputation_ablation.py`
原先用

```python
ok = (v == 'accept') == c        # 错
```

而发布实现（`deepseek_worker.py:975-980`）用的是析取：

```python
ok = ((v == 'accept') and c) or ((v == 'reject') and (not c))   # 对
```

两者在 `accept` / `reject` 上完全等价，**只在 ABSTAIN 上分歧**：当 `c = False`
（提案错误）时，`(v == 'accept') == c` 会把 **ABSTAIN 判成"投对了"**，从而可能
拿到 `+0.1` 奖励。论文 Algorithm 1 的原文正是这个错写法。已同时修正代码、论文
Algorithm 1 与 §4.4 的说明，并按修正后的语义**重测了整张声誉表**（正文
"$1{,}186$ of $1{,}305$"，原为 $1{,}217$ of $1{,}305$）。

> 教训与 3.6 相同但更尖锐：保真度审计不仅要对照**罚则**，还要对照**投票字母表
> 与真值定义**。只覆盖两种票的审计，对"弃权算不算投对"这个问题是盲的。

### 3.7 `verify_mbpp_subboundary.py` —— 越界错误提交的离线复现

论文报告：在执行验证域（MBPP）内，**越界配置**（$n{=}5, f{=}2$）出现
$5.6$--$9.6\%$ 的错误提交，而边界内一律 $0.0\%$。这组数字曾被质疑"在代码域
数学上不可能"（执行验证器会拦住任何错误代码）。为了把"可能/不可能"从断言
变成可复现的事实，本脚本**不调用任何 LLM**，在本地重建两条路径：

- `A2ABFT`（严格语义）：拜占庭验证者按代码域规则投票；
- `A2ABFSybil`（复刻 `full_bft_sweep.py` 的 Sybil 层）：拜占庭验证者以
  75% / 25% 投 REJECT / ACCEPT。

两条路径都让"提案"以 `P_MODEL = 0.70` 返回数据集标准解、否则返回被篡改的解，
从而测出：

| 路径 | n=5, f=2 错误提交 | n=6, f=2 错误提交 |
|------|------------------|------------------|
| A2ABFT（严格） | 0.3% | 0.3% |
| A2ABFSybil（扫描口径） | 3.8% | 0.3% |

（同一次运行里 `A2ABFSybil` 在 `random` 攻击下为 0.7%，即该效应需要拜占庭方
**定向**投票才会出现，不是随机噪声。）

结论：机制不是"代码执行被绕过"，而是**多模型交叉验证下少数拜占庭 ACCEPT 票
叠加诚实方的 REJECT/弃权**，在阈值塌缩到 $\theta_{accept} \leq 1$ 时凑够
$\phi \geq \theta_{accept}$。代数量化见论文 Property 4 的条件
$7f + 3s + 3 \geq 3n$（软故障弃权，即定理 5.1 的最坏情况口径；若软故障与诚实者
一起投 REJECT 则退化为 $7f + 2s + 3 \geq 3n$）。$n{=}5$ 时为 $17 \geq 15$ 可越界，
$n{=}6$ 时为 $17 \geq 18$ 不可能，与上表一致。

> 第 13 轮修正：论文原先只给了 $7f + 2s + 3 \geq 3n$ 而**未声明软故障的投票行为**。
> 该式隐含"软故障随诚实者一起 REJECT"，与定理 5.1 的 worst-case abstention 假设
> 不一致；在 $s>0$ 时它会把 238 个边界外配置误判为"不可能"（例如 $n{=}5,f{=}1,s{=}2$）。
> 论文实验网格的 7 个配置在两种口径下判定相同，故所有已报告结论不变。

---

### 3.8 `audit_revision_layer.py` —— 修订层（52 项）

**为什么单独一层**：2026-09-17 的 PAT 分诊给论文注入了 45 处新文本与 42 条压缩。
这批文本诞生于 9 页上限的压力下、由 6 个脚本分轮完成，其中两处代数条件
（附录 A.2 的软故障假阳性闭式、Property 4 的越界条件）是**全新的数学命题**——
它们没有对应的数据文件，因此 L1/L4/L6/L7 **对它天然免疫**，只有 L2 能发现错误。

脚本分三部分：

| 部分 | 内容 | 核对项 |
|------|------|--------|
| **A** | L2 代数验算：用 `Fraction` 精确算术重推每条新式，并穷举 $n\le30$、$f\le11$、$s\le11$、$p\in\{0,0.05,\dots,1\}$ 验证"论文闭式"与"从 $\phi$ 定义直接判定"严格等价 | 18 |
| **B** | 修订文本自洽性：越界机制的多副本一致性、软故障口径、记号 $V/\hat V_i/V_i$、旧值残留、`\label`↔`\ref`、域映射、`\small`、硬声明 | 22 |
| **C** | 压缩回归：用 `ast` 解析修订期 5 个压缩脚本，取出其"关键数字必须保留"断言里的 **95 个**关键词，核对当前 `.tex` 仍包含全部 | 2 |

**A 部分的关键设计**：早期的实现把"越界条件"的扫描范围放在**边界之内**
（$3f+s+1 \le n$），而越界讨论的场景恰恰发生在**边界之外**——范围写错会让检查
扫不到真正的反例。修正后扫描外边界，才暴露出 238 个被旧式漏判的配置。

**B 部分的关键设计**：用**负向先行断言**区分 `n{-}1{-}f{-}s$ honest`（软故障弃权，
正确）与 `n{-}1{-}f$ honest`（软故障被计成诚实者，与定理假设冲突）。用 `\b` 词边界
写这条检查会同时匹配到前者，产生假阳性。

**C 部分的关键设计**：压缩脚本里的关键词断言只在**运行时**验证过一次；本检查把它们
提取出来做**回归**核对——后续任何补丁若把压缩当时刻意保住的信息弄丢，这里会报警。

配套负向测试：`negative_test_revision.py`（8/8）。

---

### 3.9 `audit_decision_neutrality.py` —— 决策中性（9 项）

**为什么单独一层**：论文 §6.6 与附录 A.7 曾声称声誉追踪器的决策中性是
"verified rather than merely asserted"。但当时依据的校验写在
`reputation_ablation.py` 里，形如：

```python
stats['decisions'].append((key, rec['task_idx'], rec['decision']))   # 值 == rec['decision']
by_dec  = {(k, t): d for k, t, d in stats['decisions']}
rec_dec = {..., r['decision'] for r in records}                      # 值 == rec['decision']
consistent = all(by_dec.get(k) == v for k, v in rec_dec.items())
```

**两侧同源，恒为 True** —— 与 `c_source`、`persistence` 全然无关。这条"验证"
没有任何分辨力，据此写的 `verified` 缺乏支撑。**这是本项目第三次栽在同一类
陷阱上：检查了 0 条（或恒真）却输出"通过"。**

脚本改为可证伪的三层检验（并把恒真校验本身当作被审计对象）：

| 项 | 内容 | 结果 |
|----|------|------|
| **D1** | 从原始票重算 $\phi = \lvert\text{ACCEPT}\rvert - 0.5\lvert\text{REJECT}\rvert$，与线上记录的 $\phi$ 逐轮比对。若计票曾按声誉加权（如 `consensus_unified._compute_vote_score` 的 `score += effective_weight * reputation`），重算值必然偏离记录值 | 457/457 轮吻合 |
| **D2a/D2b** | 用记录的 $\phi/\theta$ 复现协议状态机（confirm / view change / pending），与线上的 primary 推进序列、最终 decision、轮数逐项比对 | 120/120 条一致 |
| **D3** | 变异测试：注入三种反事实权重（REJECT 加权 0.5、拜占庭者 0.3、软故障者 0.3） | $\phi$ 分别改变 421/288/189 轮，决策翻转 5/2/2 条 |
| **D4a–c** | 静态可达性：决策段不得含声誉/权重标识；`_get_reputation_weights` 零调用点；`self._reputation` 的读取点仅为日志与死代码 | 全部通过 |
| **D5** | 把旧校验本身复现一遍，确认它在决策被**全部篡改**后仍判一致 | 确认恒真 |
| **D6** | D2b 自身的变异测试：篡改一条决策必须被判为不符 | 通过 |

**D3 是本脚本的核心**：没有它，D1/D2 仍可能只是"恰好通过"；有了它才证明
"**若声誉真的进入计票，这套检查会失败**"。

#### 3.9.1 一个必须区分的口径：1,305 还是 1,459

论文的 `$1{,}186$ of $1{,}305$` 限定在**四个受攻击细胞**，全六个细胞的合计是
`1,316 of 1,459`。两者都真，但混用会看起来像数字错误：

| 范围 | 激进罚 | 误罚 | 任务级 |
|------|-------:|-----:|--------|
| 四受攻击细胞（$f>0$） | 1,305 | 1,186 | 各 20/20 均有误罚 |
| 两无拜占庭细胞（$f=0$） | 154 | 130 | 误罚 8/20 与 9/20（触发任务 10 与 9） |
| **全六细胞** | **1,459** | **1,316** | 97/120 |

摘要与贡献原先写 "its $1{,}305$"，未标注范围；已补为 "in the four attacked cells"。

---

## 4. 负向测试：证明审计不是空转

> **审计的可信度来自它抓得住注入的缺陷。** 一个"全绿"的审计若从未捕获过任何
> 东西，它与"根本没有检查"无法区分。

### `negative_test_tables.py` —— 5/5

| 用例 | 注入的缺陷 |
|------|-----------|
| 负向1 | 容错列差一：`≤` 改成 `<`（等价于把定理加强 1） |
| 负向2 | 轮数列与实测矛盾 |
| 负向3 | Δ 算术错误 |
| 负向4 | BFT 值与 JSON 不符 |
| 负向5 | A800 表述缺 GPU 数量 |

### `negative_test_figures.py` —— 8/8

| 用例 | 注入的缺陷 |
|------|-----------|
| 负向1 | 图题注缺 n=90 披露 |
| 负向2 | 表区间被篡改 |
| 负向3 | 扫描单元缺失 |
| 负向4 | 性能表值被篡改 |
| 负向5 | 表题注缺 n=90 披露 |
| 负向6 | 示意图 PDF 缺失 |

### `negative_test_theory.py` —— 3/3

| 用例 | 注入的缺陷 |
|------|-----------|
| 负向5 | `distributed_worker.py` 阈值回归为多数式 |
| 负向6 | `langgraph_integration.py` 阈值回归为多数式 |
| 负向7 | 参考实现重新引入 f=0 阈值特例 |

负向 7 尤其关键：它把历史上真实存在过的缺陷重新注入，探针报出
`code=ACCEPT paper-rule=PENDING`，证明 §7 的可执行探针**真的在比对代码与论文**，
而不是只检查文件是否存在。

### `negative_test_paths.py` —— 8/8

| 用例 | 注入的缺陷 |
|------|-----------|
| 负向1 | `parse_correctness_log.py` 恢复为 `HERE/results`（真实发生过的迁移破坏） |
| 负向2 | `run_pairing_mcnemar.py` 同上；该脚本是 McNemar 配对检验的数据来源 |
| 负向3 | `build_cleanup_list.py` 结果目录改由脚本自身位置推导 → 上一级目录不存在 |
| 负向4 | `sys.path` 插入目标被打错 |
| 负向5 | 防空转：干净状态下各类检查计数必须全部 > 0 且问题数为 0 |
| 负向6 | §5 读取型 `open()` 指向已被清理的数据文件 |
| 负向7 | §6 文档命令路径失效（`.md` 侧）——把已修好的旧路径写回去 |
| 负向8 | §6 文档命令路径失效（`.sh` 侧） |

> **负向7 当场又抓到一次同类缺陷**：`_doc_command_paths()` 起初沿用了
> `SKIP_DIRS` 做目录剪枝，而该集合含 `datasets`——于是
> `experiments/datasets/DATASET_README.md` 根本没进入扫描范围，
> 注入缺陷也报不出问题，§6 的"0 问题"实为"0 扫描"。
> 这与 §5 当年因同一个坑产生假阳性是同一个根因（见 `_repo_basenames()` 注释），
> 因此 §6 改为只剪枝点目录与 `__pycache__`。
| 负向5 | 防空转：干净状态四类计数必须全部 > 0 且问题数为 0 |

负向 1/2 同时也是对 L9 §2 的验证：注入后审计报
`[smoke] …:RESULTS 数据目录挂在脚本自身目录下 …（由脚本自身位置推导（HERE）…）`。

注入/还原全程走**字节**（`shutil.copy2` + `bytes.replace`）。若用文本读写往返，
CRLF 会被规范化成 LF，还原后文件已非逐字节相同——在 git 里就是一片假 diff。

### `negative_test_revision.py` —— 8/8

| 用例 | 注入的缺陷 |
|------|-----------|
| 负向1 | §6.3 越界机制措辞回退为"共谋者推动篡改提案" |
| 负向2 | 越界条件回退为旧的 `7f + 2s + 3` |
| 负向3 | Property 4 把软故障重新计入诚实者（`n{-}1{-}f$ honest`） |
| 负向4 | §4.2 恢复"误差随 $m$ 指数下降"的过强声称 |
| 负向5 | 判定函数记号回退为 `V_i(\pi)` |
| 负向6 | 旧值残留（`1{,}186` → `1{,}217`） |
| 负向7 | Definition 3.1 丢失 `s ≤ f` 条件 |
| 负向8 | 压缩期保留关键词丢失（`4{,}320` 全量替换） |

负向用例支持第三个元素指定**替换次数**（缺省 1，`0` 表示全部替换）。负向 8 必须
用全量替换：`4{,}320` 在论文中出现**两次**，只替换一处时检查集里仍能找到它，用例会
假性通过（实测 MISSED 过一次）。

---

## 5. 三条硬性规则

审计与负向测试的编写遵循以下规则，违反其中任何一条都会让结论失去意义：

1. **失败细节必须与成功细节不同。** 若某个检查在通过时输出 `'clean'`、
   在失败时也输出 `'clean'`，负向测试就无法区分"捕获"与"空转"。
2. **每一项新检查都必须配一个负向用例。** 没有对应的篡改测试，就无法证明它生效。
3. **检查次数为 0 必须判失败。** 若某个检查因为"没找到对象"而静默跳过，
   它看起来是绿的，实际什么都没查。必须统计实际执行次数并在为 0 时报错。
4. **负向用例的替换必须让目标串彻底消失。** 若目标串在论文中出现多次，只替换
   第一处会让检查仍然找得到它，用例假性通过——替换次数是负向用例的一部分。
5. **禁止同源比较。** 若校验的两侧取自同一字段（例如把 `rec['decision']` 与它
   自己比），它恒真、没有分辨力，且**看起来永远是绿的**。校验必须独立重算，并经
   变异测试证明"注入缺陷后它会失败"。这一条的实例见 §3.9。

> 第 3 条来自一次真实教训：曾有一个位置无关性检查用 AST 只遍历模块顶层语句，
> 而 `sys.path.insert` 被包在 `for` 循环里，于是**检查了 0 条路径却输出"通过"**。
> 修复后该检查会先统计实际求值的路径数。
>
> 同一条规则在 L9 又救了一次：L9 初版对每个文件执行了全部顶层语句，把
> `mbpp_debate_fix.py` 的实验主体一并跑了起来（真实 API 请求）。可见"审计脚本本身
> 也是代码"，它的副作用与盲区必须和被测对象一样被审查。

---

## 6. 运行

**一键（推荐）**：

```bash
./reproduce.sh verify     # = 下列 13 条命令，串行执行并给出总判定
```

`./reproduce.sh` 是唯一入口（`Makefile` 为其薄封装），完整用法见 `README.md` §3.0。
输出 `REPRODUCE_OK` / `REPRODUCE_OK_PARTIAL` / `REPRODUCE_FAILED`，退出码 0 / 0 / 1；
"未验证"不等于"通过"。

**逐条**：

```bash
python experiments/verification/audit_table_numbers.py
python experiments/verification/audit_figures.py
python experiments/verification/audit_theory_numerics.py
python experiments/verification/audit_prose_ranges.py
python experiments/verification/audit_paths.py            # L9
python experiments/verification/audit_revision_layer.py   # 第 13 轮：修订层
python experiments/verification/audit_decision_neutrality.py  # 决策中性（零 LLM）

python experiments/verification/negative_test_tables.py
python experiments/verification/negative_test_figures.py
python experiments/verification/negative_test_theory.py
python experiments/verification/negative_test_paths.py    # L9
python experiments/verification/negative_test_revision.py # 第 13 轮
```

> ⚠️ **必须串行**。负向测试会临时改写 `papers/iclr2027_main.tex` 再逐字节还原；
> 与审计并行时审计会读到注入态而报假警（实测：`audit_table_numbers` 报出
> `[tab:a2a_sim] 99.9±5.8 vs 数据 56.7±5.8`），两个负向脚本同时备份/还原
> 还会互相覆盖、留下"半注入"的论文文件。`reproduce.sh` 用锁文件 + 严格串行
> + 收尾哈希比对三重防护。
>
> `audit_figures.py` 与 `negative_test_figures.py` 需要 `matplotlib`
> （前者在导入期加载 `papers/generate_figures.py`）；其余脚本仅依赖标准库。
> 缺依赖时这两项判**失败**而非跳过——"未验证"不等于"通过"。
>
> `audit_revision_layer.py` 会**解析**（不执行）`docs/revisions/2026-09-17/`
> 下的 5 个压缩脚本以提取关键词断言。该目录的脚本依赖当时的行号，
> **已执行完毕，勿重跑**。

所有脚本通过向上查找 `.a2a_project_root` 定位项目根，**与自身所在目录无关**，
可从任意工作目录、任意深度调用（已通过"复制到 5 层深目录"实测）。

---

## 7. 历史审计报告

逐轮的审计报告保存在 `docs/reviews/`（第 19 轮目录重整时从 `papers/` 迁出——
投稿目录只保留投稿相关文件），`docs/audit/` 存放数据来源类总账：

| 报告 | 主题 |
|------|------|
| `REVIEW_2026-09-15_round5_numeric_audit.md` | 数值审计 |
| `REVIEW_2026-09-15_round6_theory_spec_audit.md` | 理论规格 |
| `REVIEW_2026-09-15_round7_reference_contribution_audit.md` | 文献与贡献 |
| `REVIEW_2026-09-15_round8_scale_stats_audit.md` | 规模与统计 |
| `REVIEW_2026-09-15_round10_figure_layer_audit.md` | 图表层（L7） |
| `REVIEW_2026-09-15_round11_algorithm_layer_audit.md` | 算法层（伪代码 vs 实现） |
| `REVIEW_2026-09-15_round12_theory_code_layer_audit.md` | 定理可证性（L5b）+ 交付代码（L8） |
| `REVIEW_2026-09-17_round13_revision_layer_audit.md` | **修订层（L2 代数 + 新文本自洽性）** |
| `PAT_TRIAGE_2026-09-17.md` | ICLR PAT 反馈逐条分诊（26 条：22 成立 / 4 误报） |
| `DATA_SOURCE_AUDIT.md` | 数据来源逐轮审计总账 |
