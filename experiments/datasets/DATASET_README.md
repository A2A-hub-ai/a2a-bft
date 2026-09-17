# A2A-BFT 实验数据集

## 数据集汇总

| 数据集 | 数量 | 类型 | 说明 |
|--------|------|------|------|
| gsm8k_test.json | 1,319 | 数学推理 | 小学数学应用题（test split） |
| mbpp_test.json | 500 | 编程 | 编程能力基准测试 |
| mmlu_3subjects.json | 312 | 知识问答 | 抽象代数 100 + 大学数学 100 + 机器学习 112 |
| humaneval_full.json | 164 | 编程任务 | 已下载，**论文实验链未使用** |

**论文实际使用的三个数据集合计**: 1,319 + 500 + 312 = **2,131 条**
（含 HumanEval 则为 2,295 条。历史遗留的 2,607 是把已删除的冗余副本
`mmlu_4subjects.json` 重复计入所致，勿再引用——机器可读的计数见
`dataset_summary.json` 的 `paper_total_tasks` 字段。）

## ⚠️ 已知问题

1. ~~**`mmlu_4subjects.json` 与 `mmlu_3subjects.json` 内容完全相同**~~ —— **已解决**：
   该文件（312 条、字节级重复、文件名误导、无任何脚本引用）已于 2026-09-17 删除。
   同日修复了 `dataset_summary.json` 的计数缺陷：旧实现的 `total_tasks` 用
   `glob("*.json")` 求和，任何多余文件都会静默计入，正是它把总数抬到了 2,607；
   现改为按声明式注册表（`experiments/env/download_datasets.py` 的
   `DATASET_REGISTRY`），新增数据集必须显式登记。
2. **上游数据集自带重复**（非下载错误）：
   - MBPP：`mbpp_0066` 与 `mbpp_0337` 任务描述相同
   - MMLU：`machine_learning_0279` 与 `0294` 仅差一个句末句点，属近似重复
   - 影响可忽略：每个 seed 仅抽样 50 题，重复对同时被抽中的概率极低，且指标为逐任务决策率。
3. 数据完整性已验证：无空题目、无缺失标准答案；MMLU 全部为 4 选项且 `answer` 必属于 `choices`（注意 `answer` 字段存的是**答案文本**而非字母）。


## 数据格式

### GSM8K
```json
{
  "id": "gsm8k_0001",
  "type": "math",
  "question": "题目文本",
  "answer": "答案",
  "difficulty": "medium"
}
```

### HumanEval
```json
{
  "id": "humaneval_000",
  "type": "code",
  "prompt": "函数定义",
  "canonical_solution": "参考答案",
  "test": "测试代码",
  "entry_point": "函数名",
  "difficulty": "medium"
}
```

### MBPP
```json
{
  "id": "mbpp_0001",
  "type": "code",
  "description": "任务描述",
  "code": "参考代码",
  "test_list": ["测试用例"],
  "difficulty": "medium"
}
```

### MMLU
```json
{
  "id": "mmlu_subject_0001",
  "type": "knowledge",
  "subject": "科目名称",
  "question": "题目",
  "choices": ["选项A", "选项B", "选项C", "选项D"],
  "answer": "正确答案",
  "difficulty": "medium"
}
```

## 使用说明

1. 在实验脚本中加载数据集
2. 根据任务类型选择合适的提示词模板
3. 运行共识实验
4. 统计接受率和性能指标

## 下载方式

```bash
HF_ENDPOINT=https://hf-mirror.com python experiments/env/download_datasets.py
```

## 更新日期

2026-09-05（2026-09-15 修正计数错误与已知问题说明）
