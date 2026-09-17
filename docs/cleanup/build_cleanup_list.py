"""Build the exact delete list for the 2026-09-15 cleanup, with hard guards
that refuse to touch any file the paper or the audit chain depends on.

历史记录：本脚本于 2026-09-15 完成清理后被移入 ``docs/cleanup/``。
注意迁移破坏——原先写作 ``ROOT = os.path.dirname(os.path.abspath(__file__))``，
在仓库根目录下运行时等于项目根；移入 ``docs/cleanup/`` 后 ROOT 变成
``docs/cleanup``，于是所有路径都解析到已删除的位置，``add()`` 一个都命中不了，
清单恒为空且不报错（静默失效）。现改为向上查找 ``.a2a_project_root``。

重跑时清单输出到 ``cleanup_manifest_20260915.regenerated.txt``，以免覆盖
已归档的 ``cleanup_manifest_20260915.txt``。
"""
import os, glob, json, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = _HERE
while not os.path.exists(os.path.join(ROOT, '.a2a_project_root')) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)
R = os.path.join(ROOT, 'experiments', 'results')

# ---------------------------------------------------------------- HARD KEEP
# Files the paper's every number traces back to, plus the audit tool-chain.
KEEP_ABS = set()
def keep(p): KEEP_ABS.add(os.path.normcase(os.path.abspath(p)))

# audit-chain dependencies (audit_table_numbers / audit_prose_ranges /
# audit_theory_numerics / run_pairing_mcnemar)
for f in ['full_bft_sweep_aggregated.json', 'multi_model_3seed_aggregated.json',
          'correctness_50t_3s_run1_from_log.json', 'run_pairing_mcnemar.json',
          'correctness_50x3_log.txt', 'correctness_count_log.txt',
          # correctness_50t_3s.json 曾在此保护之列；它于 2026-09-17 被删除
          # （论文 tab:n8_scaling 用的是由逐任务日志重建的 _run1_from_log 版本，
          #   该文件零读取方）。keep() 只是一个集合，留名无害，但会误导读者
          #   以为它还在，故移除并记录在此。
          'full_bft_sweep_gsm8k.json', 'full_bft_sweep_mbpp.json', 'full_bft_sweep_mmlu.json',
          'multi_model_multiseed.json',
          'sweep_gsm8k.log', 'sweep_mbpp.log', 'sweep_mmlu.log', 'sweep_mmlu_n5.log']:
    keep(os.path.join(R, f))

# tab:real_llm provenance (report + the three raw files it names)
keep(os.path.join(R, 'large_scale_experiment_report.md'))
for f in ['deepseek_math_fixed_20.json', 'deepseek_code_fixed_20.json',
          'deepseek_knowledge_fixed_20.json']:
    keep(os.path.join(R, f))

# results files that sit IN a reproduction chain and must survive
for f in ['multi_model_compare_ablation_v2.json', 'multi_model_compare_ablation_v3.json',
          'mbpp_debate_fix.json']:
    keep(os.path.join(R, f))

# current paper tree (minus the superseded version folder), style files,
# review trail, sources, datasets
for pat in ['papers/**/*', 'src/**/*', 'experiments/datasets/**/*', '.workbuddy/**/*']:
    for p in glob.glob(os.path.join(ROOT, pat), recursive=True):
        if '_old_versions_20260912' in p:
            continue
        keep(p)

# experiment scripts: keep everything under multi_model_autodl EXCEPT the
# three throwaway diagnostics listed below
for p in glob.glob(os.path.join(ROOT, 'experiments', 'multi_model_autodl', '*')):
    if os.path.basename(p) in ('diag.py', 'compat_check.py', 'judge_test.py'):
        continue
    keep(p)
for p in glob.glob(os.path.join(ROOT, 'experiments', '*.py')):
    if os.path.basename(p).startswith('autodl_'):
        continue          # one-off remote helpers -> delete
    keep(p)

# ---------------------------------------------------------------- DELETE LIST
D = []          # (path, category)

def add(p, cat):
    if os.path.exists(p):
        D.append((os.path.abspath(p), cat))

# --- A: simulated data (avg_time ~0.1 ms -> no LLM was ever called) ---
add(os.path.join(ROOT, 'experiments', 'archive_simulation'), 'A 模拟数据')
for f in ['main_results.json', 'ablation_results.json', 'attack_results.json',
          'comparison_results.json', 'ablation_enhanced_results.json',
          'real_dataset_results.json']:
    add(os.path.join(R, f), 'A 模拟数据')

# --- B: superseded paper versions ---
add(os.path.join(ROOT, 'papers', '_old_versions_20260912'), 'B 旧论文版本')

# --- C: old submission bundles ---
for f in ['A2A-BFT-CameraReady.tar.gz', 'a2a_bft_code.tar.gz', 'submission.tar.gz',
          'submission_final.tar.gz', 'submission_fixed.tar.gz']:
    add(os.path.join(ROOT, f), 'C 旧提交包')
add(os.path.join(ROOT, 'submission'), 'C 旧提交包')
add(os.path.join(ROOT, 'submission_final'), 'C 旧提交包')

# --- D: superseded REAL result files (provenance files excluded via guard) ---
D_DEEPSEEK = ['deepseek_results.json', 'deepseek_code_results.json',
              'deepseek_math_results.json', 'deepseek_knowledge_results.json',
              'deepseek_full_results.json',
              'deepseek_math_50.json', 'deepseek_code_50.json', 'deepseek_knowledge_50.json',
              'deepseek_math_100.json', 'deepseek_code_100.json', 'deepseek_knowledge_100.json']
D_OTHER = ['comparison_code_result.json', 'comparison_math_result.json',
           'comparison_deepseek_math_20.json', 'comparison_deepseek_code_20.json',
           'comparison_deepseek_knowledge_20.json',
           'comparison_ablation_math_10.json', 'comparison_ablation_code_10.json',
           'comparison_ablation_knowledge_10.json', 'comparison_ablation_summary.json',
           'ablation_deepseek_math_20.json', 'ablation_deepseek_code_20.json',
           'ablation_deepseek_knowledge_20.json',
           'ablation_local_final_10t_2s.json', 'knowledge_fixed.json',
           'large_scale_results.json', 'large_scale_fixed_30x2.json',
           'n8_deepseek_1t_1s.json', 'n8_deepseek_30t_3s.json',
           'multi_model_compare_ablation.json',
           'multi_model_compare_ablation_final.json',
           'multi_model_vllm_results.json',
           'correctness_20t_2s.json', 'correctness_mmlu_30t_2s.json']
D_LOGS = ['correctness_run_log.txt', 'correctness_large_log.txt', 'correctness_fixed_log.txt',
          'correctness_fixed2_log.txt', 'correctness_parallel_log.txt',
          'correctness_mmlu_log.txt', 'n8_run_log.txt',
          'multi_model_compare_ablation_report.md', 'multi_model_compare_ablation_final_report.md',
          'compare_v3.log', 'ablation_math.log', 'ablation_full.log', 'full_experiment.log',
          'comparison_math_small.log', 'experiment_report.txt', 'final_experiment_report.txt']
for f in D_DEEPSEEK + D_OTHER + D_LOGS:
    add(os.path.join(R, f), 'D 旧真实结果(被取代)')

# GPU ops/runtime logs only -- the 7 sibling *.log files document load-bearing
# runs (multiseed -> merge_3seed, debate_fix -> mbpp_debate_fix.json) and are KEPT.
add(os.path.join(R, 'logs', 'autodl_runtime'), 'D 旧真实结果(被取代)')

# --- E: one-off scripts and stale logs ---
for f in ['autodl_orchestrator.py', 'check_remote_sync.py', 'clean_and_start.py',
          'fix_and_run.py', 'launch_remote.py', 'launch_vllm_install.py', 'remote_check.py',
          'run_stage6_9.py', 'runcmd.py', 'start_download.py', 'upload_only.py',
          'upload_to_autodl.py', 'vllm_orchestrator.py', 'vllm_orchestrator2.py',
          'vllm_orchestrator3.py',
          'full_experiment_output.txt', 'iclr2026_main.log', 'iclr2026_main_new.log',
          'iclr2027_main.log', 'orchestrator3.log', 'run_stage6_9.log', 'texput.log']:
    add(os.path.join(ROOT, f), 'E 一次性脚本/日志')
for p in glob.glob(os.path.join(ROOT, 'experiments', 'autodl_*.py')):
    add(p, 'E 一次性脚本/日志')
for f in ['diag.py', 'compat_check.py', 'judge_test.py']:
    add(os.path.join(ROOT, 'experiments', 'multi_model_autodl', f), 'E 一次性脚本/日志')
for p in glob.glob(os.path.join(ROOT, '__pycache__')) + glob.glob(os.path.join(ROOT, 'experiments', '__pycache__')):
    add(p, 'E 一次性脚本/日志')

# --- F: superseded experiment process reports ---
# 注：原规则 ``experiments/*.md`` 在 2026-09-15 当时是对的（那份目录下只有实验过程报告）。
# 整理期间新增了 ``experiments/README.md``（实验模块职责与脚本清单，属交付文档），
# 该 glob 会把它误判为"旧实验报告"。这里显式排除文档文件。
for p in glob.glob(os.path.join(ROOT, 'experiments', '*.md')):
    if os.path.basename(p) in ('README.md',):
        continue
    add(p, 'F 旧实验报告')

# ---------------------------------------------------------------- GUARD
violations = [(p, c) for (p, c) in D if os.path.normcase(os.path.abspath(p)) in KEEP_ABS]
if violations:
    print('!!! ABORT: delete list touches protected paths:')
    for p, c in violations:
        print('   ', c, p)
    sys.exit(1)

seen, uniq = set(), []
for p, c in D:
    if p not in seen:
        seen.add(p); uniq.append((p, c))

print(f'delete entries: {len(uniq)}  (guard passed: 0 protected paths touched)')
bysize = {}
for p, c in uniq:
    if os.path.isdir(p):
        sz = sum(os.path.getsize(os.path.join(dp, f))
                 for dp, _, fs in os.walk(p) for f in fs)
    else:
        sz = os.path.getsize(p)
    bysize.setdefault(c, [0, 0])
    bysize[c][0] += 1; bysize[c][1] += sz
for c in sorted(bysize):
    n, s = bysize[c]
    print(f'  {c:22s} {n:4d} entries  {s/1048576:7.2f} MB')
print(f'  TOTAL {sum(v[0] for v in bysize.values()):4d} entries  '
      f'{sum(v[1] for v in bysize.values())/1048576:7.2f} MB')

MANIFEST = os.path.join(_HERE, 'cleanup_manifest_20260915.regenerated.txt')
with open(MANIFEST, 'w', encoding='utf-8') as fh:
    for p, c in sorted(uniq, key=lambda x: (x[1], x[0])):
        fh.write(f'{c}\t{p}\n')
print(f'\nmanifest -> {os.path.basename(MANIFEST)}')
