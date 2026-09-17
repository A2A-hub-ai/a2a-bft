# -*- coding: utf-8 -*-
"""声誉追踪器的**测量性**消融（real 4-model deployment）。

为什么不是"开/关声誉比接受率"
--------------------------------------------------------------------------------
论文 §4.3 与附录明确声明：声誉分数 **不进入计票规则**（式 commit 聚合的是原始票数），
因此声誉**不可能改变**任何 commit 决策。做"开 vs 关声誉、比较决策率/正确率"在数学上
必然得到恒等结果——那是定理的推论，不是实验发现。论文自己也承认这一点：
"The reputation tracker is not isolated by our ablation"。

所以本实验测量的是**追踪器本身报告了什么**（论文目前唯一没有实测数据的组件）：

  M1 决策指标：与论文 tab:ablation 对应单元对照，确认协议路径未变。
  M2 追踪器在线行为：每轮 ρ、r 轨迹；四档罚则的触发分布（按"验证者真值 × 投票是否正确"切分）。
  M3 拜占庭识别性能：把"触发激进罚 −0.25（ρ≥0.7）"当作拜占庭检测器，算 precision/recall/F1。
  M4 **误罚率**：激进罚落在"诚实验证者且该票客观上正确"上的比例（论文声称这类投票应被奖励）。
  M5 `c` 的来源对比：算法 1 要求 c = "提案是否正确"。发布实现用
     ``_estimate_correctness``（格式检查：含 ```python / 含 答案 / 长度>50），
     近乎恒为真 ⇒ ok 退化成"是否投 ACCEPT"。本实验同时用
     (a) oracle c（ground truth）与 (b) released heuristic c 重放，量化二者的差距。

两个阶段
--------------------------------------------------------------------------------
阶段 1（线上，需 GPU）：在真实 4 模型部署上跑协议，**只记录**每一轮每张票
（验证者、票、提案、提案是否真的正确、该票客观上是否正确）。不改变任何决策路径。
阶段 2（离线，纯 CPU 重放）：把记录的投票流喂给追踪器，用两种 c 定义各重放一次。
重放不产生任何 LLM 调用，因此可无限次复现——也正因如此，"决策不受声誉影响"
在重放里是**可验证**的：重放输出决策与线上记录逐字段一致。

用法::

    python experiments/reproduce/reputation_ablation.py                 # 线上 + 重放
    python experiments/reproduce/reputation_ablation.py --replay-only    # 只重放（读缓存）
    python experiments/reproduce/reputation_ablation.py --tasks 10
"""
import os
import sys
import json
import time
import random
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# --- 自定位项目根（原为硬编码服务器路径，换机器或换目录即失效）---
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while not os.path.exists(os.path.join(_ROOT, ".a2a_project_root")) and os.path.dirname(_ROOT) != _ROOT:
    _ROOT = os.path.dirname(_ROOT)
for _d in (os.path.join(_ROOT, "experiments", "reproduce"),
           os.path.join(_ROOT, "experiments", "src"),
           _HERE):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)
A2A_RESULTS = os.environ.get("A2A_RESULTS_DIR", os.path.join(_ROOT, "experiments", "results"))
A2A_DATASETS = os.environ.get("A2A_DATASET_DIR", os.path.join(_ROOT, "experiments", "datasets"))
A2A_MODELS = os.environ.get("A2A_MODEL_DIR", "/autodl-fs/data/models")

from multi_model_vllm import (VLLMClient, MultiModelWorker, MODEL_ENDPOINTS,
                              load_dataset, extract_math_answer, extract_mc_answer,
                              run_code_tests, MAX_ROUNDS)

RESULTS_DIR = A2A_RESULTS
os.makedirs(RESULTS_DIR, exist_ok=True)
VOTE_LOG = os.path.join(RESULTS_DIR, "reputation_vote_stream.json")
OUT_JSON = os.path.join(RESULTS_DIR, "reputation_ablation.json")
PARALLEL = 6

SCENARIOS = [
    {'dataset': 'gsm8k', 'n': 5, 'f': 0, 's': 0, 'attack': None},
    {'dataset': 'gsm8k', 'n': 5, 'f': 1, 's': 1, 'attack': 'strategic_reject'},
    {'dataset': 'gsm8k', 'n': 8, 'f': 2, 's': 1, 'attack': 'collusion'},
    {'dataset': 'mbpp', 'n': 5, 'f': 0, 's': 0, 'attack': None},
    {'dataset': 'mbpp', 'n': 5, 'f': 1, 's': 1, 'attack': 'strategic_reject'},
    {'dataset': 'mbpp', 'n': 8, 'f': 2, 's': 1, 'attack': 'collusion'},
]


# ============================================================ 答案归一化 / 判定
def normalize(ans, task, task_type):
    if not ans:
        return None
    if task_type == 'math':
        v = extract_math_answer(ans)
        if v is None:
            return None
        return str(int(v)) if v == int(v) else str(round(v, 2))
    if task_type == 'code':
        from multi_model_vllm import extract_code
        pat = run_code_tests(extract_code(ans), task.get('test_list', []))
        return ''.join('T' if p else 'F' for p in pat)
    return extract_mc_answer(ans)


def is_correct(ans, task, task_type):
    if not ans:
        return False
    if task_type == 'math':
        a = extract_math_answer(ans)
        b = extract_math_answer(task['answer'])
        return a is not None and b is not None and abs(a - b) < 1e-6
    if task_type == 'code':
        from multi_model_vllm import extract_code
        pat = run_code_tests(extract_code(ans), task.get('test_list', []))
        return all(pat) if pat else False
    letter = extract_mc_answer(ans)
    if not letter:
        return False
    choices = task.get('choices', [])
    idx = ord(letter) - ord('A')
    if not (0 <= idx < len(choices)):
        return False
    gold = task['answer']
    if isinstance(gold, str) and len(gold.strip()) == 1 and gold.strip().upper() in 'ABCD':
        return letter == gold.strip().upper()
    return choices[idx] == gold


def estimate_correctness_released(response, task_type):
    """复刻发布实现 deepseek_worker._estimate_correctness —— 只是**格式**检查。

    math: 含 '## 最终答案' 或 '答案'
    code: 含 '```python' 或 'def '
    else: len > 50
    """
    if not response:
        return False
    if task_type == "math":
        return '## 最终答案' in response or '答案' in response
    if task_type == "code":
        return '```python' in response or 'def ' in response
    return len(response) > 50


# ============================================================ 阶段 1：线上跑协议
def make_workers(n, f, s, attack, clients, assignment, task_type):
    return [MultiModelWorker(worker_id=i, client=clients[assignment[i]],
                             is_byzantine=(i < f),
                             byzantine_type=attack if i < f else None,
                             is_soft_fault=(f <= i < f + s),
                             task_type=task_type)
            for i in range(n)]


def validate_one(w, task, proposal, primary_is_byzantine):
    """与 multi_model_compare_ablation_v2.A2ABFT._validate 完全一致的投票逻辑。"""
    if w.is_byzantine:
        if w.byzantine_type == 'collusion':
            return 'ACCEPT' if primary_is_byzantine else 'REJECT'
        if w.byzantine_type == 'strategic_reject':
            return 'REJECT'
        return random.choice(['ACCEPT', 'REJECT'])
    if w.is_soft_fault and random.random() < 0.3:
        return 'ABSTAIN'
    if not proposal:
        return 'ABSTAIN'
    v = w._judge(task, proposal)
    return 'ABSTAIN' if v is None else ('ACCEPT' if v else 'REJECT')


def run_one_recorded(task, task_idx, sc, clients, assignment, task_type):
    """跑一遍协议并**完整记录**投票流。决策路径与论文扫描一致，不做任何改动。"""
    n, f, s = sc['n'], sc['f'], sc['s']
    workers = make_workers(n, f, s, sc['attack'], clients, assignment, task_type)
    theta_accept = n - 1 - 2 * f - s
    theta_reject = -(n - 1 - f) * 0.5

    idx, pending, rounds = 0, 0, 0
    per_round = []
    decision, proposal_final = None, None
    t0 = time.time()
    for rnd in range(1, MAX_ROUNDS + 1):
        rounds = rnd
        primary = workers[idx]
        proposal, _ = primary.solve(task)
        if not proposal:
            per_round.append({'round': rnd, 'primary': idx,
                              'primary_is_byzantine': bool(primary.is_byzantine),
                              'proposal_empty': True, 'votes': []})
            idx = (idx + 1) % n
            continue
        prop_correct = is_correct(proposal, task, task_type)
        # c 的发布口径必须在**完整回答**上求值：_estimate_correctness 是格式检查
        # （数学看末尾的 '## 最终答案'），若只拿截断文本重算会系统性判为 False。
        # 因此在线阶段就把 c_released 一并落盘，重放时优先用它。
        prop_c_released = estimate_correctness_released(proposal, task_type)
        votes = []
        for i, w in enumerate(workers):
            if i == idx:
                continue
            v = validate_one(w, task, proposal, primary.is_byzantine)
            # 该票客观上是否正确：以"提案是否正确"为真值（论文 Algorithm 1 的 ok 定义）
            vote_ok = (v == 'ACCEPT') == prop_correct if v != 'ABSTAIN' else None
            votes.append({'validator': i, 'vote': v,
                          'is_byzantine': bool(w.is_byzantine),
                          'is_soft_fault': bool(w.is_soft_fault),
                          'vote_ok_gt': vote_ok})
        acc = sum(1 for v in votes if v['vote'] == 'ACCEPT')
        rej = sum(1 for v in votes if v['vote'] == 'REJECT')
        phi = acc - 0.5 * rej
        per_round.append({'round': rnd, 'primary': idx,
                          'primary_is_byzantine': bool(primary.is_byzantine),
                          'proposal_empty': False,
                          'proposal_correct_gt': prop_correct,
                          'proposal_c_released': prop_c_released,
                          'proposal_len': len(proposal),
                          'proposal_text': proposal[:600],
                          'phi': phi, 'theta_accept': theta_accept,
                          'theta_reject': theta_reject,
                          'votes': votes})
        if phi >= theta_accept:
            decision, proposal_final = 'ACCEPT', proposal
            break
        if phi <= theta_reject or pending >= 1:
            idx = (idx + 1) % n
            pending = 0
        else:
            pending += 1
    if decision is None:
        decision = 'PENDING'

    correct_final = is_correct(proposal_final, task, task_type) if proposal_final else False
    return {
        'task_idx': task_idx, 'dataset': sc['dataset'],
        'n': n, 'f': f, 's': s, 'attack': sc['attack'] or 'baseline',
        'task_type': task_type,
        'decision': decision,
        'proposal_correct': bool(correct_final),
        'wrong_commit': bool(decision == 'ACCEPT' and not correct_final),
        'rounds': rounds,
        'elapsed': round(time.time() - t0, 1),
        'rounds_detail': per_round,
    }


def phase1(tasks_per_cell):
    MODEL_KEYS = list(MODEL_ENDPOINTS.keys())
    clients = {k: VLLMClient(k) for k in MODEL_KEYS}
    records = []
    for sc in SCENARIOS:
        ds = sc['dataset']
        task_type = 'code' if ds == 'mbpp' else ('math' if ds == 'gsm8k' else 'knowledge')
        data = load_dataset(ds)
        for t in data:
            if 'question' not in t:
                t['question'] = t.get('description', '')
        random.seed(42)
        tasks = random.sample(data, min(tasks_per_cell, len(data)))
        assignment = [MODEL_KEYS[i % len(MODEL_KEYS)] for i in range(sc['n'])]
        print(f"\n{'#'*70}\n# {ds} n={sc['n']},f={sc['f']},s={sc['s']},"
              f"attack={sc['attack'] or 'baseline'} tasks={len(tasks)}\n{'#'*70}", flush=True)
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
            done = list(ex.map(lambda p: run_one_recorded(p[1], p[0], sc, clients,
                                                          assignment, task_type),
                               list(enumerate(tasks))))
        records.extend(done)
        acc = sum(1 for r in done if r['decision'] == 'ACCEPT')
        wc = sum(1 for r in done if r['wrong_commit'])
        print(f"  决策率={acc/len(done)*100:.1f}%  错误提交={wc/len(done)*100:.1f}%  "
              f"平均轮数={sum(r['rounds'] for r in done)/len(done):.2f}  耗时={time.time()-t0:.0f}s",
              flush=True)
        with open(VOTE_LOG, 'w', encoding='utf-8') as f:
            json.dump({'timestamp': datetime.now().isoformat(),
                       'models': {k: v['name'] for k, v in MODEL_ENDPOINTS.items()},
                       'records': records}, f, ensure_ascii=False, indent=1)
    return records


# ============================================================ 追踪器（Algorithm 1）
class ReputationTracker:
    """论文 Algorithm 1 的忠实实现（含 10 轮窗口的 ρ_i 与 suspect 计数）。

    c_source:
      'oracle'    —— c 用 ground truth（提案是否真的正确）
      'released'  —— c 用发布实现的格式启发式 _estimate_correctness
    """

    WINDOW = 10
    SUSPECT_THRESHOLD = 3

    def __init__(self, n, c_source='oracle'):
        self.n = n
        self.c_source = c_source
        self.r = {i: 1.0 for i in range(n)}
        self.hist = {i: [] for i in range(n)}       # 每轮的票（'accept'/'reject'/'abstain'）
        self.suspect = {i: 0 for i in range(n)}
        self.events = []                            # 每次更新的明细（供统计）
        self.trace = {i: [] for i in range(n)}      # 逐轮 r_i，供画图

    def _rho(self, i):
        h = self.hist[i]
        if not h:
            return 0.0
        return h.count('reject') / len(h)

    def update(self, i, vote, proposal_correct_gt, proposal_text, task_type,
               proposal_c_released=None):
        v = vote.lower()
        self.hist[i].append(v)
        if len(self.hist[i]) > self.WINDOW:
            self.hist[i] = self.hist[i][-self.WINDOW:]
        rho = self._rho(i)

        if self.c_source == 'oracle':
            c = proposal_correct_gt
        elif proposal_c_released is not None:
            # 用在线阶段在**完整回答**上算出的 c（保真）
            c = proposal_c_released
        else:
            # 回退：拿记录里的截断文本重算（会有系统性偏差，仅作兼容）
            c = estimate_correctness_released(proposal_text, task_type)

        # ok 定义与发布实现 (deepseek_worker.py:975-980) 严格一致：
        #   c=True  -> ACCEPT 才算对；c=False -> REJECT 才算对；ABSTAIN 永远不算对。
        # 直接用 (v == 'accept') == c 会把"对错误提案弃权"误判为正确票（可能触发 +0.1 奖励），
        # 这是一个只在 ABSTAIN 上才暴露的析取式陷阱，故写成显式析取。
        ok = ((v == 'accept') and c) or ((v == 'reject') and (not c))
        r_before = self.r[i]
        tier = None
        if rho >= 0.7:
            self.r[i] = max(0.1, self.r[i] - 0.25)
            tier = 'aggressive(ρ≥0.7)'
        elif ok and rho < 0.5:
            self.r[i] = min(1.0, self.r[i] + 0.1)
            tier = 'reward(ok,ρ<0.5)'
        elif not ok:
            self.r[i] = max(0.5, self.r[i] - 0.05)
            tier = 'mild(¬ok)'
        else:
            self.r[i] = max(0.5, self.r[i] - 0.02)
            tier = 'drift(other)'

        # suspect 计数：发布实现里**只有奖励档会重置**，其余三档各自增 1。
        # （这条逻辑必须忠实复刻：论文附录称 suspect 仅告警，而代码在计数达阈值时
        #   会额外施加 −0.2。两者矛盾，本实验用实测数据裁决。）
        if tier == 'reward(ok,ρ<0.5)':
            self.suspect[i] = 0
        else:
            self.suspect[i] += 1

        escalated = False
        if self.suspect[i] >= self.SUSPECT_THRESHOLD:
            self.r[i] = max(0.3, self.r[i] - 0.2)
            escalated = True

        self.events.append({'validator': i, 'vote': v, 'rho': round(rho, 3),
                            'c': bool(c), 'ok': bool(ok), 'tier': tier,
                            'r_before': round(r_before, 4), 'r_after': round(self.r[i], 4),
                            'suspect_after': self.suspect[i],
                            'escalated': escalated})
        self.trace[i].append(round(self.r[i], 4))
        return tier


def replay(records, c_source, persistence='persistent'):
    """离线重放投票流。返回统计数据。

    persistence:
      'persistent' —— 声誉跨任务持续（匹配参考实现：ConsensusLayer 实例在整轮实验里
                      存活，10 轮窗口跨任务累积）。这是 Algorithm 1 的忠实读法。
      'fresh'      —— 每个任务重置（匹配本 harness 每任务重建 worker 的结构）。
                      用来判断失效模式是"冷启动假阳性"还是结构性的。

    重放只读记录的决策，不产生 LLM 调用 —— 因此"决策与声誉无关"在这里是可验证的：
    各档配置下重放出的决策序列必须与线上记录完全一致。
    """
    stats = {'by_dataset': {}, 'decisions': [], 'trace_cont': {},
             'per_task_r': defaultdict(list),
             'c_released_rounds': 0, 'c_released_truncation_flips': 0}
    trackers = {}          # persistence='persistent' 时按细胞持有长驻追踪器
    for rec in records:
        key = f"{rec['dataset']} n={rec['n']},f={rec['f']},s={rec['s']}"
        if persistence == 'persistent':
            tr = trackers.setdefault(key, ReputationTracker(rec['n'], c_source=c_source))
        else:
            tr = ReputationTracker(rec['n'], c_source=c_source)
        n_ev_before = len(tr.events)
        for rd in rec['rounds_detail']:
            if rd.get('proposal_empty'):
                continue
            # 审计：用截断文本重算 c_released 会翻转多少轮（量化"别用截断文本"这条教训）
            if rd.get('proposal_c_released') is not None:
                stats['c_released_rounds'] += 1
                if estimate_correctness_released(rd['proposal_text'],
                                                 rec['task_type']) != rd['proposal_c_released']:
                    stats['c_released_truncation_flips'] += 1
            for v in rd['votes']:
                tr.update(v['validator'], v['vote'], rd['proposal_correct_gt'],
                          rd['proposal_text'], rec['task_type'],
                          proposal_c_released=rd.get('proposal_c_released'))
        new_events = tr.events[n_ev_before:]
        # 校验：重放后决策仍等于线上记录的决策
        stats['decisions'].append((key, rec['task_idx'], rec['decision']))
        b = stats['by_dataset'].setdefault(key, {
            'n': rec['n'], 'f': rec['f'], 's': rec['s'], 'attack': rec['attack'],
            'tasks': 0, 'tiers': Counter(), 'pen_by_group': defaultdict(Counter),
            'tp': 0, 'fp': 0, 'fn': 0, 'mispenalty': 0,
            'escalations': 0, 'escalations_honest': 0, 'escalations_byz': 0,
            'tasks_with_mispenalty': 0, 'tasks_with_aggressive': 0,
            'byz_total': 0, 'honest_total': 0,
            'final_r_byz': [], 'final_r_honest': [], 'trace': defaultdict(list)})
        b['tasks'] += 1
        # 任务级统计（论文所引"每个受攻击细胞 20/20 任务出现误罚"可由此复核）
        _task_mis = _task_aggr = False
        # 每任务结束时的声誉快照（按任务索引对齐，便于对照决策）
        stats['per_task_r'][key].append({
            'task_idx': rec['task_idx'], 'decision': rec['decision'],
            'r': {str(i): round(tr.r[i], 4) for i in range(rec['n'])}})
        for i in range(rec['n']):
            grp = 'byz' if i < rec['f'] else 'honest'
            b['final_r_byz' if grp == 'byz' else 'final_r_honest'].append(tr.r[i])
            b['trace'][grp].append(list(tr.trace[i][-12:]))
        for e in new_events:
            b['tiers'][e['tier']] += 1
            grp = 'byz' if e['validator'] < rec['f'] else 'honest'
            b['pen_by_group'][grp][e['tier']] += 1
            if grp == 'byz':
                b['byz_total'] += 1
            else:
                b['honest_total'] += 1
            if e.get('escalated'):
                b['escalations'] += 1
                b['escalations_byz' if grp == 'byz' else 'escalations_honest'] += 1
            # 检测器：激进罚（ρ≥0.7）触发 ⇒ 判为"疑似拜占庭"
            if e['tier'] == 'aggressive(ρ≥0.7)':
                _task_aggr = True
                if grp == 'byz':
                    b['tp'] += 1
                else:
                    b['fp'] += 1
                # M4 误罚：激进罚落在"诚实 + 该票客观上正确"上
                if grp == 'honest' and e['ok']:
                    b['mispenalty'] += 1
                    _task_mis = True
            elif grp == 'byz':
                b['fn'] += 1

        if _task_mis:
            b['tasks_with_mispenalty'] += 1
        if _task_aggr:
            b['tasks_with_aggressive'] += 1

    # 连续轨迹：持久模式下每个验证者一条完整时间线（供图 5 实测版）
    # 旧的 b['trace'] 是每任务截尾 12 点，跨任务会大量重叠，只适合粗看；
    # 画图必须用下面这条不重叠的整条轨迹。
    if persistence == 'persistent':
        for key, tr in trackers.items():
            b = stats['by_dataset'][key]
            stats['trace_cont'][key] = {
                'n': b['n'], 'f': b['f'], 's': b['s'], 'attack': b['attack'],
                'byz': {str(i): tr.trace[i] for i in range(b['f'])},
                'honest': {str(i): tr.trace[i] for i in range(b['f'], b['n'])},
            }
    return stats


def _avg(xs):
    """空集合返回 None —— 避免 f=0 的细胞把"没有拜占庭节点"报成 r_byz=0.000。"""
    return round(sum(xs) / len(xs), 3) if xs else None


def _redecide(rec):
    """从原始票与阈值独立复现协议状态机（multi_model_compare_ablation_v3.A2ABFT.run）。

    ⚠️ 此前的"决策一致性校验"把 stats['decisions'] 与 records 相比，而两侧都取自
    ``rec['decision']`` —— 同源比较，恒为 True，**没有任何分辨力**。论文一度据此
    写 "decision-neutrality is verified rather than asserted"，该断言缺乏支撑
    （见 docs/AUDIT.md 的决策中性审计一节）。这里改为真正重算：
    phi 从原始票现算，状态机按发布规则推进，结果与 c_source / persistence 无关。
    """
    n, idx, pending = rec['n'], 0, 0
    for rd in rec['rounds_detail']:
        if rd.get('proposal_empty'):
            idx = (idx + 1) % n
            continue
        phi = sum(1.0 for v in rd['votes'] if v['vote'] == 'ACCEPT') \
            - 0.5 * sum(1.0 for v in rd['votes'] if v['vote'] == 'REJECT')
        if phi >= rd['theta_accept']:
            return 'ACCEPT', rd['round']
        if phi <= rd['theta_reject'] or pending >= 1:
            idx = (idx + 1) % n
            pending = 0
        else:
            pending += 1
    return 'PENDING', len(rec['rounds_detail'])


def summarize(stats, records, c_source, persistence, tasks_per_cell):
    mismatches = []
    for r in records:
        d, rds = _redecide(r)
        if d != r['decision'] or rds != r['rounds']:
            mismatches.append({'cell': f"{r['dataset']} n={r['n']},f={r['f']},s={r['s']}",
                               'task_idx': r['task_idx'], 'online': r['decision'],
                               'recomputed': d, 'online_rounds': r['rounds'],
                               'recomputed_rounds': rds})
    consistent = not mismatches

    rows = []
    for key, b in stats['by_dataset'].items():
        tp, fp, fn = b['tp'], b['fp'], b['fn']
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec_ = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec_ / (prec + rec_) if prec + rec_ else 0.0
        n_aggr = b['tiers'].get('aggressive(ρ≥0.7)', 0)
        # ρ≥0.7 的激进罚从未触发时，"误罚率"是未定义而非 0（0 会被误读为"无误罚"）
        mis_rate = round(b['mispenalty'] / n_aggr, 3) if n_aggr else None
        rows.append({
            'cell': key, 'attack': b['attack'], 'tasks': b['tasks'],
            'events': sum(b['tiers'].values()),
            'n_byz_validators': b['f'], 'n_honest_validators': b['n'] - b['f'],
            'tier_aggressive': n_aggr,
            'tier_reward': b['tiers'].get('reward(ok,ρ<0.5)', 0),
            'tier_mild': b['tiers'].get('mild(¬ok)', 0),
            'tier_drift': b['tiers'].get('drift(other)', 0),
            'precision': round(prec, 3), 'recall': round(rec_, 3), 'f1': round(f1, 3),
            'mispenalty_count': b['mispenalty'],
            'tasks_with_mispenalty': b['tasks_with_mispenalty'],
            'tasks_with_aggressive': b['tasks_with_aggressive'],
            'tasks_total': b['tasks'],
            'mispenalty_rate': mis_rate,
            'escalations': b['escalations'],
            'escalations_honest': b['escalations_honest'],
            'escalations_byz': b['escalations_byz'],
            'escalation_on_honest_rate': (round(b['escalations_honest'] / b['escalations'], 3)
                                          if b['escalations'] else None),
            'final_r_byzantine': _avg(b['final_r_byz']) if b['f'] else None,
            'final_r_honest': _avg(b['final_r_honest']),
        })
    return {'c_source': c_source, 'persistence': persistence,
            'decision_consistent': consistent, 'decision_mismatches': mismatches,
            'rows': rows, 'tasks_per_cell': tasks_per_cell}


def m1_table(records):
    """与论文 tab:ablation 对应的决策指标。

    这些指标直接从线上记录算，**不读取** c_source / persistence，所以"四档给出
    相同 M1"是构造性的、不是被验证出来的 —— 它只能说明决策分项在设计上与追踪器
    配置无关。真正有分辨力的中性检验见
    experiments/verification/audit_decision_neutrality.py。
    """
    g = defaultdict(list)
    for r in records:
        g[f"{r['dataset']} n={r['n']},f={r['f']},s={r['s']}"].append(r)
    rows = []
    for key, rs in g.items():
        n = len(rs)
        rows.append({
            'cell': key, 'attack': rs[0]['attack'], 'tasks': n,
            'decision_rate': round(sum(1 for r in rs if r['decision'] == 'ACCEPT') / n, 3),
            'pending_rate': round(sum(1 for r in rs if r['decision'] == 'PENDING') / n, 3),
            'wrong_commit_rate': round(sum(1 for r in rs if r['wrong_commit']) / n, 3),
            'accuracy_when_decided': round(
                sum(1 for r in rs if r['decision'] == 'ACCEPT' and r['proposal_correct'])
                / max(1, sum(1 for r in rs if r['decision'] == 'ACCEPT')), 3),
            'avg_rounds': round(sum(r['rounds'] for r in rs) / n, 2),
        })
    return rows


def _rel(p):
    """相对项目根；跨盘时退回绝对路径（Windows 上 relpath 会抛 ValueError）。"""
    try:
        return os.path.relpath(p, _ROOT)
    except ValueError:
        return p


USAGE = """\
声誉追踪器测量性消融

用法:
  python experiments/reproduce/reputation_ablation.py [--tasks N] [--replay-only]

选项:
  --tasks N     每个细胞的任务数（默认 20，共 6 个细胞）
  --replay-only 跳过线上阶段，直接读缓存投票流重放（纯 CPU，零 LLM 调用）
  -h, --help    显示本帮助

注意: 线上阶段需要 4 个 vLLM 实例在 8000-8003 端口就绪；脚本会先做预检再开跑。
"""


def preflight():
    """线上阶段前预检四个端点，未就绪则直接退出（避免空跑烧时间）。"""
    import urllib.request
    bad, ok = [], []
    for key, ep in MODEL_ENDPOINTS.items():
        origin = ep["base_url"].rstrip("/")
        if origin.endswith("/v1"):
            origin = origin[: -len("/v1")]
        try:
            with urllib.request.urlopen(origin + "/health", timeout=8) as resp:
                if resp.status == 200:
                    ok.append(key)
                else:
                    bad.append(f"{key}({origin}) HTTP {resp.status}")
        except Exception as e:
            bad.append(f"{key}({origin}) {type(e).__name__}")
    if bad:
        sys.exit("[预检失败] 以下端点不可用，请先启动 vLLM：\n  - " + "\n  - ".join(bad))
    print(f"[预检] {len(ok)} 个端点全部就绪: " + ", ".join(ok), flush=True)


def main():
    args = sys.argv[1:]
    if '-h' in args or '--help' in args:
        print(USAGE)
        return
    tasks_per_cell = 20
    if '--tasks' in args:
        tasks_per_cell = int(args[args.index('--tasks') + 1])
    replay_only = '--replay-only' in args

    print('=' * 78)
    print(f'声誉追踪器测量性消融 | tasks/cell={tasks_per_cell} | replay_only={replay_only}')
    print('=' * 78, flush=True)

    if replay_only:
        if not os.path.exists(VOTE_LOG):
            sys.exit(f"没有缓存的投票流: {VOTE_LOG}（先跑一次线上阶段）")
        records = json.load(open(VOTE_LOG, encoding='utf-8'))['records']
        print(f"[重放] 载入 {len(records)} 条任务记录（无 LLM 调用）")
    else:
        preflight()
        records = phase1(tasks_per_cell)

    m1 = m1_table(records)
    print('\n' + '=' * 78)
    print('M1 决策指标（与声誉设置无关 —— 论文定理的可验证体现）')
    print('=' * 78)
    print(f"{'细胞':<22}{'任务':>5}{'接受率':>9}{'PENDING':>9}{'错误提交':>10}{'决定后正确率':>13}{'平均轮数':>9}")
    for r in m1:
        print(f"{r['cell']:<22}{r['tasks']:>5}{r['decision_rate']:>9.3f}{r['pending_rate']:>9.3f}"
              f"{r['wrong_commit_rate']:>10.3f}{r['accuracy_when_decided']:>13.3f}{r['avg_rounds']:>9.2f}")

    print('\n' + '=' * 78)
    print('阶段 2：离线重放（c 定义 × 声誉持久性 四档）')
    print('=' * 78)
    out = {'timestamp': datetime.now().isoformat(),
           'tasks_per_cell': tasks_per_cell,
           'n_records': len(records),
           'm1_decision_metrics': m1,
           'arms': []}
    traj_oracle = None
    for c_source in ('oracle', 'released'):
        for persistence in ('persistent', 'fresh'):
            st = replay(records, c_source, persistence)
            summ = summarize(st, records, c_source, persistence, tasks_per_cell)
            out['arms'].append(summ)
            if c_source == 'oracle' and persistence == 'persistent':
                traj_oracle = st
            print(f"\n--- c={c_source} / 声誉{('跨任务持续' if persistence=='persistent' else '每任务重置')} ---"
                  f"  决策序列与线上记录一致: {summ['decision_consistent']}")
            print(f"{'细胞':<22}{'事件':>5}{'激进':>5}{'奖励':>5}{'轻惩':>5}{'漂移':>5}"
                  f"{'P':>7}{'R':>7}{'误罚':>7}{'误罚率':>8}{'升级':>6}{'升级伤诚':>9}"
                  f"{'r_byz':>8}{'r_hon':>7}")
            for r in summ['rows']:
                rb = '-' if r['final_r_byzantine'] is None else f"{r['final_r_byzantine']:.3f}"
                mr = '-' if r['mispenalty_rate'] is None else f"{r['mispenalty_rate']:.3f}"
                eh = '-' if r['escalation_on_honest_rate'] is None else f"{r['escalation_on_honest_rate']:.3f}"
                print(f"{r['cell']:<22}{r['events']:>5}{r['tier_aggressive']:>5}{r['tier_reward']:>5}"
                      f"{r['tier_mild']:>5}{r['tier_drift']:>5}{r['precision']:>7.3f}{r['recall']:>7.3f}"
                      f"{r['mispenalty_count']:>7}{mr:>8}{r['escalations']:>6}{eh:>9}"
                      f"{rb:>8}{r['final_r_honest']:>7.3f}")

    # 轨迹（供图 5 由"示意"改为"实测"）
    # trajectories: 持久模式下每个验证者的连续 r_i 时间线（不重叠，可直接画图）
    # per_task_reputation: 每个任务结束时的 r_i 快照（按 task_idx 对齐，便于对照决策）
    out['trajectories'] = traj_oracle.get('trace_cont', {})
    out['per_task_reputation'] = dict(traj_oracle.get('per_task_r', {}))
    out['trajectory_note'] = ('trajectories = c=oracle / 声誉跨任务持续 一档；'
                              '每细胞按 byz/honest 分组给出每个验证者的完整 r_i 时间线')

    # 审计：截断文本重算 c_released 的翻转率（四档相同，取任一档即可）
    flips = traj_oracle.get('c_released_truncation_flips', 0)
    rounds_n = traj_oracle.get('c_released_rounds', 0)
    out['c_released_truncation'] = {
        'rounds': rounds_n, 'flips': flips,
        'flip_rate': round(flips / rounds_n, 4) if rounds_n else None}
    print('\n' + '-' * 78)
    print(f"[审计] 用截断文本重算 c_released：{rounds_n} 轮中 {flips} 轮被翻转"
          f"（{out['c_released_truncation']['flip_rate']}）—— 故 released 档使用在线记录的"
          f"完整文本口径")

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n结果 -> {_rel(OUT_JSON)}")
    print(f"投票流 -> {_rel(VOTE_LOG)}")
    print('REPUTATION_ABLATION_DONE')


if __name__ == '__main__':
    main()
