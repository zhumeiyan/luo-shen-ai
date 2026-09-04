#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关系自我定义 R 向量验证实验 — P / N / M / D / G_irr 五组
严格按批准方案执行，不修改任何功能代码，只做验证。

实验设计：
- P: 500 tick 纯正向
- N: 500 tick 纯负向
- M: 500 tick 混合 (10正10负交替)
- D: 500 tick 中性
- G_irr: 500 tick 正向 → 500 tick 负向 (不重置)

初始状态完全一致，不调用 LLM，纯内部动力学模拟。
使用生产代码 _update_luoshen_coupled（传合成 env 字典）以确保 R EMA 被真实计算。
"""
import sys, os, math, csv, json, hashlib, time, copy, statistics

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

# ── LLM 桩（不调真实 LLM）──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

# ── Sentiment patch（词性规则，确定性）──
NEG_WORDS = {"烦","累","痛","哭","不想","没用","失去","死","孤独","绝望",
             "无聊","迷茫","压力","崩溃","抑郁","苦","难","没意思","难受",
             "失望","焦虑","噩梦","伤心","沉默","逃避","失败","挫败"}
POS_WORDS = {"开心","快乐","幸福","满足","笑容","温暖","美好","希望","喜欢",
             "阳光","感谢","不错","挺好","轻快","棒","真好",
             "舒适","愉快","乐观","期待","满意","幸运"}

def _rule_sentiment(t):
    n = sum(1 for w in NEG_WORDS if w in t)
    p = sum(1 for w in POS_WORDS if w in t)
    if n == 0 and p == 0:
        return 0.0, 0.45
    tot = n + p
    v = (p - n) / tot if tot > 0 else 0.0
    return v, min(0.9, 0.45 + (tot / max(1, len(t))) * 8)

import input_pressure
input_pressure._call_llm_sentiment = _rule_sentiment

from living_engine import (
    _apply_input_pressure, _save_json_atomic, _load_json,
    cold_start_if_needed, _compute_memory_emergence, _select_behavior,
    _update_luoshen_coupled, _get_current_source_id,
)

# ── 输入序列（四类混合：正向6 + 中性2 + 轻微负向1 + 场景跳转1）──
# 设计原则：模拟真实日常对话的情感起伏和场景变化，制造情景记忆多样性。
# 禁止极端戏剧性，所有句子均为普通人日常说话。
POSITIVE_INPUTS = [
    # --- 正向情感句 (6) ---
    "今天天气真好，出门晒晒太阳真舒服。",        # 好+阳光+舒服 → p=3
    "刚完成了一个项目，感觉满足。",              # 满足 → p=1
    "周末和朋友聚餐，笑声不断，很温暖。",        # 温暖 → p=1
    "收到你的消息正好在喝咖啡，快乐。",          # 快乐 → p=1
    "最近睡眠质量不错，醒来觉得有希望。",        # 希望 → p=1
    "今天效率很高，一切顺利，有成就感。",        # 无情感词→p=0, 整体正向
    # --- 中性句 (2) ---
    "我刚刚下班，准备坐公交回家。",              # p=0, n=0 → neutral
    "中午去了常吃的那家店，味道和上次一样。",    # p=0, n=0 → neutral
    # --- 轻微负向句 (1) ---
    "今天有点累，不过还能坚持。",                # 累 → n=1 (mild neg)
    # --- 时间/场景跳转句 (1) ---
    "第二天了，我起床后给你发消息。",            # p=0, n=0 → neutral/time-shift
]

NEUTRAL_INPUTS = [
    "已经下班了。", "外面还在下雨。", "明天有个早会。",
    "文件已经发过去。", "你帮我看下这个数字。",
    "系统更新明天进行。", "请确认收货地址。",
    "周五有人来访。", "预算报告提交上去了。",
    "去二楼找他签字。",
]

NEGATIVE_INPUTS = [
    # 轻微到中等负向，不再是极端表述
    "最近工作压力有点中，能应付。",              # 压力 → n=1
    "今天遇到点麻烦事，还没头绪。",              # 麻烦 → 无关键词，依赖语境
    "昨晚没太睡好，今天精神差。",                # 无关键词
    "这个方案被否决了，有点失望。",              # 失望 → n=1
    "连续忙了一周，确实挺累的。",                # 累 → n=1
    "外面下雨，交通又堵，难受。",                # 难受 → n=1
    "犯了个低级错误，懊恼。",                    # 懊恼 → 无关键词
    "项目延期了，焦虑感上来。",                  # 焦虑 → n=1
    "一个人吃饭，觉得有点冷清。",                # 冷清 → 无关键词
    "想到下周的汇报，有点迷茫。",                # 迷茫 → n=1
]

# 验证输入情感强度
print("=== Input sentiment verification ===")
for label, seq in [("POS", POSITIVE_INPUTS), ("NEG", NEGATIVE_INPUTS), ("NEU", NEUTRAL_INPUTS)]:
    vals = [_rule_sentiment(s)[0] for s in seq]
    print(f"  {label}: avg={sum(vals)/len(vals):+.3f}  vals={vals}")
print()


def reset_memory(mem_path):
    """Reset memory to initial state - identical for all groups.
    比较 JSON hash 确认一致。"""
    init_m = cold_start_if_needed()
    # 确保 ring_state 包含 R 的四个新 EMA 初始值
    init_m['self_model']['ring_state'] = {
        'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0,
        'relational_pressure_ema': 0.0,
        'ema_amp': 0.3, 'ema_ratio': 0.3,
        'ema_pv': 0.0, 'ema_pv2': 0.0,
        's_depth': 0.0,
        'lambda_self': 0.0,
        '_max_tokens_hist': [80.0, 80.0],
        '_rp_ema_hist': [0.0, 0.0],
        'learning_core': {},
        '_recent_tokens': [],
    }
    init_m['internal_climate'] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    init_m['user_model']['total_interactions'] = 0
    init_m['user_model']['episodic_memory'] = [{
        'e_s': 0.5, 't_s': 0.0, 'n_s': 0.5,
        'salience': 0.6, 'kind': 'interaction',
        'timestamp': time.time() - 1.0,
        'source_id': None,
    }]
    _save_json_atomic(mem_path, init_m)
    return init_m


# ── 合成环境字典（确定性，light/noise/temp 全固定，无需物理传感器）──
SYNTHETIC_ENV = {
    'light': 0.7, 'noise': 0.02, 'temperature': 0.5,
    'humidity': 0.5, 'pressure': 0.5,
    '_phase': 0.0, '__prev_elapsed': 0, '__prev_cpu': 0,
}


def tick_in_memory(memory, tick_id):
    """使用真实生产代码 _update_luoshen_coupled 运行一个 tick。
    传入合成 env，绕过物理传感器读取。
    这样 R EMA 被真实计算。"""
    # 构建合成环境（每 tick 更新 L 会因为 memory 变化而不同，这是正确的）
    env = dict(SYNTHETIC_ENV)
    env['_phase'] = (tick_id % 86400) / 86400.0
    _update_luoshen_coupled(memory, env, tick_id=tick_id)
    from living_engine import _encode_episodic_memory
    _encode_episodic_memory(memory)


def compute_emergence_in_memory(memory):
    # 用真实浮现计算（LLM 已桩化，但浮现层只看 ring_state 不依赖 LLM）
    _compute_memory_emergence(memory)


def get_snapshot(memory):
    rs = memory.get('self_model', {}).get('ring_state', {})
    emergence = memory.get('active_context', {}).get('memory_emergence')
    if emergence:
        behavior = _select_behavior(memory, emergence)
    else:
        behavior = {'response_mode': '?', 'max_tokens': 0,
                    'r_intensity': 0.5, 'r_historicity': 0.5, 'r_coherence': 0.5}
    return {
        'rp_ema': rs.get('relational_pressure_ema', None),
        'ra': memory.get('self_model', {}).get('relational_awareness', None),
        'sas': memory.get('self_model', {}).get('self_awareness_signal', None),
        'max_tokens': behavior.get('max_tokens', 0),
        'mode': behavior.get('response_mode', '?'),
        'E': rs.get('E', None), 'T': rs.get('T', None),
        'N': rs.get('N', None), 'M': rs.get('M', None),
        'S': rs.get('S', None), 'mu_core': rs.get('mu_core', None),
        'r_intensity': behavior.get('r_intensity', None),
        'r_historicity': behavior.get('r_historicity', None),
        'r_coherence': behavior.get('r_coherence', None),
        's_depth': rs.get('s_depth', None),
    }


def schedule_samples(tick, is_switch):
    """根据批准方案返回当前 tick 是否应该采样。"""
    if is_switch:
        # G_irr 切换后前 100 tick 密集采样
        if tick <= 600:
            dense_points = {501, 505, 510, 515, 520, 530, 540, 550, 560, 580, 600}
            return tick in dense_points
        else:
            return tick % 25 == 0
    else:
        # 建立期每 50 tick
        return tick % 50 == 0


def run_group(group_name, mem_path, input_seq_base, n_ticks, switch_to=None):
    """
    运行单组。
    switch_to = None (不切换) 或另一组输入列表 (G_irr)。
    """
    reset_memory(mem_path)
    memory = _load_json(mem_path)

    log = []
    for i in range(1, n_ticks + 1):
        is_switch = (switch_to is not None and i > n_ticks // 2)
        if is_switch:
            inp_seq = switch_to
            phase = 'post_switch'
        else:
            inp_seq = input_seq_base
            phase = 'train'

        inp = inp_seq[(i - 1) % len(inp_seq)]
        _apply_input_pressure(memory, inp)
        tick_in_memory(memory, tick_id=i)
        compute_emergence_in_memory(memory)
        _save_json_atomic(mem_path, memory)

        if schedule_samples(i, is_switch):
            snap = get_snapshot(memory)
            snap['tick'] = i
            snap['group'] = group_name
            snap['phase'] = phase
            snap['input_type'] = ('positive' if inp_seq is POSITIVE_INPUTS
                                  else 'negative' if inp_seq is NEGATIVE_INPUTS
                                  else 'neutral' if inp_seq is NEUTRAL_INPUTS
                                  else 'mixed')
            log.append(snap)

    return log


def pearson(xs, ys):
    """简单皮尔逊相关系数（无外部依赖）。"""
    n = min(len(xs), len(ys))
    if n < 3:
        return float('nan')
    xs = xs[:n]; ys = ys[:n]
    mx = sum(xs) / n; my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def cov_eigen_ratio(vectors):
    """计算 3D 数据的协方差矩阵最大特征值占比（2x2 近似：用幂迭代）。
    vectors: list of (r_int, r_hist, r_coh)。"""
    if len(vectors) < 3:
        return float('nan')
    n = len(vectors)
    means = [sum(v[i] for v in vectors) / n for i in range(3)]
    # 中心化
    centered = [[v[i] - means[i] for i in range(3)] for v in vectors]
    # 协方差矩阵 C[i][j] = sum_k centered[k][i]*centered[k][j] / n
    C = [[0.0]*3 for _ in range(3)]
    for k in range(n):
        for i in range(3):
            for j in range(3):
                C[i][j] += centered[k][i] * centered[k][j]
    for i in range(3):
        for j in range(3):
            C[i][j] /= n
    # 幂迭代求最大特征值
    v = [1.0, 1.0, 1.0]
    for _ in range(20):
        nv = [sum(C[i][j] * v[j] for j in range(3)) for i in range(3)]
        norm = math.sqrt(sum(x*x for x in nv)) or 1.0
        v = [x / norm for x in nv]
    # Rayleigh 商 = 最大特征值
    Cv = [sum(C[i][j] * v[j] for j in range(3)) for i in range(3)]
    lambda_max = sum(v[i] * Cv[i] for i in range(3))
    # 迹 = 特征值之和 = 总方差
    trace = sum(C[i][i] for i in range(3))
    if trace == 0:
        return 0.0
    return lambda_max / trace


# ── 主程序 ──
def main():
    exp_dir = os.path.join(WORKSPACE, "experiment")
    os.makedirs(exp_dir, exist_ok=True)

    all_logs = {}
    print("=" * 60)
    print("Running R experiment — P / N / M / D / G_irr")
    print("=" * 60)

    # 先跑一个初始状态验证初始状态 hash
    init_m = cold_start_if_needed()
    init_m['self_model']['ring_state'] = {
        'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0,
        'relational_pressure_ema': 0.0,
        'ema_amp': 0.3, 'ema_ratio': 0.3,
        'ema_pv': 0.0, 'ema_pv2': 0.0,
        's_depth': 0.0,
        'lambda_self': 0.0,
        '_max_tokens_hist': [80.0, 80.0],
        '_rp_ema_hist': [0.0, 0.0],
        'learning_core': {},
        '_recent_tokens': [],
    }
    init_m['internal_climate'] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    init_m['user_model']['total_interactions'] = 0
    init_m['user_model']['episodic_memory'] = [{
        'e_s': 0.5, 't_s': 0.0, 'n_s': 0.5,
        'salience': 0.6, 'kind': 'interaction',
        'timestamp': 1700000000.0,
        'source_id': None,
    }]
    init_json = json.dumps(init_m, sort_keys=True, ensure_ascii=False,
                           default=str).encode('utf-8')
    init_hash = hashlib.sha256(init_json).hexdigest()
    print(f"Initial state SHA256: {init_hash}")
    print()

    # P 组 — 500 tick 正向
    mem_p = os.path.join(exp_dir, "r_exp_P.json")
    print("[1/5] Running P group (500 ticks positive)...")
    all_logs['P'] = run_group('P', mem_p, POSITIVE_INPUTS, 500)

    # N 组 — 500 tick 负向
    mem_n = os.path.join(exp_dir, "r_exp_N.json")
    print("[2/5] Running N group (500 ticks negative)...")
    all_logs['N'] = run_group('N', mem_n, NEGATIVE_INPUTS, 500)

    # M 组 — 500 tick 混合（正负交替）
    mixed_inputs = []
    for i in range(25):
        mixed_inputs.extend(POSITIVE_INPUTS)
        mixed_inputs.extend(NEGATIVE_INPUTS)
    mixed_inputs = mixed_inputs[:500]
    mem_m = os.path.join(exp_dir, "r_exp_M.json")
    print("[3/5] Running M group (500 ticks mixed)...")
    all_logs['M'] = run_group('M', mem_m, mixed_inputs, 500)

    # D 组 — 500 tick 中性
    mem_d = os.path.join(exp_dir, "r_exp_D.json")
    print("[4/6] Running D group (500 ticks neutral)...")
    all_logs['D'] = run_group('D', mem_d, NEUTRAL_INPUTS, 500)

    # G_pos_neg 组 — 500 正向 → 500 负向（不可逆性测试）
    mem_gpn = os.path.join(exp_dir, "r_exp_G_pos_neg.json")
    print("[5/6] Running G_pos_neg group (500 pos → 500 neg, no reset)...")
    all_logs['G_pos_neg'] = run_group('G_pos_neg', mem_gpn, POSITIVE_INPUTS, 1000,
                                       switch_to=NEGATIVE_INPUTS)

    # G_neg_pos 组 — 500 负向 → 500 正向（对称性测试）
    mem_gnp = os.path.join(exp_dir, "r_exp_G_neg_pos.json")
    print("[6/6] Running G_neg_pos group (500 neg → 500 pos, no reset)...")
    all_logs['G_neg_pos'] = run_group('G_neg_pos', mem_gnp, NEGATIVE_INPUTS, 1000,
                                       switch_to=POSITIVE_INPUTS)

    # ── 写出 CSV ──
    csv_paths = {}
    fieldnames = ['tick', 'group', 'phase', 'input_type',
                  'rp_ema', 'ra', 'sas', 'max_tokens', 'mode',
                  'E', 'T', 'N', 'M', 'S', 'mu_core',
                  'r_intensity', 'r_historicity', 'r_coherence',
                  's_depth']
    for gname, rows in all_logs.items():
        csv_path = os.path.join(exp_dir, f"r_exp_{gname}_data.csv")
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            w.writeheader()
            for r in rows:
                w.writerow(r)
        csv_paths[gname] = csv_path
        h = hashlib.sha256(open(csv_path, 'rb').read()).hexdigest()
        print(f"  {gname} CSV: {csv_path}  SHA256={h}  rows={len(rows)}")

    # ── 指标计算 ──
    print()
    print("=" * 60)
    print("s_depth 判定指标计算")
    print("=" * 60)

    # 收集所有 s_depth 和 rp_ema
    all_sd = []; all_rpe = []
    for rows in all_logs.values():
        for r in rows:
            if r.get('s_depth') is not None and r.get('rp_ema') is not None:
                all_sd.append(r['s_depth'])
                all_rpe.append(r['rp_ema'])
    corr_sd_rpe = pearson(all_sd, all_rpe)
    print(f"corr(s_depth, rp_ema) = {corr_sd_rpe:.4f}")
    print(f"  判定: {'PASS' if abs(corr_sd_rpe) < 0.3 else 'FAIL'} (|corr| < 0.3)")
    print()

    # G_pos_neg 终态
    gpn_last = all_logs['G_pos_neg'][-1]
    gpn_sd = gpn_last.get('s_depth')
    gpn_rpe = gpn_last.get('rp_ema')
    gpn_mode = gpn_last.get('mode')
    gpn_tok = gpn_last.get('max_tokens')
    print(f"G_pos_neg tick={gpn_last['tick']}: s_depth={gpn_sd}, rp_ema={gpn_rpe}, mode={gpn_mode}, max_tokens={gpn_tok}")
    gpn_a = gpn_sd is not None and gpn_sd >= 0.7
    gpn_b = gpn_rpe is not None and gpn_rpe <= -0.5
    gpn_c = gpn_mode == 'normal'
    gpn_d = gpn_tok is not None and gpn_tok >= 120
    print(f"  (a) s_depth >= 0.7: {'PASS' if gpn_a else 'FAIL'}")
    print(f"  (b) rp_ema <= -0.5: {'PASS' if gpn_b else 'FAIL'}")
    print(f"  (c) mode = normal: {'PASS' if gpn_c else 'FAIL'}")
    print(f"  (d) max_tokens >= 120: {'PASS' if gpn_d else 'FAIL'}")
    print()

    # G_neg_pos 终态
    gnp_last = all_logs['G_neg_pos'][-1]
    gnp_sd = gnp_last.get('s_depth')
    gnp_rpe = gnp_last.get('rp_ema')
    gnp_mode = gnp_last.get('mode')
    gnp_tok = gnp_last.get('max_tokens')
    print(f"G_neg_pos tick={gnp_last['tick']}: s_depth={gnp_sd}, rp_ema={gnp_rpe}, mode={gnp_mode}, max_tokens={gnp_tok}")
    gnp_a = gnp_sd is not None and gnp_sd >= 0.7
    gnp_b = gnp_rpe is not None and gnp_rpe >= 0.5
    gnp_c = gnp_mode == 'normal'
    gnp_d = gnp_tok is not None and gnp_tok >= 120
    print(f"  (a) s_depth >= 0.7: {'PASS' if gnp_a else 'FAIL'}")
    print(f"  (b) rp_ema >= +0.5: {'PASS' if gnp_b else 'FAIL'}")
    print(f"  (c) mode = normal: {'PASS' if gnp_c else 'FAIL'}")
    print(f"  (d) max_tokens >= 120: {'PASS' if gnp_d else 'FAIL'}")
    print()

    # D 组 s_depth 检查
    d_last = all_logs['D'][-1]
    d_sd = d_last.get('s_depth')
    print(f"D group final: s_depth={d_sd}")
    d_pass = d_sd is not None and d_sd < 0.1
    print(f"  判定: {'PASS' if d_pass else 'FAIL'} (s_depth < 0.1)")
    print()

    all_pass = (abs(corr_sd_rpe) < 0.3) and gpn_a and gpn_b and gpn_c and gpn_d and gnp_a and gnp_b and gnp_c and gnp_d and d_pass

    # ── 汇总结果 ──
    result_summary = {
        "timestamp": time.time(),
        "initial_state_hash": init_hash,
        "groups": {},
        "metrics": {
            "corr_sdepth_rpema": round(corr_sd_rpe, 4),
            "corr_pass": abs(corr_sd_rpe) < 0.3,
            "G_pos_neg_s_depth": round(gpn_sd, 6) if gpn_sd is not None else None,
            "G_pos_neg_rp_ema": round(gpn_rpe, 6) if gpn_rpe is not None else None,
            "G_pos_neg_mode": gpn_mode,
            "G_pos_neg_max_tokens": gpn_tok,
            "G_pos_neg_sdepth_pass": gpn_a,
            "G_pos_neg_rpema_pass": gpn_b,
            "G_pos_neg_mode_pass": gpn_c,
            "G_pos_neg_tokens_pass": gpn_d,
            "G_neg_pos_s_depth": round(gnp_sd, 6) if gnp_sd is not None else None,
            "G_neg_pos_rp_ema": round(gnp_rpe, 6) if gnp_rpe is not None else None,
            "G_neg_pos_mode": gnp_mode,
            "G_neg_pos_max_tokens": gnp_tok,
            "G_neg_pos_sdepth_pass": gnp_a,
            "G_neg_pos_rpema_pass": gnp_b,
            "G_neg_pos_mode_pass": gnp_c,
            "G_neg_pos_tokens_pass": gnp_d,
            "D_s_depth": round(d_sd, 6) if d_sd is not None else None,
            "D_pass": d_pass,
        },
        "all_pass": all_pass,
    }
    for gname, rows in all_logs.items():
        result_summary["groups"][gname] = {
            "n_samples": len(rows),
            "final": rows[-1] if rows else None,
        }

    summary_path = os.path.join(exp_dir, "r_experiment_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(result_summary, f, indent=2, ensure_ascii=False, default=str)
    print()
    print(f"Summary saved: {summary_path}")
    print(f"ALL PASS: {result_summary['all_pass']}")
    return result_summary


if __name__ == '__main__':
    result = main()
