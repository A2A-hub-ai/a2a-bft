#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`audit_revision_layer.py` 的负向测试。

审计工具的可信度不来自它的输出，而来自它能否抓住**人为注入的缺陷**。
本脚本逐类篡改论文源文件，确认对应检查真的报警，然后字节级恢复。

规则（来自多轮实战教训）：
  ① 期望字符串必须含检查的**标签**，这样"检查空转"与"检查通过"可区分；
  ② 每个用例必须包含**促使该检查诞生**的那个缺陷本身（不是同类别的另一个）；
  ③ 恢复后必须验证：篡改串计数 0、原串计数 > 0。
"""
import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_papers():
    cur = HERE
    for _ in range(6):
        cand = os.path.join(cur, "papers")
        if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "iclr2027_main.tex")):
            return cand
        cur = os.path.dirname(cur)
    raise FileNotFoundError("papers/ not found")


PAPERS = _find_papers()
TEX = os.path.join(PAPERS, "iclr2027_main.tex")
AUDIT = os.path.join(HERE, "audit_revision_layer.py")
BAK = TEX + ".ntr.bak"

results = []


def read():
    return io.open(TEX, encoding="utf-8", newline="").read()


def write(t):
    io.open(TEX, "w", encoding="utf-8", newline="").write(t)


def run_audit():
    r = subprocess.run([sys.executable, AUDIT], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout + (r.stderr or "")


CASES = [
    # (名称, 期望字符串, [(锚点, 替换)])
    ("R13-1 §6.3 越界机制措辞回退", "[PROBLEM] B2b",
     [(r"lets two Byzantine ACCEPTs offset the honest REJECTs of a non-tampering "
       r"primary's wrong proposal (the $n{=}6$ MBPP row stays at $0.0\%$: execution "
       r"mechanically rejects tampered code, so its violation surfaces through text "
       r"proposals; Appendix~\ref{app:proofs})",
       r"lets two colluders carry a tampered proposal alone.")]),

    ("R13-2 越界条件回退为旧式", "[PROBLEM] B1b",
     [(r"exactly when $7f + 3s + 3 \geq 3n$",
       r"exactly when $7f + 2s + 3 \geq 3n$")]),

    ("R13-3 Property 4 把软故障计回诚实者", "[PROBLEM] B3",
     [(r"rejected by the $n{-}1{-}f{-}s$ honest validators (the worst case, with soft faults ",
       r"rejected by the $n{-}1{-}f$ honest validators (the worst case, with soft faults ")]),

    ("R13-4 尾和单调性声称回退", "[PROBLEM] A6e",
     [(r"This tail decays exponentially only once $k/m$ is held fixed",
       r"This tail decreases exponentially with $m$")]),

    ("R13-5 判定函数记号回退", "[PROBLEM] B7b",
     [("    \\hat{V}_i(\\pi) = \\begin{cases}",
       "    V_i(\\pi) = \\begin{cases}")]),

    ("旧值残留（1,217）", "[PROBLEM] B8 旧值已清除 1{,}217",
     [("1{,}186", "1{,}217")]),

    ("Definition 3.1 丢失 s<=f 条件", "[PROBLEM] B5b",
     [(r"with $s \leq f$ when soft faults vote REJECT rather than abstaining",
       r"when soft faults vote REJECT rather than abstaining")]),

    ("压缩期保留关键词丢失（4,320）", "[PROBLEM] C1",
     [("4{,}320", "4320", 0)]),   # 第三项 0 = 全部替换；该串在论文中出现两次
]

print("=" * 66)
print("negative_test_revision.py —— 修订层审计的负向测试")
print("=" * 66)

# 基线：未篡改时必须 0 问题
out = run_audit()
assert "问题数: 0" in out, f"基线不干净，无法进行负向测试：\n{out[-600:]}"
print("[baseline] 未篡改时 问题数: 0  -> OK\n")

shutil.copy2(TEX, BAK)
orig = read()
try:
    for name, expect, pairs in CASES:
        write(orig)
        t = read()
        for item in pairs:
            old, new = item[0], item[1]
            # 第三项为替换次数；缺省 1，0 表示全部替换
            cnt = item[2] if len(item) > 2 else 1
            assert old in t, f"{name}: 篡改锚点未找到 {old[:70]!r}"
            t = t.replace(old, new, cnt if cnt else -1)
        write(t)
        out = run_audit()
        ok = expect in out
        results.append((name, ok, expect))
        print(f"[{'CAUGHT' if ok else 'MISSED'}] {name}  (期望串 {expect!r})")
finally:
    write(orig)
    shutil.copy2(BAK, TEX)
    os.remove(BAK)

# 恢复校验：篡改串不得残留，且整体必须与原始内容逐字节一致
after = read()
for name, expect, pairs in CASES:
    for item in pairs:
        old, new = item[0], item[1]
        n_after, n_orig = after.count(new), orig.count(new)
        assert n_after == n_orig, \
            f"恢复不完整（用例 {name}）：{new[:50]!r} 计数 {n_orig} -> {n_after}"
assert after == orig, "恢复后文件与原始内容不一致"
print("\n[restore] 文件已字节级恢复，与原始内容一致")

caught = sum(1 for _, ok, _ in results if ok)
print("-" * 66)
print(f"负向测试: {caught}/{len(results)} 捕获")
if caught != len(results):
    for name, ok, expect in results:
        if not ok:
            print(f"  MISSED: {name}")
    sys.exit(1)
print("NEGATIVE_REVISION_DONE")
