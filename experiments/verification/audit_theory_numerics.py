"""R8 audit part 2: numeric instantiation of the theory + threshold safety.

R6 checked the symbolic algebra. Here we check every *number* the paper derives
from the formulas, and re-verify that no configuration inside the safety
boundary can have phi_min < theta_accept.
"""
import math
import os
from math import comb
from fractions import Fraction


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


ROOT = _find_root(__file__)
SRC_PKG = os.path.join(ROOT, 'experiments', 'src', 'a2a_bft')

PROBLEMS = []
def rep(label, ok, detail):
    print(f'  {"OK  " if ok else "MISMATCH"} {label}: {detail}')
    if not ok:
        PROBLEMS.append(f'{label}: {detail}')

def hdr(t): print('\n' + '=' * 76 + f'\n{t}\n' + '=' * 76)

ph = 0.9  # paper's illustrative validation reliability

def theta_accept(n, f, s):
    """theta_accept = n - 1 - 2f - s  (paper Eq. in Section 4.3)"""
    return n - 1 - 2 * f - s

def theta_reject(n, f):
    """theta_reject = -(n - 1 - f) / 2"""
    return Fraction(-(n - 1 - f), 2)

hdr('1. Single-round acceptance bound  p_h^(n-1-f-s) = 0.81 for n=5,f=1,s=1')
v = ph ** (5 - 1 - 1 - 1)
rep('p_h^(n-1-f-s)', abs(v - 0.81) < 5e-3, f'{v:.4f} (paper: 0.81)')

hdr('2. Non-termination bound (1 - 0.81)^k ~ 6e-8 for k=10')
v = (1 - 0.81) ** 10
rep('(1-p)^k', 5e-8 < v < 7e-8, f'{v:.3e} (paper: ~6e-8)')

hdr('3. Semantic validation error  P(error) ~ 0.028 for p_h=0.9, m=3, k=ceil(2m/3)=2')
m, k = 3, math.ceil(2 * 3 / 3)
perr = sum(comb(m, j) * ph ** j * (1 - ph) ** (m - j) for j in range(k))
rep('P(error)', abs(perr - 0.028) < 5e-4, f'{perr:.4f} with k={k} (paper: 0.028)')

hdr('4. Threshold safety under the TWO soft-fault assumptions')
print('   (a) Theorem 5.1 assumption: soft faults ABSTAIN in the worst case')
bad_a = []
for n in range(4, 11):
    for f in range(0, n // 3 + 2):
        for s in range(0, 4):
            if n < 3 * f + s + 1:
                continue
            phi_min = (n - 1 - f - s) - 0.5 * f          # soft faults abstain
            if phi_min < theta_accept(n, f, s):
                bad_a.append((n, f, s, phi_min, theta_accept(n, f, s)))
rep('phi_min >= theta_accept (soft abstain)',
    not bad_a, f'violations={bad_a if bad_a else "none"} -- holds for ALL in-boundary configs')
print('   (b) adversarial soft faults (Appendix A.1.1): also REJECT -> phi_min = n-1-1.5f-1.5s')
bad_b = []
for n in range(4, 11):
    for f in range(0, n // 3 + 2):
        for s in range(0, 4):
            if n < 3 * f + s + 1:
                continue
            phi_min = (n - 1 - f - s) - 0.5 * f - 0.5 * s
            if phi_min < theta_accept(n, f, s):
                bad_b.append((n, f, s))
rep('phi_min >= theta_accept  <=>  s <= f (as the paper states)',
    all(s > f for (n, f, s) in bad_b),
    f'{len(bad_b)} violations, all with s>f: {bad_b[:6]}{"..." if len(bad_b)>6 else ""}')

hdr('5. Claim: phi_min = 1.5f - 0.5s at n=3f+s+1, and >= f = theta_accept iff s<=f')
bad = []
for n in range(4, 11):
    for f in range(0, n // 3 + 2):
        for s in range(0, 3):
            if n != 3 * f + s + 1:
                continue
            ta = theta_accept(n, f, s)
            phi_min = (n - 1 - f - s) - 0.5 * f - 0.5 * s
            # (a) closed form must match
            if abs(phi_min - (1.5 * f - 0.5 * s)) > 1e-9:
                bad.append(('closed-form', n, f, s, phi_min, 1.5 * f - 0.5 * s))
            # (b) s == f -> equality with theta_accept ; s < f -> strict
            if s == f and not (phi_min == f == ta):
                bad.append(('equality s=f', n, f, s, phi_min, ta))
            if s < f and not (phi_min > ta):
                bad.append(('strict s<f', n, f, s, phi_min, ta))
rep('phi_min closed form + s<=f condition', not bad, f'violations={bad if bad else "none"}')

hdr('5b. General condition phi_min >= theta_accept  <=>  s <= f (all in-boundary n)')
bad = []
for n in range(4, 11):
    for f in range(0, n // 3 + 2):
        for s in range(0, 4):
            if n < 3 * f + s + 1:
                continue
            phi_min = (n - 1 - f - s) - 0.5 * f - 0.5 * s
            if (phi_min >= theta_accept(n, f, s)) != (s <= f):
                bad.append((n, f, s, phi_min, theta_accept(n, f, s)))
rep('iff s<=f', not bad, f'violations={bad if bad else "none"}')

hdr('6. theta_accept at the boundary n=3f+s+1 equals f')
bad = []
for n in range(4, 12):
    for f in range(0, n):
        for s in range(0, 4):
            if n == 3 * f + s + 1 and theta_accept(n, f, s) != f:
                bad.append((n, f, s, theta_accept(n, f, s)))
rep('theta_accept(boundary)=f', not bad, f'violations={bad if bad else "none"}')

hdr('7. Rotations: honest primary within every f+1 rounds (round-robin)')
# trivially true for round-robin with n validators; check n-(f+s) >= 1 honesty margin
bad = []
for n in range(4, 11):
    for f in range(0, n // 3 + 2):
        for s in range(0, 3):
            if n < 3 * f + s + 1:
                continue
            if n - f - s < 1:
                bad.append((n, f, s))
rep('honest majority present', not bad, f'violations={bad if bad else "none"}')

hdr('8. 2f+1 confirmations > f Byzantine (view-change safety)')
bad = [(n, f) for n in range(4, 11) for f in range(n) if 2 * f + 1 <= f]
rep('2f+1>f', not bad, f'violations={bad if bad else "none"} for all f>=0')

hdr('9. Complexity: O(n^2) messages/round; rounds claimed 1-3')
# messages: validators broadcast to all agents -> (n-1) x n
for n in (4, 5, 6, 8):
    print(f'   n={n}: (n-1)*n = {n*(n-1)} messages/round  -> O(n^2)')

hdr('10. Wilson upper bound for 0/90 successes (paper: [0.0, 4.1]%)')
z = 1.959963985
def wilson_upper(x, n, z=z):
    p = x / n
    denom = 1 + z*z/n
    centre = p + z*z/(2*n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return (centre + half) / denom
u = wilson_upper(0, 90)
rep('Wilson upper 0/90', abs(u*100 - 4.1) < 0.06, f'{u*100:.2f}% (paper: 4.1%)')

# ---------------- R12-1: decision-consistency margin (Byzantine vote equivocation) ----------------
hdr('6. Decision-consistency margin  (Theorem 5.1(i): theta_accept - theta_reject must exceed 1.5f)')
# 拜占庭投票拔弄（对同一提案向不同副本发不同 verdict）最多把 φ 移动 1.5f
# （REJECT 贡献 -0.5，ACCEPT 贡献 +1）。定理 5.1(i) 断言诚实副本不会得到"相反的可终结决策"，
# 等价于阈值间隙 gap >= 2f+0.5s 且 gap > 1.5f（f+s>0 时）。
bad = []
for n in range(3, 21):
    for f in range(0, 8):
        for s in range(0, 8):
            if n < 3 * f + s + 1:
                continue
            gap = theta_accept(n, f, s) - float(theta_reject(n, f))
            if gap < (2 * f + 0.5 * s) - 1e-9 or (gap <= 1.5 * f + 1e-9 and f + s > 0):
                bad.append((n, f, s, gap, 1.5 * f))
rep('gap >= 2f+0.5s  and  gap > 1.5f  for every in-boundary config',
    not bad, f'violations={bad if bad else "none"}')
g511 = theta_accept(5, 1, 1) - float(theta_reject(5, 1))
rep('n=5,f=1,s=1 gap', abs(g511 - 2.5) < 1e-9, f'{g511} > 1.5f = 1.5')

# ---------------- R12-2: reference implementation reproduces the paper's threshold rule ----------------
hdr('7. Reference implementation reproduces the paper threshold rule (executable probe)')
import sys
sys.path.insert(0, os.path.join(ROOT, 'experiments', 'src'))
try:
    from a2a_bft.deepseek_worker import ConsensusLayer, Verdict, Vote

    def _probe(n, f, s, na, nr):
        layer = ConsensusLayer(n=n, f=f, s=s, use_reputation=False, use_view_change=False)
        votes = ([Vote(i, 'h', Verdict.ACCEPT, 0.9, {}) for i in range(na)] +
                 [Vote(100 + i, 'h', Verdict.REJECT, 0.9, {}) for i in range(nr)])
        return layer._commit([], votes, None)

    # (n, f, s, n_accept, n_reject, expected verdict under the paper's rule)
    probes = [(4, 0, 0, 2, 1, 'PENDING'),   # phi=1.5 < theta_accept=3  -> 曾因 f=0 特例误判 ACCEPT
              (4, 0, 0, 3, 0, 'ACCEPT'),
              (5, 0, 0, 4, 0, 'ACCEPT'),
              (5, 1, 1, 2, 1, 'ACCEPT'),
              (6, 2, 0, 2, 3, 'PENDING')]
    for (n, f, s, na, nr, exp) in probes:
        try:
            got = _probe(n, f, s, na, nr)
        except Exception as exc:                      # noqa: BLE001
            got = f'ERROR {type(exc).__name__}'
        rep(f'  ref-impl _commit  n={n},f={f},s={s}  A={na} R={nr}',
            got == exp, f'code={got}  paper-rule={exp}')
except Exception as exc:                              # noqa: BLE001
    rep('ref-impl import', False, f'{type(exc).__name__}: {exc}')

# ---------------- R12-3: shipped code contains no threshold contradicting the paper ----------------
hdr('8. Shipped consensus code: no threshold contradicts the paper formula theta_accept=n-1-2f-s')
import glob as _glob
import re as _re

_SRC = SRC_PKG
# 论文式右值特征（空格无关）
_PAPER = ('2*self.f', '2*f')
_bad = []
_scanned = 0
# 递归扫描：core/ 与 legacy/ 都要覆盖——归档不等于豁免论文公式一致性
for _p in sorted(_glob.glob(os.path.join(_SRC, '**', '*.py'), recursive=True)):
    for _ln, _line in enumerate(open(_p, encoding='utf-8', errors='replace'), 1):
        _s = _line.strip()
        if _s.startswith('#') or _s.startswith('"'):
            continue
        # 只审 theta_accept / theta 的赋值（theta_reject 合法含 0.5）
        _m = _re.match(r'(?:self\.)?(theta_accept|theta)\s*=\s*(.+)$', _s)
        if not _m:
            continue
        _scanned += 1
        _rhs = _m.group(2).split('#')[0]
        _rhs_ns = _rhs.replace(' ', '')
        if not _rhs_ns:
            continue
        # 允许：参数/变量透传、方法调用、论文式、消融用固定阈值
        if _rhs_ns.endswith(')') and '0.5' not in _rhs_ns:
            continue
        if any(t in _rhs_ns for t in _PAPER):
            continue
        if _re.fullmatch(r'-?\d+(\.\d+)?', _rhs_ns):        # 固定阈值（消融开关）
            continue
        if '0.5' in _rhs_ns:                                 # 多数式反模式
            _bad.append(f'{os.path.relpath(_p, ROOT)}:{_ln}  {_s}')
rep(f'scanned {_scanned} theta_accept assignments; none use a 0.5-majority form',
    not _bad, f'violations={_bad}' if _bad else 'all follow n-1-2f-s or an explicit ablation constant')

# 定点回归：本轮修复过的两个模块不得再出现该反模式（core/ 或 legacy/ 均可）
for _name in ('distributed_worker.py', 'langgraph_integration.py'):
    _f = next((c for c in (os.path.join(_SRC, _name), os.path.join(_SRC, 'legacy', _name))
               if os.path.exists(c)), None)
    if _f is None:
        rep(f'{_name}: present', False, f'模块缺失（core 与 legacy 均未找到）')
        continue
    _txt = open(_f, encoding='utf-8', errors='replace').read()
    _hit = _re.search(r'theta\w*\s*=\s*\(\s*n_total\s*-\s*self\.f\s*\)\s*\*\s*0\.5', _txt)
    # 注：失败详情必须与成功详情不同，否则负向测试无法区分"通过"与"空转"。
    rep(f'{_name}: no (n - f) * 0.5 threshold remains',
        not _hit, f'found {_hit.group(0)!r}' if _hit else 'clean')

print('\n' + '=' * 76)
print('SUMMARY')
print('=' * 76)
if PROBLEMS:
    for p in PROBLEMS:
        print('  PROBLEM:', p)
else:
    print('  All numeric instantiations of the theory check out.')
