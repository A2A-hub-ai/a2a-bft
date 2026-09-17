# -*- coding: utf-8 -*-
"""把 reputation_ablation.json 渲染成 Markdown 报告。

用法::

    python experiments/reproduce/render_reputation_report.py
"""
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while not os.path.exists(os.path.join(_ROOT, ".a2a_project_root")) and os.path.dirname(_ROOT) != _ROOT:
    _ROOT = os.path.dirname(_ROOT)

A2A_RESULTS = os.environ.get("A2A_RESULTS_DIR", os.path.join(_ROOT, "experiments", "results"))
IN_JSON = os.path.join(A2A_RESULTS, "reputation_ablation.json")
OUT_MD = os.path.join(A2A_RESULTS, "reputation_ablation_report.md")

ARM_LABEL = {
    ('oracle', 'persistent'): 'oracle $c$ / 声誉跨任务持续',
    ('oracle', 'fresh'): 'oracle $c$ / 声誉每任务重置',
    ('released', 'persistent'): 'released $c$ / 声誉跨任务持续',
    ('released', 'fresh'): 'released $c$ / 声誉每任务重置',
}


def fmt(x, nd=3):
    return '—' if x is None else f'{x:.{nd}f}'


def arm_table(arm):
    lines = [
        '| 细胞 | 事件 | 激进 | 奖励 | 轻惩 | 漂移 | 升级 | P | R | F1 | 误罚数 | 误罚率 | 误罚任务 | 触发任务 | 升级伤诚率 | r_byz | r_hon |',
        '|------|-----:|-----:|-----:|-----:|-----:|-----:|--:|--:|---:|-------:|-------:|---------:|---------:|-----------:|------:|------:|',
    ]
    for r in arm['rows']:
        lines.append(
            f"| `{r['cell']}` | {r['events']} | {r['tier_aggressive']} | {r['tier_reward']} | "
            f"{r['tier_mild']} | {r['tier_drift']} | {r['escalations']} | "
            f"{fmt(r['precision'])} | {fmt(r['recall'])} | {fmt(r['f1'])} | "
            f"{r['mispenalty_count']} | {fmt(r['mispenalty_rate'])} | "
            f"{r.get('tasks_with_mispenalty', '—')}/{r.get('tasks_total', '—')} | "
            f"{r.get('tasks_with_aggressive', '—')}/{r.get('tasks_total', '—')} | "
            f"{fmt(r['escalation_on_honest_rate'])} | {fmt(r['final_r_byzantine'])} | "
            f"{fmt(r['final_r_honest'])} |")
    return '\n'.join(lines)


def main():
    if not os.path.exists(IN_JSON):
        sys.exit(f"缺少 {IN_JSON}（先跑 reputation_ablation.py）")
    d = json.load(open(IN_JSON, encoding='utf-8'))

    L = []
    L.append('# 声誉追踪器测量性消融 —— 实测报告')
    L.append('')
    L.append(f"- 生成时间：{d['timestamp']}")
    L.append(f"- 每细胞任务数：{d['tasks_per_cell']}（共 {d['n_records']} 条任务记录）")
    L.append(f"- 轨迹口径：{d.get('trajectory_note', '')}")
    L.append('')
    L.append('## M1 决策指标（与声誉设置无关）')
    L.append('')
    L.append('声誉分数不进入计票规则（式 `commit` 聚合的是原始票数），因此下面这些指标'
             '**在四档重放中完全相同**——这是论文安全定理的可验证体现。')
    L.append('')
    L.append('| 细胞 | 攻击 | 任务 | 接受率 | PENDING | 错误提交 | 决定后正确率 | 平均轮数 |')
    L.append('|------|------|-----:|-------:|--------:|---------:|-------------:|---------:|')
    for r in d.get('m1_decision_metrics', []):
        L.append(f"| `{r['cell']}` | {r['attack']} | {r['tasks']} | {r['decision_rate']:.3f} | "
                 f"{r['pending_rate']:.3f} | {r['wrong_commit_rate']:.3f} | "
                 f"{r['accuracy_when_decided']:.3f} | {r['avg_rounds']:.2f} |")
    L.append('')

    L.append('## 四档重放')
    L.append('')
    all_consistent = True
    for arm in d['arms']:
        label = ARM_LABEL.get((arm['c_source'], arm['persistence']),
                              f"{arm['c_source']} / {arm['persistence']}")
        L.append(f"### {label}")
        L.append('')
        L.append(f"决策序列与线上记录逐字段一致：**{arm['decision_consistent']}**"
                 + ('' if arm['decision_consistent'] else '  ← 不一致，结果不可采信'))
        all_consistent = all_consistent and arm['decision_consistent']
        L.append('')
        L.append(arm_table(arm))
        L.append('')

    L.append('## 读法')
    L.append('')
    L.append('- **误罚率**：激进罚（ρ≥0.7，−0.25）落在"诚实验证者**且**该票客观上正确"'
             '上的比例。论文声称这类投票应被**奖励**，故该值越高，说明罚则与论文'
             '所述意图偏离越大。`—` 表示该细胞从未触发激进罚（分母为 0，'
             '不是"没有问题"）。')
    L.append('- **误罚任务 / 触发任务**：该细胞 20 条任务中，至少出现一次"误罚"/"激进罚触发"'
             '的任务数。论文正文（§6.6）与附录 A.7 的任务级断言即由此列支持：四个含拜占庭节点的'
             '细胞为 20/20；两个无拜占庭细胞的"触发任务"为 10/20 与 9/20，其中产生误罚的为 8/20 与 9/20。'
             '之所以单列，是因为声誉更新在验证者与任务之间高度聚集，事件级比例不适合直接附二项区间。')
    L.append('- **升级伤诚率**：suspect 计数达阈值时那次额外 −0.2 落在诚实节点上的比例。'
             '论文附录称 suspect 仅为告警，`audit_reputation_fidelity.py` 已证明代码会实际施加该罚。')
    L.append('- **P / R / F1**：把"激进罚触发"当作拜占庭检测器时的性能。')
    L.append('- **r_byz / r_hon**：细胞结束时拜占庭与诚实验证者声誉的均值。`—` 表示该细胞'
             '没有拜占庭节点（f=0），而非"拜占庭被罚到 0"。')
    L.append('- **c 的来源**：`oracle` = 提案是否**真的**正确（Algorithm 1 的定义）；'
             '`released` = 发布实现 `_estimate_correctness` 的格式检查。两者差距即'
             '论文声明与发布实现之间的差距。')
    L.append('')
    L.append(f'**四档一致性总判：{"全部通过" if all_consistent else "存在不一致，需排查"}**')
    L.append('')

    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print(f"报告 -> {os.path.relpath(OUT_MD, _ROOT) if OUT_MD.startswith(_ROOT) else OUT_MD}")


if __name__ == '__main__':
    main()
