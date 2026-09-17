"""audit_figures.py 的负向测试：故意篡改工件，确认每项检查都会报警。

原则：不能区分"检查通过"与"检查形同虚设"的审计是没有价值的。
本脚本对 7 个已知缺陷各注入一次，并追加 1 条**反向**用例（只改注释不得误报），
逐字节备份/恢复原文件。

用法: python experiments/verification/negative_test_figures.py
"""
import json
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
AGG = os.path.join(ROOT, "experiments", "results", "full_bft_sweep_aggregated.json")
MULTI = os.path.join(ROOT, "experiments", "results",
                     "multi_model_3seed_aggregated.json")
GENFIG = os.path.join(ROOT, "papers", "generate_figures.py")
REP = os.path.join(ROOT, "papers", "figures", "reputation_mechanism.pdf")
# 子进程解释器：优先 A2A_PY，否则用**当前正在运行本脚本的解释器**。
# 此前默认值写死为 ~/.workbuddy/... 的本机 venv 路径：在别人的机器上该路径
# 不存在，子进程直接 FileNotFoundError(WinError 2)，整套负向测试全线"报错"
# ——而它看起来像环境问题，很容易被当成"不是我该管的"。
PY = os.environ.get("A2A_PY") or sys.executable
BAK = os.path.join(ROOT, ".tmp_figcheck", "_bak")


def _find_audit(name):
    """在本脚本所在目录及候选目录中定位审计脚本，使脚本不依赖自身位置。"""
    for d in (HERE, os.path.join(ROOT, "experiments"),
              os.path.join(ROOT, "experiments", "verification")):
        cand = os.path.join(d, name)
        if os.path.exists(cand):
            return cand
    raise RuntimeError(f"找不到审计脚本 {name}")


AUDIT = _find_audit("audit_figures.py")


def run_audit():
    p = subprocess.run([PY, AUDIT], capture_output=True, text=True, cwd=ROOT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def snapshot():
    os.makedirs(BAK, exist_ok=True)
    shutil.copy2(TEX, os.path.join(BAK, "main.tex"))
    shutil.copy2(AGG, os.path.join(BAK, "agg.json"))
    shutil.copy2(MULTI, os.path.join(BAK, "multi.json"))
    shutil.copy2(GENFIG, os.path.join(BAK, "generate_figures.py"))
    shutil.copy2(REP, os.path.join(BAK, "rep.pdf"))


def restore():
    shutil.copy2(os.path.join(BAK, "main.tex"), TEX)
    shutil.copy2(os.path.join(BAK, "agg.json"), AGG)
    shutil.copy2(os.path.join(BAK, "multi.json"), MULTI)
    shutil.copy2(os.path.join(BAK, "generate_figures.py"), GENFIG)
    shutil.copy2(os.path.join(BAK, "rep.pdf"), REP)


def tamper_tex(old, new):
    s = open(TEX, encoding="utf-8").read()
    assert old in s, f"待篡改文本未找到: {old[:60]!r}"
    assert s.count(old) == 1, f"待篡改文本不唯一({s.count(old)}): {old[:60]!r}"
    open(TEX, "w", encoding="utf-8").write(s.replace(old, new))


def tamper_agg_drop(dataset, n, f, s, atk):
    d = json.load(open(AGG, encoding="utf-8"))
    before = len(d["rows"])
    d["rows"] = [r for r in d["rows"]
                 if not (r["dataset"] == dataset and r["n"] == n and r["f"] == f
                         and r["s"] == s and r["attack"] == atk)]
    assert len(d["rows"]) == before - 1, "未删除到单元数"
    json.dump(d, open(AGG, "w", encoding="utf-8"), ensure_ascii=False)


def case(name, expect, tex_edit=None, agg_drop=None, fig_delete=None, pre=None,
         expect_absent=False):
    snapshot()
    try:
        if pre:
            pre()
        if tex_edit:
            tamper_tex(*tex_edit)
        if agg_drop:
            tamper_agg_drop(*agg_drop)
        if fig_delete and os.path.exists(fig_delete):
            os.remove(fig_delete)
        rc, out = run_audit()
        # expect_absent=True 是"反向用例"：期望审计仍然全绿（不得误报）
        hit = (expect not in out) if expect_absent else (expect in out)
        print(f"{name}: {'OK' if hit else 'MISSED ❌'}")
        if hit:
            if not expect_absent:
                for line in out.splitlines():
                    if expect in line:
                        print("      ->", line.strip())
                        break
            else:
                print("      (审计保持全绿，无误报)")
        else:
            print("      (审计输出与预期不符)", expect)
            print("      rc=", rc)
        return hit
    finally:
        restore()


def main():
    results = []
    # 1) 图题注丢失 n=90 披露 -> 披露一致性检查
    results.append(case(
        "负向1 (图题注缺 n=90 披露)",
        "未披露边界内 collusion 来自 n=90",
        tex_edit=("$n{=}90$ ablation/comparison deployment",
                  "$n{=}250$ ablation/comparison deployment"),
    ))
    # 2) tab:attacks 区间被篡改 -> 内含性检查
    results.append(case(
        "负向2 (表区间被篡改)",
        "超出 tab:attacks 区间",
        tex_edit=("$70.0$--$80.8$ & $0.0$--$23.2$", "$10.0$--$20.0$ & $0.0$--$23.2$"),
    ))
    # 3) 扫描单元被静默删除 -> 黄金计数检查（_sweep_mean 会改均值而非报错）
    results.append(case(
        "负向3 (扫描单元缺失)",
        "单元数漂移",
        agg_drop=("gsm8k", 4, 1, 0, "random"),
    ))
    # 4) tab:performance 的值被篡改 -> 逐格相等检查（表值从 tex 解析）
    results.append(case(
        "负向4 (性能表值被篡改)",
        "tab:performance",
        tex_edit=("$61.3$s & $12.7$", "$99.9$s & $12.7$"),
    ))
    # 5) tab:attacks 题注丢失 n=90 披露 -> 题注解析式披露检查
    #    （旧实现用"label 前 900 字符窗口"，窗口内若恰好有别的 n=90 会静默通过）
    results.append(case(
        "负向5 (表题注缺 n=90 披露)",
        "tab:attacks 的题注未披露",
        tex_edit=(r"from Table~\ref{tab:hetero_compare}, $n{=}90$ per cell)",
                  r"from Table~\ref{tab:hetero_compare})"),
    ))
    # 6) 删除示意类图 PDF -> 图件清单/新鲜度检查（此前只守 2 张数据图）
    results.append(case(
        "负向6 (示意图 PDF 缺失)",
        "缺少 reputation_mechanism.pdf",
        fig_delete=REP,
    ))
    # 7) 数据内容已变但图未重出 -> 内容级新鲜度检查
    #    （2026-09-17 由 mtime 改为内容指纹：这里改数据内容，md5 必变，必须报警）
    def tamper_multi():
        d = json.load(open(MULTI, encoding="utf-8"))
        d["_negative_test_marker"] = True
        json.dump(d, open(MULTI, "w", encoding="utf-8"), ensure_ascii=False)

    results.append(case(
        "负向7 (数据内容已变但图未重出)",
        "[freshness]",
        pre=tamper_multi,
    ))
    # 8) 反向用例：只往生成脚本追加注释 -> **不得**把图判为陈旧
    #    这正是 mtime 基准的失效模式（改一行注释触发 3 张图误报），
    #    任何情况下都必须保持全绿，否则守卫会因噪音被无视。
    def add_comment_only():
        s = open(GENFIG, encoding="utf-8").read()
        with open(GENFIG, "w", encoding="utf-8") as fp:
            fp.write(s + "\n# 负向测试：仅追加注释，不得触发陈旧告警\n")

    results.append(case(
        "反向8 (仅改注释不得误报陈旧)",
        "问题数: 0",
        pre=add_comment_only,
        expect_absent=False,   # 期望字符串"问题数: 0"必须出现
    ))

    ok = sum(results)
    print(f"\n负向测试: {ok}/{len(results)} 项符合预期")
    restore()
    # 收尾：快照目录只服务于本脚本，跑完即删，避免污染仓库（clone 后不应看到它）
    shutil.rmtree(os.path.join(ROOT, ".tmp_figcheck"), ignore_errors=True)
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
