# -*- coding: utf-8 -*-
"""L9 路径解析层审计：交付脚本里的每个路径常量是否指向真实位置。

为什么需要这一层：2026-09-15 代码整理时，若干脚本被移动了目录，而它们的数据
目录常量是按**脚本自身位置**推导的，迁移后指向不存在的目录：

  * ``experiments/reproduce/parse_correctness_log.py``、``run_pairing_mcnemar.py``
    原写 ``os.path.join(HERE, "results", ...)``；HERE 从 ``experiments/`` 变成
    ``experiments/reproduce/`` 后指向不存在的 ``experiments/reproduce/results/``。
    这两个脚本正是论文 ``tab:n8_scaling`` 与 McNemar 检验的数据来源。
  * ``docs/cleanup/build_cleanup_list.py`` 原写
    ``ROOT = os.path.dirname(os.path.abspath(__file__))``；移入 ``docs/cleanup/``
    后 ROOT 变成 ``docs/cleanup``，``add()`` 一个路径都命中不了，清单恒为空。

整理时的验收只验证了 ``sys.path`` 插入目标，**完全没覆盖"数据目录常量"这一类**，
于是"全绿"掩盖了脚本已经跑不起来。本层补上该盲区。

检查项
  §1 项目内路径常量的父目录必须存在（写文件的路径允许目标文件尚不存在）
  §2 冒烟指纹：路径不得**由脚本自身目录推导**出 ``<脚本目录>/<数据目录名>/``
     —— 代码目录下不会挂数据目录；这是"迁移后静默失效"的典型形态
  §3 所有被插入 sys.path 的目录必须存在
  §4 诊断：含路径分隔符的相对路径常量（依赖 CWD，仅提示不判失败）
  §5 读取型 ``open()`` 的数据文件必须真实存在（2026-09-17 新增）
  §6 文档/脚本里给出的 ``python|bash <路径>`` 命令必须指向真实存在的脚本
     （2026-09-17 新增；复现者照抄文档命令即踩空的盲区）

关于 §5（本层最后补上的盲区）
  §1 只看**模块级**路径常量，所以下面这类缺陷它一无所知：
  ``papers/generate_figures.py`` 里 ``load_experiment_data()`` 用
  ``open(os.path.join(data_path, 'final_results_100rounds.json'))`` 读三个
  模拟期文件；三个文件当时已被删除，数据目录常量 ``EXPERIMENTS`` 却真实存在，
  于是 §1 全绿——而函数一旦被调用就是 ``FileNotFoundError``。§2 也看不出来，
  因为常量是从项目根推导的、写法正确。缺陷藏在**函数体内联拼接的文件名**里。
  这类"脚本看起来可用、实际一跑就炸"的失效正是本层存在的理由，故 §5 补上：
  对读取模式的 ``open()``，取其字符串字面量文件名并断言仓库内确有该文件。

实现约束（血泪教训，改这个文件前请先读）
  * **绝不 exec**。本审计早期版本用 ``exec`` 逐条执行顶层语句来取常量值，结果把
    ``mbpp_debate_fix.py`` 的实验主体也执行了，真实打出 API 请求并挂住进程。
    现在改为纯 AST 符号求值：只认 ``os.path.*`` / 字符串拼接 / f-string /
    ``Path / "x"`` / ``os.environ.get`` 默认值这一小类表达式；求不出即 UNKNOWN。
  * **防空转**。检查次数为 0 必须判失败——"0 次检查 + 0 个问题"不是通过，
    是结论无效。每类检查各有独立计数器。
  * **识别"向上查找项目根"的各种写法**。本仓库存在两种：
        ① ``while not exists(join(X, ".a2a_project_root")): X = dirname(X)``
        ② ``X = None; while True: if exists(join(_cur, ".a2a_project_root")): X = _cur; break``
    只识别其中一种，另一种就会被算成"脚本目录"并产生一片假阳性
    （``negative_test_figures.py`` 等 4 个脚本曾因此被误报）。
  * **指纹看"推导来源"而非"恰好同名"**。``papers/generate_figures.py`` 里
    ``ROOT/papers/figures`` 恰好等于"脚本目录/figures"，但它是从项目根推导的，
    属于正确写法；真正的缺陷是从脚本自身目录推导。二者不能混为一谈。

用法: python experiments/verification/audit_paths.py
退出码: 0 = 无问题且检查非空转；1 = 有问题或空转
"""
import ast
import os
import re
import sys

# ---------------------------------------------------------------- 项目根定位


def _find_root(start):
    cur = os.path.dirname(os.path.abspath(start))
    while True:
        if os.path.exists(os.path.join(cur, ".a2a_project_root")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise RuntimeError("未找到项目根：缺少 .a2a_project_root 标记文件")
        cur = parent


ROOT = _find_root(__file__)
MARKER = ".a2a_project_root"

# 2026-09-21：公开工件模式。补充材料包自该日起不再收录 papers/（论文源随正文
# 经 OpenReview 提交），包内指向 papers/ 的路径常量与文档命令必然"目标不存在"。
# 该模式下此类目标统计为 skip（豁免）而不判失败；papers/ 在位（完整项目/工作区）
# 时 ARTIFACT_MODE=False，行为与原版完全一致——不放过任何 papers 路径回归。
ARTIFACT_MODE = not os.path.isdir(os.path.join(ROOT, "papers"))


def _paper_exempt(rel_target):
    """artifact 模式下，位于 papers/ 或 docs/ 下的目标豁免存在性检查。

    2026-09-21 起公开工件（补充材料/GitHub）同时不含 papers/ 与 docs/：
    指向两者的路径常量与文档命令必然"目标不存在"，统计为豁免（skip）而不判失败；
    papers/ 或 docs/ 任一在位（完整项目/工作区）时 ARTIFACT_MODE 判定依据是
    papers/ 的存在性 —— 此时行为与原版完全一致，docs/ 目标照常检查。
    """
    if not ARTIFACT_MODE:
        return False
    r = rel_target.replace("\\", "/").rstrip("/")
    return (r == "papers" or r.startswith("papers/")
            or r == "docs" or r.startswith("docs/"))


DATA_DIR_NAMES = ("results", "datasets", "figures", "papers", "models", "logs")
SKIP_DIRS = {".git", "__pycache__", ".workbuddy", "node_modules", ".openscience",
             "datasets", "site-packages", ".venv", "venv", ".tmp_d2bak"}


def _looks_like_file(p):
    return "." in os.path.basename(p.rstrip("\\/"))


def _is_runtime_scratch(p, rel):
    """运行期临时区（.tmp*/_bak*）审计时不一定存在，不参与存在性判定。"""
    parts = rel.replace("\\", "/").split("/")
    return any(seg.startswith((".tmp", "_bak")) for seg in parts)


# ------------------------------------------------------------ 纯符号求值器
_UNKNOWN = object()


def _dotted(node):
    """还原 a.b.c 形式的属性链；失败返回 None。"""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _eval(node, env, fpath):
    """把表达式符号求值为 str / 数值 / _UNKNOWN。绝不执行外部代码。"""
    if node is None:
        return _UNKNOWN
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, (str, int)) else _UNKNOWN
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return fpath
        return env.get(node.id, _UNKNOWN)
    if isinstance(node, ast.JoinedStr):                       # f-string
        out = []
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                r = _eval(v.value, env, fpath)
                if not isinstance(r, str):
                    return _UNKNOWN
                out.append(r)
            elif isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.append(v.value)
            else:
                return _UNKNOWN
        return "".join(out)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a = _eval(node.left, env, fpath)
        b = _eval(node.right, env, fpath)
        return a + b if isinstance(a, str) and isinstance(b, str) else _UNKNOWN
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        # pathlib 的 Path / "x"
        a = _eval(node.left, env, fpath)
        b = _eval(node.right, env, fpath)
        if isinstance(a, str) and isinstance(b, str):
            return os.path.join(a, b)
        return _UNKNOWN
    if isinstance(node, ast.IfExp):
        return _eval(node.body, env, fpath)
    if isinstance(node, ast.Call):
        fn = _dotted(node.func)
        if fn is None or any(isinstance(a, ast.Starred) for a in node.args):
            return _UNKNOWN
        args = [_eval(a, env, fpath) for a in node.args]
        S = lambda i: isinstance(args[i], str)                # noqa: E731
        if fn == "os.path.join":
            if not all(isinstance(a, str) for a in args):
                return _UNKNOWN
            return os.path.join(*args) if args else _UNKNOWN
        if fn in ("os.path.dirname", "os.path.basename"):
            if len(args) == 1 and S(0):
                return getattr(os.path, fn.split(".")[-1])(args[0])
            return _UNKNOWN
        if fn == "os.path.abspath":
            # 只接受已绝对化的输入：本审计不依赖 CWD
            if len(args) == 1 and S(0) and os.path.isabs(args[0]):
                return os.path.normpath(args[0])
            return _UNKNOWN
        if fn in ("os.path.normpath", "os.path.realpath"):
            return os.path.normpath(args[0]) if len(args) == 1 and S(0) else _UNKNOWN
        if fn == "os.path.relpath":
            if len(args) == 2 and S(0) and S(1):
                try:
                    return os.path.relpath(args[0], args[1])
                except ValueError:
                    return _UNKNOWN
            return _UNKNOWN
        if fn == "os.path.expanduser":
            return os.path.expanduser(args[0]) if len(args) == 1 and S(0) else _UNKNOWN
        if fn in ("os.environ.get", "os.getenv"):
            # 取默认值：审计要检查"仓库默认约定"，不受本机环境变量干扰
            return args[1] if len(args) >= 2 and S(1) else _UNKNOWN
        if fn in ("str", "os.fspath"):
            return args[0] if len(args) == 1 and S(0) else _UNKNOWN
        if fn in ("Path", "pathlib.Path"):
            return args[0] if len(args) == 1 and S(0) else _UNKNOWN
        return _UNKNOWN
    return _UNKNOWN


# -------------------------------------- 识别"向上查找项目根"的各种写法
def _file_dirname_depth(node):
    """``dirname(abspath(__file__))`` / ``Path(__file__).parent`` 链的 dirname 层数。"""
    if node is None:
        return None
    if isinstance(node, ast.Call):
        fn = _dotted(node.func)
        if fn == "os.path.dirname" and len(node.args) == 1:
            inner = _file_dirname_depth(node.args[0])
            return inner + 1 if inner is not None else None
        if fn == "os.path.abspath" and len(node.args) == 1 \
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__":
            return 0
        if fn in ("Path", "pathlib.Path") and node.args \
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__":
            return 0
        return None
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        inner = _file_dirname_depth(node.value)
        return inner + 1 if inner is not None else None
    return None


def _root_walk_names(tree, src):
    """返回被"向上查找 .a2a_project_root"循环赋为项目根的变量名集合。

    覆盖两种写法（见模块 docstring）：
      ① while ...: X = os.path.dirname(X)
      ② X = None; while True: if exists(join(_cur, MARKER)): X = _cur; break
    """
    if MARKER not in src:
        return set()
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.While, ast.For)):
            continue
        seg = ast.get_source_segment(src, node) or ""
        if MARKER not in seg:
            continue
        for st in ast.walk(node):
            if isinstance(st, ast.Assign) and len(st.targets) == 1 \
                    and isinstance(st.targets[0], ast.Name):
                tgt = st.targets[0].id
                v = st.value
                # ① dirname 自身
                if isinstance(v, ast.Call) and _dotted(v.func) == "os.path.dirname" \
                        and len(v.args) == 1 and isinstance(v.args[0], ast.Name) \
                        and v.args[0].id == tgt:
                    names.add(tgt)
    # ② 在 while 体内的 ``if <测试引用标记文件>`` 分支里把游标赋给它
    for node in ast.walk(tree):
        if not isinstance(node, (ast.While, ast.For)):
            continue
        for st in ast.walk(node):
            if not isinstance(st, ast.If):
                continue
            if MARKER not in (ast.get_source_segment(src, st.test) or ""):
                continue
            for a in ast.walk(st):
                if isinstance(a, ast.Assign) and len(a.targets) == 1 \
                        and isinstance(a.targets[0], ast.Name) \
                        and isinstance(a.value, ast.Name):
                    names.add(a.targets[0].id)
    return names


def _root_finder_funcs(tree, src):
    """识别 ``def _find_root(start): ... ".a2a_project_root" ... return cur`` 这类
    辅助函数——脚本常写成 ``ROOT = _find_root(__file__)``，符号求值器无法执行它，
    但其返回值必然就是项目根。"""
    if MARKER not in src:
        return set()
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if MARKER not in (ast.get_source_segment(src, node) or ""):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Name):
                names.add(node.name)
                break
    return names


def _walk_stmts(body, env, refs, sp_sites, fpath, ctx):
    """按顺序符号执行模块级语句，只记录常量值与 sys.path 目标，无任何副作用。"""
    for node in body:
        if isinstance(node, ast.Assign):
            val = _eval(node.value, env, fpath)
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) \
                    and node.value.func.id in ctx["root_finders"]:
                val = ROOT                      # ROOT = _find_root(__file__)
            ids = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
            for t in node.targets:
                if isinstance(t, ast.Name):
                    if t.id in ctx["root_walk"]:
                        env[t.id] = ROOT           # 循环终点即项目根
                    else:
                        env[t.id] = val
                    refs.setdefault(t.id, set()).update(ids)
                elif isinstance(t, (ast.Tuple, ast.List)):
                    for e in t.elts:
                        if isinstance(e, ast.Name):
                            env[e.id] = _UNKNOWN
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                env[node.target.id] = (_eval(node.value, env, fpath)
                                       if node.value is not None else _UNKNOWN)
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name) and isinstance(node.op, ast.Add):
                cur = env.get(node.target.id, _UNKNOWN)
                add = _eval(node.value, env, fpath)
                env[node.target.id] = (cur + add if isinstance(cur, str)
                                       and isinstance(add, str) else _UNKNOWN)
        elif isinstance(node, ast.If):
            _walk_stmts(node.body, env, refs, sp_sites, fpath, ctx)
            _walk_stmts(node.orelse, env, refs, sp_sites, fpath, ctx)
        elif isinstance(node, ast.Try):
            _walk_stmts(node.body, env, refs, sp_sites, fpath, ctx)
            _walk_stmts(node.orelse, env, refs, sp_sites, fpath, ctx)
            _walk_stmts(node.finalbody, env, refs, sp_sites, fpath, ctx)
            for h in node.handlers:
                _walk_stmts(h.body, env, refs, sp_sites, fpath, ctx)
        elif isinstance(node, ast.While):
            tgt = {a.targets[0].id for a in ast.walk(node)
                   if isinstance(a, ast.Assign) and len(a.targets) == 1
                   and isinstance(a.targets[0], ast.Name)} & ctx["root_walk"]
            if tgt:
                for n in tgt:
                    env[n] = ROOT
            else:
                _walk_stmts(node.body, env, refs, sp_sites, fpath, ctx)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            # 逐元素展开，保证 `for _d in (a, b, c): sys.path.insert(0, _d)` 可求值
            it = node.iter
            elts = None
            if isinstance(it, (ast.Tuple, ast.List, ast.Set)):
                elts = [_eval(e, env, fpath) for e in it.elts]
            if elts is not None and isinstance(node.target, ast.Name):
                for v in elts:
                    env[node.target.id] = v
                    _walk_stmts(node.body, env, refs, sp_sites, fpath, ctx)
                env[node.target.id] = _UNKNOWN
            else:
                if isinstance(node.target, ast.Name):
                    env[node.target.id] = _UNKNOWN
                _walk_stmts(node.body, env, refs, sp_sites, fpath, ctx)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            _walk_stmts(node.body, env, refs, sp_sites, fpath, ctx)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            fn = _dotted(node.value.func)
            if fn in ("sys.path.insert", "sys.path.append", "sys.path.extend"):
                for ln, v in _sys_path_values(node.value, env, fpath):
                    sp_sites.append((ln, v))
        # Import / FunctionDef / ClassDef / ... 一律不求值


def _sys_path_values(call, env, fpath):
    """取出一次 sys.path 操作的目标值（insert 取末参；extend 逐元素）。"""
    fn = _dotted(call.func)
    if fn == "sys.path.extend" and call.args:
        arg = call.args[0]
        if isinstance(arg, (ast.List, ast.Tuple, ast.Set)):
            return [(call.lineno, _eval(e, env, fpath)) for e in arg.elts]
    if not call.args:
        return [(call.lineno, _UNKNOWN)]
    return [(call.lineno, _eval(call.args[-1], env, fpath))]


def _all_sys_path_calls(tree):
    """兜底：全树扫描所有 sys.path 调用点行号（防止有写法未被顺序执行覆盖）。"""
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _dotted(node.func) in (
                "sys.path.insert", "sys.path.append", "sys.path.extend"):
            lines.add(node.lineno)
    return lines


# ------------------------------------------------------ §5 读取型 open() 输入
DATA_EXTS = (".json", ".csv", ".tsv", ".txt", ".log", ".npy", ".npz", ".pkl",
             ".jsonl", ".yaml", ".yml")

# 运行期才产生、提交时本就不该存在的输入（凭据、缓存等）。
# 另外会并入 .gitignore 里出现过的文件名——被忽略的文件"不在仓库里"是正常状态。
ALLOW_MISSING = {"credentials.json", "secrets.json", "service-account.json"}

_BASENAME_INDEX = None


def _repo_basenames():
    """仓库内所有文件名（小写）→ 供 §5 判断"有没有这个文件"。

    注意：这里**不能**沿用 SKIP_DIRS —— 它含 ``datasets``（本层不遍历数据目录内容），
    但那正是数据文件的存放处。早期版本照抄 SKIP_DIRS，于是 ``gsm8k_test.json``
    这类明明存在的文件被判"全仓库都不存在"，产生一片假阳性。
    文件名索引只取名字、不读内容，代价可忽略。
    """
    global _BASENAME_INDEX
    if _BASENAME_INDEX is not None:
        return _BASENAME_INDEX
    idx = set()
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn
                 if d not in (".git", "__pycache__") and not d.startswith(".tmp")]
        for f in fn:
            idx.add(f.lower())
    gi = os.path.join(ROOT, ".gitignore")
    if os.path.exists(gi):
        for line in open(gi, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line and not line.startswith("#") and "*" not in line and "/" not in line:
                ALLOW_MISSING.add(line.lower())
    _BASENAME_INDEX = idx
    return idx


def _open_read_literals(tree):
    """收集读取模式 ``open()`` 的字符串字面量文件名（含 io.open / Path.open）。

    写模式（w/a/x/+）跳过——目标文件尚不存在是正常的。
    只取**不含路径分隔符**的纯文件名：含分隔符的由 §1/§2 负责。
    """
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = _dotted(node.func)
        if fn not in ("open", "io.open", "codecs.open"):
            if not (isinstance(node.func, ast.Attribute) and node.func.attr == "open"):
                continue
        mode = None
        if len(node.args) >= 2:
            m = node.args[1]
            if isinstance(m, ast.Constant) and isinstance(m.value, str):
                mode = m.value
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant) \
                    and isinstance(kw.value.value, str):
                mode = kw.value.value
        if mode and any(c in mode for c in "wax+"):
            continue                       # 输出路径，允许尚不存在
        # 文件名可能在第 1 个参数里，也可能在 os.path.join(...) 的末位
        cands = []
        if node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                cands.append(a0.value)
            elif isinstance(a0, ast.Call) and _dotted(a0.func) == "os.path.join":
                last = a0.args[-1] if a0.args else None
                if isinstance(last, ast.Constant) and isinstance(last.value, str):
                    cands.append(last.value)
        for c in cands:
            if os.sep in c or "/" in c:
                continue
            if c.lower().endswith(DATA_EXTS):
                out.append((node.lineno, c))
    return out


# ---------------------------------------------- §6 文档中给出的可执行命令路径
# 复现者不会读源码，只会照抄 README / REPRODUCTION.md 里的命令。
# 2026-09-17 目录重整（src/ → experiments/src/，审计脚本 → verification/）后，
# 实测仍有 5 处包内文档写着旧路径（如 `python experiments/audit_table_numbers.py`），
# 照抄即 "No such file or directory"。§1–§5 全部只看 .py，对这一类完全无感。
DOC_CMD_RE = re.compile(
    r'(?:^|[\s`$(])(?:python3?|bash|sh)\s+'
    r'((?:experiments|papers|docs|src)/[\w./-]+\.(?:py|sh))')

# docs/reviews/ 是"当时状态"的历史快照（且不进补充材料包），其中的命令反映的是
# 撰写该报告时的目录布局，改写成今天的路径反而会篡改历史记录，故不参与判定。
DOC_CMD_SKIP_PREFIX = (os.path.join("docs", "reviews") + os.sep, "docs/reviews/")


def _doc_command_paths():
    """扫描 .md/.sh/.txt 里出现的 ``python|bash <repo相对路径>`` 命令。

    返回 (命中列表, 实际扫描文件数)；命中元素为 (相对文件, 行号, 命令行, 目标路径)。
    """
    hits, files = [], 0
    for dp, dn, fn in os.walk(ROOT):
        # ⚠️ 这里**不能**沿用 SKIP_DIRS：它含 ``datasets``，而
        #    ``experiments/datasets/DATASET_README.md`` 恰恰是会随包发布、
        #    且写着下载命令的文档。§5 已因同一个坑产生过一片假阳性
        #    （见 _repo_basenames 的注释），§6 的负向7 又抓到一次：
        #    沿用 SKIP_DIRS 时 DATASET_README.md 根本没进入扫描范围，
        #    注入缺陷也报不出问题——审计"0 问题"实为"0 扫描"。
        dn[:] = [d for d in dn
                 if not d.startswith(".") and d != "__pycache__"]
        for f in sorted(fn):
            if not f.endswith((".md", ".sh", ".txt")):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
            if any(rel.startswith(pref.replace(os.sep, "/"))
                   for pref in DOC_CMD_SKIP_PREFIX):
                continue
            try:
                src = open(p, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            files += 1
            for m in DOC_CMD_RE.finditer(src):
                hits.append((rel, src[:m.start()].count("\n") + 1,
                             m.group(0).strip(), m.group(1)))
    return hits, files


# ------------------------------------------------------------------ 主流程

def scan_py_files():
    out = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn
                 if d not in SKIP_DIRS and not d.startswith("_bak")
                 and not d.startswith(".tmp")]
        for f in sorted(fn):
            if f.endswith(".py") and not f.startswith(".tmp_"):
                out.append(os.path.join(dp, f))
    return out


def main():
    problems = []
    scanned = parsed = 0
    fileish = dirish = smoke = smoke_hits = sp_checked = 0
    open_checked = 0
    doc_checked = doc_files = 0
    paper_skipped = 0
    rel_diag = []
    posix_hits = []
    examples = []
    basenames = _repo_basenames()

    for path in scan_py_files():
        scanned += 1
        rel = os.path.relpath(path, ROOT)
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src, path)
        except (SyntaxError, UnicodeDecodeError):
            continue
        parsed += 1
        fpath = os.path.abspath(path)
        script_dir = os.path.dirname(fpath)
        env, refs, sp_sites = {}, {}, []
        ctx = {"root_walk": _root_walk_names(tree, src),
               "root_finders": _root_finder_funcs(tree, src)}
        _walk_stmts(tree.body, env, refs, sp_sites, fpath, ctx)

        # ---- §1 / §2：模块级字符串常量中的路径 ----
        for name in sorted(env):
            val = env[name]
            if not isinstance(val, str) or not val or name == "__file__":
                continue
            if not os.path.isabs(val):
                # POSIX 绝对路径（AutoDL 侧挂载点）在 Windows 上 isabs()==False，
                # 单独归类，不混进"相对路径"诊断
                if val.startswith("/"):
                    posix_hits.append(f"{rel}:{name} = {val!r}")
                elif ("/" in val or "\\" in val) and len(val) < 200 \
                        and "\n" not in val and "{" not in val:
                    rel_diag.append(f"{rel}:{name} = {val!r}")
                continue
            try:
                if os.path.commonpath([val, ROOT]) != ROOT:
                    continue                 # 项目外（AutoDL 模型盘等），本机不存在属正常
            except ValueError:
                continue
            scratch = _is_runtime_scratch(val, os.path.relpath(val, ROOT))

            # §2 冒烟指纹：是否"由脚本自身目录推导"出 <脚本目录>/<数据目录名>/
            smoke += 1                       # 比较次数（保证非空转）
            for dn in DATA_DIR_NAMES:
                bad = os.path.join(script_dir, dn)
                if val != bad and not val.startswith(bad + os.sep):
                    continue
                smoke_hits += 1
                here_like = []
                for r in refs.get(name, ()):                 # 变量来源
                    rv = env.get(r)
                    if r == "__file__" or (isinstance(rv, str) and rv == script_dir):
                        here_like.append(r)
                for n in ast.walk(tree):                     # 内联 dirname 链
                    if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                            and isinstance(n.targets[0], ast.Name) \
                            and n.targets[0].id == name:
                        for sub in ast.walk(n.value):
                            d = _file_dirname_depth(sub)
                            if d is not None:
                                base = script_dir
                                for _ in range(d - 1):
                                    base = os.path.dirname(base)
                                if base == script_dir:
                                    here_like.append(f"dirname×{d}(__file__)")
                                break
                parent = os.path.dirname(val.rstrip("\\/"))
                missing = not (os.path.exists(val) or os.path.isdir(parent))
                if scratch:
                    break
                if here_like or missing:
                    why = (f"由脚本自身位置推导（{'/'.join(sorted(set(here_like)))}）"
                           if here_like else "该位置并不存在")
                    problems.append(
                        f"[smoke] {rel}:{name} 数据目录挂在脚本自身目录下 -> "
                        f"{os.path.relpath(val, ROOT)}"
                        f"（{why}；脚本位于 {os.path.relpath(script_dir, ROOT)}，"
                        f"迁移后会静默失效，应向上查找 {MARKER}）")
                break

            if scratch:
                continue

            # §1 父目录存在性
            parent = os.path.dirname(val.rstrip("\\/"))
            if _looks_like_file(val):
                fileish += 1
                if not os.path.isdir(parent) and not _paper_exempt(os.path.relpath(val, ROOT)):
                    problems.append(
                        f"[path] {rel}:{name} 目标所在目录不存在 -> "
                        f"{os.path.relpath(val, ROOT)}"
                        f"（缺失目录: {os.path.relpath(parent, ROOT)}）")
                elif not os.path.isdir(parent):
                    paper_skipped += 1
                elif len(examples) < 8:
                    examples.append(f"{rel}:{name} -> {os.path.relpath(val, ROOT)}")
            else:
                dirish += 1
                if parent and not os.path.isdir(parent):
                    if _paper_exempt(os.path.relpath(val, ROOT)):
                        paper_skipped += 1
                    else:
                        problems.append(
                            f"[path] {rel}:{name} 目录的上一级不存在 -> "
                            f"{os.path.relpath(val, ROOT)}")

        # ---- §5 读取型 open() 的数据文件必须存在 ----
        for lineno, fname in _open_read_literals(tree):
            low = fname.lower()
            if low in ALLOW_MISSING:
                continue
            open_checked += 1
            if low not in basenames:
                problems.append(
                    f"[open] {rel}:{lineno} 读取的数据文件在整个仓库中都不存在 -> "
                    f"{fname}（若该文件已被清理，脚本应同步删除或改指现存数据源）")

        # ---- §3 sys.path 插入目标 ----
        covered = {ln for ln, _ in sp_sites}
        for ln in sorted(_all_sys_path_calls(tree) - covered):
            sp_sites.append((ln, _UNKNOWN))
        for lineno, tgt in sp_sites:
            if not isinstance(tgt, str):
                sp_checked += 1
                problems.append(f"[sys.path] {rel}:{lineno} 目标无法符号求值")
                continue
            if not os.path.isabs(tgt):
                tgt = os.path.abspath(os.path.join(script_dir, tgt))
            sp_checked += 1
            if not os.path.isdir(tgt):
                problems.append(f"[sys.path] {rel}:{lineno} 目标不存在 -> {tgt}")

    # ---- §6 文档/脚本里给出的命令路径必须存在 ----
    doc_cmds, doc_files = _doc_command_paths()
    for rel_doc, lineno, cmd, target in doc_cmds:
        doc_checked += 1
        if not os.path.exists(os.path.join(ROOT, target)):
            if _paper_exempt(target):
                paper_skipped += 1
            else:
                problems.append(
                    f"[doccmd] {rel_doc}:{lineno} 文档给出的命令指向不存在的脚本 -> "
                    f"{cmd}（目录重整后未同步更新；复现者照抄即失败）")

    # ---- 防空转：各类检查都必须真的执行过 ----
    if fileish == 0:
        problems.append("文件类路径检查次数为 0 —— 本轮结论无效（不得据此判通过）")
    if dirish == 0:
        problems.append("目录类路径检查次数为 0 —— 本轮结论无效（不得据此判通过）")
    if smoke == 0:
        problems.append("冒烟指纹比较次数为 0 —— 本轮结论无效（不得据此判通过）")
    if sp_checked == 0:
        problems.append("sys.path 目标检查次数为 0 —— 本轮结论无效（不得据此判通过）")
    if open_checked == 0:
        problems.append("读取型 open() 检查次数为 0 —— 本轮结论无效（不得据此判通过）")
    if doc_files == 0:
        problems.append("§6 扫描的文档数为 0 —— 本轮结论无效（不得据此判通过）")

    # ---- 输出 ----
    print("=" * 72)
    print("L9 路径解析层审计")
    print("=" * 72)
    print(f"  扫描 .py 文件            : {scanned}（成功解析 {parsed}）")
    print(f"  §1 文件类路径目标        : {fileish}")
    print(f"  §1 目录类路径目标        : {dirish}")
    print(f"  §2 冒烟指纹比对          : {smoke}（前缀命中 {smoke_hits}）")
    print(f"  §3 sys.path 插入目标     : {sp_checked}")
    print(f"  §5 读取型 open() 数据文件: {open_checked}")
    print(f"  §6 文档命令路径          : {doc_checked}"
          f"（扫描 {doc_files} 个 .md/.sh/.txt，不含 docs/reviews 历史快照）")
    if paper_skipped:
        print(f"  工件模式豁免: {paper_skipped}（papers/ 与 docs/ 不在本工件内，"
              f"指向两者的目标不判失败；完整项目无此项）")
    if rel_diag:
        print(f"  §4 诊断：相对路径常量 {len(rel_diag)} 条（依赖 CWD，不判失败）")
        for d in rel_diag[:10]:
            print(f"      {d}")
    if posix_hits:
        print(f"  §4 诊断：AutoDL 侧 POSIX 路径 {len(posix_hits)} 条（本机不适用，不判失败）")
        for d in posix_hits[:3]:
            print(f"      {d}")
    if examples:
        print("  抽样（文件类，已确认所在目录存在）:")
        for e in examples:
            print(f"      {e}")
    print()
    if problems:
        uniq = list(dict.fromkeys(problems))
        print(f"问题数: {len(uniq)}")
        for p in uniq:
            print("   ", p)
        sys.exit(1)
    print("问题数: 0")
    print("所有路径常量均指向真实位置，且不存在「从脚本自身位置推导数据目录」的形态。")


if __name__ == "__main__":
    main()
