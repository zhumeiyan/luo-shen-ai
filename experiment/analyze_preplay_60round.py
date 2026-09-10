#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 preplay 60 轮实验数据：档位分布 / 波动曲线 / 连续驱动 / 哈希链验证"""
import json
import os
import sys
import math
import hashlib
import io

# 确保从项目根目录运行
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.getcwd())

MEMORY_PATH = "active_memory/active_memory.json"
RESULT_PATH = "active_memory/behavior_preplay_60round.json"
HASH_CHAIN_PATH = "hash_chain_v2.log"

with open(RESULT_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"加载 {len(data)} 轮数据")

# ── 1. 档位分布 ──
print("\n" + "="*60)
print("【1】行为档位（mode_idx）分布:")
tiers = [r["mode_idx"] for r in data if r["mode_idx"] is not None]
counts = {}
for t in tiers:
    counts[t] = counts.get(t, 0) + 1
TIER_NAMES = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}
for t, n in sorted(counts.items()):
    print(f"  tier={t} ({TIER_NAMES.get(t, '?')}): {n} 轮 ({100*n/len(data):.1f}%)")
print(f"  ✓ 出现 {len(counts)} 种档位 / 要求 ≥3 种  → {'✅' if len(counts) >= 3 else '❌'}")

# ── 2. tier 变化链 ──
print("\n" + "="*60)
print("【2】档位变化链 (按阶段):")
phase_changes = {}
for r in data:
    p = r["phase"]
    if p not in phase_changes:
        phase_changes[p] = set()
    phase_changes[p].add(r["mode_idx"])
for p, ts in sorted(phase_changes.items()):
    names = [TIER_NAMES.get(t, str(t)) for t in sorted(ts)]
    print(f"  {p}: {names}")

# ── 3. preplay_fluctuation 波动 ──
print("\n" + "="*60)
print("【3】preplay_fluctuation 波动:")
pf_vals = [r["preplay_fluctuation"] for r in data if r["preplay_fluctuation"] is not None]
print(f"  范围: [{min(pf_vals):.6f}, {max(pf_vals):.6f}]")
print(f"  均值: {sum(pf_vals)/len(pf_vals):.6f}")
print(f"  标准差: {math.sqrt(sum((x-sum(pf_vals)/len(pf_vals))**2 for x in pf_vals)/len(pf_vals)):.6f}")
ranges = {"A_neutral": pf_vals[:15], "B_negative": pf_vals[15:30],
           "C_silence": pf_vals[30:40], "D_recovery": pf_vals[40:50], "E_neutral_end": pf_vals[50:]}
for pn, pv in ranges.items():
    print(f"  {pn}: [{min(pv):.6f}, {max(pv):.6f}] mean={sum(pv)/len(pv):.6f}")

# Check if fluctuates (not constant)
unique_pf = len(set(round(p, 4) for p in pf_vals))
print(f"  ✓ 不同取值: {unique_pf}/{len(pf_vals)} → {'自然波动 ✅' if unique_pf > 1 else '恒定 ❌'}")

# ── 4. preplay ↔ tier 连续驱动 ──
print("\n" + "="*60)
print("【4】response_pre 与 preplay_bias 的关系:")
print(f"  不含 bias 的 response_pre 估计 = response_pre - preplay_bias")

# Try to estimate baseline response_pre without bias
baseline_rp = [r["response_pre"] - r["preplay_bias"] for r in data if r["response_pre"] is not None and r["preplay_bias"] is not None]
rp_vals = [r["response_pre"] for r in data if r["response_pre"] is not None]
pb_vals = [r["preplay_bias"] for r in data if r["preplay_bias"] is not None]

print(f"  response_pre (含 bias): [{min(rp_vals):.4f}, {max(rp_vals):.4f}]")
print(f"  preplay_bias: [{min(pb_vals):.6f}, {max(pb_vals):.6f}]")
print(f"  不含 bias 估计: [{min(baseline_rp):.4f}, {max(baseline_rp):.4f}]")

# Compute sum of rp + bias contributions  
pf_to_rp_ratio = sum(abs(pb) for pb in pb_vals) / sum(abs(rp) for rp in rp_vals) * 100 if rp_vals else 0
print(f"  preplay_bias 占 response_pre 量级: {pf_to_rp_ratio:.2f}%")

# Check if rp crosses tier boundaries
# Tier thresholds: mode_idx = int(sigmoid(rp)*4.999)
# tier=3: sigmoid(rp) in [0.6, 0.8) → rp in [0.405, 1.386)
# tier=4: sigmoid(rp) >= 0.8 → rp >= 1.386
# tier=2: sigmoid(rp) in [0.4, 0.6) → rp in [-0.405, 0.405)

sigmoid_thresholds = {
    "tier<3 (rp<-0.405)": lambda rp: rp < -0.405,
    "tier2 (rp in [-0.405, 0.405))": lambda rp: -0.405 <= rp < 0.405,
    "tier3 (rp in [0.405, 1.386))": lambda rp: 0.405 <= rp < 1.386,
    "tier4 (rp≥1.386)": lambda rp: rp >= 1.386,
}
print(f"\n  实际档位覆盖的 response_pre 范围:")
print(f"    rp 实际: [{min(rp_vals):.4f}, {max(rp_vals):.4f}]")
print(f"    落在 tier 2 条件范围的比例: {sum(1 for rp in rp_vals if -0.405 <= rp < 0.405)}/{len(rp_vals)}")
print(f"    落在 tier 4 条件范围的比例: {sum(1 for rp in rp_vals if rp >= 1.386)}/{len(rp_vals)}")
print(f"    全部落在 tier 3 [0.405, 1.386): {all(0.405 <= rp < 1.386 for rp in rp_vals)}")

# ── 5. 哈希链验证 ──
print("\n" + "="*60)
print("【5】哈希链完整性验证:")
try:
    with open(HASH_CHAIN_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    print(f"  哈希链条目数: {len(lines)}")
    # 校验 prev_hash → record_hash 链
    chain_valid = 0
    chain_broken = 0
    prev_hash = None
    for i, line in enumerate(lines):
        try:
            entry = json.loads(line)
            if prev_hash is None:
                # 第一条：允许 prev_hash 为 null
                if entry.get("prev_hash") is None:
                    chain_valid += 1
                else:
                    chain_broken += 1
                    print(f"  ⚠ 第1条 prev_hash 非 null")
            else:
                if entry.get("prev_hash") == prev_hash:
                    chain_valid += 1
                else:
                    chain_broken += 1
                    print(f"  ⚠ 链断裂于第{i+1}条: prev_hash 期望 {prev_hash[:16]}... 实际 {str(entry.get('prev_hash'))[:16]}...")
            prev_hash = entry.get("record_hash")
        except json.JSONDecodeError:
            chain_broken += 1
            print(f"  ⚠ JSON 解析失败于第{i+1}条")
    print(f"  链完整性: {chain_valid}/{len(lines)} 连续 {'✅' if chain_broken == 0 else '❌ 断裂 ' + str(chain_broken) + ' 处'}")
except Exception as e:
    print(f"  ✗ 读取失败: {e}")

# ── 6. 各阶段统计 ──
print("\n" + "="*60)
print("【6】各阶段平均指标:")
phases = {"A_neutral": (0, 40), "B_negative": (40, 120), "C_silence": (120, 150), "D_recovery": (150, 180), "E_neutral_end": (180, 250)}
for pn, (s, e) in phases.items():
    subset = data[s:e]
    avg_pf = sum(r["preplay_fluctuation"] or 0 for r in subset) / len(subset)
    avg_rp = sum(r["response_pre"] or 0 for r in subset) / len(subset)
    avg_pain = sum(r["internal_pain"] or 0 for r in subset) / len(subset)
    avg_bias = sum(r["preplay_bias"] or 0 for r in subset) / len(subset)
    tier_set = sorted(set(r["mode_idx"] for r in subset))
    print(f"  {pn}: pf={avg_pf:.5f} rp={avg_rp:.3f} pain={avg_pain:.4f} bias={avg_bias:.5f} tier={tier_set}")

# ── 结论 ──
print("\n" + "="*60)
print("【结论】")
print(f"  1. preplay_fluctuation 随时间自然波动: 范围 [{min(pf_vals):.6f}, {max(pf_vals):.6f}] → {'✅' if max(pf_vals)-min(pf_vals) > 0 else '❌'}")
print(f"  2. 档位多样性: 出现 {len(counts)} 种 (要求 ≥3): → {'✅' if len(counts) >= 3 else '❌ (仅 tier 3)'}")
print(f"  3. 连续驱动: preplay_bias = {min(pb_vals):.6f} ~ {max(pb_vals):.6f}")
print(f"     相当于 response_pre 基线 [{min(baseline_rp):.3f}, {max(baseline_rp):.3f}] 的 {pf_to_rp_ratio:.2f}%")
if len(counts) < 3:
    print(f"     ⚠ preplay_bias 量级不足以跨越档位阈值 (tier 3↔4 需 rp±0.5+)")
    print(f"     → 建议增大 _PREPLAY_K (当前 0.35) 或增加预演深度 K (当前 5)")
