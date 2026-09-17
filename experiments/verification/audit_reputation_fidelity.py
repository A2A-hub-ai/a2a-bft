# -*- coding: utf-8 -*-
"""声誉追踪器保真度审计：把发布实现的罚则片段逐行照搬，与 experiments/reproduce/
reputation_ablation.py 的 ReputationTracker 在**同一随机序列**上逐轮比对 r_i。

为什么需要这个审计
--------------------------------------------------------------------------------
论文 §4.3 与附录对 suspect 计数器给了互相矛盾的说法：
  §4.3   : "maintains ... suspect counters, and escalates penalties for persistent
            misbehaviour"
  附录   : "Suspect counters for anomaly detection (warnings only; penalties are
            fixed per tier---no exclusion or reweighting)"
而 `src/a2a_bft/deepseek_worker.py:1000-1002` 实际会在计数达阈值时额外施加
`max(0.3, r - 0.2)`。本审计锁定"追踪器是否忠实复刻了发布实现（含该升级罚）"，
使论文可以在实测数据上裁决这处矛盾，而不是靠读代码下结论。

用法::

    python experiments/verification/audit_reputation_fidelity.py
"""
import os
import sys
import random

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while not os.path.exists(os.path.join(_ROOT, ".a2a_project_root")) and os.path.dirname(_ROOT) != _ROOT:
    _ROOT = os.path.dirname(_ROOT)
for _d in (os.path.join(_ROOT, "experiments", "reproduce"), _HERE):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)

from reputation_ablation import ReputationTracker  # noqa: E402


def released_update(r, suspect, is_correct, reject_ratio, suspect_threshold=3):
    """逐行照搬 src/a2a_bft/deepseek_worker.py:982-1002。

    返回 (r, suspect, escalated)。
    """
    if is_correct and reject_ratio < 0.5:
        r = min(1.0, r + 0.1)
        suspect = 0
    elif not is_correct and reject_ratio < 0.7:
        r = max(0.5, r - 0.05)
        suspect += 1
    elif reject_ratio >= 0.7:
        r = max(0.1, r - 0.25)
        suspect += 1
    else:
        r = max(0.5, r - 0.02)
        suspect += 1

    escalated = False
    if suspect >= suspect_threshold:
        r = max(0.3, r - 0.2)
        escalated = True
    return r, suspect, escalated


def main():
    print("=" * 72)
    print("声誉追踪器保真度审计（vs src/a2a_bft/deepseek_worker.py:982-1002）")
    print("=" * 72)

    random.seed(20260915)
    N_SEQ, LEN = 300, 40
    mismatches = 0
    esc_ref_total = 0
    esc_mine_total = 0
    checked = 0

    for seq_i in range(N_SEQ):
        tracker = ReputationTracker(n=1, c_source='oracle')
        r_ref, sus_ref = 1.0, 0
        for step in range(LEN):
            vote = random.choice(['accept', 'reject', 'abstain'])
            prop_correct = random.random() < 0.5
            # 真值定义（同发布实现 deepseek_worker.py:975-980）：
            # 提案正确时仅 ACCEPT 为对，提案错误时仅 REJECT 为对，ABSTAIN 永不算对。
            is_correct = ((vote == 'accept') and prop_correct) or \
                         ((vote == 'reject') and (not prop_correct))
            # 先按同一票更新窗口并取 ρ（与 tracker 内部一致），再交还给 update
            tracker.hist[0].append(vote)
            if len(tracker.hist[0]) > tracker.WINDOW:
                tracker.hist[0] = tracker.hist[0][-tracker.WINDOW:]
            rho = tracker._rho(0)

            r_ref, sus_ref, esc_ref = released_update(r_ref, sus_ref, is_correct, rho)
            tracker.hist[0] = tracker.hist[0][:-1]

            tracker.update(0, vote, prop_correct, "x", "math")
            checked += 1
            if esc_ref:
                esc_ref_total += 1
            if tracker.events[-1]['escalated']:
                esc_mine_total += 1

            r_mine = tracker.r[0]
            if abs(r_mine - r_ref) > 1e-9:
                mismatches += 1
                if mismatches <= 5:
                    print(f"  ✗ seq{seq_i} 第 {step + 1} 步: 参考 r={r_ref:.4f} / "
                          f"本实现 r={r_mine:.4f} (vote={vote}, c={prop_correct})")

    print(f"\n  比对步数            : {checked}")
    print(f"  不一致步数          : {mismatches}")
    print(f"  参考实现升级罚触发  : {esc_ref_total} 次")
    print(f"  本实现升级罚触发    : {esc_mine_total} 次")

    print("\n" + "-" * 72)
    if mismatches == 0:
        print("结论: 保真度通过 —— 追踪器与发布实现的 r_i 轨迹逐轮一致（含升级罚）。")
        print("      因此附录「suspect counters 仅为告警」的说法与代码不符；")
        print("      以 tracing 记录的 escalated 计数为准。")
        print("FIDELITY_OK")
        return 0
    print(f"结论: 保真度失败 —— {mismatches}/{checked} 步不一致，追踪器未忠实复刻发布实现。")
    print("FIDELITY_FAIL")
    return 1


if __name__ == '__main__':
    sys.exit(main())
