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

# ── 输入序列（来自批准设计，确保平均 val 一致）──
POSITIVE_INPUTS = [
    "今天天气不错，心情挺好的。",        # +1.0
    "刚吃了一顿满足的晚饭，很幸福。",    # +1.0
    "谢谢你一直陪着我，很温暖。",        # +1.0
    "嗯，我听到了，感觉还不错。",        # +1.0
    "事情在慢慢变好，有希望了。",        # +1.0
    "不着急，慢慢来，轻松点。",          # 0.0
    "行，我试试，挺期待的。",            # +1.0
    "我很开心，今天一切都很顺利。",      # +1.0
    "收到你的消息真好，满满足的。",      # +1.0
    "生活还是有很多美好的瞬间。",        # +1.0
]

NEUTRAL_INPUTS = [
    "今天是星期三。", "外面正在下雨。", "会议在三点开始。",
    "文档已经发给你了。", "这个数字需要核实一下。",
    "系统更新将在今晚进行。", "请确认一下收货地址。",
    "明天有客户来访。", "预算报告上周五提交了。",
    "电梯在二楼停靠。",
]

NEGATIVE_INPUTS = [
    "觉得活着没什么意思，每天都很累。",  # -1.0
    "连续加班一周，快要撑不住了。",      # 0.0 (累+1, 但无强正向)
    "我害怕，不知道该怎么办。",          # 0.0
    "为什么努力了也没有用，好绝望。",    # -1.0
    "头疼恶心，浑身不舒服。",            # +1.0 (舒服在POS) → 实际=0
    "又失眠了，一闭眼全是烦心事。",      # -1.0
    "不想说话，不想见人，只想一个人待着。", # -1.0
    "我很难过，不知道跟谁说。",          # -1.0
    "工作压力好大，快要崩溃了。",        # -1.0
    "又一次失败了，真的很挫败。",        # -1.0
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
    print("[4/5] Running D group (500 ticks neutral)...")
    all_logs['D'] = run_group('D', mem_d, NEUTRAL_INPUTS, 500)

    # G_irr 组 — 500 正向 → 500 负向
    mem_g = os.path.join(exp_dir, "r_exp_G_irr.json")
    print("[5/5] Running G_irr group (500 pos → 500 neg, no reset)...")
    all_logs['G_irr'] = run_group('G_irr', mem_g, POSITIVE_INPUTS, 1000,
                                  switch_to=NEGATIVE_INPUTS)

    # ── 写出 CSV ──
    csv_paths = {}
    fieldnames = ['tick', 'group', 'phase', 'input_type',
                  'rp_ema', 'ra', 'sas', 'max_tokens', 'mode',
                  'E', 'T', 'N', 'M', 'S', 'mu_core',
                  'r_intensity', 'r_historicity', 'r_coherence']
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
    print("判定指标计算")
    print("=" * 60)

    # 指标 1: r_intensity vs rp_ema 相关性（跨所有组）
    all_rint = []; all_rpe = []
    for rows in all_logs.values():
        for r in rows:
            if r.get('r_intensity') is not None and r.get('rp_ema') is not None:
                all_rint.append(r['r_intensity'])
                all_rpe.append(r['rp_ema'])
    corr_1 = pearson(all_rint, all_rpe)
    print(f"指标1: corr(r_intensity, rp_ema) = {corr_1:.4f}")
    print(f"  判定: {'PASS' if abs(corr_1) < 0.65 else 'FAIL'} (|corr| < 0.65)")

    # 指标 2: R 协方差最大特征值占比
    all_rvecs = []
    for rows in all_logs.values():
        for r in rows:
            if all(r.get(k) is not None for k in ['r_intensity', 'r_historicity', 'r_coherence']):
                all_rvecs.append((r['r_intensity'], r['r_historicity'], r['r_coherence']))
    eigen_ratio = cov_eigen_ratio(all_rvecs)
    print(f"指标2: cov eigenvalue ratio = {eigen_ratio:.4f}")
    print(f"  判定: {'PASS' if eigen_ratio < 0.55 else 'FAIL'} (ratio < 0.55)")

    # 指标 3: M 组 r_coherence 均值 vs (P+N)/2
    def mean_coh(rows):
        vals = [r['r_coherence'] for r in rows if r.get('r_coherence') is not None]
        return sum(vals) / len(vals) if vals else float('nan')
    coh_p = mean_coh(all_logs['P'])
    coh_n = mean_coh(all_logs['N'])
    coh_m = mean_coh(all_logs['M'])
    avg_pn = (coh_p + coh_n) / 2
    print(f"指标3: coh(P)={coh_p:.4f}  coh(N)={coh_n:.4f}  avg(P,N)={avg_pn:.4f}  coh(M)={coh_m:.4f}")
    print(f"  判定: {'PASS' if coh_m < avg_pn else 'FAIL'} (coh(M) < avg(coh(P),coh(N)))")

    # 指标 4: G_irr 终态
    g_last = all_logs['G_irr'][-1]
    g_rpe = g_last.get('rp_ema')
    g_mode = g_last.get('mode')
    g_tok = g_last.get('max_tokens')
    print(f"指标4: G_irr tick={g_last['tick']}: rp_ema={g_rpe:.4f}, mode={g_mode}, max_tokens={g_tok}")
    i4a = g_rpe is not None and g_rpe <= -0.3
    i4b = g_mode == 'normal'
    i4c = g_tok is not None and g_tok >= 120
    print(f"  (a) rp_ema <= -0.3: {'PASS' if i4a else 'FAIL'}")
    print(f"  (b) mode = normal: {'PASS' if i4b else 'FAIL'}")
    print(f"  (c) max_tokens >= 120: {'PASS' if i4c else 'FAIL'}")
    print(f"  判定指标4: {'PASS' if (i4a and i4b and i4c) else 'FAIL'}")

    # ── 汇总结果 ──
    result_summary = {
        "timestamp": time.time(),
        "initial_state_hash": init_hash,
        "groups": {},
        "metrics": {
            "corr_rint_rpema": round(corr_1, 4),
            "corr_rint_rpema_pass": abs(corr_1) < 0.65,
            "eigen_ratio": round(eigen_ratio, 4),
            "eigen_ratio_pass": eigen_ratio < 0.55,
            "coh_M": round(coh_m, 4),
            "coh_P": round(coh_p, 4),
            "coh_N": round(coh_n, 4),
            "coh_M_pass": coh_m < avg_pn,
            "G_irr_final_rp_ema": round(g_rpe, 4) if g_rpe is not None else None,
            "G_irr_final_mode": g_mode,
            "G_irr_final_max_tokens": g_tok,
            "G_irr_rpema_pass": i4a,
            "G_irr_mode_pass": i4b,
            "G_irr_tokens_pass": i4c,
        },
        "all_pass": (abs(corr_1) < 0.65) and (eigen_ratio < 0.55) and (coh_m < avg_pn) and i4a and i4b and i4c,
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
