"""audit_theory_numerics.py 第 6/7/8 节（R12-1/2/3）新增检查的负向测试。

原则：不能区分"检查通过"与"检查形同虚设"的审计没有价值。
此前负向测试只覆盖**表格层**与**图件层**；本轮新增的检查落在**理论层与代码层**，
因此需要自己的注入套件。对 3 个缺陷各注入一次，逐字节备份/恢复源文件。

用法: python experiments/verification/negative_test_theory.py
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
# 子进程解释器：优先 A2A_PY，否则用**当前正在运行本脚本的解释器**。
# 此前默认值写死为 ~/.workbuddy/... 的本机 venv 路径：在别人的机器上该路径
# 不存在，子进程直接 FileNotFoundError(WinError 2)，整套负向测试全线"报错"
# ——而它看起来像环境问题，很容易被当成"不是我该管的"。
PY = os.environ.get("A2A_PY") or sys.executable
BAK = os.path.join(ROOT, ".tmp_figcheck", "_bak_theory")


def _find(name, *rel_dirs):
    """在本脚本所在目录及若干候选目录中定位文件，使脚本不依赖自身位置。"""
    for d in (HERE,) + tuple(os.path.join(ROOT, *rd) for rd in rel_dirs):
        cand = os.path.join(d, name)
        if os.path.exists(cand):
            return cand
    raise RuntimeError(f"找不到 {name}（候选目录：{HERE}, {rel_dirs}）")


AUDIT = _find("audit_theory_numerics.py", ("experiments",), ("experiments", "verification"))

SRC = os.path.join(ROOT, "experiments", "src", "a2a_bft")


def _src_file(name):
    """核心模块可能在 a2a_bft/ 或 a2a_bft/legacy/。"""
    for cand in (os.path.join(SRC, name), os.path.join(SRC, "legacy", name)):
        if os.path.exists(cand):
            return cand
    raise RuntimeError(f"找不到源码文件 {name}")


TARGETS = {
    "dw": _src_file("distributed_worker.py"),
    "lg": _src_file("langgraph_integration.py"),
    "dsw": _src_file("deepseek_worker.py"),
}


def run_audit():
    p = subprocess.run([PY, AUDIT], capture_output=True, text=True, cwd=ROOT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def case(name, key, expect, old, new):
    path = TARGETS[key]
    os.makedirs(BAK, exist_ok=True)
    bak = os.path.join(BAK, os.path.basename(path))
    shutil.copy2(path, bak)
    try:
        s = open(path, encoding="utf-8").read()
        assert old in s, f"待篡改文本未找到: {old!r}"
        assert s.count(old) == 1, f"待篡改文本不唯一({s.count(old)}): {old!r}"
        open(path, "w", encoding="utf-8").write(s.replace(old, new))
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
        shutil.copy2(bak, path)


def main():
    results = [
        # 5) 把多数式阈值注入回分布式模块（即 R12-3 修复前的缺陷）
        case("负向5 (distributed_worker 多数式阈值回归)",
             "dw", "0.5-majority form: violations=",
             "theta_accept = n_total - 2 * self.f - self.s",
             "theta_accept = (n_total - self.f) * 0.5"),
        # 6) 同上，注入回 LangGraph 模块，验证定点回归检查有效
        case("负向6 (langgraph_integration 多数式阈值回归)",
             "lg", "no (n - f) * 0.5 threshold remains: found",
             "theta_accept = n_total - 2 * self.f - self.s",
             "theta_accept = (n_total - self.f) * 0.5"),
        # 7) 把 R12-2 修掉的 f=0 特例注入回去 -> 可执行探针必须捕获
        case("负向7 (f=0 阈值特例回归)",
             "dsw", "code=ACCEPT  paper-rule=PENDING",
             "theta_accept = n_validators - 2 * self.f - self.s",
             "theta_accept = n_validators * 0.5 if self.f == 0 else n_validators - 2 * self.f - self.s"),
    ]
    ok = sum(results)
    print(f"\n负向测试: {ok}/{len(results)} 项被捕获")
    # 双保险恢复全部目标文件
    for _p in TARGETS.values():
        bak = os.path.join(BAK, os.path.basename(_p))
        if os.path.exists(bak):
            shutil.copy2(bak, _p)
    # 收尾：本脚本自己的快照目录跑完即删，避免污染仓库
    shutil.rmtree(BAK, ignore_errors=True)
    try:
        os.rmdir(os.path.dirname(BAK))          # 父目录空了就一并删掉
    except OSError:
        pass
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
