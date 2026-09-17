"""audit_table_numbers.py 新增检查（tab:complexity / tab:a2a_sim / 承诺面）的负向测试。

原则：不能区分"检查通过"与"检查形同虚设"的审计没有价值。
对 5 个缺陷各注入一次，逐字节备份/恢复原文件。

⚠️ 锚点会随论文修订而失效（2026-09-17 实例）
    负向3 原锚点 ``$+15.1$ / $+28.4$ pp`` 是 tab:a2a_sim_comparison 第 1 行的 Δ；
    R15 判定该行跨源不可比、移除 Δ 列后锚点消失，``assert old in s`` 直接抛异常
    终止了整个脚本——于是负向4/5 也再没跑过，表格层负向验证实际上全面停摆
    却没有任何信号（退出码非 0 出现在 CI 之外的语境里很容易被当作"环境问题"）。
  处置：① 重锚到仍存在的 f=1 Δ（$+12.2$ pp）；② ``case()`` 不再因锚点失效而中断，
    而是记为 ``STALE ❌`` 并继续跑完其余用例——锚点失效本身就是失败，必须被看见。

用法: python experiments/verification/negative_test_tables.py
退出码: 0 = 全部注入被捕获；1 = 有漏检或锚点失效
"""
import os
import shutil
import subprocess
import sys

ROOT = None
_cur = os.path.dirname(os.path.abspath(__file__))
while True:
    if os.path.exists(os.path.join(_cur, ".a2a_project_root")):
        ROOT = _cur
        break
    _parent = os.path.dirname(_cur)
    if _parent == _cur:
        raise RuntimeError("未找到项目根：缺少 .a2a_project_root 标记文件")
    _cur = _parent

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(ROOT, "papers", "iclr2027_main.tex")
# 子进程解释器：优先 A2A_PY，否则用**当前正在运行本脚本的解释器**。
# 此前默认值写死为 ~/.workbuddy/... 的本机 venv 路径：在别人的机器上该路径
# 不存在，子进程直接 FileNotFoundError(WinError 2)，整套负向测试全线"报错"
# ——而它看起来像环境问题，很容易被当成"不是我该管的"。
PY = os.environ.get("A2A_PY") or sys.executable
BAK = os.path.join(ROOT, ".tmp_figcheck", "_bak_tables")


def _find_audit(name):
    """在本脚本所在目录及候选目录中定位审计脚本，使脚本不依赖自身位置。"""
    for d in (HERE, os.path.join(ROOT, "experiments"),
              os.path.join(ROOT, "experiments", "verification")):
        cand = os.path.join(d, name)
        if os.path.exists(cand):
            return cand
    raise RuntimeError(f"找不到审计脚本 {name}")


AUDIT = _find_audit("audit_table_numbers.py")


def run_audit():
    p = subprocess.run([PY, AUDIT], capture_output=True, text=True, cwd=ROOT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def case(name, expect, old, new):
    """注入一处缺陷，要求审计输出里出现 expect；无论成败都逐字节还原。

    锚点失效（论文修订后该文本已不存在/不唯一）**不抛异常**——它本身就是一种失败
    （对应用例已失去验证能力），记为 STALE 并继续，以免一个陈旧锚点把其余用例
    一并挡掉、造成"整套负向测试其实没跑"的静默停摆。
    """
    os.makedirs(BAK, exist_ok=True)
    bak = os.path.join(BAK, "main.tex")
    shutil.copy2(TEX, bak)
    try:
        s = open(TEX, encoding="utf-8").read()
        if old not in s:
            print(f"{name}: STALE ❌  —— 锚点已不存在于论文中: {old!r}")
            print("      该用例已失去验证能力，需重锚到仍存在的文本")
            return False
        if s.count(old) != 1:
            print(f"{name}: STALE ❌  —— 锚点不唯一({s.count(old)} 处): {old!r}")
            return False
        open(TEX, "w", encoding="utf-8").write(s.replace(old, new))
        rc, out = run_audit()
        hit = expect in out
        print(f"{name}: {'CAUGHT' if hit else 'MISSED ❌'}")
        if hit:
            for line in out.splitlines():
                if expect in line:
                    print("      ->", line.strip())
                    break
        else:
            print("      rc=", rc)
        return hit
    finally:
        shutil.copy2(bak, TEX)


def main():
    results = [
        # 1) 容错列改回差一错误（原缺陷）-> 与定理推导不等价
        case("负向1 (容错列差一: <= 改 <)",
             "[tab:complexity]",
             "$3f + s \\leq n-1$", "$3f + s < n-1$"),
        # 2) 轮数列改回与实测矛盾的 1-3（原缺陷）
        case("负向2 (轮数列与实测矛盾)",
             "[tab:complexity]",
             "2.6--4.5$^\\ast$", "1-3"),
        # 3) Delta 算术被篡改（重锚 2026-09-17：原锚点是第 1 行 Δ，R15 已移除该列）
        case("负向3 (f=1 Delta 算术错)",
             "[tab:a2a_sim]",
             "$+12.2$ pp", "$+99.2$ pp"),
        # 4) BFT 数值与数据源不符
        case("负向4 (BFT 值与 JSON 不符)",
             "[tab:a2a_sim]",
             "$56.7{\\pm}5.8$", "$99.9{\\pm}5.8$"),
        # 5) 可复现声明丢失 GPU 数量（R12-4 原缺陷）
        case("负向5 (A800 表述缺数量)",
             "未给出 GPU 数量",
             "on two NVIDIA A800-SXM4-80GB GPUs",
             "on NVIDIA A800-SXM4-80GB GPUs"),
    ]
    ok = sum(results)
    print(f"\n负向测试: {ok}/{len(results)} 项被捕获")
    shutil.copy2(os.path.join(BAK, "main.tex"), TEX)   # 双保险恢复
    # 收尾：本脚本自己的快照目录跑完即删，避免污染仓库
    shutil.rmtree(BAK, ignore_errors=True)
    try:
        os.rmdir(os.path.dirname(BAK))          # 父目录空了就一并删掉
    except OSError:
        pass
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
