"""R8 audit: verify prose range claims against the underlying data subsets.

Two data sources:
  sweep  = full_bft_sweep_aggregated.json   -> 31 cells, n=250, datasets gsm8k/mbpp/mmlu
  tri    = multi_model_3seed_aggregated.json-> 48 cells, n=90,  datasets gsm8k/mbpp

Method pools MUST be kept disjoint: ablation variants are NOT baselines.
"""
import json, os


def _find_root(start):
    """向上查找项目根标记文件，使本脚本与自身所在目录无关（见 audit_table_numbers.py）。"""
    cur = os.path.dirname(os.path.abspath(start))
    while True:
        if os.path.exists(os.path.join(cur, '.a2a_project_root')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise RuntimeError('未找到项目根：缺少 .a2a_project_root 标记文件')
        cur = parent


RES = os.path.join(_find_root(__file__), 'experiments', 'results')

TRUE_BASELINES = {'A2A-Sim', 'LLM-Debate', 'Simple Majority', 'Weighted Majority'}
# The paper's abstract/related-work claim "16.7-63.4%" is scoped to the
# *unvalidated voting- and debate-based* baselines, which explicitly excludes
# A2A-Sim (a supermajority-stop self-aggregation protocol adapted with a
# 0.7 confidence filter in our baseline, discussed separately in Section 6.5).
VOTING_DEBATE = {'LLM-Debate', 'Simple Majority', 'Weighted Majority'}
ABLATION_VARIANTS = {'A2A-BFT w/o 视图切换', 'A2A-BFT w/o 语义验证', 'A2A-BFT 固定阈值'}
FULL = 'A2A-BFT'

def load(fn):
    d = json.load(open(os.path.join(RES, fn), encoding='utf-8'))
    return d if isinstance(d, list) else d.get('rows', [])

sweep = load('full_bft_sweep_aggregated.json')
tri = load('multi_model_3seed_aggregated.json')

def sub(rows, **kw):
    out = []
    for r in rows:
        if all(r.get(k) == v for k, v in kw.items()):
            out.append(r)
    return out

def in_boundary(r):
    return r['n'] >= 3 * r['f'] + r['s'] + 1

def rng(rows, key):
    v = [r[key] for r in rows]
    return (min(v), max(v), len(v)) if v else (None, None, 0)

PROBLEMS = []

def check(label, rows, key, lo_c, hi_c, tol=0.55):
    lo, hi, n = rng(rows, key)
    if lo is None:
        print(f'  ?? {label}: NO DATA'); PROBLEMS.append(f'{label}: no data'); return
    ok = abs(lo - lo_c) <= tol and abs(hi - hi_c) <= tol
    print(f'  {"OK  " if ok else "MISMATCH"} {label}: data=[{lo:.1f}, {hi:.1f}] n={n}  claimed=[{lo_c}, {hi_c}]')
    if not ok:
        PROBLEMS.append(f'{label}: data [{lo:.1f},{hi:.1f}]  claimed [{lo_c},{hi_c}]')

hdr = lambda t: print('\n' + '=' * 76 + f'\n{t}\n' + '=' * 76)

# ---------------------------------------------------------------- A
hdr('A. Fault-free decision rates')
# MBPP: sweep baselines AND the n=90 companion borrowed into tab:baseline
mbpp_ff = sub(sweep, dataset='mbpp', attack='baseline') + \
          sub(tri, dataset='mbpp', attack='baseline', method=FULL)
check('MBPP fault-free decision (70-74%)', mbpp_ff, 'decision_rate_mean', 70, 74)
check('GSM8K fault-free decision (55-59%)',
      sub(sweep, dataset='gsm8k', attack='baseline'), 'decision_rate_mean', 55, 59)
check('MMLU fault-free decision (11-15%)',
      sub(sweep, dataset='mmlu', attack='baseline'), 'decision_rate_mean', 11, 15)

# ---------------------------------------------------------------- B
hdr('B. Within-boundary MBPP wrong-commit must be 0.0 under every attack')
wb = [r for r in sweep if r['dataset'] == 'mbpp' and r['attack'] != 'baseline' and in_boundary(r)]
wb += [r for r in tri if r['dataset'] == 'mbpp' and r['method'] == FULL
       and r['attack'] != 'baseline' and in_boundary(r)]
check('MBPP within-boundary wrong-commit (0.0)', wb, 'wrong_commit_rate_mean', 0, 0)

# ---------------------------------------------------------------- C
hdr('C. Sub-boundary violations (abstract: GSM8K<=72.4, MMLU<=90.0, code 0-9.6)')
for nm, ds in [('GSM8K', 'gsm8k'), ('MMLU', 'mmlu'), ('MBPP', 'mbpp')]:
    rs = [r for r in sweep if r['dataset'] == ds and not in_boundary(r)]
    lo, hi, n = rng(rs, 'wrong_commit_rate_mean')
    print(f'  {nm:6s} sub-boundary wrong-commit=[{lo:.1f}, {hi:.1f}] n={n}')
exp = {'GSM8K': 72.4, 'MMLU': 90.0, 'MBPP': 9.6}
for nm, ds in [('GSM8K', 'gsm8k'), ('MMLU', 'mmlu'), ('MBPP', 'mbpp')]:
    rs = [r for r in sweep if r['dataset'] == ds and not in_boundary(r)]
    hi = rng(rs, 'wrong_commit_rate_mean')[1]
    if abs(hi - exp[nm]) > 0.55:
        PROBLEMS.append(f'abstract sub-boundary max {nm}={hi:.1f} claimed {exp[nm]}')

# ---------------------------------------------------------------- D
hdr('D. MMLU in-prose ranges')
check('MMLU under attack decision (65-96%)',
      [r for r in sweep if r['dataset'] == 'mmlu' and r['attack'] != 'baseline'],
      'decision_rate_mean', 65, 96)
mmlu_sub = [r for r in sweep if r['dataset'] == 'mmlu' and not in_boundary(r)]
lo, hi, n = rng(mmlu_sub, 'wrong_commit_rate_mean')
check('MMLU below-boundary wrong-commit (56-90%)', mmlu_sub, 'wrong_commit_rate_mean', 56, 90)

# ---------------------------------------------------------------- E
hdr('E. Voting/debate baselines wrong-commit under collusion (abstract: 16.7-63.4%)')
bc = [r for r in tri if r['method'] in VOTING_DEBATE and r['attack'] == 'collusion' and in_boundary(r)]
check('voting/debate baselines collusion wrong-commit (16.7-63.4%)', bc, 'wrong_commit_rate_mean', 16.7, 63.4)
print('    reference: A2A-Sim is reported separately (Section 6.5), and its GSM8K')
print('    collusion wrong-commit is *lower* than ours, which the paper discloses:')
asx = [r for r in tri if r['method'] == 'A2A-Sim' and r['attack'] == 'collusion' and in_boundary(r)]
for r in asx:
    print(f'      A2A-Sim {r["dataset"]}: wrong-commit={r["wrong_commit_rate_mean"]:.1f}%')
ab = [r for r in tri if r['method'] == FULL and r['attack'] == 'collusion' and in_boundary(r)]
for r in ab:
    print(f'      A2A-BFT {r["dataset"]}: wrong-commit={r["wrong_commit_rate_mean"]:.1f}%')

# ---------------------------------------------------------------- F
hdr('F. accuracy-when-decided (ours 83-100% vs TRUE baselines 37-89%)')
check('A2A-BFT accuracy-when-decided (83-100%)',
      [r for r in tri if r['method'] == FULL and r['attack'] != 'baseline'],
      'accuracy_when_decided_mean', 83, 100)
check('true baselines accuracy-when-decided (37-89%)',
      [r for r in tri if r['method'] in TRUE_BASELINES and r['attack'] != 'baseline'],
      'accuracy_when_decided_mean', 37, 89)

# ---------------------------------------------------------------- G
hdr('G. GSM8K within-boundary wrong commits (prose: 11.6-23.2%)')
g = [r for r in sweep if r['dataset'] == 'gsm8k' and r['attack'] != 'baseline' and in_boundary(r)]
check('GSM8K within-boundary wrong-commit (11.6-23.2%)', g, 'wrong_commit_rate_mean', 11.6, 23.2)
print('    (cells at n=250 only; the 4.5% cell is the n=90 ablation companion)')

# ---------------------------------------------------------------- H
hdr('H. Decision-rate rise under attack (up to 98% vs 59.2% fault-free)')
gsm_atk = [r for r in sweep if r['dataset'] == 'gsm8k' and r['attack'] != 'baseline']
lo, hi, n = rng(gsm_atk, 'decision_rate_mean')
ff = rng(sub(sweep, dataset='gsm8k', attack='baseline'), 'decision_rate_mean')[0]
print(f'  GSM8K attacked decision max={hi:.1f}; fault-free min={ff:.1f}  (prose: "up to 98%" vs "59.2%")')

# ---------------------------------------------------------------- I
hdr('I. Sweep / ablation scale arithmetic')
print(f'  sweep cells={len(sweep)}  tasks={sum(r.get("total_tasks",0) for r in sweep)}  (paper: 31 cells / 7,750)')
print(f'  tri   cells={len(tri)}  tasks={sum(r.get("total_tasks",0) for r in tri)}  (paper: 48 cells / 4,320)')
if len(sweep) != 31 or sum(r.get('total_tasks', 0) for r in sweep) != 7750:
    PROBLEMS.append('sweep scale claim wrong')
if len(tri) != 48 or sum(r.get('total_tasks', 0) for r in tri) != 4320:
    PROBLEMS.append('ablation scale claim wrong')

# ---------------------------------------------------------------- J
hdr('J. Table coverage (how many of the 48 cells are actually displayed)')
disp_abl = [r for r in tri if r['method'] in (ABLATION_VARIANTS | {FULL})
            and not (r['n'] == 5 and r['f'] == 0 and r['s'] == 0)]
disp_cmp = [r for r in tri if r['method'] in (TRUE_BASELINES | {FULL})
            and not (r['n'] == 5 and r['f'] == 0 and r['s'] == 0)]
print(f'  displayed in tab:ablation      = {len(disp_abl)} of 24 variant cells')
print(f'  displayed in tab:hetero_compare= {len(disp_cmp)} of 30 method cells')
print(f'  -> {len(disp_abl)+len(disp_cmp)} shown / 48 total; '
      f'{48-len(disp_abl)-len(disp_cmp)} baseline-condition cells unreported')

# ---------------------------------------------------------------- K
# R16-2 回归守卫：正文凡声称 "$48$ cells"（数据 48、表内仅 36），同句附近必须带
# "$36$ tabulated" 披露。Round 8 修复过、页数压缩时曾被静默删除，且本脚本旧版
# 只算账不查标注在位——此处补上。
hdr('K. "$48$ cells" claims must disclose "$36$ tabulated" (R16-2 guard)')
TEX = None
_cur = os.path.dirname(os.path.abspath(__file__))
for _rel in ('../../papers/iclr2027_main.tex',):
    _p = os.path.normpath(os.path.join(_cur, _rel))
    if os.path.exists(_p):
        TEX = _p
        break
if TEX is None:
    PROBLEMS.append('K: 找不到 papers/iclr2027_main.tex')
else:
    _tex = open(TEX, encoding='utf-8').read()
    _claims = list(__import__('re').finditer(r'\$48\$', _tex))
    if not _claims:
        PROBLEMS.append('K: 正文找不到任何 "$48$" 声称（可能措辞已变，请复核本守卫）')
    for m in _claims:
        lo, hi = max(0, m.start() - 500), min(len(_tex), m.end() + 500)
        window = _tex[lo:hi]
        checked_k = 'tabulated' in window
        ln = _tex[:m.start()].count('\n') + 1
        if checked_k:
            print(f'  L{ln}: "$48$" 声称带 tabulated 披露  OK')
        else:
            PROBLEMS.append(f'K: L{ln} 的 "$48$" 声称缺少 "$36$ tabulated" 披露'
                            '（读者逐表只能数到 36 cells）')

print('\n' + '=' * 76)
print('SUMMARY')
print('=' * 76)
if PROBLEMS:
    for p in PROBLEMS:
        print('  PROBLEM:', p)
else:
    print('  No numeric mismatches found.')
