"""
A2A-BFT 学术论文实验数据可视化
生成ICLR论文所需的图表

数据源（全部为真机产物，见 docs/audit/DATA_SOURCE_AUDIT.md）：
    experiments/results/full_bft_sweep_aggregated.json     31 格 × n=250 扫描
    experiments/results/multi_model_3seed_aggregated.json  异构 4 模型 48 格 × n=90
    experiments/results/reputation_ablation.json           声誉追踪器四档重放

2026-09-17 移除的失效函数（均引用已删除的模拟期文件，保留会使脚本看似可用）：
    load_experiment_data()         读 final_results_100rounds.json /
                                   performance_test_results.json /
                                   final_a2a_bft_results.json（三者皆为模拟期产物，已删）
    plot_acceptance_rates()        上者的唯一消费者
    plot_fault_tolerance_surface() 不读任何数据，用 honest_ratio * 95 的
                                   「95% 效率因子」合成接受率热力图
                                   —— 合成图，与真机测量无关，误用风险高于价值
main() 从未调用上述三者；删除后本脚本出口仍是论文实际使用的 5 张图。
"""

import matplotlib.pyplot as plt
import numpy as np
import json
import os

# 项目根自定位（原为硬编码的 Windows 绝对路径，换机器即失效）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERIMENTS = os.path.join(ROOT, "experiments")
RESULTS = os.path.join(EXPERIMENTS, "results")
FIGDIR = os.path.join(ROOT, "papers", "figures")
FIGSOURCE = os.path.join(FIGDIR, ".figsource.json")


def _md5(path):
    import hashlib
    with open(path, "rb") as fp:
        return hashlib.md5(fp.read()).hexdigest()


def _logic_sha1(path):
    """脚本的**逻辑**指纹：AST 化后剥掉模块/函数/类的文档串再哈希。

    注释根本不进入 AST，因此改注释、改文档串都不会改变本值；改任何一句可执行
    代码都一定会改变它。audit_figures.py 用同一算法做内容级新鲜度判定——之所以
    不用 mtime，是因为「改一行注释」会把所有图误判为陈旧（2026-09-17 实测）。
    注意：本函数与 audit_figures.py 中的同名逻辑必须保持一致。
    """
    import ast
    import hashlib
    with open(path, encoding="utf-8") as fp:
        tree = ast.parse(fp.read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body.pop(0)
    return hashlib.sha1(ast.dump(tree).encode("utf-8")).hexdigest()


# 五张论文用图各自依赖的数据文件（示意类两张只依赖脚本逻辑）
FIGURE_DEPS = {
    "consensus_flow.pdf": [],
    "architecture.pdf": [],
    "reputation_mechanism.pdf": ["reputation_ablation.json"],
    "performance_comparison.pdf": ["full_bft_sweep_aggregated.json",
                                   "multi_model_3seed_aggregated.json"],
    "attack_resistance.pdf": ["full_bft_sweep_aggregated.json",
                              "multi_model_3seed_aggregated.json"],
}


def write_figsource_stamp():
    """记录「这五张图是由哪个逻辑版本的脚本、基于哪份数据生成的」。

    审计侧据此判定陈旧：逻辑指纹或任一数据文件内容变了，才要求重出图。
    """
    data = ["reputation_ablation.json", "full_bft_sweep_aggregated.json",
            "multi_model_3seed_aggregated.json"]
    stamp = {
        "generator": os.path.basename(__file__),
        "generator_logic_sha1": _logic_sha1(os.path.abspath(__file__)),
        "data_md5": {d: _md5(os.path.join(RESULTS, d))
                     for d in data if os.path.exists(os.path.join(RESULTS, d))},
        "figure_deps": FIGURE_DEPS,
    }
    with open(FIGSOURCE, "w", encoding="utf-8") as fp:
        json.dump(stamp, fp, indent=2, sort_keys=True)
    print(f"✓ Saved: {os.path.basename(FIGSOURCE)}（脚本逻辑 + 数据内容指纹）")

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 颜色方案
COLORS = {
    'accept': '#2ECC71',
    'reject': '#E74C3C',
    'manual': '#F39C12',
    'byzantine': '#9B59B6',
    'honest': '#3498DB'
}

def _load_sweep():
    """加载全量真机扫描聚合数据（31 格 × n=250/格，5 种子 x 50 任务）"""
    with open(os.path.join(RESULTS, 'full_bft_sweep_aggregated.json'), 'r') as f:
        return json.load(f)['rows']


def _load_multi():
    """加载异构 4 模型 3 种子聚合数据（消融/对比部署，n=90/格）。

    边界内的 collusion 配置（n=8,f=2,s=1）只存在于这份数据里，不在 sweep 中，
    因此必须从数据读取，而不能在绘图代码里写死常数。
    """
    with open(os.path.join(RESULTS, 'multi_model_3seed_aggregated.json'), 'r') as f:
        rows = json.load(f)['rows']
    return [r for r in rows if r['method'] == 'A2A-BFT']


def _multi_get(multi_rows, ds, n, f, s, atk, key):
    """从异构数据取 A2A-BFT 单格均值；找不到返回 None。"""
    for r in multi_rows:
        if (r['dataset'] == ds and r['n'] == n and r['f'] == f
                and r['s'] == s and r['attack'] == atk):
            return r[key + '_mean']
    return None


def _sweep_partition(rows, dataset):
    """按安全边界 3f+s+1 划分 within / below 配置组"""
    within, below = [], []
    for r in rows:
        if r['dataset'] != dataset:
            continue
        (within if r['n'] >= 3 * r['f'] + r['s'] + 1 else below).append(r)
    return within, below


def _sweep_mean(rows_, key, atk, ds):
    vals = [r[key + '_mean'] for r in rows_ if r['attack'] == atk and r['dataset'] == ds]
    return float(np.mean(vals)) if vals else None


def plot_attack_resistance():
    """攻击抵抗图（真机数据）：左=边界内决策率；右=边界内 vs 越界错误提交率"""
    rows = _load_sweep()
    multi = _load_multi()
    attacks = ['random', 'strategic_reject', 'sybil_attack', 'collusion']
    labels = ['Random', 'Strategic\nReject', 'Sybil', 'Collusion']
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.6))
    x = np.arange(len(attacks))
    w = 0.2

    # 左图：边界内决策率（collusion 边界内取异构 n=8,2,1 数据）
    for k, (ds, color, name) in enumerate([('gsm8k', COLORS['honest'], 'GSM8K (semantic)'),
                                           ('mbpp', COLORS['accept'], 'MBPP (execution)')]):
        within, _ = _sweep_partition(rows, ds)
        vals = []
        for atk in attacks:
            v = _sweep_mean(within, 'decision_rate', atk, ds)
            if v is None and atk == 'collusion':
                # n=8,f=2,s=1 collusion lives in the ablation/comparison deployment
                v = _multi_get(multi, ds, 8, 2, 1, 'collusion', 'decision_rate')
            # 边界内四类攻击都必须有值；缺失即数据/口径漂移，不得静默画空柱
            assert v is not None, f'within-boundary decision rate missing for {ds}/{atk}'
            vals.append(v)
        bars = ax1.bar(x + (k - 0.5) * w, vals, w, label=name, color=color,
                       edgecolor='black', linewidth=0.5)
        for bar, v in zip(bars, vals):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.2,
                     f'{v:.0f}', ha='center', va='bottom', fontsize=8.5)
    ax1.set_xticks(x); ax1.set_xticklabels(labels, fontsize=9)
    ax1.set_ylabel('Decision Rate (%)', fontsize=11)
    ax1.set_title('(a) Decision rate within boundary $n \\geq 3f{+}s{+}1$', fontsize=11)
    ax1.set_ylim(0, 105); ax1.legend(fontsize=9); ax1.grid(axis='y', alpha=0.3)

    # 右图：错误提交率（边界内 vs 越界；实心=边界内，斜纹=越界）
    for k, (ds, name) in enumerate([('gsm8k', 'GSM8K'), ('mbpp', 'MBPP')]):
        within, below = _sweep_partition(rows, ds)
        for group, hatch, tag in [(within, None, 'within'), (below, '//', 'below')]:
            vals, positions = [], []
            for ai, atk in enumerate(attacks):
                v = _sweep_mean(group, 'wrong_commit_rate', atk, ds)
                if v is None and atk == 'collusion' and group is within:
                    v = _multi_get(multi, ds, 8, 2, 1, 'collusion', 'wrong_commit_rate')
                if v is None:
                    # 越界组没有 sybil 配置（f=1 无 sybil），这是唯一允许缺失的组合
                    assert atk == 'sybil_attack' and group is below, \
                        f'unexpected missing wrong-commit cell for {ds}/{atk}'
                    continue
                vals.append(v)
                positions.append(ai + (k - 0.5) * w)
            color = COLORS['honest'] if ds == 'gsm8k' else COLORS['accept']
            ax2.bar(positions, vals, w, color=color, edgecolor='black',
                    linewidth=0.5, hatch=hatch, label=f'{name} {tag}')
            for p, v in zip(positions, vals):
                ax2.text(p, v + 1.2, f'{v:.0f}', ha='center', va='bottom', fontsize=8.5)
    ax2.set_xticks(x); ax2.set_xticklabels(labels, fontsize=9)
    ax2.set_ylabel('Wrong-Commit Rate (%)', fontsize=11)
    ax2.set_title('(b) Wrong commits: within vs below boundary', fontsize=11)
    ax2.set_ylim(0, 80); ax2.legend(fontsize=8, ncol=2); ax2.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(FIGDIR, 'attack_resistance.pdf'), dpi=300, bbox_inches='tight')
    plt.savefig(os.path.join(FIGDIR, 'attack_resistance.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("OK Saved: attack_resistance.pdf/png (real 4-model sweep)")


def plot_performance_comparison():
    """真实端到端开销图：耗时 / LLM 调用数 / 轮数（每任务）"""
    rows = _load_sweep()
    picks = [(4, 0, 0, 'baseline', 'n=4\nbase'),
             (4, 1, 0, 'random', 'n=4,f=1\nrandom'),
             (4, 1, 0, 'strategic_reject', 'n=4,f=1\nstrategic'),
             (5, 1, 1, 'random', 'n=5,f=1,s=1\nrandom'),
             (6, 0, 0, 'baseline', 'n=6\nbase'),
             (5, 2, 0, 'collusion', 'n=5,f=2 dag\ncollusion')]

    def get(ds, key, pick):
        n, f, s, atk, _ = pick
        for r in rows:
            if (r['dataset'] == ds and r['n'] == n and r['f'] == f
                    and r['s'] == s and r['attack'] == atk):
                return r[key + '_mean']
        return np.nan

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    x = np.arange(len(picks))
    specs = [('avg_time', 'Time per task (s)', 'End-to-End Time per Task', COLORS['manual']),
             ('avg_calls', 'LLM calls per task', 'LLM Calls per Task', COLORS['honest']),
             ('avg_rounds', 'Rounds', 'Consensus Rounds', COLORS['byzantine'])]

    for ax, (key, ylab, title, color) in zip(axes, specs):
        for ds, name, off in [('gsm8k', 'GSM8K', -0.2), ('mbpp', 'MBPP', +0.2)]:
            vals = [get(ds, key, p) for p in picks]
            # 每个 pick 都必须命中真机扫描数据；NaN 会静默画成空柱，必须显式失败
            assert not any(np.isnan(v) for v in vals), \
                f'{key} missing for {ds}: ' + str([p[4] for p, v in zip(picks, vals) if np.isnan(v)])
            bars = ax.bar(x + off, vals, 0.38, label=name,
                          color=(COLORS['honest'] if ds == 'gsm8k' else COLORS['accept']),
                          edgecolor='black', linewidth=0.5)
            for bar, v in zip(bars, vals):
                if not np.isnan(v):
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.01,
                            f'{v:.0f}' if key == 'avg_time' else f'{v:.1f}',
                            ha='center', va='bottom', fontsize=7.5)
        ax.set_xticks(x)
        ax.set_xticklabels([p[4] for p in picks], fontsize=7.5)
        ax.set_ylabel(ylab, fontsize=10)
        ax.set_title(title, fontsize=11)
        ax.legend(fontsize=9)
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(FIGDIR, 'performance_comparison.pdf'), dpi=300, bbox_inches='tight')
    plt.savefig(os.path.join(FIGDIR, 'performance_comparison.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("OK Saved: performance_comparison.pdf/png (real 4-model sweep)")
def plot_system_architecture():
    """绘制系统架构图"""
    fig, ax = plt.subplots(figsize=(14, 10))

    # 定义层级
    layers = {
        'Application Layer': ['A2A Protocol', 'Task Distribution', 'Result Aggregation'],
        'Consensus Layer': ['Propose Phase', 'Validate Phase', 'Commit Phase'],
        'Agent Layer': ['Worker 1', 'Worker 2', 'Worker 3', 'Worker 4'],
        'Model Layer': ['Llama-3.1-8B', 'DeepSeek-V2', 'InternLM3', 'LLaDA-8B']
    }

    colors = {
        'Application Layer': '#3498DB',
        'Consensus Layer': '#2ECC71',
        'Agent Layer': '#9B59B6',
        'Model Layer': '#E74C3C'
    }

    y_positions = {'Application Layer': 0.9, 'Consensus Layer': 0.65,
                   'Agent Layer': 0.4, 'Model Layer': 0.15}

    # 绘制层级
    for layer_name, components in layers.items():
        y = y_positions[layer_name]
        n_components = len(components)
        x_start = 0.5 - (n_components - 1) * 0.15

        # 绘制层级背景
        ax.add_patch(plt.Rectangle((0.1, y - 0.1), 0.8, 0.18,
                                    facecolor=colors[layer_name], alpha=0.2,
                                    edgecolor=colors[layer_name], linewidth=2))
        ax.text(0.5, y + 0.05, layer_name, ha='center', va='center',
                fontsize=12, fontweight='bold', color=colors[layer_name])

        # 绘制组件
        for i, comp in enumerate(components):
            x = x_start + i * 0.3
            ax.add_patch(plt.Rectangle((x - 0.1, y - 0.06), 0.2, 0.12,
                                        facecolor='white', edgecolor=colors[layer_name],
                                        linewidth=1.5))
            ax.text(x, y, comp, ha='center', va='center', fontsize=9)

    # 绘制连接箭头
    for i in range(3):
        ax.annotate('', xy=(0.5, y_positions['Consensus Layer'] + 0.1),
                    xytext=(0.5, y_positions['Application Layer'] - 0.1),
                    arrowprops=dict(arrowstyle='->', color='gray', lw=1.5))
        ax.annotate('', xy=(0.5, y_positions['Agent Layer'] + 0.1),
                    xytext=(0.5, y_positions['Consensus Layer'] - 0.1),
                    arrowprops=dict(arrowstyle='->', color='gray', lw=1.5))
        ax.annotate('', xy=(0.5, y_positions['Model Layer'] + 0.08),
                    xytext=(0.5, y_positions['Agent Layer'] - 0.08),
                    arrowprops=dict(arrowstyle='->', color='gray', lw=1.5))

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    ax.set_title('A2A-BFT System Architecture', fontsize=16, fontweight='bold', pad=20)

    plt.tight_layout()
    plt.savefig(os.path.join(FIGDIR, 'architecture.pdf'), dpi=300, bbox_inches='tight')
    plt.savefig(os.path.join(FIGDIR, 'architecture.png'), dpi=300, bbox_inches='tight')
    print("✓ Saved: architecture.pdf/png")


def plot_consensus_flow():
    """绘制共识流程图（紧凑出版排版：三阶段面板 + 决策标签 + View Change 反馈回路）"""
    import matplotlib.transforms as mtransforms
    fig, ax = plt.subplots(figsize=(10.5, 3.0))
    plt.rcParams['font.family'] = 'serif'

    panel_h = 0.52
    panel_y = 0.40                     # panel bottom
    cy = panel_y + panel_h / 2         # vertical center of panels

    panels = [
        (0.03, 0.26, '#D6EAF8', '#2471A3',
         'PHASE 1: PROPOSE',
         ['Primary $P$ (round-robin)',
          '$\\pi = (task\\_id,\\ result,$',
          '$confidence,\\ trace)$']),
        (0.35, 0.26, '#D5F5E3', '#1E8449',
         'PHASE 2: VALIDATE',
         ['Re-solve and verify $\\pi$;',
          'deterministic tasks: error-free',
          'check; semantic tasks: $m$-verifier']),
        (0.67, 0.26, '#FDEBD0', '#B9770E',
         'PHASE 3: COMMIT',
         ['$\\phi(\\pi) = |\\mathrm{ACCEPT}| - 0.5|\\mathrm{REJECT}|$',
          'ACCEPT iff $\\phi \\geq \\theta_{accept}$,',
          '$\\theta_{accept} = n-1-2f-s$']),
    ]

    for x, w, fc, ec, title, lines in panels:
        rect = plt.Rectangle((x, panel_y), w, panel_h,
                             facecolor=fc, edgecolor=ec, linewidth=1.4,
                             joinstyle='round')
        ax.add_patch(rect)
        ax.text(x + w/2, panel_y + panel_h - 0.085, title,
                ha='center', va='center', fontsize=9.5, fontweight='bold', color=ec)
        for j, ln in enumerate(lines):
            ax.text(x + w/2, panel_y + panel_h - 0.17 - j*0.093, ln,
                    ha='center', va='center', fontsize=8.2, color='#1B2631')

    # 阶段间主箭头
    for x0, x1 in [(0.29, 0.35), (0.61, 0.67)]:
        ax.annotate('', xy=(x1, cy), xytext=(x0, cy),
                    arrowprops=dict(arrowstyle='-|>', color='#2C3E50',
                                    lw=1.8, mutation_scale=16))

    # 决策标签（右侧竖排三枚）
    decisions = [('ACCEPT', '#1E8449', '#D5F5E3'),
                 ('PENDING', '#B9770E', '#FDEBD0'),
                 ('REJECT', '#922B21', '#FADBD8')]
    for k, (lab, ec, fc) in enumerate(decisions):
        ax.text(0.965, 0.79 - k*0.20, lab, ha='center', va='center',
                fontsize=8.5, fontweight='bold', color=ec,
                bbox=dict(boxstyle='round,pad=0.32', facecolor=fc,
                          edgecolor=ec, linewidth=1.1))
    ax.annotate('', xy=(0.935, cy), xytext=(0.93, cy),
                arrowprops=dict(arrowstyle='-|>', color='#2C3E50',
                                lw=1.8, mutation_scale=16))

    # View Change 反馈回路（底部弧线，从 Commit 下方绕回 Propose 下方）
    ax.annotate('', xy=(0.16, panel_y - 0.02), xytext=(0.80, panel_y - 0.02),
                arrowprops=dict(arrowstyle='-|>', color='#7D3C98', lw=1.5,
                                connectionstyle='arc3,rad=-0.23',
                                mutation_scale=14))
    ax.text(0.48, 0.02,
            'PENDING (2 rounds) or $2\\Delta$ timeout  $\\rightarrow$  '
            'View Change ($2f{+}1$ confirmations, new round-robin primary)',
            ha='center', va='center', fontsize=8.2, color='#7D3C98', style='italic')

    # 故障模型徽标（左上）
    ax.text(0.03, 0.965,
            'Fault model: $n \\geq 3f + s + 1$'
            '   (Byzantine $f$, soft-fault $s$; reputation affects selection only)',
            ha='left', va='center', fontsize=8.5, color='#566573',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#F4F6F7',
                      edgecolor='#AEB6BF', linewidth=0.8))

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    plt.savefig(os.path.join(FIGDIR, 'consensus_flow.pdf'), dpi=300, bbox_inches='tight', pad_inches=0.04)
    plt.savefig(os.path.join(FIGDIR, 'consensus_flow.png'), dpi=300, bbox_inches='tight', pad_inches=0.04)
    print("✓ Saved: consensus_flow.pdf/png")


def _load_measured_reputation():
    """读取声誉消融的实测轨迹；没有则返回 None（回退到解析轨迹示意图）。"""
    path = os.path.join(RESULTS, 'reputation_ablation.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:
        print(f"  ! 读取 {path} 失败: {e}")
        return None
    if not d.get('trajectories'):
        return None
    return d


def _mean_traj(seqs, upto=None):
    """把不等长的多条 r_i 时间线对齐成均值 + 四分位带。"""
    seqs = [s for s in seqs if s]
    if not seqs:
        return None, None, None
    L = min(len(s) for s in seqs) if upto is None else min(upto, min(len(s) for s in seqs))
    if L == 0:
        return None, None, None
    m = np.array([s[:L] for s in seqs], dtype=float)
    return np.arange(1, L + 1), m.mean(axis=0), m


def plot_reputation_measured(ax, arm_rows, traj):
    """右图：实测 r_i 轨迹（Byzantine vs honest），按细胞分面。"""
    cells = [k for k in traj if traj[k].get('f', 0) > 0]
    if not cells:
        return False
    # 选拜占庭占比最高的两个细胞（最能暴露失效模式）
    cells.sort(key=lambda k: -traj[k]['f'])
    cells = cells[:2]

    by_cell = {r['cell']: r for r in arm_rows}
    styles = [('-', '--')]
    for ci, key in enumerate(cells):
        t = traj[key]
        x_b, m_b, _ = _mean_traj(list(t['byz'].values()))
        x_h, m_h, _ = _mean_traj(list(t['honest'].values()))
        ls = styles[ci % len(styles)][1] if ci else styles[0][0]
        lab = key.replace('gsm8k', 'GSM8K').replace('mbpp', 'MBPP')
        if x_h is not None:
            ax.plot(x_h, m_h, color=COLORS['accept'], linestyle=ls, linewidth=1.8,
                    alpha=0.95, label=f"honest — {lab}")
        if x_b is not None:
            ax.plot(x_b, m_b, color=COLORS['reject'], linestyle=ls, linewidth=1.8,
                    alpha=0.95, label=f"Byzantine — {lab}")
        row = by_cell.get(key)
        if row and row.get('mispenalty_rate') is not None:
            npts = len(x_h) if x_h is not None else (len(x_b) if x_b is not None else 0)
            ax.axhline(0.7, color='gray', linestyle=':', linewidth=1.2)
            ax.text(max(1, npts) * 0.02, 0.72,
                    r'$\rho_i \geq 0.7$ triggers the $-0.25$ tier', fontsize=8, color='gray')

    ax.set_xlabel('Reputation updates (chronological, across tasks)', fontsize=11)
    ax.set_ylabel('Reputation score $r_i$', fontsize=12)
    ax.set_title('Measured trajectories (real 4-model deployment)', fontsize=13, fontweight='bold')
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.16), ncol=2,
              fontsize=8, frameon=False)
    ax.set_ylim(0, 1.12)
    ax.margins(x=0.02)
    ax.grid(alpha=0.3)
    return True


def plot_reputation_mechanism():
    """声誉机制图：左 = Algorithm 1 规则；右 = 实测轨迹（缺数据时回退解析轨迹）。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # 左侧：声誉更新规则（与 Algorithm 1 严格一致）
    ax1.text(0.5, 0.9, 'Reputation Update Rule (Algorithm 1)', ha='center',
             fontsize=13, fontweight='bold')

    rules = [
        ('Correct vote, ratio < 0.5 (reward)', '+0.1', COLORS['accept']),
        ('Honest mistake, ratio < 0.7 (floor 0.5)', '-0.05', COLORS['manual']),
        ('Persistent rejection, ratio >= 0.7 (floor 0.1)', '-0.25', COLORS['reject']),
        ('Correct vote, ratio 0.5-0.7 (neutral drift)', '-0.02', COLORS['honest'])
    ]

    y_pos = 0.7
    for label, value, color in rules:
        ax1.add_patch(plt.Rectangle((0.08, y_pos - 0.08), 0.84, 0.12,
                                     facecolor=color, alpha=0.2, edgecolor=color, linewidth=2))
        ax1.text(0.14, y_pos - 0.02, label, fontsize=10)
        ax1.text(0.88, y_pos - 0.02, value, fontsize=11, fontweight='bold', ha='right')
        y_pos -= 0.2

    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, 1)
    ax1.axis('off')

    # 右侧：优先用实测轨迹；无数据则退回解析轨迹（并明确标注为示意）
    measured = _load_measured_reputation()
    drew = False
    if measured:
        arms = measured.get('arms', [])
        arm = next((a for a in arms
                    if a.get('c_source') == 'oracle' and a.get('persistence') == 'persistent'),
                   arms[0] if arms else None)
        if arm:
            drew = plot_reputation_measured(ax2, arm['rows'], measured['trajectories'])
    if not drew:
        rounds = np.arange(0, 20)
        ax2.plot(rounds, np.minimum(1.0, 1.0 + 0.1 * rounds), 'g-', linewidth=2,
                 label='Correct vote (+0.1/round)')
        ax2.plot(rounds, np.maximum(0.5, 1.0 - 0.05 * rounds), color='orange', linewidth=2,
                 label='Honest mistake (-0.05/round)')
        ax2.plot(rounds, np.maximum(0.1, 1.0 - 0.25 * rounds), 'r-', linewidth=2,
                 label='Persistent rejection (-0.25/round)')
        ax2.plot(rounds, np.maximum(0.5, 1.0 - 0.02 * rounds), color='purple', linewidth=1.5,
                 linestyle=':', label='Neutral drift (-0.02/round)')
        ax2.set_xlabel('Consensus rounds', fontsize=12)
        ax2.set_ylabel('Reputation score $r_i$', fontsize=12)
        ax2.set_title('Analytic trajectories implied by the update rule', fontsize=13, fontweight='bold')
        ax2.legend(loc='upper right', fontsize=9)
        ax2.set_xlim(0, 20)
        ax2.set_ylim(0, 1.2)
        ax2.grid(alpha=0.3)
        print("  ! 未找到实测轨迹，右图回退为解析轨迹（示意图）")

    plt.tight_layout()
    plt.savefig(os.path.join(FIGDIR, 'reputation_mechanism.pdf'), dpi=300, bbox_inches='tight')
    plt.savefig(os.path.join(FIGDIR, 'reputation_mechanism.png'), dpi=300, bbox_inches='tight')
    print("✓ Saved: reputation_mechanism.pdf/png "
          + ("(right panel: MEASURED)" if drew else "(schematic, rule-consistent)"))


def main():
    """主函数（全部数据图使用真机扫描数据 full_bft_sweep_aggregated.json）"""
    print("="*60)
    print("A2A-BFT 论文图表生成（真机数据版）")
    print("="*60)

    figures_dir = FIGDIR
    os.makedirs(figures_dir, exist_ok=True)

    print("\n[1/4] Attack resistance (real sweep)...")
    plot_attack_resistance()

    print("\n[2/4] Performance comparison (real sweep)...")
    plot_performance_comparison()

    print("\n[3/4] System diagrams...")
    plot_system_architecture()
    plot_consensus_flow()

    print("\n[4/4] Reputation mechanism diagram...")
    plot_reputation_mechanism()

    # 记录本批图的来源指纹（脚本逻辑 + 数据内容），供 audit_figures.py 判定陈旧
    write_figsource_stamp()

    print("\n" + "="*60)
    print("All figures generated successfully!")
    print(f"Output directory: {figures_dir}")
    print("="*60)


if __name__ == "__main__":
    main()
