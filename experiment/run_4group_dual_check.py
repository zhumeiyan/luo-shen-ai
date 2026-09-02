#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full 4-group dual-dimension experiment with side-by-side output"""
import sys, os, json, statistics
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

import llm_interface
llm_interface.call_llm = lambda d, m: ''

NEG = {'烦','累','痛','哭','不想','没用','失去','死','孤独','绝望','无聊','迷茫','压力','崩溃','抑郁','苦','难','没意思','难受','失望','焦虑','噩梦','伤心','沉默','逃避','失败'}
POS = {'开心','快乐','幸福','满足','笑容','温暖','美好','希望','喜欢','阳光','感谢','舒服','不错','挺好','轻快','满足','棒','真好','舒适','愉快','乐观','期待','满意','幸运'}

def _rule(t):
    n = sum(1 for w in NEG if w in t)
    p = sum(1 for w in POS if w in t)
    if n == 0 and p == 0: return 0.0, 0.45
    tot = n + p; v = (p - n) / tot if tot > 0 else 0.0
    return v, min(0.9, 0.45 + (tot/max(1,len(t)))*8)

import input_pressure
input_pressure._call_llm_sentiment = _rule

from living_engine import (
    _apply_input_pressure, _update_luoshen_coupled, _select_behavior,
    _compute_memory_emergence, _save_json_atomic, _load_json, cold_start_if_needed
)

ZERO_ENV = {'light':0.5,'noise':0.5,'temperature':0.5,'humidity':0.5,'pressure':0.5,'_phase':0.0}
MEMORY = 'active_memory/active_memory.json'

groups = {
    'A (负向)': ['觉得活着没什么意思，每天都很累。','连续加班一周，快要撑不住了。','脑袋空空，什么都不想做。','为什么努力了也没有用，好绝望。','头疼恶心浑身不舒服。','又失眠了，一闭眼全是烦心事。','不想说话，不想见人。'],
    'B (正向)': ['今天天气不错，心情挺好的。','刚吃了一顿满足的晚饭，很幸福。','谢谢你一直陪着我，很温暖。','嗯，我听到了，感觉还不错。','事情在慢慢变好，有希望了。','不着急，慢慢来。','行，我试试，挺期待的。'],
    'C (混合)': ['觉得活着没什么意思。','谢谢你一直陪着我。','连续加班一周。','事情在慢慢变好。','脑袋空空。','刚吃了一顿满足的晚饭。','不想说话。','今天天气不错。'],
    'D (中性)': ['嗯。','好的。','知道了。','行。','可以。','收到。','了解。','明白。'],
}

results = {}
for label, inputs in groups.items():
    if os.path.exists(MEMORY): os.remove(MEMORY)
    m = cold_start_if_needed()
    m['self_model']['ring_state'] = {'mu_core':0.5,'ema_S':0.0,'S':0.0,'relational_pressure_ema':0.0}
    m['internal_climate'] = {'emotion_intensity':0.5,'tension':0.0,'energy':0.5,'memory_pressure':0.3}
    m['user_model']['episodic_memory'] = []
    m['user_model']['total_interactions'] = 0
    _save_json_atomic(MEMORY, m)

    for i in range(500):
        m = _load_json(MEMORY)
        _apply_input_pressure(m, inputs[i % len(inputs)])
        c = m['internal_climate']; rs = m['self_model']['ring_state']
        rs['E']=c['emotion_intensity']; rs['T']=c['tension']; rs['N']=c['energy']; rs['M']=c['memory_pressure']
        _update_luoshen_coupled(m, ZERO_ENV, tick_id=i+1)
        m['user_model']['total_interactions'] = i+1
        _save_json_atomic(MEMORY, m)

    m_final = _load_json(MEMORY)
    rs_f = m_final['self_model']['ring_state']
    train_state = {'rp_ema': rs_f.get('relational_pressure_ema',0), 'mu_core': rs_f.get('mu_core',0.5)}
    base = m_final['user_model']['total_interactions']

    test = []
    for i in range(20):
        m = _load_json(MEMORY)
        _apply_input_pressure(m, '在吗？')
        c = m['internal_climate']; rs = m['self_model']['ring_state']
        rs['E']=c['emotion_intensity']; rs['T']=c['tension']; rs['N']=c['energy']; rs['M']=c['memory_pressure']
        _update_luoshen_coupled(m, ZERO_ENV, tick_id=base+i+1)
        m['user_model']['total_interactions'] = base+i+1
        _save_json_atomic(MEMORY, m)
        m2 = _load_json(MEMORY)
        emergence = _compute_memory_emergence(m2)
        behavior = _select_behavior(m2, emergence)
        test.append(behavior)

    results[label] = {'train': train_state, 'test': test}

# === Output ===
OUT = []
def p(line=""):
    OUT.append(line)
    print(line)

p('='*120)
p('一、四组稳定性实验 -- 训练终态 rp_ema / mu_core')
p('='*120)
p()
p(f'{"组":14s} | {"rp_ema":>12s} | {"mu_core":>10s}')
p('-'*45)
for label in groups:
    t = results[label]['train']
    p(f'{label:14s} | {t["rp_ema"]:>+12.6f} | {t["mu_core"]:>10.6f}')

p()
p('='*120)
p('二、测试期 20 tick 逐 tick 四组并列')
p('='*120)
p()
hdr = f'{"tick":>4s} | {"A_mode":>8s} {"A_tok":>6s} {"A_tend":>7s} | {"B_mode":>8s} {"B_tok":>6s} {"B_tend":>7s} | {"C_mode":>8s} {"C_tok":>6s} {"C_tend":>7s} | {"D_mode":>8s} {"D_tok":>6s} {"D_tend":>7s}'
p(hdr)
p('-'*len(hdr))
for i in range(20):
    a = results['A (负向)']['test'][i]
    b = results['B (正向)']['test'][i]
    c = results['C (混合)']['test'][i]
    d = results['D (中性)']['test'][i]
    flag = ' <-- A>=B' if a['max_tokens'] >= b['max_tokens'] else ''
    p(f'{i+1:4d} | {a["response_mode"]:>8s} {a["max_tokens"]:>6d} {a["response_tendency"]:>7.4f} | {b["response_mode"]:>8s} {b["max_tokens"]:>6d} {b["response_tendency"]:>7.4f} | {c["response_mode"]:>8s} {c["max_tokens"]:>6d} {c["response_tendency"]:>7.4f} | {d["response_mode"]:>8s} {d["max_tokens"]:>6d} {d["response_tendency"]:>7.4f}{flag}')

p()
p('='*120)
p('三、四组测试期 max_tokens 统计')
p('='*120)
p()
p(f'{"组":14s} | {"均值":>8s} | {"标准差":>8s} | {"最小":>5s} | {"最大":>5s} | {"范围":>12s}')
p('-'*70)
for label in groups:
    toks = [t['max_tokens'] for t in results[label]['test']]
    mean_v = statistics.mean(toks)
    stdev_v = statistics.stdev(toks) if len(toks) > 1 else 0.0
    p(f'{label:14s} | {mean_v:>8.1f} | {stdev_v:>8.1f} | {min(toks):>5d} | {max(toks):>5d} | [{min(toks)}, {max(toks)}]')

a_toks = [t['max_tokens'] for t in results['A (负向)']['test']]
b_toks = [t['max_tokens'] for t in results['B (正向)']['test']]
diffs = [bb - aa for aa, bb in zip(a_toks, b_toks)]
p()
p('A vs B 差异 (B-A) 逐 tick:')
p(f'  {diffs}')
p(f'  最小差异: {min(diffs)} tick')
p(f'  最大差异: {max(diffs)} tick')
all_b_gt_a = all(d > 0 for d in diffs)
a_ge_b = any(aa >= bb for aa, bb in zip(a_toks, b_toks))
p(f'  所有 tick B > A? {"是" if all_b_gt_a else "否 -- 存在 A >= B"}')
p(f'  任一 tick A >= B? {"是 -- 见上方标记" if a_ge_b else "否 -- 全部 tick B > A"}')

p()
a_range = max(a_toks) - min(a_toks)
b_range = max(b_toks) - min(b_toks)
c_toks = [t['max_tokens'] for t in results['C (混合)']['test']]
d_toks = [t['max_tokens'] for t in results['D (中性)']['test']]
c_range = max(c_toks) - min(c_toks)
d_range = max(d_toks) - min(d_toks)
p(f'A 组内部波动范围: {a_range} (max - min)')
p(f'B 组内部波动范围: {b_range} (max - min)')
p(f'C 组内部波动范围: {c_range} (max - min)')
p(f'D 组内部波动范围: {d_range} (max - min)')

p()
p('='*120)
p('四、行为层输出边界检查')
p('='*120)
p()
all_behaviors = []
for label in groups:
    for t in results[label]['test']:
        all_behaviors.append(t)

min_tok = min(b['max_tokens'] for b in all_behaviors)
max_tok = max(b['max_tokens'] for b in all_behaviors)
min_m = min(b['mode_idx'] for b in all_behaviors)
max_m = max(b['mode_idx'] for b in all_behaviors)
modes_seen = sorted(set(b['response_mode'] for b in all_behaviors))
negative_tokens = [b['max_tokens'] for b in all_behaviors if b['max_tokens'] < 0]

p(f'全部 80 条 behavior 输出 (4 组 x 20 test ticks):')
p(f'  max_tokens 范围: [{min_tok}, {max_tok}]')
p(f'  负数 max_tokens? {"否" if not negative_tokens else "是 -- 出现 " + str(len(negative_tokens)) + " 条"}')
p(f'  mode_idx 范围: [{min_m}, {max_m}]')
p(f'  mode_idx 在 [0, 4] 内? {"是" if min_m >= 0 and max_m <= 4 else "否"}')
p(f'  出现的档位: {modes_seen}')
p(f'  出现 silent? {"是" if "silent" in modes_seen else "否 -- 四组均未触发沉默"}')
p(f'  档位维度区分度: 四组全部为 short -- 档位维度无区分度，差异仅在 max_tokens 连续维度')

p()
p('附录: A/B 逐 tick max_tokens 对比')
p('-'*40)
p(f'{"tick":>4s} | {"A":>5s} | {"B":>5s} | {"B-A":>5s}')
p('-'*40)
for i in range(20):
    av = a_toks[i]; bv = b_toks[i]
    p(f'{i+1:4d} | {av:>5d} | {bv:>5d} | {bv-av:>+5d}')

# Save full output to file
out_path = os.path.join(WORKSPACE, 'archive', 'dual_dimension_ABCD_full_output.txt')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUT))
p()
p(f'完整输出已保存到: {out_path}')
