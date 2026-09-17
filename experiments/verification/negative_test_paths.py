# -*- coding: utf-8 -*-
"""audit_paths.py（L9 路径解析层）的负向测试。

原则：不能区分"检查通过"与"检查形同虚设"的审计没有价值。
本脚本对 8 个已知缺陷各注入一次，逐字节备份/恢复源文件，确认审计会报警。

覆盖的缺陷形态（全部来自 2026-09-15 代码整理暴露出的真实问题）：
  负向1  ``HERE/results``——数据目录由脚本自身位置推导（parse_correctness_log.py）
  负向2  同上（run_pairing_mcnemar.py，McNemar 配对检验的数据来源）
  负向3  目录常量由脚本自身位置推导（docs/cleanup/build_cleanup_list.py，
         移入 docs/cleanup/ 后删除清单恒为空）
  负向4  ``sys.path`` 插入目标不存在
  负向5  防空转：干净状态下各类检查计数必须全部 > 0 且问题数为 0
         （若检查形同虚设——0 次检查——必须判失败）
  负向6  §5 读取型 ``open()`` 指向已被清理的数据文件
         （2026-09-17 真实发生：papers/generate_figures.py 的三个函数读
          final_results_100rounds.json 等模拟期文件，删库后仍留在脚本里）
  负向7  §6 文档命令路径失效（.md 侧）——把已修好的旧路径写回去
         （2026-09-17 真实发生：目录重整后 5 处包内文档仍写着旧路径，照抄即踩空）
  负向8  §6 文档命令路径失效（.sh 侧）——同上，确认 .sh 也在覆盖范围内

用法: python experiments/verification/negative_test_paths.py
退出码: 0 = 全部注入都被捕获且干净状态确有非空转检查；1 = 有漏检
"""
import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = _HERE
while not os.path.exists(os.path.join(ROOT, ".a2a_project_root")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)

# 子进程解释器：优先 A2A_PY，否则用**当前正在运行本脚本的解释器**。
# 此前默认值写死为 ~/.workbuddy/... 的本机 venv 路径：在别人的机器上该路径
# 不存在，子进程直接 FileNotFoundError(WinError 2)，整套负向测试全线"报错"
# ——而它看起来像环境问题，很容易被当成"不是我该管的"。
PY = os.environ.get("A2A_PY") or sys.executable
AUDIT = os.path.join(_HERE, "audit_paths.py")
BAK = os.path.join(ROOT, ".tmp_pathcheck", "_bak")


def run_audit():
    p = subprocess.run([PY, AUDIT], capture_output=True, text=True, cwd=ROOT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def case(name, path, old, new, expect):
    """注入一处缺陷，要求审计输出里出现 expect；无论成败都逐字节还原。

    注意：备份/还原/注入全部走**字节**。若用文本读写往返，CRLF 会被规范化成 LF，
    还原后文件已非逐字节相同（在 git 里就是一片假 diff）。
    """
    os.makedirs(BAK, exist_ok=True)
    bak = os.path.join(BAK, os.path.basename(path))
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    raw = open(bak, "rb").read()
    try:
        assert raw.count(old.encode()) == 1, \
            f"待篡改文本不唯一({raw.count(old.encode())}): {old!r}"
        open(path, "wb").write(raw.replace(old.encode(), new.encode()))
        rc, out = run_audit()
        hit = expect in out and rc != 0
        print(f"{name}: {'CAUGHT' if hit else 'MISSED ❌'}")
        if hit:
            for line in out.splitlines():
                if expect in line:
                    print("      ->", line.strip())
                    break
        else:
            print(f"      rc={rc}")
            for line in out.splitlines():
                if line.strip().startswith(("[path]", "[smoke]", "[sys.path]")):
                    print("      out>", line.strip())
        return hit
    finally:
        open(path, "wb").write(raw)
        assert open(path, "rb").read() == raw, f"还原失败: {path}"


def virgin_check():
    """干净状态：问题数必须为 0，且三类检查计数都 > 0（防空转）。"""
    rc, out = run_audit()
    ok = True
    if rc != 0 or "问题数: 0" not in out:
        print("负向5 (干净状态): MISSED ❌  —— 审计对干净仓库报错")
        for line in out.splitlines():
            if "问题数" in line or line.strip().startswith("["):
                print("      out>", line.strip())
        ok = False
    counts = {}
    for line in out.splitlines():
        for key in ("§1 文件类路径目标", "§1 目录类路径目标", "§2 冒烟指纹比对",
                    "§3 sys.path 插入目标", "§5 读取型 open() 数据文件",
                    "§6 文档命令路径"):
            if line.strip().startswith(key):
                counts[key] = int(line.split(":")[1].split("（")[0].strip())
    zeros = [k for k, v in counts.items() if v == 0]
    if zeros:
        print(f"负向5 (防空转): MISSED ❌  —— 计数为 0 的检查: {zeros}")
        ok = False
    if ok:
        print(f"负向5 (干净状态 + 防空转): CAUGHT ✅  "
              f"计数 {counts} 全部 > 0，问题数 0")
    return ok


def main():
    targets = {
        "parse": os.path.join(ROOT, "experiments", "reproduce", "parse_correctness_log.py"),
        "pair": os.path.join(ROOT, "experiments", "reproduce", "run_pairing_mcnemar.py"),
        "clean": os.path.join(ROOT, "docs", "cleanup", "build_cleanup_list.py"),
        "theory": os.path.join(ROOT, "experiments", "verification", "audit_theory_numerics.py"),
        "subbound": os.path.join(ROOT, "experiments", "verification", "verify_mbpp_subboundary.py"),
        "docreadme": os.path.join(ROOT, "experiments", "datasets", "DATASET_README.md"),
        "docsh": os.path.join(ROOT, "experiments", "env", "run_on_autodl.sh"),
    }
    for k, v in targets.items():
        if not os.path.exists(v):
            print(f"找不到目标文件 {k}: {v}")
            sys.exit(1)

    results = [
        # 负向1：把"由脚本自身位置推导数据目录"注入回去（真实发生过的缺陷）
        case("负向1 (parse_correctness_log.py  HERE/results 回归)",
             targets["parse"],
             'RESULTS = os.environ.get("A2A_RESULTS_DIR", os.path.join(_ROOT, "experiments", "results"))',
             'RESULTS = os.path.join(HERE, "results")',
             "[smoke] experiments\\reproduce\\parse_correctness_log.py:RESULTS"),
        # 负向2：McNemar 配对检验的数据来源，同一缺陷
        case("负向2 (run_pairing_mcnemar.py  HERE/results 回归)",
             targets["pair"],
             'RESULTS = os.environ.get("A2A_RESULTS_DIR", os.path.join(_ROOT, "experiments", "results"))',
             'RESULTS = os.path.join(HERE, "results")',
             "[smoke] experiments\\reproduce\\run_pairing_mcnemar.py:RESULTS"),
        # 负向3：目录常量由脚本自身位置推导 → 上一级目录不存在
        case("负向3 (build_cleanup_list.py 结果目录解析失效)",
             targets["clean"],
             "R = os.path.join(ROOT, 'experiments', 'results')",
             "R = os.path.join(_HERE, 'experiments', 'results')",
             "[path] docs\\cleanup\\build_cleanup_list.py:R 目录的上一级不存在"),
        # 负向4：sys.path 插入目标不存在
        case("负向4 (审计脚本 sys.path 目标被打错)",
             targets["theory"],
             "sys.path.insert(0, os.path.join(ROOT, 'experiments', 'src'))",
             "sys.path.insert(0, os.path.join(ROOT, 'srcs'))",
             "[sys.path] experiments\\verification\\audit_theory_numerics.py:180 目标不存在"),
        # 负向6：读取型 open() 指向已被清理的数据文件（§5 首次校准）
        case("负向6 (verify_mbpp_subboundary.py 读取已删除的 MBPP 数据)",
             targets["subbound"],
             '"experiments", "datasets", "mbpp_test.json"',
             '"experiments", "datasets", "mbpp_test_DELETED.json"',
             "[open] experiments\\verification\\verify_mbpp_subboundary.py"),
        # 负向7：§6 文档命令路径——把 2026-09-17 刚修好的旧路径原样写回 .md
        case("负向7 (文档命令路径失效 .md 侧)",
             targets["docreadme"],
             "python experiments/env/download_datasets.py",
             "python experiments/download_datasets.py",
             "[doccmd] experiments/datasets/DATASET_README.md"),
        # 负向8：同上，.sh 侧（run_on_autodl.sh 里 echo 出的手动命令）
        case("负向8 (文档命令路径失效 .sh 侧)",
             targets["docsh"],
             "python experiments/legacy/real_dataset_experiment.py",
             "python experiments/real_dataset_experiment.py",
             "[doccmd] experiments/env/run_on_autodl.sh"),
        virgin_check(),
    ]

    ok = sum(results)
    print(f"\n负向测试: {ok}/{len(results)} 项通过")

    # 双保险还原（case() 已在 finally 里还原），再清理快照目录避免污染仓库
    for v in targets.values():
        bak = os.path.join(BAK, os.path.basename(v))
        if os.path.exists(bak):
            shutil.copy2(bak, v)
    shutil.rmtree(BAK, ignore_errors=True)
    try:
        os.rmdir(os.path.dirname(BAK))          # 父目录空了就一并删掉
    except OSError:
        pass
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
