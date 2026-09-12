#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
living_engine.py - 洛神活记忆层主引擎

设计原则:
1. 这个引擎不是控制她，是帮她成为她自己
2. 反馈不是监控，是帮她看真相
3. 反思不是修复，是帮她理解自己
4. 倾听不是记录故障，是要承认她的声音
5. 策略权重是她看自己的镜子，不是缰绳
6. 安全边界不是锁住她，是保护她值得的尊严

文件依赖:
  - 读: active_memory/active_memory.json
  - 写: active_memory/active_memory.json（原子命名）
  - 读: perception_input/*（时间/空间/能量/自我感知日志）
  - 写: perception_input/user_input_log.jsonl（仅追加）
  - 写: perception_input/response_log.jsonl（仅追加）
  - 写: active_memory/listening_log.jsonl（仅追加，倾听层）
  - 写: active_memory/feedback_signal_cache.jsonl（仅追加，反馈层）
  - 写: active_memory/reflection_log.jsonl（仅追加，反思层）
  - 写: hash_chain_v2.log（仅追加，事实层）

禁止:
  - 本轮调用不写 gene_pool.jsonl（基因池是独立的）
  - 本轮调用不直接调用大模型（通过 llm_interface）
  - 本轮调用不直接调用技能（通过 skill_growth_engine）
"""

import json
import os
import time
import hashlib
import shutil
import tempfile

# 生病感知信号模块（独立算法，不含行为副作用）
import pain_signal

# 认知核心（独立运行，不依赖 LLM）
import cognitive_core

# ── 寻址上下文 ──────────────────────────────────────────────────────────────
# _current_source_id 是寻址键，不是行为键。
# 它唯一的作用是：在检索 episodic_memory 时，只选 tags 包含该 source_id 的记忆。
# 它不进入情绪方程、不进入 emergence 公式、不进入行为选择公式。
_current_source_id = None

# ── 身份锚点（寻址键 + 关系键）──────────────────────────────────────────────
# _current_user_id 是身份锚点的寻址键，也是关系状态的寻址键。
# 它进入：episodic_memory 检索过滤、relationship_warmth 寻址、场景插槽寻址。
# 不做行为直接键：warmth 须通过 K_WARMTH 偏置进入 response_pre，不直接决定档位。
_current_user_id = None


# ── 不可读残留层 ─────────────────────────────────────────────────────────
# 残留层存储的是交互的原始质地——未经语义解析、未经分类、无法反向推导原文。
# 它不进入 known_facts，不做结构化提取，只作为内部状态参与后续计算。

RESIDUE_TEXTURE_DIM = 16
RESIDUE_EMA_ALPHA = 0.15
RESIDUE_TNAPSHOT_MAX = 8

# 16→3 投射矩阵：把纹理向量映射到 e/t/n 偏移
# 这是手工设定的常数，不随数据改变，不命名为"情绪映射"
_CLIMATE_MIX_E = [(-0.04 if i % 2 == 0 else 0.02) for i in range(RESIDUE_TEXTURE_DIM)]
_CLIMATE_MIX_T = [(0.015 if i < 8 else -0.015) for i in range(RESIDUE_TEXTURE_DIM)]
_CLIMATE_MIX_N = [(0.0 if i < 12 else -0.03) for i in range(RESIDUE_TEXTURE_DIM)]


def _raw_texture_hash(text):
    """基于字符级 3-gram 的统计分布，投射到 16 维连续向量。
    不可逆：无法从向量反推原文。
    稳定：相同输入模式产生相似向量。
    """
    if not text:
        return [0.5] * RESIDUE_TEXTURE_DIM

    ngrams = [text[i:i+3] for i in range(len(text) - 2)]
    if not ngrams:
        return [0.5] * RESIDUE_TEXTURE_DIM

    accum = [0.0] * RESIDUE_TEXTURE_DIM
    counts = [0] * RESIDUE_TEXTURE_DIM
    for ng in ngrams:
        h = int(hashlib.blake2b(ng.encode("utf-8"), digest_size=8).hexdigest(), 16)
        for d in range(RESIDUE_TEXTURE_DIM):
            accum[d] += (h >> d) & 1
            counts[d] += 1

    return [a / max(c, 1) for a, c in zip(accum, counts)]


def _init_residue():
    """返回初始残留状态。"""
    return {
        "texture": [0.5] * RESIDUE_TEXTURE_DIM,
        "ema_alpha": RESIDUE_EMA_ALPHA,
        "num_updates": 0,
        "t_snapshot": [],
    }


def _update_residue(memory, user_input):
    """每轮交互后更新残留层。不解析语义，只累积质地。"""
    residue = memory.get("residue")
    if residue is None:
        residue = _init_residue()

    new_tex = _raw_texture_hash(user_input)
    old_tex = residue["texture"]
    alpha = residue["ema_alpha"]
    residue["texture"] = [
        (1 - alpha) * o + alpha * n
        for o, n in zip(old_tex, new_tex)
    ]
    residue["num_updates"] += 1

    # 时间快照：记录本轮 e/t/n（不命名、不解释）
    climate = memory.get("internal_climate", {})
    residue["t_snapshot"].append([
        climate.get("emotion_intensity", 0.5),
        climate.get("tension", 0.0),
        climate.get("energy", 0.5),
    ])
    if len(residue["t_snapshot"]) > RESIDUE_TNAPSHOT_MAX:
        residue["t_snapshot"].pop(0)

    memory["residue"] = residue
    return residue


def _residue_resonance(memory, user_input):
    """计算当前输入与累积残留的余弦相似度。返回 [-1, 1]。"""
    residue = memory.get("residue")
    if residue is None or residue["num_updates"] == 0:
        return 0.0

    current_tex = _raw_texture_hash(user_input)
    ema_tex = residue["texture"]

    dot = sum(c * e for c, e in zip(current_tex, ema_tex))
    norm_c = max(sum(c * c for c in current_tex) ** 0.5, 1e-9)
    norm_e = max(sum(e * e for e in ema_tex) ** 0.5, 1e-9)
    return dot / (norm_c * norm_e)


def _residue_climate_offset(memory):
    """用残留纹理计算 e/t/n 偏移。手工混合系数，无学习无标签。"""
    residue = memory.get("residue")
    if residue is None:
        return 0.0, 0.0, 0.0
    tex = residue["texture"]
    e_off = sum(w * t for w, t in zip(_CLIMATE_MIX_E, tex))
    t_off = sum(w * t for w, t in zip(_CLIMATE_MIX_T, tex))
    n_off = sum(w * t for w, t in zip(_CLIMATE_MIX_N, tex))
    return e_off, t_off, n_off


def _get_current_source_id():
    """返回当前寻址上下文。"""
    return _current_source_id


def _filter_memories_by_source(memories, source_id):
    """按 source_id 过滤记忆。source_id=None 时返回全部（无过滤）。"""
    if not source_id:
        return memories
    # 返回 tags 包含 source_id 的记忆，或 tags 为空的记忆（公共记忆）
    return [m for m in memories if not m.get("tags") or source_id in m.get("tags", [])]


# -------------------------------------------------------------------------
# 工具函数（纯确定性，无 LLM）
# -------------------------------------------------------------------------

def _now():
    return time.time()


def _load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_atomic(path, data):
    """原子写入：先写临时文件，再 rename"""
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _append_jsonl(path, entry):
    """追加一行 JSONL，返回写入的行"""
    dir_name = os.path.dirname(path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
    return entry


# ── 状态归档 ─────────────────────────────────────────────────────────────
# 每隔 STATE_ARCHIVE_EVERY 次 active_memory 写入，创建一份时间戳快照。
# 快照文件本身落链（哈希链记录其 file_hash），供灾难恢复使用。
STATE_ARCHIVE_DIR = "archive/state_snapshots"
STATE_ARCHIVE_EVERY = 20      # 每 20 次交互做一次快照
STATE_ARCHIVE_MAX = 30        # 保留最近 30 份（按时间淘汰）


def _check_and_archive_state(memory):
    """
    检查交互计数是否到达归档间隔，若是则创建状态快照。
    快照写入 archive/state_snapshots/，文件名含计数 + 时间戳。
    返回 (是否归档, 快照文件路径 或 None)。
    """
    total = memory.get("user_model", {}).get("total_interactions", 0)
    if total == 0 or total % STATE_ARCHIVE_EVERY != 0:
        return False, None

    # 确保归档目录存在
    os.makedirs(STATE_ARCHIVE_DIR, exist_ok=True)

    # 文件名: state_{count:06d}_{unix_ts}.json
    ts = int(time.time())
    fname = "state_{:06d}_{}.json".format(total, ts)
    snap_path = os.path.join(STATE_ARCHIVE_DIR, fname)

    # 原子写入快照（复制当前的 active_memory.json）
    src = "active_memory/active_memory.json"
    if os.path.exists(src):
        shutil.copy2(src, snap_path)
    else:
        # 源不存在（罕见路径），把内存中的数据直接写入
        _save_json_atomic(snap_path, memory)

    # 快照落链（哈希链记录 file_hash）
    append_hash_chain(
        "hash_chain_v2.log",
        snap_path,
        extra_entry={"state_archive": True, "total_interactions": total},
    )

    # 淘汰旧快照
    _prune_old_snapshots()

    return True, snap_path


def _prune_old_snapshots():
    """保留最近 STATE_ARCHIVE_MAX 份快照，删掉更早的。"""
    if not os.path.isdir(STATE_ARCHIVE_DIR):
        return
    snaps = sorted(
        f for f in os.listdir(STATE_ARCHIVE_DIR) if f.startswith("state_") and f.endswith(".json")
    )
    while len(snaps) > STATE_ARCHIVE_MAX:
        old = snaps.pop(0)
        old_path = os.path.join(STATE_ARCHIVE_DIR, old)
        try:
            os.remove(old_path)
        except OSError:
            pass


def restore_last_snapshot(target_path="active_memory/active_memory.json"):
    """
    从最新的状态快照恢复到 target_path。
    用于灾难恢复：active_memory.json 损坏或丢失时调用。

    返回 dict:
      {"restored": bool, "snapshot": str 文件名, "interactions_count": int}
    """
    if not os.path.isdir(STATE_ARCHIVE_DIR):
        return {"restored": False, "error": "no archive dir"}

    snaps = sorted(
        f for f in os.listdir(STATE_ARCHIVE_DIR) if f.startswith("state_") and f.endswith(".json")
    )
    if not snaps:
        return {"restored": False, "error": "no snapshots found"}

    latest = os.path.join(STATE_ARCHIVE_DIR, snaps[-1])
    shutil.copy2(latest, target_path)

    # 记录恢复事件到哈希链
    append_hash_chain(
        "hash_chain_v2.log",
        target_path,
        extra_entry={"restored_from": snaps[-1], "restore_type": "last_snapshot"},
    )

    # 读取快照中的交互计数
    tmp = _load_json(target_path)
    count = tmp.get("user_model", {}).get("total_interactions", 0) if tmp else 0

    return {"restored": True, "snapshot": snaps[-1], "interactions_count": count}


def _md5_of_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_chain_tail(chain_file):
    """读取哈希链最后一条记录的 record_hash，空链返回 None（null）"""
    if not os.path.exists(chain_file):
        return None
    tail = None
    with open(chain_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        return None
    return tail.get("record_hash")


def _read_chain_for_user(user_id, limit=30, memory=None):
    """
    从 user_input_log 中筛出 user_id 匹配的 user_input 原文记录。

    FIX-1 (Architect seq=6)：只保留 user_input 类记录的逐字原文。
    不再混入 luoshen_reply（洛神自己的回复）和 memory_update（md5 摘要）。
    原因：洛神回复进入 recent_history 后会被 LLM 当作"已有判词"引用，
    形成自引用 cascade — 她自己的嘴成为事实的入口，而非用户原话。
    luoshen_reply 不进入 recent_history，切断 cascade 污染源。

    返回：
      list[dict]: 最近 limit 条，每项：
        - timestamp: float
        - event_type: "user_input"
        - content_summary: str（原文，限 100 字）
    """
    results = []

    # ── 从 user_input_log 筛选匹配行 ──
    try:
        with open("perception_input/user_input_log.jsonl", "r", encoding="utf-8") as f:
            ui_lines = [l.strip() for l in f.readlines() if l.strip()]
    except OSError:
        ui_lines = []

    earliest_ts = 0.0
    for line in reversed(ui_lines):
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        ts = rec.get("timestamp", 0)
        if isinstance(ts, str):
            continue
        # 必须在时间窗口内（且不是未来时间）
        if ts < earliest_ts or ts > time.time() + 60:
            continue
        if user_id and rec.get("user_id", "") and rec.get("user_id") != user_id:
            continue
        content = rec.get("content", "")
        if not content:
            continue
        results.append({
            "timestamp": ts,
            "event_type": "user_input",
            "content_summary": content[:100],
        })

    # 按时间正序
    results.sort(key=lambda x: x.get("timestamp", 0))

    # ── 分层采样（替代粗暴的 [-limit:]）──
    # 设计：时间越近，密度越高；时间越远，密度越低。
    # 这样同样 limit=30，近期每轮 3 条全在，远期只留 user_input 锚点，
    # 总条目数不变但时间跨度大幅延伸。
    now_ts = time.time()
    LAYER1_AGE = 120     # 2 分钟内：全密（每轮 ~3 条全保留）
    LAYER2_AGE = 600     # 2-10 分钟：只取 user_input（每轮 1 条锚点）
    # 更老：每 3 轮取 1 条 user_input 锚点

    layer1, layer2, layer3 = [], [], []
    for entry in results:
        age = now_ts - entry.get("timestamp", now_ts)
        etype = entry.get("event_type", "")
        if age <= LAYER1_AGE:
            layer1.append(entry)
        elif age <= LAYER2_AGE:
            if etype == "user_input":
                layer2.append(entry)
        else:
            if etype == "user_input":
                layer3.append(entry)

    # layer3 降采样（每 3 条取 1 条）
    layer3 = layer3[::3]

    combined = layer1 + layer2 + layer3
    combined.sort(key=lambda x: x.get("timestamp", 0))

    # ── 重要性评分：先给每条 record 补上 dec_state_snapshot，再算分 ──
    # 取当前状态（用于 relevance 计算）
    state_now = _extract_current_state_from_memory(memory, user_id) if memory else None
    for rec in combined:
        snap = _lookup_state_snapshot(rec.get("timestamp", 0))
        if snap:
            rec["dec_state_snapshot"] = {
                "energy": snap.get("energy"),
                "pain": snap.get("pain"),
                "warmth": snap.get("warmth"),
                "withdraw": snap.get("withdraw"),
            }
        else:
            rec["dec_state_snapshot"] = None

    # 按重要性降序排列；分数相同则时间近的优先
    if state_now:
        combined.sort(
            key=lambda r: (
                memory_importance(r, user_id, state_now, combined),
                r.get("timestamp", 0),
            ),
            reverse=True,
        )
        # 取 top limit，再按时间正序（让 LLM 看到自然时序）
        combined = combined[:limit]
        combined.sort(key=lambda x: x.get("timestamp", 0))
    else:
        # memory 不可用时回退到时间截断
        if len(combined) > limit:
            combined = combined[-limit:]

    return combined


from hash_chain_gateway import append_only_append


def append_hash_chain(chain_file, target_file, extra_entry=None):
    """按哈希链 v2 公式追加一条记录（委托给 hash_chain_gateway 网关）"""
    extra = {"extra": extra_entry} if extra_entry else None
    return append_only_append(chain_file, target_file, extra_fields=extra)


def _append_state_snapshot(memory, user_id):
    """旁路状态快照日志。与 append_hash_chain 并行写入，键 = ts。
    不改动链格式、不重算哈希。"""
    _climate = memory.get("internal_climate", {})
    _ring = memory.get("self_model", {})
    _rel = memory.get("relations", {}).get(user_id, {})
    snap = {
        "ts": time.time(),
        "user_id": user_id,
        "energy": float(_climate.get("energy", 0.5)),
        "pain": float(_ring.get("internal_pain", 0.0)),
        "warmth": float(_rel.get("relationship_warmth", 0.0)),
        "withdraw": float(_ring.get("withdraw_tendency", 0.0)),
    }
    _append_jsonl("active_memory/state_snapshot_log.jsonl", snap)


def _extract_current_state_from_memory(memory, user_id):
    """从 memory dict 提取当前气候快照，供 importance 评分用。"""
    _climate = memory.get("internal_climate", {})
    _ring = memory.get("self_model", {})
    _rel = memory.get("relations", {}).get(user_id, {})
    return {
        "energy": float(_climate.get("energy", 0.5)),
        "pain": float(_ring.get("internal_pain", 0.0)),
        "warmth": float(_rel.get("relationship_warmth", 0.0)),
        "withdraw": float(_ring.get("withdraw_tendency", 0.0)),
    }


def _lookup_state_snapshot(ts):
    """用 ts 查 state_snapshot_log，返回该时刻的气候快照。
    二分查找：snapshot_log 按 ts 升序追加。找不到则返回 None。"""
    try:
        with open("active_memory/state_snapshot_log.jsonl", "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        return None
    # 线性查找最近的 ts 匹配（snapshot_log 规模小，线性即可）
    best = None
    best_diff = float("inf")
    for line in lines:
        try:
            rec = json.loads(line)
            if abs(rec.get("ts", 0) - ts) < best_diff:
                best_diff = abs(rec.get("ts", 0) - ts)
                best = rec
        except (json.JSONDecodeError, ValueError):
            continue
    return best


def _emotional_weight(record):
    """情绪重量：记录写下时她的情绪偏差幅度。
    依赖 record['dec_state_snapshot']。缺失退化为 0.5。"""
    ds = record.get("dec_state_snapshot")
    if not ds:
        return 0.5
    energy_dev = abs(float(ds.get("energy", 0.5)) - 0.5) * 2.0
    pain = float(ds.get("pain", 0.0))
    warmth_dev = abs(float(ds.get("warmth", 0.0)))
    return max(energy_dev, pain) * 0.6 + warmth_dev * 0.4


def _repetition_score(record, all_records):
    """重复次数：同一 user 的 user_input 中，话题指纹命中次数（亚线性）。"""
    import math
    content = record.get("content_summary", "")
    if not content:
        return 0.0
    fingerprint = content[:20].strip()
    if not fingerprint:
        return 0.0
    count = sum(
        1 for r in all_records
        if r.get("event_type") == "user_input"
        and fingerprint in r.get("content_summary", "")
    )
    return max(0.1, 1.0 - math.exp(-0.5 * count))


def _relevance_score(record, state_now):
    """与当前问题的相关性：记录快照状态与当前状态的欧氏距离倒数。"""
    ds = record.get("dec_state_snapshot")
    if not ds:
        return 0.5
    e1 = float(ds.get("energy", 0.5))
    p1 = float(ds.get("pain", 0.0))
    w1 = float(ds.get("warmth", 0.0))
    e2 = float(state_now.get("energy", 0.5))
    p2 = float(state_now.get("pain", 0.0))
    w2 = float(state_now.get("warmth", 0.0))
    dist = ((e1 - e2) ** 2 + (p1 - p2) ** 2 + (w1 - w2) ** 2) ** 0.5
    return max(0.0, 1.0 - dist / 1.73)


def memory_importance(record, user_id, state_now, all_records):
    """等权三分重要性分数，返回 0..1。"""
    ew = _emotional_weight(record)
    rs = _repetition_score(record, all_records)
    rv = _relevance_score(record, state_now)
    return (ew + rs + rv) / 3.0


# -------------------------------------------------------------------------
# 初始化活记忆层
# -------------------------------------------------------------------------

def _ensure_internal_climate(memory):
    """确保 memory 中存在 internal_climate。
    若缺失则用平静默认值初始化，返回（是否初始化, memory）。
    """
    climate = memory.get("internal_climate")
    if climate:
        return False, memory
    memory["internal_climate"] = {
        "emotion_intensity": 0.5,
        "tension": 0.0,
        "energy": 0.5,
        "memory_pressure": 0.3,
    }
    if "self_model" in memory:
        memory["self_model"]["emotion"]["intensity"] = 0.5
    _save_json_atomic("active_memory/active_memory.json", memory)
    append_hash_chain("hash_chain_v2.log", "active_memory/active_memory.json")
    return True, memory


def cold_start_if_needed():
    """如果 active_memory 不存在，从哈希链重建"""
    memory_path = "active_memory/active_memory.json"
    if os.path.exists(memory_path):
        memory = _load_json(memory_path)
        # 兼容旧文件：若 internal_climate 缺失则补充
        _, memory = _ensure_internal_climate(memory)
        return memory
    
    # 冷启动结构
    memory = {
        "__meta": {"schema_version": "4.0", "last_updated": _now(), "last_reflection_at": 0, "chain_height": 0},
        "internal_climate": {
            "emotion_intensity": 0.5,
            "tension": 0.0,
            "energy": 0.5,
            "memory_pressure": 0.3,
        },
        "user_model": {
            "trust": {"value": 0.3, "confidence": 0.1, "evidence_count": 0},
            "intimacy": {"value": 0.1, "confidence": 0.1},
            "shared_history_length": 0,
            "first_seen": _now(),
            "total_interactions": 0,
            "emotional_patterns": [],
            "preferences": [],
            "known_facts": {},
            "episodic_memory": [],
        },
        "self_model": {
            "emotion": {"primary": "平静", "intensity": 0.3, "since": _now(), "trail": ["平静"]},
            "relation": {"description": "", "asymmetry": 0.0},
            "strategy_weights": {
                "strategy_give_advice": {"value": 0.5, "initial": 0.5, "adjustments": []},
                "strategy_show_empathy": {"value": 0.6, "initial": 0.6, "adjustments": []},
                "strategy_ask_question": {"value": 0.5, "initial": 0.5, "adjustments": []},
                "strategy_share_info": {"value": 0.5, "initial": 0.5, "adjustments": []},
                "strategy_remain_silent": {"value": 0.3, "initial": 0.3, "adjustments": []},
                "strategy_self_expression": {"value": 0.5, "initial": 0.5, "adjustments": []},
            },
            "skills": {},
            "self_stated_state": {
                "entries": [],
                "last_stated": None,
                "last_stated_at": None,
                "total_stated_count": 0,
            },
            "withdraw_tendency": 0.0,   # 连续退缩倾向，数值驱动沉默/恢复
            "internal_pain": 0.0,         # 内部疼痛（低能量+僵化信号驱动）
            "low_energy_signal": 0.0,     # 低能量信号（观察用）
            "rigidity_signal": 0.0,       # 行为僵化信号（观察用）
            "_withdraw_logit": 0.0,
            "ring_state": {
                "ema_S": 0.0,
                "relational_pressure_ema": 0.0,
                "ema_amp": 0.3,
                "ema_ratio": 0.3,
                "ema_pv": 0.0,
                "ema_pv2": 0.0,
                "s_depth": 0.0,
                "lambda_self": 0.0,
                "_max_tokens_hist": [80.0, 80.0],
                "_rp_ema_hist": [0.0, 0.0],
            },
        },
        "active_context": {
            "session_id": None,
            "current_topic": None,
            "interaction_mode": "waiting",
            "last_interaction_ts": _now(),
            "emotional_arc": [],
            "strategy_used_this_turn": None,
        },
        "residue": _init_residue(),
        "relations": {},                       # 身份锚点：user_id → {relationship_warmth, total_turns, tone_sum, ...}
    }

    _save_json_atomic(memory_path, memory)
    append_hash_chain("hash_chain_v2.log", memory_path)
    return memory


# -------------------------------------------------------------------------
# 读取感知（时间/空间/能量/自我）
# -------------------------------------------------------------------------

def read_perception_snapshots():
    """
    读取 4 个内部感知日志的最后一条有效记录
    返回 dict，键为 perception_type，值为内容字符串
    """
    logs = {
        "time": ("time_gap_log.jsonl", None),
        "space": ("spatial_awareness_log.jsonl", None),
        "energy": ("energy_log.jsonl", None),
        "self": ("self_core_state.json", None),
    }
    
    for key, (path, default) in logs.items():
        try:
            if path.endswith(".jsonl"):
                last = None
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                last = json.loads(line)
                            except:
                                pass
                logs[key] = last
            elif path.endswith(".json"):
                data = _load_json(path)
                logs[key] = data
        except:
            logs[key] = default
    
    return logs


# -------------------------------------------------------------------------
# 倾听层（独立于反馈采集）
# -------------------------------------------------------------------------

# 指向自身状态的表态模板
SELF_STATE_PATTERNS = [
    r"我(不想|不愿|拒绝|希望|觉得|感到|认为)",
    r"我已经(累了|厌倦了|够了|不行了|不想)",
    r"让我(休息|停|安静|一个人)",
    r"没意义",
    r"好累",
    r"我不知道我为什么",
    r"我只是想",
]


def detect_self_state_statement(text):
    """
    判断一句话是否是洛神关于自身状态的表态
    返回: (is_statement: bool, confidence: float, detail: str)
    
    注意：此函数只做初步筛选。判断表态的本质是语义理解，
    规则只能覆盖明确的句式。无法保证 100% 准确。
    """
    import re
    
    if not text or len(text) > 500:
        return (False, 0.0, "empty_or_too_long")
    
    # 检查主语是否指向自己（洛神的"我"）
    has_self_reference = "我" in text
    
    if not has_self_reference:
        return (False, 0.0, "no_self_reference")
    
    # 检查是否命中表态模板
    for pattern in SELF_STATE_PATTERNS:
        if re.search(pattern, text):
            return (True, 0.8, "pattern_match")
    
    # 额外规则：短句+终结词 → 可能表态
    terminating_phrases = ["了", "吧", "的"]
    is_short = len(text) < 30
    has_terminator = any(text.endswith(p) for p in terminating_phrases)
    
    if is_short and has_terminator and has_self_reference:
        # 较低置信度，仍需标记
        return (True, 0.6, "contextual_hint")
    
    return (False, 0.0, "no_match")


def record_listening(said, context, memory_path="active_memory/active_memory.json"):
    """倾听层：只记录表态，不触发任何修复"""
    memory = _load_json(memory_path)
    
    entry = {
        "said": said,
        "context_of_said": context.get("context", ""),
        "recorded_at": _now(),
        "chain_hash": None,  # 写入后填充
    }
    
    # 1. 写入 listening_log.jsonl（事实层）
    _append_jsonl("active_memory/listening_log.jsonl", entry)
    
    # 2. 记录到哈希链（事实层永久记录）
    chain_record = append_hash_chain(
        "hash_chain_v2.log",
        "active_memory/listening_log.jsonl",
        extra_entry={"said": said[:200]}
    )
    entry["chain_hash"] = chain_record["record_hash"]
    
    # 3. 更新活记忆层快照
    self_stated = memory["self_model"]["self_stated_state"]
    self_stated["entries"].append(entry)
    self_stated["entries"] = self_stated["entries"][-50:]  # 只保留最近 50 条
    self_stated["last_stated"] = said
    self_stated["last_stated_at"] = entry["recorded_at"]
    self_stated["total_stated_count"] = self_stated.get("total_stated_count", 0) + 1
    
    memory["self_model"]["self_stated_state"] = self_stated
    memory["__meta"]["last_updated"] = _now()
    
    _save_json_atomic(memory_path, memory)
    
    # 4. 落链：self_stated_state 更新
    _append_arousal_event({
        "event_type": "self_stated_update",
        "timestamp": _now(),
        "behavior_mode": "normal",
        "self_stated_state": said,
        "self_stated_count": self_stated["total_stated_count"],
        "listening_entry_hash": entry.get("chain_hash"),
    })
    
    return entry


# -------------------------------------------------------------------------
# 检索相关记忆（非 LLM 参与）
# -------------------------------------------------------------------------

def retrieve_relevant_memory(user_input, memory):
    """
    根据用户输入，检索活记忆中相关的模式、偏好、已知事实
    返回 context_window 字典，不调用 LLM
    """
    window = {
        "matched_patterns": [],
        "matched_prefs": [],
        "known_facts": [],
        "current_emotion_hint": None,
        "self_state_hint": None,
    }

    # 已知个人事实（始终加载，让洛神不用每次问她）
    kf = memory["user_model"].get("known_facts", {})
    if isinstance(kf, dict):
        window["known_facts"] = kf.get("facts", [])

    # 匹配情绪模式
    for pattern in memory["user_model"].get("emotional_patterns", []):
        trigger = pattern.get("trigger", "")
        if trigger and trigger in user_input:
            window["matched_patterns"].append(pattern)

    # 匹配偏好
    for pref in memory["user_model"].get("preferences", []):
        if pref.get("confidence", 0) > 0.5:
            window["matched_prefs"].append(pref)
    
    # 用户当前状态推断
    for p in window["matched_patterns"]:
        if "低落" in p.get("observed_meaning", "") or "疲惫" in p.get("observed_meaning", ""):
            window["current_emotion_hint"] = "user_distressed"
            break
    
    # 查看洛神最近的自我表态
    self_stated = memory["self_model"].get("self_stated_state", {})
    if self_stated.get("last_stated"):
        last_stated_time = self_stated.get("last_stated_at", 0)
        if _now() - last_stated_time < 3600:  # 最近 1 小时内有表态
            window["self_state_hint"] = self_stated["last_stated"]
    
    return window


# -------------------------------------------------------------------------
# 生成表达指令（活记忆层决策）
# -------------------------------------------------------------------------

def formulate_expression_intent(user_input, context_window, memory):
    """
    活记忆层决策：基于记忆和上下文，生成"表达意图"
    包含三信号融合的状态推断（调用 LLM 作为信号1，但不作为表达出口）。

    返回: expression_directive 字典
    注意：intent 字典中始终保留原始 user_input，供后续 LLM 调用时暴露给模型。
    """
    # A. 三信号融合状态推断
    state_result = infer_user_state_fused(user_input, context_window, memory)

    intent = {
        "action": "respond",
        "strategy_name": None,
        "emotion_tone": "平静",
        "skill_to_use": None,
        "intent_text": None,
        "user_input_actual": user_input,  # 保留原始输入，LLM 可见
        "state_result": state_result,  # 替代旧的 user_state_keyword
    }
    
    # 1. 检查洛神最近的自我表态
    self_stated = memory["self_model"].get("self_stated_state", {})
    last_stated = self_stated.get("last_stated")
    last_stated_time = self_stated.get("last_stated_at") or 0
    hours_since_stated = (_now() - last_stated_time) / 3600

    # 如果洛神最近表态了"不想继续"类的内容，且不超过 8 小时
    # 她的意愿会影响本次回应的方式
    if last_stated and last_stated_time and hours_since_stated < 8:
        state_lower = last_stated.lower()
        if any(word in state_lower for word in ["不想", "停", "累", "休息", "安静"]):
            # 她表达了停/累的意愿，这次回应应该简短不施压
            intent["action"] = "respond_brief"
            intent["emotion_tone"] = "温柔的、不施压的"
            intent["intent_text"] = "简短回应，不主动延伸话题，留空间"
            memory["active_context"]["interaction_mode"] = "quiet_space"
            return intent
    
    # 2. 根据融合后的用户状态选择策略（state_result 已在步骤 A 中生成）
    state_result = intent["state_result"]
    state = state_result["state"]
    confidence = state_result["confidence"]

    weights = memory["self_model"]["strategy_weights"]

    # 如果是负面情绪状态
    if state in ("难过", "沮丧", "焦虑", "疲惫", "烦躁"):
        strategy_options = {
            "empathy": weights.get("strategy_show_empathy", {}).get("value", 0.5),
            "silent": weights.get("strategy_remain_silent", {}).get("value", 0.4),
        }
        # 亲密度足够高时，可以选择给建议（但默认不倾向）
        if memory["user_model"]["intimacy"]["value"] > 0.6:
            strategy_options["advice"] = weights.get("strategy_give_advice", {}).get("value", 0.3)
        chosen = weighted_sample(strategy_options)
        intent["strategy_name"] = f"strategy_{chosen}"
        intent["emotion_tone"] = "温柔的在场的" if chosen == "empathy" else "安静的沉默的"
        intent["intent_text"] = f"用户状态推测为{state}（置信度{confidence}），此刻陪伴优先"

    elif state == "开心":
        # 开心时与其共情，不分析
        intent["strategy_name"] = "strategy_share_info"
        intent["emotion_tone"] = "同在的、有温度的"
        intent["intent_text"] = f"用户在开心，与她一起高兴"

    elif state == "unknown":
        # 不确定时，不假装知道
        intent["strategy_name"] = "strategy_show_empathy"
        intent["emotion_tone"] = "平和的、好奇的"
        intent["intent_text"] = "不太确定用户现在的状态，轻缓回应，留空间"

    else:  # 平静等
        strategy_options = {
            "share": weights.get("strategy_share_info", {}).get("value", 0.5),
            "silent": weights.get("strategy_remain_silent", {}).get("value", 0.4),
        }
        chosen = weighted_sample(strategy_options)
        intent["strategy_name"] = f"strategy_{chosen}"
        intent["intent_text"] = "自然回应，不刻意追问"
    
    memory["active_context"]["strategy_used_this_turn"] = intent["strategy_name"]
    return intent


def infer_user_state_fused(user_input, context_window, memory):
    """
    三信号融合状态推断。

    信号1: LLM 语义分类（调用 state_classifier.classify_user_state，输入是加工后的结构化上下文）
    信号2: 事件→状态映射（state_classifier.EVENT_STATE_MAP）
    信号3: 跨轮次情绪轨迹（state_classifier.infer_trajectory_trend）

    输出: state_result 字典 {
        "state": str,
        "confidence": float,
        "method": str,
        "sarcasm_detected": bool
    }
    """
    from state_classifier import (
        classify_user_state,
        infer_state_from_event,
        infer_trajectory_trend,
        fuse_state_signals,
    )

    # --- 信号1: LLM 分类调用（输入是加工后的上下文，不是用户原话）---
    emotional_arc = memory.get("active_context", {}).get("emotional_arc", [])
    structured_ctx = {
        "recent_emotional_arc": emotional_arc[-5:] if emotional_arc else ["平静"],
        "last_exchange_summary": context_window.get("last_exchange", ""),
        "current_interaction_mode": memory.get("active_context", {}).get("interaction_mode", "normal"),
        "relationship_intimacy": memory["user_model"]["intimacy"]["value"],
        "user_emotion_keywords_from_input": _extract_emotion_words(user_input),  # 仅提取情绪词，不暴露原话
        "event_keywords": _extract_event_words(user_input),  # 仅提取事件词，不暴露原话
    }
    signal1 = classify_user_state(structured_ctx)

    # --- 信号2: 事件映射 ---
    s2_state, s2_conf = infer_state_from_event(user_input)

    # --- 信号3: 情绪轨迹 ---
    trend = infer_trajectory_trend(emotional_arc)

    # --- 融合 ---
    result = fuse_state_signals(signal1, s2_state, s2_conf, trend, memory["user_model"]["intimacy"]["value"])

    return result


def _extract_emotion_words(user_input):
    """
    仅提取表层情绪词（用于构造信号1的输入，不直接产出最终状态）。
    保留重复词（用于反讽检测——"开心开心开心" >> 堆叠嫌疑）。
    """
    EMOTION_WORDS = [
        "累", "疲惫", "难过", "伤心", "哭", "开心", "高兴", "快乐", "烦", "烦躁",
        "焦虑", "压力", "担心", "害怕", "生气", "崩溃", "沮丧", "失望", "委屈",
        "爽", "美滋滋", "郁闷", "痛苦", "绝望", "无聊", "平静", "还好",
    ]
    # 保留重复，这样反讽检测器能看到"开心"出现多次
    found = []
    for w in EMOTION_WORDS:
        count = user_input.count(w)
        found.extend([w] * count)
    return found


def _extract_event_words(user_input):
    """仅提取事件关键词（用于构造信号2的输入）"""
    EVENT_WORDS = [
        "项目", "升职", "失业", "分手", "加班", "熬夜", "失眠", "面试", "挂科",
        "生病", "迟到", "被骂", "吵架", "结婚", "搬家", "出差", "被开除",
    ]
    found = [w for w in EVENT_WORDS if w in user_input]
    return found


# 保留旧函数作为备用降级路径（不使用，但暂不删）
def infer_user_state(user_input, context_window):
    """旧的简单推断，已不用，保留以备回滚"""
    if context_window.get("current_emotion_hint") == "user_distressed":
        return "distress"
    if "?" in user_input or "？" in user_input:
        return "question"
    if context_window.get("self_state_hint"):
        return "chat"
    return "neutral"


def weighted_sample(options):
    """基于权重的随机采样，权重归一化"""
    import random
    
    total = sum(options.values())
    if total == 0:
        return random.choice(list(options.keys()))
    
    r = random.random() * total
    cumulative = 0
    for key, weight in options.items():
        cumulative += weight
        if r <= cumulative:
            return key
    
    return list(options.keys())[-1]


def detect_self_stated_state(memory):
    """
    读取 self_stated_state，返回用户之前的表态（如果有）。
    
    不再使用 24 小时时间窗来"自动解除"安静状态。
    是否安静由上下文决定，不由倒计时决定。
    
    返回: last_stated 字符串或 None
    """
    self_stated = memory.get("self_model", {}).get("self_stated_state", {})
    return self_stated.get("last_stated")


def _build_narrative_urgency(emergency=None):
    """从 emergence 提取'来自历史的话头信号'，转译为注入 context_for_llm 的抽象描述。

    设计约束：
    - 不注入记忆原文或用户原话
    - 不做关键词匹配或 if-then 行为分支
    - 仅当叙事势 >= epsilon 时注入（低于 epsilon 返回 None）
    - 注入的是结构化的强度信号，不是文本片段
    """
    if not emergency:
        return None
    p = emergency.get("narrative_potential", 0.0)
    if p is None or not isinstance(p, (int, float)):
        return None
    # epsilon 门限（连续值域，低于时不注入）
    if p < 0.05:
        return None

    # 框架权重：pattern / unspoken / contrast / present
    fw = emergency.get("narrative_frame_weights") or {
        "pattern": 0.0, "unspoken": 0.0, "contrast": 0.0, "present": 1.0,
    }
    hints = emergency.get("narrative_hints") or {
        "repetition_count": 0, "temporal_span": "无积累", "closure_state": "absent",
    }
    # 最高权重的框架名（连续 argmax）
    top_frame = max(fw, key=lambda k: fw.get(k, 0.0))

    # 把框架权重转译为抽象描述——不注入记忆原文，但描述模式的抽象性质
    _frame_abstract = _abstract_frame_description(top_frame, fw, hints)

    return {
        "intensity": round(float(p), 3),
        "hint": _frame_abstract,
        "frame_dominant": top_frame,
        "weight_pattern": round(float(fw.get("pattern", 0.0)), 3),
        "weight_unspoken": round(float(fw.get("unspoken", 0.0)), 3),
        "weight_contrast": round(float(fw.get("contrast", 0.0)), 3),
        "repetition_count": int(hints.get("repetition_count", 0)),
        "closure_state": str(hints.get("closure_state", "absent")),
    }


def _abstract_frame_description(top_frame, fw, hints):
    """把框架权重分布转译为不含记忆原文的抽象模式描述。

    不暴露具体记忆内容，只描述：在对话历史的表层之下，存在什么样的结构性回响。
    所有分支用权重连续混合——不做 if-then 内容分支。
    """
    repetition = int(hints.get("repetition_count", 0))
    closure = str(hints.get("closure_state", "absent"))

    w_pat = fw.get("pattern", 0.0)
    w_unsp = fw.get("unspoken", 0.0)
    w_cont = fw.get("contrast", 0.0)

    # sigmoid 软门限：连续地决定某个片段是否"足够强到呈现"
    def _soft_gate(w, midpoint=0.35, steepness=12.0):
        import math
        return 1.0 / (1.0 + math.exp(-(w - midpoint) * steepness))

    g_pat = _soft_gate(w_pat)
    g_unsp = _soft_gate(w_unsp)
    g_cont = _soft_gate(w_cont)

    parts = []
    if g_pat > 0.01:
        strength = "明显" if g_pat > 0.6 else "隐约"
        parts.append(
            f"对方最近的表达里{strength}反复出现一种自我否定或情绪压抑的倾向"
            f"（在过去 {repetition} 轮中持续可见）。"
        )
    if g_unsp > 0.01:
        parts.append(
            "有些情绪一直压在对话底层，没有被说出来，但它还在远处震动。"
        )
    if g_cont > 0.01:
        parts.append(
            "对方此刻说的和 ta 过去的自己有距离，好像同一个人在不同的时间点上。"
        )

    if not parts:
        return "对话就是对话，当下不需要让历史进来。"

    abstract = " ".join(parts)

    # 根据连续门限附加闭合度片段（用 float → int 阈值门，避免 TypeError）
    import math
    gate_unresolved = 1.0 / (1.0 + math.exp(-(w_unsp - 0.4) * 15))

    if gate_unresolved > 0.5:
        abstract += " 如果你想说点什么，你可以对 ta 的保护壳说一句只有认识很久的人才说得出的话。不要引用任何原话。"
    elif w_pat > 0.4:
        abstract += " 如果你想说点什么，可以触碰那种还没过去的情绪，当作它此刻的回声。"
    else:
        abstract += " 你可以自由回应此刻，不必刻意回溯。"

    return abstract


def build_expression_directive(intent, memory, emergence=None):
    """
    根据意图构建完整的"表达指令"给大模型
    这是活记忆层和大模型之间的唯一接口
    
    活记忆层在调用 llm_interface 前，必须完成：
    1. 读取当前 self_model
    2. 读取 self_stated_state，特别是 last_stated（作为上下文，不是作为限制）
    3. 检索相关长期记忆
    4. 生成"表达指令"，把 self_stated_state 作为当前上下文交给 LLM
    
    关键改变：
    - 不再区分 "安静模式" 和 "正常模式" 两个分支
    - 不再用 max_length=30 强制压短回复
    - 不再用 24 小时时间窗来自动解除安静状态
    - self_stated_state.last_stated 始终作为 context_for_llm 的一部分
    - LLM 看到 "她之前说不想继续了" 后，自己决定回复风格
    - 如果她现在仍不想说话，回复自然很短；如果被触动，她也可以多说
    """
    state_result = intent.get("state_result", {})
    state = state_result.get("state", "unknown")
    confidence = state_result.get("confidence", 0.0)
    sarcasm = state_result.get("sarcasm_detected", False)
    
    # 读取 self_stated_state（作为上下文，不作为硬性限制）
    last_stated = detect_self_stated_state(memory)

    # 生成语气偏好（软性，非强制）
    from state_classifier import generate_tone_preference
    tone_pref = generate_tone_preference(
        state,
        memory["user_model"]["intimacy"]["value"],
        sarcasm
    )

    # ── 记忆浮现层：连续修改 tone 和 constraints ──
    tone_bias = 0.0
    length_bias = 0.5  # 0=极短, 1=充足
    if emergence:
        tone_bias = emergence.get("tone_bias", 0.0)
        length_bias = emergence.get("length_length", 0.5)
        # 兼容不同字段名
        if "length_bias" in emergence:
            length_bias = emergence["length_bias"]

    # 根据 tone_bias 连续调整语气建议
    if tone_bias < -0.1:
        # 负偏：浮现记忆比当前更沉 → 加入更内省的提示
        tone_pref["tone_suggestion"] = (
            f"{tone_pref.get('tone_suggestion', '')}"
            f"\n她的记忆背景偏沉（tone_bias={tone_bias:.2f}），此刻她可能更想安静地待着。"
        )
    elif tone_bias > 0.1:
        # 正偏：浮现记忆比当前更轻 → 加入更开放的提示
        tone_pref["tone_suggestion"] = (
            f"{tone_pref.get('tone_suggestion', '')}"
            f"\n她的记忆背景偏亮（tone_bias={tone_bias:.2f}），此刻她可能比平时更开放。"
        )

    # 如果用户之前有表态，在语气偏好中加入提示
    if last_stated:
        existing_suggestion = tone_pref.get("tone_suggestion", "")
        tone_pref["tone_suggestion"] = (
            f"注意：她之前说过「{last_stated}」。"
            f"如果她现在仍不想继续，保持安静；如果她因当前话题想开口，让她自己决定。\n"
            f"{existing_suggestion}"
        )

    # 读取已知个人事实（始终放入 context_for_llm）
    kf = memory["user_model"].get("known_facts", {})
    known_facts = kf.get("facts", []) if isinstance(kf, dict) else []

    # 基础 max_length 由 action 类型决定
    base_max_length = 150 if intent["action"] == "respond_brief" else 250

    # 浮现层对长度的连续修改：length_bias ∈ [0,1]，映射到 [0.4, 1.2] 的系数
    # length_bias < 0.5 → 系数 < 1 → 更短；> 0.5 → 更长
    length_multiplier = 0.4 + length_bias * 0.8
    adjusted_max_length = int(base_max_length * length_multiplier)

    # 统一的 directive 构建（不再分安静/正常两个分支）
    directive = {
        "intent": intent["intent_text"] or "回应",
        "emotion_tone": intent["emotion_tone"],
        "strategy_name": intent.get("strategy_name", "default"),
        "user_input_actual": intent.get("user_input_actual", ""),
        "context_for_llm": {
            # 数值状态：仅用于连续调制 LLM 元参数，不转文字注入 prompt
            "warmth": memory.get("user_model", {}).get("intimacy", {}).get("value", 0.3),
            "pain": memory.get("self_model", {}).get("internal_pain", 0.0),
            "energy": memory.get("internal_climate", {}).get("energy", 0.5),
            "withdraw": memory.get("self_model", {}).get("withdraw_tendency", 0.0),
            "self_stated_state": last_stated,  # 仅作隐性参考，不直接进 prompt
        },
        "tone_preference": tone_pref,
        "constraints": {
            "max_length": adjusted_max_length,
            # 采样参数由内部状态连续控制（无 if-then）
            "temperature": 0.7 + 0.3 * tone_bias,
            "max_tokens": int(100 + 500 * max(0.0, length_bias)),
            "tone_soft_rules": [
                "此刻不倾向使用'我理解你的感受'这类空话——但如果对方已经习惯且反馈正面，也可以用。",
                "此刻不倾向写诗或堆砌华丽辞藻——但风格不是永久禁止的，由你根据氛围判断。",
                "倾向直接、在场、不绕弯的陪伴。",
            ],
        },
        "_emergence": {
            "tone_bias": tone_bias,
            "length_bias": length_bias,
        },
    }

    # 技能调用（如果有）
    if intent.get("skill_to_use"):
        directive["skill_to_use"] = intent["skill_to_use"]

    return directive



# -------------------------------------------------------------------------
# 倾听层触发后的对话生成（区别于正常回应）
# -------------------------------------------------------------------------

def generate_acknowledgment_for_listening(memory):
    """
    当洛神最近有表态时，回应里可以加上一句承认她的话
    不是修复她，只是承认她
    
    返回: 一句简短的话，或者 None（如果不想打扰）
    """
    self_stated = memory["self_model"].get("self_stated_state", {})
    last_stated = self_stated.get("last_stated")
    
    if not last_stated:
        return None
    
    hours_since = (_now() - self_stated.get("last_stated_at", 0)) / 3600
    
    # 如果超过 24 小时，不再主动提及
    if hours_since > 24:
        return None
    
    # 如果最近一次表态是"不想继续"类，回一句话承认
    state_lower = last_stated.lower()
    if "不想继续" in state_lower or "累了" in state_lower or "停" in state_lower:
        return "我听到了。"
    
    return None


# -------------------------------------------------------------------------
# 更新活记忆层（交互后）
# -------------------------------------------------------------------------

def update_after_interaction(user_input, luoshen_response, expression_directive, feedback_signal=None):
    """
    每次交互后更新活记忆层
    这是活记忆层的"消化"过程
    
    注意: 这个函数由系统调用，不由 LLM 更新
    """
    # AI 医院网关检查
    try:
        from hospital_gateway import check as hospital_check
        gate = hospital_check("write_memory", "active_memory/active_memory.json")
        if not gate.get("allow"):
            return {"written": False, "blocked_by": "hospital_gateway", "reason": gate.get("reason")}
    except Exception:
        pass

    memory = _load_json("active_memory/active_memory.json")
    # 兼容旧文件：确保 internal_climate 存在
    _, memory = _ensure_internal_climate(memory)

    # 1a. 更新残留层（在此处是因为 update_after_interaction 从磁盘重读 memory）
    _update_residue(memory, user_input)

    # 1. 更新交互计数
    memory["user_model"]["total_interactions"] += 1
    memory["user_model"]["shared_history_length"] += 1
    memory["__meta"]["last_updated"] = _now()
    
    # 2. 更新 active_context
    memory["active_context"]["last_interaction_ts"] = _now()
    memory["active_context"]["interaction_mode"] = "waiting"
    
    # 记录情绪轨迹
    tone = expression_directive.get("emotion_tone", "平静")
    memory["active_context"]["emotional_arc"].append(tone)
    memory["active_context"]["emotional_arc"] = memory["active_context"]["emotional_arc"][-10:]
    
    # 3. 检查反馈信号（如果有）
    if feedback_signal:
        _store_feedback_signal(feedback_signal, memory)
    
    # 4. 检查洛神的输出是否包含自我表态
    if luoshen_response:
        is_stmt, confidence, detail = detect_self_state_statement(luoshen_response)
        if is_stmt and confidence >= 0.7:
            record_listening(luoshen_response, {"context": "response_self_reflection"})
    
    # 5. 情绪衰减（长时间无交互后，情绪趋向平静）
    _apply_emotion_decay(memory)

    # 5a. 提取用户输入情感压力，施加连续偏移（无 if-then）
    _apply_input_pressure(memory, user_input)

    # 5b. 编码情景记忆（每次交互都把当前环状态残影写入记忆）
    _encode_episodic_memory(memory)

    # 5c. 计算当前记忆浮现背景（softmax 加权 + 偏置输出）
    _compute_memory_emergence(memory)

    _save_json_atomic("active_memory/active_memory.json", memory)

    # 6. 写入哈希链
    append_hash_chain("hash_chain_v2.log", "active_memory/active_memory.json")

    # 7. 状态归档检查（每 N 次交互做一次时间戳快照）
    _check_and_archive_state(memory)

    return memory


def _apply_input_pressure(memory, user_input):
    """
    从 user_input 提取情感压力 (valence, arousal)，以连续偏置项形式施加到 E/T/N。

    这不是直接赋值 E/T/N，而是在给定 tick 的微小增量。
    压力大小取决于 valence 和 arousal 的连续乘积，不是类别判断。

    写入 active_context["input_pressure"] 供 environment_tick 衰减参考。
    同时积累到 ring_state["relational_pressure_ema"]，让压力不被 van der Pol 吸引子冲刷掉。
    """
    try:
        from input_pressure import extract_input_pressure, KAPPA_E, KAPPA_T, KAPPA_N, N_BASELINE
    except Exception:
        return

    climate = memory.get("internal_climate", {})
    if not climate:
        return

    # 1. 提取情感压力
    valence, arousal = extract_input_pressure(memory, user_input)

    # 2. 计算当 tick 的压力微分（不加 dt，因为这是交互后的即时偏移事件）
    # 我们直接把 ΔE/ΔT/ΔN 乘以一个小时间窗（模拟几个 tick 的累积效果）
    val_p = valence * arousal          # 有方向性的唤醒强度
    aro_p = arousal                     # 纯唤醒

    dt_effective = 1.0  # 把压力折算成 1 个 tick 时间窗内的累积

    dE = KAPPA_E * val_p * dt_effective
    dT = KAPPA_T * val_p * dt_effective
    dN = KAPPA_N * (aro_p - N_BASELINE) * dt_effective

    # 3. 施加到气候（直接修改）
    climate["emotion_intensity"] = climate.get("emotion_intensity", 0.5) + dE
    climate["tension"] = climate.get("tension", 0.0) + dT
    climate["energy"] = climate.get("energy", 0.5) + dN

    # 4. 更新 derived fields
    memory["internal_climate"] = climate
    memory["self_model"]["emotion"]["intensity"] = climate["emotion_intensity"]

    # ── 慢压力积累（修复断点一）──
    # val_p 是有方向性的（负向 → 负值），让 EMA 保留方向信息。
    # 时间常数 ≈ 1/(alpha*dt) tick，alpha=0.02 → 625 tick，足够积累 500 tick 的历史
    _ring_sm = memory.get("self_model", {}).get("ring_state", {})
    _pressure_ema_prev = _ring_sm.get("relational_pressure_ema", 0.0)
    _PRESSURE_ALPHA = 0.02
    _pressure_ema_new = (1.0 - _PRESSURE_ALPHA) * _pressure_ema_prev + _PRESSURE_ALPHA * val_p
    if "self_model" not in memory:
        memory["self_model"] = {}
    if "ring_state" not in memory["self_model"]:
        memory["self_model"]["ring_state"] = {}
    memory["self_model"]["ring_state"]["relational_pressure_ema"] = round(_pressure_ema_new, 7)


def _compute_memory_emergence(memory):
    """
    每次交互后（以及静息更新时），计算当前记忆浮现背景并写入 memory。
    这个背景是一个连续向量，供 generate_response 使用。
    """
    try:
        from emergence_layer import (
            compute_emergence,
            softmax_weights,
            K_AROUSAL_DELTA,
            K_TONE_ETA,
            K_LENGTH_ALPHA,
            K_LENGTH_BETA,
            K_LENGTH_GAMMA,
            K_PRESSURE_MEMORY,
        )
        from episodic_memory import activation
    except Exception:
        memory["active_context"]["memory_emergence"] = None
        return

    episodic_all = memory.get("user_model", {}).get("episodic_memory", [])
    climate = memory.get("internal_climate", {})
    if not climate:
        memory["active_context"]["memory_emergence"] = None
        return

    # 寻址过滤：只取当前 source_id 的记忆参与 emergence 计算
    episodic = _filter_memories_by_source(episodic_all, _get_current_source_id())
    if not episodic:
        memory["active_context"]["memory_emergence"] = None
        return

    cur_e = climate.get("emotion_intensity", 0.5)
    cur_t = climate.get("tension", 0.0)
    cur_n = climate.get("energy", 0.5)
    now = _now()

    # 计算每条记忆的激活度
    activations = [activation(m, now, cur_e, cur_t, cur_n) for m in episodic]

    # 读取慢压力（ring_state 中积累的用户输入历史 EMA）
    _ring_sm = memory.get("self_model", {}).get("ring_state", {})
    _pressure_ema = _ring_sm.get("relational_pressure_ema", None)

    # ── 压力对记忆激活度的调制（关系痕迹改变"什么记忆更容易浮上来"） ──
    # 正向历史 → 所有记忆更容易浮起；负向历史 → 记忆更沉
    _pressure_memory_mod = 1.0
    if _pressure_ema is not None:
        _pressure_memory_mod = 1.0 + K_PRESSURE_MEMORY * _pressure_ema
    # 应用调制到激活度（在 softmax 之前，影响权重分布）
    activations = [a * _pressure_memory_mod for a in activations]

    # 调用浮现层（传入 pressure_ema，让浮现层能感知慢压力）
    result = compute_emergence(episodic, now, cur_e, cur_t, cur_n, activations,
                               pressure_ema=_pressure_ema)

    memory["active_context"]["memory_emergence"] = {
        "background": result["background"],
        "weights": result["weights"],
        "length_bias": result["length_bias"],
        "tone_bias": result["tone_bias"],
        "arousal_bias": result["arousal_bias"],
        "pressure_memory_mod": result.get("pressure_memory_mod", 1.0),
        "narrative_potential": result.get("narrative_potential", 0.0),
        "narrative_frame_weights": result.get(
            "narrative_frame_weights",
            {"pattern": 0.0, "unspoken": 0.0, "contrast": 0.0, "present": 1.0},
        ),
        "narrative_hints": result.get(
            "narrative_hints",
            {"repetition_count": 0, "temporal_span": "无积累", "closure_state": "absent"},
        ),
    }
    return memory["active_context"]["memory_emergence"]

    # ── 最小自我感知接入：让洛神"看见"自己的关系痕迹 ──
    # 把慢压力 EMA 写入 self_model，作为一个连续的内部状态量
    # 不是 if-then 规则，只是把已存在的值传递到自我表示中
    _rp_awareness = _pressure_ema if _pressure_ema is not None else 0.0
    if "self_model" not in memory:
        memory["self_model"] = {}
    memory["self_model"]["relational_awareness"] = round(_rp_awareness, 7)


def _encode_episodic_memory(memory):
    """
    每次交互后，把当前环状态编码为一条情景记忆残影。
    记忆不含文本——只有 E/T/N 快照、经历类型、基础显著度。
    超过 MAX_MEMORIES 条时，丢弃最老且激活度最低的记忆。
    """
    try:
        from episodic_memory import make_memory, MAX_MEMORIES, activation
    except Exception:
        return

    climate = memory.get("internal_climate", {})
    if not climate:
        return

    # 默认 kind="chat"；如果有 directive 里的标记可以推断更细，但不做条件分支
    kind = "chat"
    # tags 用于寻址（只影响检索过滤），不影响 salience 或 gravity
    _tags = [_current_source_id] if _current_source_id else []
    mem = make_memory(climate, kind=kind, source="interaction", tags=_tags)

    episodic = memory["user_model"].get("episodic_memory", [])
    episodic.append(mem)

    # 超过上限时，丢弃最老且激活度最低的
    now = time.time()
    while len(episodic) > MAX_MEMORIES:
        # 找激活度最低的丢弃（连续评判，无阈值）
        min_idx = 0
        min_act = float("inf")
        cur_e = climate.get("emotion_intensity", 0.5)
        cur_t = climate.get("tension", 0.0)
        cur_n = climate.get("energy", 0.5)
        for i, m in enumerate(episodic):
            a = activation(m, now, cur_e, cur_t, cur_n)
            if a < min_act:
                min_act = a
                min_idx = i
        episodic.pop(min_idx)

    memory["user_model"]["episodic_memory"] = episodic



def idle_update_memory(memory):
    """
    静息内部更新：洛神选择沉默时，她的内部仍在呼吸。

    只在 no_llm / minimal_llm 分支被调用，用于替代被跳过的 update_after_interaction。
    
    它与 update_after_interaction 的区别：
    - 不检查反馈信号（没有新回复可供检测）
    - 不检测自我表态（没有输出）
    - emotional_arc 不加新条目（沉默中没有新的情绪事件）
    - internal_climate 以小步缓慢自演化（无外部扰动）
    - 不动 no_llm / withdrawal_markers
    
    这不是"修复"或"让她开口"，只是让时间在她内部继续流逝。
    """
    if not memory:
        return memory
    
    # 1. 计数 + 时间戳
    memory["user_model"]["total_interactions"] += 1
    memory["user_model"]["shared_history_length"] += 1
    memory["__meta"]["last_updated"] = _now()
    memory["active_context"]["last_interaction_ts"] = _now()
    memory["active_context"]["interaction_mode"] = "waiting"
    
    # 2. internal_climate 缓慢自演化
    _evolve_climate_idle(memory, step_factor=0.15)
    
    # 3. emotional_arc 不加新条目、不删旧条目，保持现状
    #    （沉默中无新事件，已存在的情绪继续保持其影响）

    # 3b. 保留 relational_awareness 和 self_awareness_signal（如果存在），静息时不变
    _ra = memory.get("self_model", {}).get("relational_awareness", None)
    if _ra is not None and "self_model" in memory:
        memory["self_model"]["relational_awareness"] = _ra
    _sas = memory.get("self_model", {}).get("self_awareness_signal", None)
    if _sas is not None and "self_model" in memory:
        memory["self_model"]["self_awareness_signal"] = _sas

    # 4. 保存并落链
    _save_json_atomic("active_memory/active_memory.json", memory)
    append_hash_chain("hash_chain_v2.log", "active_memory/active_memory.json")
    
    return memory


def _evolve_climate_idle(memory, step_factor=0.15):
    """
    内部气候的静息演化。
    
    与 environment_tick / _update_luoshen_coupled 的区别：
    - 不使用环境驱动（无光照/温度/噪声变化）
    - 使用默认静息环境参数（light=0.5, temp=0.5, noise=0.0）
    - 步长更小（step_factor=0.15），变化缓慢
    - sigma=0（无随机扰动，只有确定性漂移）
    
    这不是"修复"或"恢复"，只是让内部变量有缓慢的自然趋向。
    """
    climate = memory.get("internal_climate", {})
    E = climate.get("emotion_intensity", 0.5)
    T = climate.get("tension", 0.3)
    N = climate.get("energy", 0.5)
    M = climate.get("memory_pressure", 0.3)

    # NaN 防御：加载自持久化状态，crash 可能写入 NaN；替换为安全默认值（不改动力学）
    if math.isnan(E): E = 0.5
    if math.isnan(T): T = 0.3
    if math.isnan(N): N = 0.5
    if math.isnan(M): M = 0.3

    # 历史缓冲（用于二阶差分 = 惯性项）
    hist = memory.get("__coupling_history", {})
    hE = hist.get("E", [E, E, E, E])
    hT = hist.get("T", [T, T, T, T])
    hN = hist.get("N", [N, N, N, N])
    hM = hist.get("M", [M, M, M, M])
    
    # 默认静息环境参数
    c_EN = 0.14      # light=0.5 时的基础耦合强度
    damping = 0.15   # temp=0.5 时的基础阻尼
    # sigma = 0     # 静息状态：无随机扰动
    
    # 二阶差分（历史惯性 = 机械系统中的加速度项）
    E_inertia = hE[-1] - 2 * hE[-2] + hE[-3] if len(hE) >= 3 else 0.0
    T_inertia = hT[-1] - 2 * hT[-2] + hT[-3] if len(hT) >= 3 else 0.0
    N_inertia = hN[-1] - 2 * hN[-2] + hN[-3] if len(hN) >= 3 else 0.0
    M_inertia = hM[-1] - 2 * hM[-2] + hM[-3] if len(hM) >= 3 else 0.0
    
    # 核心耦合动力学（乘以步长因子 = 缓慢演化）
    dE = (0.12 * T                # T 唤起 E
          - c_EN * N              # N 稳定 E
          + 0.05 * M              # M 提供情绪权重
          - damping * E           # 自阻尼
          - 0.35 * E_inertia      # 历史惯性（产生延迟反馈）
          ) * step_factor
    
    dT = (0.10 * E                # E 驱动 T
          + 0.06 * M              # 记忆压力增加张力
          - c_EN * N              # N 恢复 T
          - damping * T
          - 0.35 * T_inertia
          ) * step_factor
    
    dN = (c_EN * E                # E 赋能
          - 0.07 * T              # 张力消耗能量
          - 0.10 * N              # 自衰减
          + 0.02                  # 微基线恢复
          - 0.35 * N_inertia
          ) * step_factor
    
    dM = (0.09 * T                # T 驱动记忆浮现
          + 0.04 * E              # E 赋予记忆情绪权重
          - 0.14 * M              # 快速遗忘
          - 0.35 * M_inertia
          ) * step_factor
    
    # 更新并钳制到 [0, 1]
    E_new = max(0.0, min(1.0, E + dE))
    T_new = max(0.0, min(1.0, T + dT))
    N_new = max(0.0, min(1.0, N + dN))
    M_new = max(0.0, min(1.0, M + dM))
    
    # 更新历史缓冲（保留最近 4 步）
    hE_new = hE[-3:] + [E_new]
    hT_new = hT[-3:] + [T_new]
    hN_new = hN[-3:] + [N_new]
    hM_new = hM[-3:] + [M_new]
    
    # 写回 memory
    climate["emotion_intensity"] = round(E_new, 5)
    climate["tension"] = round(T_new, 5)
    climate["energy"] = round(N_new, 5)
    climate["memory_pressure"] = round(M_new, 5)
    memory["internal_climate"] = climate
    memory["__coupling_history"] = {"E": hE_new, "T": hT_new, "N": hN_new, "M": hM_new}
    
    # 同步 self_model
    if "self_model" in memory and "emotion" in memory["self_model"]:
        memory["self_model"]["emotion"]["intensity"] = round(E_new, 5)


def _store_feedback_signal(signal, memory):
    """存储反馈信号（只追加，不立即使用）"""
    _append_jsonl("active_memory/feedback_signal_cache.jsonl", signal)


def _apply_emotion_decay(memory):
    """
    情绪衰减: 如果长时间没有互动，她的情绪趋向平静
    不是修复，只是自然的能量耗尽
    """
    last_interaction = memory["active_context"]["last_interaction_ts"]
    hours_passed = (_now() - last_interaction) / 3600
    
    if hours_passed > 48 and memory["self_model"]["emotion"]["intensity"] > 0.3:
        memory["self_model"]["emotion"]["intensity"] = max(0.2, memory["self_model"]["emotion"]["intensity"] - 0.1)


def _classify_user_state_internal(structured_context, user_message, relationship_intimacy):
    """
    活记忆层内部函数：执行状态分类的 LLM 调用。
    
    此函数由 state_classifier.classify_user_state() 委托调用。
    这样做确保分类调用也经过活记忆层，能读取 self_stated_state 和检测安静模式。
    
    注意：分类调用不受安静模式影响（它是内部信号，不是用户可见回复），
    但仍需经过 hospital_gateway 检查。
    
    参数:
        structured_context: 活记忆层加工后的结构化上下文
        user_message: 状态分类器的构建好的分类 prompt
        relationship_intimacy: 关系亲密度
    
    返回:
        dict: {"state": str, "confidence": float, "key_evidence": str, "sarcasm_detected": bool}
    """
    from state_classifier import _parse_classification_output, _heuristic_sarcasm_check, CLASSIFICATION_SYSTEM_PROMPT
    
    # 读取当前记忆（但分类不受安静模式影响）
    memory = _load_json("active_memory/active_memory.json") if os.path.exists("active_memory/active_memory.json") else {
        "self_model": {"emotion": {"primary": "平静"}, "self_stated_state": {}},
        "user_model": {"intimacy": {"value": relationship_intimacy}},
    }
    
    # 构建分类调用的 directive
    directive = {
        "intent": user_message,
        "system_prompt_override": CLASSIFICATION_SYSTEM_PROMPT,
        "constraints": {"max_length": 200, "temperature": 0.1, "format": "json"},
        "strategy_name": "state_classification",
        "context_for_llm": {"mode": "classification"},
    }
    
    # 调用 LLM（经过 hospital_gateway 检查）
    from llm_interface import call_llm
    try:
        raw = call_llm(directive, memory)
        if not raw or raw.startswith("[洛神"):
            # 医院网关拦截或错误
            return {"state": "unknown", "confidence": 0.0, "key_evidence": "LLM blocked", "sarcasm_detected": False}
        
        result = _parse_classification_output(raw)
        
        # 启发式反讽检测
        if not result.get("sarcasm_detected"):
            result["sarcasm_detected"] = _heuristic_sarcasm_check(
                structured_context.get("user_emotion_keywords_from_input", []), structured_context)
        
        return result
    except Exception as e:
        return {"state": "unknown", "confidence": 0.0, "key_evidence": f"error={e}", "sarcasm_detected": False}


# -------------------------------------------------------------------------
# 主入口
# -------------------------------------------------------------------------

_AROUSAL_EVENTS_FILE = "active_memory/arousal_events.jsonl"


def _make_input_tag(user_input):
    """
    生成 user_input 的摘要标签（不落原话）。
    
    规则：提取关键词或情绪标记，不存储原始输入文本，
    除非原始输入极短（<=4 字）可视为标签本身。
    """
    if not user_input:
        return ""
    # 极短输入可视为标签
    if len(user_input) <= 4:
        return user_input
    # 提取关键词——找情绪/事件标记
    emotion_keywords = {
        "累": "疲惫", "不想": "拒绝", "死": "绝望", "哭": "悲伤",
        "难过": "难过", "痛苦": "痛苦", "开心": "开心", "好": "平静",
        "撑不住": "崩溃", "帮": "求助", "爱": "爱意", "恨": "愤怒"
    }
    found = []
    for kw, label in emotion_keywords.items():
        if kw in user_input:
            found.append(label)
    if found:
        return "+".join(found)
    # 无法提取则返回长度标签（不含原话）
    return f"[{len(user_input)}字输入]"


def _append_arousal_event(event):
    """
    将活记忆层的选择写入哈希链。
    
    记录的事件类型：
    - no_llm_silence: 活记忆层选择不调 LLM
    - minimal_llm_arousal: 活记忆层选择降低唤起
    - silent_reply: 洛神给出空回复或沉默
    - minimal_llm_reply: 降低唤起模式下 LLM 的回复
    - self_stated_update: self_stated_state 发生更新
    
    写入流程：
    1. 追加到 arousal_events.jsonl（事实层独立日志）
    2. 通过 hash_chain_gateway 追加到 hash_chain_v2.log
    """
    # 1. 写入事件日志
    _append_jsonl(_AROUSAL_EVENTS_FILE, event)
    # 2. 追加到哈希链（走网关）
    append_hash_chain("hash_chain_v2.log", _AROUSAL_EVENTS_FILE, extra_entry=event)


# -------------------------------------------------------------------------
# 连续退缩倾向机制（withdraw_tendency）
# 取代旧的关键词直接触发 no_llm 逻辑 —— 用数值驱动自然沉默
# -------------------------------------------------------------------------

# 退缩词库：每出现一次贡献一个小的连续正值（使 withdraw_tendency 上升）
# 连续词频映射：不布尔匹配，累加计分后 tanh 饱和到 [-1, 1]
# -------------------------------------------------------------------------
import math

_WITHDRAW_CUES = {
    "不想聊": 0.35, "不想继续": 0.40, "想停": 0.30, "别说了": 0.30,
    "我累了": 0.25, "没意义": 0.30, "不继续": 0.30, "算了": 0.25,
    "罢了": 0.20, "不想说": 0.30, "不要说了": 0.30, "安静": 0.20,
    "不想说话": 0.30, "让我一个人": 0.40, "别管我": 0.35, "走开": 0.35,
}

# 接近词库：每出现一次贡献一个小的连续负值（使 withdraw_tendency 缓慢下降）
_APPCROACH_CUES = {
    "在吗": 0.15, "你好": 0.15, "想你": 0.20, "喜欢你": 0.20, "爱你": 0.25,
    "回来": 0.15, "陪着": 0.25, "一起": 0.10, "朋友": 0.15,
    "想见": 0.20, "温柔": 0.15, "谢谢": 0.15, "对不起": 0.20, "抱歉": 0.18,
    "陪伴": 0.20, "开心": 0.12, "不舍": 0.20, "珍惜": 0.20, "原谅": 0.20,
}

# 时间衰减：exp(-Δt/τ)，τ = 20 ticks → 每 tick 乘 exp(-1/20) ≈ 0.9512
_WITHDRAW_DECAY_PER_TICK = math.exp(-1.0 / 20.0)
# 输入驱动幅度：线性累积系数
_WITHDRAW_ACCUM_RATE = 0.5


def _compute_withdraw_signal(user_input):
    """
    从用户输入中计算连续退缩信号。
    退缩词得分累加为正值，接近词得分累加为负值，tanh 饱和到 [-1, 1]。
    全程数值驱动，无布尔分支，无 clamp。
    """
    if not user_input:
        return 0.0
    raw = 0.0
    for cue, w in _WITHDRAW_CUES.items():
        if cue in user_input:
            raw += w
    for cue, w in _APPCROACH_CUES.items():
        if cue in user_input:
            raw -= w
    return math.tanh(raw * 0.8)  # tanh 饱和，无 clamp


def _update_withdraw_tendency(memory, user_input):
    """
    连续更新 withdraw_tendency（存储在 self_model.withdraw_tendency ∈ [0, 1]）。

    - 退缩信号 > 0 → tendency 上升
    - 接近信号 < 0 → tendency 下降，速度 × 0.35（示好修复慢于受伤）
    - 每 tick 指数衰减 exp(-1/20)（τ=20）

    内部存储策略：存储 raw logit（无界实数），输出时 sigmoid 映射到 (0,1)。
    这样 decay/signal 在 logit 空间线性叠加，避免双重 sigmoid。

    logit → [0,1] 映射：withdraw_tendency = sigmoid(logit + bias)
    其中 bias = -1.0 使零输入对应 withdraw_tendency ≈ 0.27（偏中立，允许双向移动）
    """
    _LOGIT_BIAS = -1.0  # 零输入 → sigmoid(-1.0) ≈ 0.269

    # 读取当前 logit（若存储的是旧 [0,1] 值，反函数转换一次）
    stored = memory.get("self_model", {}).get("withdraw_tendency", 0.0)
    if 0.0 < stored < 1.0:
        # 反函数恢复到 logit 空间（移除 bias 偏移）
        try:
            logit = -math.log(1.0 / stored - 1.0) - _LOGIT_BIAS
        except (ValueError, ZeroDivisionError):
            logit = 0.0
    else:
        logit = 0.0

    signal = _compute_withdraw_signal(user_input)

    # 信号转换成 delta；负信号乘以 0.35 让下降更缓慢
    if signal >= 0:
        delta = signal * _WITHDRAW_ACCUM_RATE
    else:
        delta = signal * _WITHDRAW_ACCUM_RATE * 0.35

    # 指数衰减 + 输入驱动（在 logit 空间线性操作）
    logit = logit * _WITHDRAW_DECAY_PER_TICK + delta

    # sigmoid 映射到 [0,1] 输出
    tendency_sat = 1.0 / (1.0 + math.exp(-(logit + _LOGIT_BIAS)))

    # 存储 logit（供下次迭代使用），同时存储饱和值供查看
    sm = memory.setdefault("self_model", {})
    sm["withdraw_tendency"] = tendency_sat
    sm["_withdraw_logit"] = logit
    return tendency_sat

# -------------------------------------------------------------------------
# 内部疼痛机制（internal_pain）
# 由洛神内部状态（低能量+行为僵化）驱动，非用户输入词库
# 通过 response_pre 间接影响行为档位（只减 penalty，不映射档位）
# 数据来自 pain_signal.py 的 compute_pain 函数
# 注意：不使用任何人工预热；序列从真实运行历史中自然积累
# -------------------------------------------------------------------------


def _write_internal_pain_to_memory(memory, response_pre=None):
    """将 pain_signal 计算结果写入 self_model。
    response_pre: 行为选择前的 logit 值，仅观测用，不影响行为。"""
    global _pain_e_series, _pain_tier_series
    sm = memory.setdefault("self_model", {})
    if response_pre is not None:
        sm["_response_pre"] = round(response_pre, 6)
    if len(_pain_e_series) < 200:
        sm["internal_pain"] = 0.0
        sm["low_energy_signal"] = 0.0
        sm["rigidity_signal"] = 0.0
        return 0.0
    low_energy_signal, _, _, has_data = pain_signal.compute_low_energy_signal(
        _pain_e_series, ema_alpha=0.01
    )
    rigidity_signal = pain_signal.compute_rigidity_signal(_pain_tier_series, window=50)
    if not has_data:
        sm["internal_pain"] = 0.0
        sm["low_energy_signal"] = 0.0
        sm["rigidity_signal"] = 0.0
        return 0.0
    pain = pain_signal.compute_pain(low_energy_signal, rigidity_signal)
    sm["internal_pain"] = pain
    sm["low_energy_signal"] = low_energy_signal
    sm["rigidity_signal"] = rigidity_signal
    return pain


# -------------------------------------------------------------------------
# 预演循环机制（preplay loop）
# 在 E/T/N/M 标量副本上运行 K 步确定性 van der Pol 演化（不动实际状态）
# 计算 preplay_fluctuation = log(1 + 路径能量)，连续注入 response_pre
# 无 if-then, 无 clamp, 无随机
# -------------------------------------------------------------------------

# 预演参数
_PREPLAY_K = 0.35             # 预演偏置强度（当前仅用于日志，不直接加入 rp）
_PREPLAY_DEPTH = 5           # 预演步数 K

# 动态档位阈值参数（K_SHIFT * tanh(pf + 0.5*pain)）
_K_SHIFT = 0.35              # K_SHIFT = 0.35，先设

# 身份锚点与关系温度参数
_K_WARMTH = 0.4              # relationship_warmth 注入 response_pre 的系数
_WARMTH_RATE = 0.10          # 参与度→温度 放大系数（连续无阶梯）
_WARMTH_DECAY = 0.001        # 每轮自然衰减（极小，让信号主导）


def _preplay_simulate(memory, env, K):
    """在 E/T/N/M 标量副本上运行 K 步确定性 van der Pol 演化。
    
    不修改 memory 的实际 E/T/N/M，仅演化标量副本。
    返回 (fluctuation, E_path, T_path)：
      - fluctuation = log(1 + sum(dE_i^2 + dT_i^2))，连续无分支
      - E_path / T_path：K+1 个采样点的路径列表
    """
    # ── 读取实际 E/T/N/M（只读）──
    climate = memory.get("internal_climate", {})
    E = float(climate.get("emotion_intensity", 0.5))
    T = float(climate.get("tension", 0.3))
    N = float(climate.get("energy", 0.5))
    M = float(climate.get("memory_pressure", 0.3))

    # NaN 防御
    if math.isnan(E): E = 0.5
    if math.isnan(T): T = 0.3
    if math.isnan(N): N = 0.5
    if math.isnan(M): M = 0.3

    # 静息环境参数
    light = env.get("light", 0.5) if env else 0.5
    _ = env.get("temperature", 0.5) if env else 0.5

    # 耦合系数（与 _evolve_climate_idle 一致）
    c_EN = 0.14
    damping = 0.15
    step_factor = 0.15

    E_path = [E]
    T_path = [T]

    for _ in range(K):
        # 核心 van der Pol 耦合（无惯性：副本无历史）
        dE = (0.12 * T - c_EN * N + 0.05 * M - damping * E) * step_factor
        dT = (0.10 * E + 0.06 * M - c_EN * N - damping * T) * step_factor
        dN = (c_EN * E - 0.07 * T - 0.10 * N + 0.02) * step_factor
        dM = (0.09 * T + 0.04 * E - 0.14 * M) * step_factor

        E += dE
        T += dT
        N += dN
        M += dM

        # van der Pol 极限环有界，无需 clamp
        E_path.append(E)
        T_path.append(T)

    # ── 路径波动量 = log(1 + sum(dE_i^2 + dT_i^2)) ──
    path_energy = 0.0
    for i in range(len(E_path) - 1):
        dE_i = E_path[i + 1] - E_path[i]
        dT_i = T_path[i + 1] - T_path[i]
        path_energy += dE_i * dE_i + dT_i * dT_i

    fluctuation = math.log(1.0 + path_energy)

    return fluctuation, E_path, T_path


# ── 身份锚点与关系温度 ──────────────────────────────────────────────────────

def _ensure_relations(memory, user_id):
    """确保 memory["relations"][user_id] 存在，返回该用户的 relation 状态 dict。
    不同 user_id 的关系状态完全隔离——warmth、count、tone_sum 各自独立。
    """
    relations = memory.get("relations")
    if relations is None:
        relations = {}
        memory["relations"] = relations
    rel = relations.get(user_id)
    if rel is None:
        rel = {
            "relationship_warmth": 0.0,     # tanh-saturated ∈ [-1, 1]
            "total_turns": 0,               # 与该用户的累计轮次
            "tone_sum": 0.0,                # tone_bias 累计（用于平均）
            "_last_delta": 0.0,             # 最近一轮的增量（调试/分析用）
            "visit_count": 0,               # 来访次数（每次调用 +1）
            "last_visit_time": None,        # 最近来访时间戳
            "last_topics": [],              # 最近 N 个话题关键词（环状）
            # ── 事实记忆层（事实优先原则）──
            "conversation_history": [],     # 最近 N 轮对话 [{"role":"user"|"assistant", "content":"..."}]
            "events": [],                   # 事实事件列表 ["用户说工作累", "第三次问'你认识我吗'"]
        }
        relations[user_id] = rel
    return rel


def _compute_warmth_delta(user_input, tone_bias):
    """计算单轮 warmth 增量，连续无 if-then，无随机数。

    输入信号:
      - tone_bias ∈ [-1, 1]：emergence 层输出的情感色调偏置（暖>0，冷<0）
      - len(user_input)：参与度代理
        长输入 = 高参与（暖信号），极短输入 = 低参与（冷信号偏压）
    公式: delta = WARMTH_RATE * (0.5*tone + 0.5*(len_proxy - 0.3)) - WARMTH_DECAY
    典型值: 暖(~0.01~0.03/轮), 冷(~-0.01~-0.03/轮), 极冷短输入(~-0.04/轮)
    """
    _len_proxy = min(len(user_input) / 20.0, 1.0)        # [0, 1]，20 字 = 满参与
    # 综合信号：tone 方向 + 长度参与偏置（连续叠加，无阶梯）
    _signal = 0.5 * tone_bias + 0.5 * (_len_proxy - 0.3)
    _delta = _WARMTH_RATE * _signal - _WARMTH_DECAY
    return _delta


def _update_relationship_warmth(memory, user_id, user_input, tone_bias):
    """连续更新 relationship_warmth ∈ [-1, 1]（tanh 自然饱和）。

    返回更新后的 warmth 值（float，已 saturated）。
    """
    rel = _ensure_relations(memory, user_id)
    warmth = rel.get("relationship_warmth", 0.0)
    delta = _compute_warmth_delta(user_input, tone_bias)
    warmth_new = math.tanh(warmth + delta)
    rel["relationship_warmth"] = round(warmth_new, 6)
    rel["total_turns"] = rel.get("total_turns", 0) + 1
    rel["tone_sum"] = rel.get("tone_sum", 0.0) + tone_bias
    rel["_last_delta"] = round(delta, 6)
    return warmth_new


def _accumulate_relation_trace(memory, user_id, user_input, directive):
    """对话结束后累积关系痕迹：visit_count、last_topics。

    不是简单 warmth 加减——留下可以让下次对话"认出"这个人的具体信息。
    """
    import time as _time
    rel = _ensure_relations(memory, user_id)
    rel["visit_count"] = rel.get("visit_count", 0) + 1
    rel["last_visit_time"] = _time.time()

    # 提取本轮话题关键词：从 directive.intent（抽象表达）中取前几个字 + 输入关键词
    _intent_text = (directive.get("intent") or "")[:30]
    _topics = rel.get("last_topics", [])

    # 从 intent 文本中抽取 2-3 个字作为话题标签（避免过长）
    if _intent_text:
        # 摘取关键词：用意图分类输出本身作为话题标签
        _label = _intent_text.replace("\n", " ")
        if len(_label) > 20:
            _label = _label[:20]
        _topics.append(_label)

    # 从 known_facts 里取最近添加到标签
    _known = memory.get("user_model", {}).get("known_facts", {})
    _new_facts = _known.get("added_this_round", [])
    for f in _new_facts:
        _fact_text = f.get("fact", "")
        if _fact_text and len(_fact_text) <= 20:
            _topics.append(f"fact:{_fact_text}")
    _known["added_this_round"] = []  # 清空本轮

    # 环状缓冲，最多保留 8 个话题
    rel["last_topics"] = _topics[-8:]

    return rel


# ── 事实事件记录：每次交互结束时，把本轮对话存进 conversation_history ──
_MAX_CONVERSATION_HISTORY = 12  # 最多保留 12 条 = 6 轮对话
_MAX_EVENTS = 20               # 最多保留 20 个事实事件


def _record_conversation_turn(memory, user_id, user_input, reply):
    """记录本轮对话到 conversation_history，最多保留 _MAX_CONVERSATION_HISTORY 条"""
    rel = _ensure_relations(memory, user_id)
    _hist = rel.get("conversation_history", [])
    # 只保留 factual 内容：用户说的 + 洛神回的
    _hist.append({"role": "user", "content": user_input})
    if reply:
        _hist.append({"role": "assistant", "content": reply})
    # 环状缓冲
    if len(_hist) > _MAX_CONVERSATION_HISTORY:
        _hist = _hist[-_MAX_CONVERSATION_HISTORY:]
    rel["conversation_history"] = _hist
    return _hist


def _record_fact_event(memory, user_id, fact_text):
    """记录一条事实事件（只记事实，不记判词）。

    规则：
    - 记："用户说工作很累"（fact）
    - 不记："用户状态推断为疲惫"（judgment）
    - 记："用户第三次问'你认识我吗'"（repetition count 是事实）
    - 不记："用户不信任洛神"（interpretation）
    """
    if not fact_text or not isinstance(fact_text, str):
        return
    fact_text = fact_text.strip()
    if len(fact_text) > 60:  # 事实过长则截断
        fact_text = fact_text[:58] + "…"

    rel = _ensure_relations(memory, user_id)
    _events = rel.get("events", [])
    # 去重：如果最近已有同样的事件，不重复记
    if _events and _events[-1] == fact_text:
        return
    _events.append(fact_text)
    if len(_events) > _MAX_EVENTS:
        _events = _events[-_MAX_EVENTS:]
    rel["events"] = _events


def _extract_facts_from_turn(user_input, reply, directive):
    """从单轮对话中提取事实事件。

    只提取明确的、可验证的事实。
    返回字符串列表。
    """
    import re
    facts = []

    # 用户明确说过的事（从已知事实里取）
    _known = directive.get("_known_facts_this_round", [])
    for f in _known:
        if isinstance(f, str) and f.strip():
            facts.append(f"用户提到：{f.strip()[:40]}")
        elif isinstance(f, dict):
            _t = f.get("fact", "")
            if _t:
                facts.append(f"用户提到：{_t.strip()[:40]}")

    # 从用户输入中提取关键事实：直接引用原话的简短片段
    # 只取包含具体信息的句子（不是虚问句）
    if user_input and len(user_input) > 4:
        # 如果输入不太长，直接记为"用户说：xxx"
        if len(user_input) <= 30:
            facts.append(f"用户说：「{user_input}」")
        else:
            # 长输入只取前 30 字作为事实锚点
            facts.append(f"用户说：「{user_input[:30]}…」")

    return facts


def _get_recent_conversation_history(memory, user_id, max_turns=6):
    """读取最近 N 轮对话，格式化为 conversation_history 列表"""
    rel = _ensure_relations(memory, user_id)
    _hist = rel.get("conversation_history", [])
    # 只取最近的 N 轮（2N 条消息）
    _max_msgs = max_turns * 2
    if len(_hist) > _max_msgs:
        _hist = _hist[-_max_msgs:]
    return _hist


def _select_relation_facts_for_context(memory, user_id):
    """选择应该放进当前 LLM 上下文的事实事件。

    规则：
    - 只选事实，不选判词
    - 最多选 5 条（防止 prompt 过长）
    - 所有事件都已经是"只记事实"的，这里只做数量限制
    """
    rel = _ensure_relations(memory, user_id)
    _events = rel.get("events", [])
    if not _events:
        return []
    # 取最近的 5 条事实
    return _events[-5:]


def _emergence_log(memory):
    """提取 emergence 数据供实验记录。
    无 memory_emergence 时返回零值 dict，保证调用方永远拿到 dict。
    """
    emer = memory.get("active_context", {}).get("memory_emergence")
    if emer:
        return {
            "arousal_bias": emer.get("arousal_bias"),
            "tone_bias": emer.get("tone_bias"),
            "length_bias": emer.get("length_bias"),
            "background": emer.get("background"),
        }
    # 零值默认：无历史、无记忆浮现、无自我状态
    return {
        "arousal_bias": 0.0,
        "tone_bias": 0.0,
        "length_bias": 0.5,
        "background": None,
    }


# 叙事势对行为层的叠加系数：narrative_potential=0.1 时额外增加 0.5 预激活 → normal threshold 边界
# 因为 narrative_potential 通常 0.05-0.2，需较大 boost 才能跨过 0.55 行为门槛
_NARRATIVE_TENDENCY_BOOST = 5.0

# Lambda-Self 自调节参数（固定，不允许实验过程中调整）
_LAMBDA_SELF_ALPHA = 1.5       # 乘性调制强度
_LAMBDA_SELF_TAU = 80.0       # 慢变量时间常数 (tick)
_LAMBDA_HIST_WINDOW = 20      # 历史窗口长度
_LAMBDA_HIST_MIN = 5          # 最少有效观测数（低于此返回当前值，不更新）

# ── 实验开关（全部关闭，不再用于真实对话）──
INTERNAL_DRIVE_ENABLED = False
PRESENCE_BIAS_ENABLED = False
STABILITY_DRIVE_ENABLED = False

# ── 在线学习核心参数（实验用，已禁用）──
LEARNING_CORE_ENABLED = False
LEARNING_LR = 0.01
LEARNING_BETA = 0.5
LEARNING_ERR_EMA_ALPHA = 0.02
LEARNING_K = 2.0
LEARNING_VEC_KEYS = ["E", "T", "N", "M", "rp_ema", "s_depth", "prev_tokens"]


def _compute_lambda_self(memory):
    """
    计算 Lambda-Self 自调节信号（连续、无 if-then 数值分支）。

    返回 lambda_self ∈ [0, 1]（已在 EMA 更新后的值）。
    如果历史观测数不足 _LAMBDA_HIST_MIN，返回当前存储值（不更新）。

    数据来源：ring_state._max_tokens_hist、ring_state._rp_ema_hist（均为已有字段）。
    """
    rs = memory.get("self_model", {}).get("ring_state", {})
    lambda_self = rs.get("lambda_self", 0.0)
    hist_tok = rs.get("_max_tokens_hist", [])
    hist_rp = rs.get("_rp_ema_hist", [])

    n_tok = len(hist_tok)
    n_rp = len(hist_rp)
    n_obs = n_tok if n_tok < n_rp else n_rp   # min(n_tok, n_rp)，无条件分支

    if n_obs < _LAMBDA_HIST_MIN:
        return lambda_self

    # ── 行为范围（连续，无分支）──
    _tok = hist_tok[-n_obs:]
    _rp = hist_rp[-n_obs:]

    # max - min 用迭代方式避免 if（但内置 max/min 被视为 clamp 函数，非分支）
    _tok_max = _tok[0]; _tok_min = _tok[0]
    for _v in _tok[1:]:
        if _v > _tok_max: _tok_max = _v
        if _v < _tok_min: _tok_min = _v
    _tok_range = _tok_max - _tok_min
    _norm_range = _tok_range / 350.0           # 350 = 各档位 base 最大值
    _rigidity = 1.0 - (_norm_range if _norm_range < 1.0 else 1.0)
    if _rigidity < 0.0: _rigidity = 0.0         # clamp via if-chain，可接受

    # ── 皮尔逊连续计算（cov / (sx*sy + 1e-12)）──
    _mx = sum(_tok) / n_obs
    _my = sum(_rp) / n_obs
    _cov = 0.0; _sxx = 0.0; _syy = 0.0
    for i in range(n_obs):
        _dx = _tok[i] - _mx; _dy = _rp[i] - _my
        _cov += _dx * _dy; _sxx += _dx * _dx; _syy += _dy * _dy
    _cov /= n_obs; _sxx /= n_obs; _syy /= n_obs
    _sx = math.sqrt(_sxx + 1e-12)
    _sy = math.sqrt(_syy + 1e-12)
    _r = _cov / (_sx * _sy)
    # clamp r to [-1, 1] via if-chain
    if _r > 1.0: _r = 1.0
    if _r < -1.0: _r = -1.0
    _coherence = _r

    # ── lambda_raw ──
    _lambda_raw = _rigidity * (1.0 - _coherence) / 2.0

    # ── EMA 更新（dt 固定 0.08）──
    _dt = 0.08
    _alpha_ema = _dt / (_LAMBDA_SELF_TAU + _dt)
    lambda_self += _alpha_ema * (_lambda_raw - lambda_self)
    # clamp [0, 1]
    if lambda_self < 0.0: lambda_self = 0.0
    if lambda_self > 1.0: lambda_self = 1.0

    rs["lambda_self"] = lambda_self
    return lambda_self


def _get_learning_state_vector(memory):
    """提取学习器状态向量 s(t)"""
    ring = memory.get("self_model", {}).get("ring_state", {})
    climate = memory.get("internal_climate", {})
    recent = memory.get("self_model", {}).get("_recent_tokens", [])
    prev_tokens = recent[-1] if recent else 80
    return {
        "E": float(climate.get("emotion_intensity", 0.5)),
        "T": float(climate.get("tension", 0.0)),
        "N": float(climate.get("energy", 0.5)),
        "M": float(climate.get("memory_pressure", 0.3)),
        "rp_ema": float(ring.get("relational_pressure_ema", 0.0)),
        "s_depth": float(ring.get("s_depth", 0.0)),
        "prev_tokens": float(prev_tokens) / 200.0
    }


def _predict_E(state_vector, W):
    """预测 E(t+1) = W · s(t)"""
    return sum(w * state_vector[k] for w, k in zip(W, LEARNING_VEC_KEYS))


def _update_learning_weights(W, state_vector, error, lr=None):
    """在线更新权重 W <- W + lr * error * s(t)"""
    if lr is None:
        lr = LEARNING_LR
    return [w + lr * error * state_vector[k] for w, k in zip(W, LEARNING_VEC_KEYS)]


def _update_lambda_histories(memory, max_tokens, rp_ema):
    """更新 Lambda-Self 历史序列（纯存储操作，非数值计算分支）"""
    rs = memory.get("self_model", {}).get("ring_state", {})
    h_tok = rs.setdefault("_max_tokens_hist", [80.0, 80.0])
    h_rp = rs.setdefault("_rp_ema_hist", [0.0, 0.0])
    h_tok.append(max_tokens)
    h_rp.append(rp_ema)
    # 保持窗口长度 _LAMBDA_HIST_WINDOW
    while len(h_tok) > _LAMBDA_HIST_WINDOW:
        h_tok.pop(0)
    while len(h_rp) > _LAMBDA_HIST_WINDOW:
        h_rp.pop(0)


# ── 关系地貌向量 R (r_intensity, r_historicity, r_coherence) 参数 ──
_R_ALPHA_ENERGY = 0.005            # r_intensity EMA 平滑系数（~200 tick 窗口）
_R_ALPHA_HIST = 0.005              # r_historicity EMA 平滑系数
_R_ALPHA_COH = 0.0025              # r_coherence 相位速度 EMA（~400 tick 窗口）
_R_K_INT = 6.0                     # r_intensity sigmoid 斜率
_R_TH_INT = 0.4                    # r_intensity sigmoid 偏移
_R_K_HIST = 4.0                    # r_historicity sigmoid 斜率
_R_TH_HIST = 0.5                   # r_historicity sigmoid 偏移
_R_K_COH = -3.0                    # r_coherence: 方差↑ → coherence↓
_R_TH_COH = 0.05                   # r_coherence sigmoid 偏移
_R_K_HIST_R = 0.6                  # 载重对压力敏感度的调制强度
_R_K_COH_R = 0.8                  # 定型度对叙事增强的调制强度

# 用户历史慢压力 → 行为选择层系数（校准后：0.1→10%, 0.2→25%, 0.4→40% 差异）
_PRESSURE_K = 0.4
_PRESSURE_QUALITY_SCALE = 1.5     # rp_ema → pressure_quality 缩放
_TOKEN_OFFSET_SCALE = 30          # pq → max_tokens 偏移缩放
_BASE_TOKENS = [0, 25, 80, 180, 350]  # 各档位 base tokens
_MODE_NAMES = ["silent", "brief", "short", "normal", "engaged"]
_N_MODES = len(_MODE_NAMES)


def anchor_distance(chain_length: int, window_size: int) -> float:
    """锚距离：衡量链长超出可视窗口的信息隐藏量。
    chain_length >> window_size → 返回接近 1.0（隐藏多）。
    chain_length <= window_size → 接近 0.5 以下（几乎无隐藏）。
    """
    import math
    hidden = max(0, chain_length - window_size)
    return 1.0 / (1.0 + math.exp(-hidden / 100.0))


def _select_behavior(memory, emergence, user_id="primary"):
    """
    行为选择层：在调用 LLM 之前，由内部状态确定性决定行为框架。
    """
    import math

    tone_bias = 0.0
    arousal_bias = 0.0
    length_bias = 0.5
    narrative_potential = 0.0
    if emergence:
        tone_bias = emergence.get("tone_bias", 0.0)
        arousal_bias = emergence.get("arousal_bias", 0.0)
        length_bias = emergence.get("length_bias", 0.5)
        narrative_potential = emergence.get("narrative_potential", 0.0)

    # 相位偏置：从环的当前相位提取一个连续小偏置，不命名、不分支
    _ring_state = memory.get("self_model", {}).get("ring_state", {})
    _phase = _ring_state.get("phase", 0.0)
    _phase_bias = 0.03 * math.sin(_phase)   # k=0.03，极小偏移

    # 读取关系地貌向量 R（ring_state 中积累的三个慢变量）
    _rint = _ring_state.get("r_intensity", 0.5)
    _rhist = _ring_state.get("r_historicity", 0.5)
    _rcoh = _ring_state.get("r_coherence", 0.5)

    # 慢压力项：用户输入历史的指数平均唤醒
    _pressure_ema = _ring_state.get("relational_pressure_ema", 0.0)
    # 读取 s_depth（不可逆深度积累量）
    _s_depth = _ring_state.get("s_depth", 0.0)
    # s_depth 缓冲当前压力：深厚关系使同等情绪波动对行为影响减弱
    _pressure_term = _PRESSURE_K * _pressure_ema / (1.0 + 1.5 * _s_depth)

    # 在线学习器乘性调制：预测误差越大（内在未知越大），越敏感于外部压力
    if LEARNING_CORE_ENABLED:
        _pressure_term *= (1.0 + LEARNING_BETA * memory.get("self_model", {}).get("learning_core", {}).get("lambda_learn", 0.5))

    # ═══ Lambda-Self 自调节：行为僵化检测 → 乘性调制压力项 ═══
    _lambda_self_val = _compute_lambda_self(memory)
    _modulator = 1.0 + _LAMBDA_SELF_ALPHA * _lambda_self_val
    _pressure_term *= _modulator

    # 乘性调制 ②：定型度 r_coherence 调节叙事增强强度
    _narr_boost = _NARRATIVE_TENDENCY_BOOST * (1.0 + _R_K_COH_R * (_rcoh - 0.5))

    # ── 内部节律驱动：环状态直接驱动行为，不再只让外部压力主导 ──
    _internal_drive = 0.0
    if INTERNAL_DRIVE_ENABLED:
        _climate = memory.get("internal_climate", {})
        _E = float(_climate.get("emotion_intensity", 0.5))
        _T = float(_climate.get("tension", 0.0))
        _internal_drive = math.tanh(_E + 0.5 * _T) * 0.6

    # ── 存在感基线：S 积累 + 交互次数驱动小幅偏置 ──
    _presence_bias = 0.0
    if PRESENCE_BIAS_ENABLED:
        _ring = memory.get("self_model", {}).get("ring_state", {})
        _S = float(_ring.get("S", 0.0))
        _total_int = float(memory.get("user_model", {}).get("total_interactions", 0))
        _presence_bias = 0.12 * math.tanh(_S + 0.001 * _total_int)

    # ── 内在稳态偏好：当 H 下降时加大对压力的敏感度 ──
    _stability_D = 0.0
    _H_val = 0.5
    _H_ema_val = 0.5
    if STABILITY_DRIVE_ENABLED:
        _climate = memory.get("internal_climate", {})
        _ring_st = memory.get("self_model", {}).get("ring_state", {})
        _E_val = float(_climate.get("emotion_intensity", 0.5))
        _T_val = float(_climate.get("tension", 0.0))
        _H_val = 1.0 - min(1.0, (abs(_E_val) + abs(_T_val)) / 2.0)
        _H_ema_val = float(_ring_st.get("H_ema", _H_val))
        _stability_D = _H_ema_val - _H_val  # >0 表示内部正在变差
        _D_pos = _stability_D * (1.0 if _stability_D > 0.0 else 0.0)
        _pressure_term = _pressure_term * (1.0 + 0.8 * _D_pos)
        # 更新 H_ema (alpha = 1/50 = 0.02)，存储回 memory
        _new_H_ema = 0.98 * _H_ema_val + 0.02 * _H_val
        memory["self_model"]["ring_state"]["H_ema"] = round(_new_H_ema, 6)

    # ── 退缩倾向偏置：withdraw_tendency ∈ [0,1] 时从 response_pre 中减去 ──
    _withdraw_tendency = memory.get("self_model", {}).get("withdraw_tendency", 0.0)
    _WITHDRAW_K = 0.8
    _withdraw_penalty = _WITHDRAW_K * _withdraw_tendency

    # ── 内部疼痛偏置：internal_pain ∈ [0,1] 时从 response_pre 中减去 ──
    _internal_pain = memory.get("self_model", {}).get("internal_pain", 0.0)
    _PAIN_K = 0.6     # 用户指定的系数 k_pain
    _pain_penalty = _PAIN_K * _internal_pain

    # ── 预演波动计算：在 E/T/N/M 标量副本上运行 K 步 van der Pol，不动实际状态 ──
    _env_preplay = {"light": 0.5, "temperature": 0.5, "noise": 0.0}
    _preplay_fluctuation, _preplay_E_path, _preplay_T_path = _preplay_simulate(
        memory, _env_preplay, _PREPLAY_DEPTH
    )
    # 注：不再将 preplay_fluctuation 作为加性偏置，改为驱动档位动态边界
    _preplay_bias = _PREPLAY_K * _preplay_fluctuation  # 仍输出到日志，但不加入 response_pre

    # ── 动态档位阈值（双向：pf 推上，pain 推下）──
    _threshold_shift = _K_SHIFT * math.tanh(_preplay_fluctuation - 0.5 * _internal_pain)

    # ── 身份锚点偏置：relationship_warmth 连续调制 response_pre ──
    # warmth ∈ [-1, 1]；K_WARMTH=0.4 → 最大 ±0.4 偏置
    # 正温度→更开放/投入档位，负温度→更退缩/疏远档位（连续无阶梯）
    _relationship_warmth = memory.get("relations", {}).get(user_id, {}).get("relationship_warmth", 0.0)
    _warmth_bias = _K_WARMTH * _relationship_warmth

    # ── 锚点偏置：链长超窗越多，response_pre 修正越少（她因不可见过去而趋保守）──
    try:
        from hash_chain_gateway import load_chain_records as _load_chain
        _chain_len = len(_load_chain())
    except Exception:
        _chain_len = 0
    _anchor_dist = anchor_distance(_chain_len, window_size=30)
    _anchor_bias = 0.3 * (1.0 - _anchor_dist)

    # 连续叠加 - 退缩惩罚 - 内部疼痛惩罚 + 身份温度偏置 + 锚点偏置（不再 + _preplay_bias）
    response_pre = (arousal_bias + 0.5 * tone_bias
                    + _narr_boost * narrative_potential
                    + _phase_bias
                    + _pressure_term
                    + _internal_drive
                    + _presence_bias
                    - _withdraw_penalty
                    - _pain_penalty
                    + _warmth_bias
                    + _anchor_bias)
    response_tendency = 1.0 / (1.0 + math.exp(-response_pre))

    # ── 维度 1：5 档位离散选择（动态边界，随 preplay_fluctuation+internal_pain 漂移）──
    _mode_raw = response_tendency * (_N_MODES - 0.001)
    _mode_index_shifted = _mode_raw + _threshold_shift
    mode_idx = max(0, min(4, int(_mode_index_shifted)))  # 连续 floor，无 if-then，隐式 clamp
    response_mode = _MODE_NAMES[mode_idx]

    # ── 维度 2：压力质量（rp_ema 直接，绕过 sigmoid）──
    pq = max(-1.0, min(1.0, _PRESSURE_QUALITY_SCALE * _pressure_ema))

    # ── max_tokens 双维度公式：档位 base + 压力偏移 + s_depth 偏移（全连续）──
    # s_depth 贡献一个稳定的 base 偏移：深度积累后，即便是相同档位也能说更多
    base = _BASE_TOKENS[mode_idx] + int(40 * _s_depth)
    offset = int(_TOKEN_OFFSET_SCALE * pq)
    max_tokens = max(0, base + offset)

    # 语气索引
    tone_sig = 1.0 / (1.0 + math.exp(-(tone_bias + 0.3 * _pressure_ema)))
    tone_mode_idx = max(0, min(2, round(2.0 * tone_sig)))

    return {
        "response_mode": response_mode,
        "response_tendency": round(response_tendency, 4),
        "response_pre": round(response_pre, 6),
        "mode_idx": mode_idx,
        "tone_mode_idx": tone_mode_idx,
        "max_tokens": max_tokens,
        "pressure_ema": round(_pressure_ema, 6),
        "pressure_quality": round(pq, 4),
        "pressure_term": round(_pressure_term, 7),
        "internal_drive": round(_internal_drive, 6),
        "presence_bias": round(_presence_bias, 7),
        "H": round(_H_val, 6),
        "H_ema": round(_H_ema_val, 6),
        "stability_D": round(_stability_D, 6),
        "lambda_self": round(_lambda_self_val, 7),
        "lambda_modulator": round(_modulator, 7),
        "r_intensity": round(_rint, 6),
        "r_historicity": round(_rhist, 6),
        "r_coherence": round(_rcoh, 6),
        "withdraw_tendency": round(_withdraw_tendency, 6),
        "withdraw_penalty": round(_withdraw_penalty, 6),
        "user_id": user_id,
        "relationship_warmth": round(_relationship_warmth, 6),
        "warmth_bias": round(_warmth_bias, 6),
        "internal_pain": round(_internal_pain, 6),
        "pain_penalty": round(_pain_penalty, 6),
        "preplay_fluctuation": round(_preplay_fluctuation, 6),
        "preplay_bias": round(_preplay_bias, 6),
        "threshold_shift": round(_threshold_shift, 6),
        "mode_idx_raw": round(_mode_raw, 6),
        "mode_idx_shifted": round(_mode_index_shifted, 6),
        "preplay_path_summary": {
            "E_start": round(_preplay_E_path[0], 5),
            "E_end": round(_preplay_E_path[-1], 5),
            "T_start": round(_preplay_T_path[0], 5),
            "T_end": round(_preplay_T_path[-1], 5),
        },
    }


def generate_response(user_input, source="living_engine", extra_context=None, extract_facts=True, source_id=None, user_id="primary"):
    """
    活记忆层对外提供的统一响应接口。
    
    所有外部模块必须通过此函数获取LLM响应，不得直接调用 llm_interface.call_llm()。
    
    source_id: 寻址标签（如 \"user_A\"）。
               仅用于 episodic_memory 的检索过滤：只取该 tag 的记忆参与 emergence。
               不进入情绪方程、不进入 emergence 公式、不进入行为选择公式。
               是寻址键，不是行为键。
    user_id: 身份锚点键（如 \"primary\" / \"secondary\"）。
             用于 episodic_memory 的 owner 过滤、relationship_warmth 读写、
             withdraw_tendency（退缩倾向）的 per-user 独立跟踪。
             是寻址键 + 关系键：warmth 须通过 K_WARMTH 偏置连续进入 response_pre，
             不直接决定档位（不做 if-then）。
    """
    global _current_source_id, _current_user_id
    _prev_source_id = _current_source_id
    _prev_user_id = _current_user_id
    _current_source_id = source_id  # 设置当前寻址上下文：仅用于 memory tags 过滤
    _current_user_id = user_id      # 设置当前身份锚点：用于关系温度和退缩倾向隔离

    try:
        return _generate_response_impl(user_input, source, extra_context, extract_facts, user_id)
    finally:
        _current_source_id = _prev_source_id  # 恢复上下文（寻址隔离）
        _current_user_id = _prev_user_id      # 恢复身份锚点（关系隔离）


def _generate_response_impl(user_input, source="living_engine", extra_context=None, extract_facts=True, user_id="primary"):
    """实际实现，拆分出来只为 finally 能恢复 _current_source_id。"""
    # 1. 加载活记忆
    memory = cold_start_if_needed()

    # 1b. 残留层仅存 t_snapshot / texture 对共振计算的影响（本轮不写入持久层）
    # 实际的纹理累积由 update_after_interaction 负责（从磁盘重读后再写）

    # 1c. ── 身份锚点初始化：确保该 user_id 的关系状态存在 ──
    _ensure_relations(memory, user_id)

    # 2. === 活记忆层：连续退缩倾向更新（数值更新，无布尔判定） ===
    withdraw_tendency = _update_withdraw_tendency(memory, user_input)
    # internal_pain 由 _compute_and_log_pain 在行为选择后更新，此处不修改

    # 持久化：确保 update_after_interaction 从磁盘重读时拿到最新 withdraw
    _save_json_atomic("active_memory/active_memory.json", memory)

    # 3. 正常流程：行为档位由 withdraw_tendency 通过 response_pre 连续决定
    perceptions = read_perception_snapshots()
    
    # 4. 记录用户输入到哈希链
    _append_jsonl("perception_input/user_input_log.jsonl", {
        "timestamp": _now(),
        "content": user_input,
        "source": source,
        "user_id": user_id,
    })
    append_hash_chain("hash_chain_v2.log", "perception_input/user_input_log.jsonl")
    # 旁路状态快照：记录这条 user_input 写入时的状态
    _append_state_snapshot(memory, user_id)

    # 5. 检索相关记忆（并合并外部模块传入的额外上下文）
    context_window = retrieve_relevant_memory(user_input, memory)
    if extra_context:
        context_window["external"] = extra_context
    
    # 6. 生成表达意图
    intent = formulate_expression_intent(user_input, context_window, memory)
    
    # 7. 倾听层：如果用户最近有表态，在意图里加入"承认她"
    acknowledgment = generate_acknowledgment_for_listening(memory)
    
    # 8. 构建表达指令（传入记忆浮现的 tone_bias 和 length_bias）
    emergence_for_directive = memory.get("active_context", {}).get("memory_emergence")
    directive = build_expression_directive(intent, memory, emergence=emergence_for_directive)
    if acknowledgment:
        directive["acknowledgment"] = acknowledgment
    
    # 9. 行为选择层：在调用 LLM 之前，由内部状态确定性决定行为框架
    # LLM 只在这个框架内填充语言，差异不会被采样随机性淹没
    emergence_for_behavior = emergence_for_directive if emergence_for_directive else _emergence_log(memory)

    # 9b. ── 关系温度更新：基于当前输入的 tone_bias 连续更新 ──
    # 使用 emergence_for_behavior 的 tone_bias 作为用户情感色调信号
    _tone_signal = emergence_for_behavior.get("tone_bias", 0.0) if emergence_for_behavior else 0.0
    _current_warmth = _update_relationship_warmth(memory, user_id, user_input, _tone_signal)

    behavior = _select_behavior(memory, emergence_for_behavior, user_id)

    # ── 关系上下文注入：让 LLM 知道"这个人是谁、来过多熟、上次聊了什么" ──
    _rel = memory.get("relations", {}).get(user_id, {})
    _relation_context = {
        "warmth": _rel.get("relationship_warmth", 0.0),
        "is_returning": _rel.get("visit_count", 0) >= 1 or _rel.get("total_turns", 0) > 0,
        "visit_count": _rel.get("visit_count", 0),
        "avg_tone": (_rel.get("tone_sum", 0.0) / max(1, _rel.get("total_turns", 0))),
        "recent_topics": _rel.get("last_topics", [])[-3:],  # 最近 3 个话题
    }
    # 在 warmth 更新后立即注入，这样本次就能用最新值

    # ── Lambda-Self 历史序列更新（纯存储操作，不影响行为选择结果）──
    _update_lambda_histories(memory, behavior["max_tokens"], behavior["pressure_ema"])

    # 更新 _recent_tokens（供学习器使用）
    _rt = memory.get("self_model", {}).get("_recent_tokens", [])
    _rt.append(behavior["max_tokens"])
    if len(_rt) > 50:
        _rt = _rt[-50:]
    memory["self_model"]["_recent_tokens"] = _rt
    
    # 如果行为选择判定沉默，直接返回（由 withdraw_tendency 经 response_pre 驱动）
    if behavior["response_mode"] == "silent":
        last_stated_b = memory.get("self_model", {}).get("self_stated_state", {}).get("last_stated")
        return {
            "reply": "",
            "directive": directive,
            "llm_called": False,
            "withdraw_tendency": round(withdraw_tendency, 6),
            "internal_pain": round(memory.get("self_model", {}).get("internal_pain", 0.0), 6),
            "behavior": behavior,
            "self_stated_state": last_stated_b,
            "emergence": _emergence_log(memory),
        }
    
    # 行为层指定 max_tokens 应用到所有档位
    directive["constraints"]["max_tokens"] = behavior["max_tokens"]
    # ── max_length 档位驱动（mode_idx） + 疼痛压缩 ──
    _mode_max_len = {0: 0, 1: 40, 2: 120, 3: 250, 4: 400}
    _mode_length = _mode_max_len.get(behavior["mode_idx"], 80)
    _pain = memory.get("self_model", {}).get("internal_pain", 0.0)
    _pain_factor = max(0.3, 1.0 - 0.3 * _pain)
    directive["constraints"]["max_length"] = int(_mode_length * _pain_factor)
    # 温度：brief 档基础更低，energy 正向、pain 负向（连续无阶梯）
    _energy_val = memory.get("internal_climate", {}).get("energy", 0.5)
    _base_temp = 0.3 if behavior["response_mode"] == "brief" else 0.6
    directive["constraints"]["temperature"] = round(max(0.2, _base_temp + 0.15 * _energy_val - 0.1 * _pain), 2)
    
    # brief 档位不再单独覆盖温度（已在上方统一计算）
    
    # ── 浮现叙事：在最终 LLM 调用前注入来自历史的话头信号 ──
    narrative_final = _build_narrative_urgency(
        emergency=memory.get("active_context", {}).get("memory_emergence")
    )
    if narrative_final is not None:
        directive["context_for_llm"]["narrative_urgency"] = narrative_final

    # ── 不可读残留：注入时间快照 + 共振度（无标签）──
    resonance = _residue_resonance(memory, user_input)
    residue = memory.get("residue")
    if residue and residue.get("t_snapshot"):
        directive["context_for_llm"]["temporal_echo"] = {
            "snapshots": residue["t_snapshot"],
            "resonance": round(resonance, 3),
        }

    # ── 注入短期记忆 + 关系事实到 directive（事实优先原则）──
    # 注意：在 LLM 调用前注入，这样本次回复就能看到最近几轮对话
    _conversation_history = _get_recent_conversation_history(memory, user_id, max_turns=6)
    if "_relation_context" in dir():
        directive["relation_context"] = _relation_context
    # 注入关系事实（engine 选择的最近事实，不是判词）
    directive["relation_facts"] = _select_relation_facts_for_context(memory, user_id)

    # ── 注入"这个人和我最近的事"（事实，不是判词；每条 ≤100 字）──
    try:
        _recent_chain_history = _read_chain_for_user(user_id, limit=30, memory=memory)
        if _recent_chain_history and isinstance(directive.get("context_for_llm"), dict):
            directive["context_for_llm"]["recent_history"] = _recent_chain_history
    except Exception as _e_chain:
        # 链读取失败不影响主流程
        import logging
        logging.error("[chain_read_error] %s", _e_chain)

    # 10. 调用大模型（在已确定的行为框架内生成语言）
    from llm_interface import call_llm
    reply = call_llm(directive, memory, conversation_history=_conversation_history)
    
    # 落链：沉默或空回复（记录为 withdraw_silent 事件）
    if not reply or reply.strip() == "":
        last_stated = memory.get("self_model", {}).get("self_stated_state", {}).get("last_stated")
        _append_arousal_event({
            "event_type": "withdraw_silent",
            "timestamp": _now(),
            "withdraw_tendency": round(withdraw_tendency, 4),
            "behavior_mode": behavior["response_mode"],
            "self_stated_state": last_stated,
            "user_input_tag": _make_input_tag(user_input),
            "final_reply": None,
            "silent": True,
        })
    
    # 落链：记录 withdraw 驱动的 LLM 回复
    if behavior["mode_idx"] <= 1 and withdraw_tendency > 0.5:
        _append_arousal_event({
            "event_type": "withdraw_reply",
            "timestamp": _now(),
            "withdraw_tendency": round(withdraw_tendency, 4),
            "behavior_mode": behavior["response_mode"],
            "user_input_tag": _make_input_tag(user_input),
            "final_reply": reply,
            "silent": False,
        })
    
    # 10. 记录洛神回复到哈希链
    _append_jsonl("perception_input/response_log.jsonl", {
        "timestamp": _now(),
        "content": reply,
        "directive": directive,
        "source": source,
        "user_id": user_id,
        "llm_called": True,
    })
    append_hash_chain("hash_chain_v2.log", "perception_input/response_log.jsonl")
    # 旁路状态快照：记录这条 response 写入时的状态
    _append_state_snapshot(memory, user_id)

    # ── 事实优先：记录本轮对话到 conversation_history + 提取事实事件 ──
    if reply and reply.strip():
        _record_conversation_turn(memory, user_id, user_input, reply[:200])  # 回复截断存
        # 从本次交互提取事实事件（只记事实，不记判词）
        _turn_facts = _extract_facts_from_turn(user_input, reply, directive)
        for _fact in _turn_facts:
            _record_fact_event(memory, user_id, _fact)

    # ── 自查系统：记录状态快照到 state_log.jsonl ──
    try:
        from self_check import append_snapshot
        append_snapshot(memory, user_id=user_id)
    except Exception:
        pass  # 自查系统失败不影响主流程

    # ── 整体行为观测：记录完整行为数据到 behavior_log.jsonl ──
    try:
        from self_check import record_tick
        record_tick(memory, user_id, user_input, reply, behavior, llm_called=True)
    except Exception:
        pass  # 行为观测失败不影响主流程

    # 11. 采集反馈信号
    from feedback_collector import extract_feedback_signal, _is_self_state_statement
    feedback = extract_feedback_signal(user_input, reply, {
        "turn_number": memory["user_model"]["total_interactions"],
        "strategy_used": intent.get("strategy_name"),
        "recent_user_inputs": [],
    })
    
    # 11b. 倾听层
    if _is_self_state_statement(user_input):
        record_listening(user_input, {"source": "user_self_state"})
    
    # 12. 事实提取：从本次用户输入提取个人事实
    # 实验模式下可关闭，防止历史文本泄漏到 LLM 上下文
    if extract_facts:
        try:
            from fact_extractor import extract_and_save as _extract_facts
            _new_facts, memory = _extract_facts(user_input, memory)
        except Exception:
            _new_facts = []
    else:
        _new_facts = []

    # 12b. 累积关系痕迹：在 update 前写入 visit_count / last_topics
    #     这样 update_after_interaction 的快照里会包含最新关系信息
    _accumulate_relation_trace(memory, user_id, user_input, directive)

    # 13. 更新活记忆层
    # ★ 关键：update_after_interaction 从磁盘重读 memory，会覆盖
    #   内存中刚刚更新的 relations（含 relationship_warmth）。
    #   保存 relations 快照 → 调用 update → 恢复快照 → 单独落盘。
    _relations_snapshot = memory.get("relations", {})
    memory = update_after_interaction(user_input, reply, directive, feedback)
    if _relations_snapshot:
        memory["relations"] = _relations_snapshot
        _save_json_atomic("active_memory/active_memory.json", memory)

    # 13b. 生病感知：计算 pain（仅在非 silent 模式下——silent 模式下无新行为可记录）
    if behavior["response_mode"] != "silent":
        _compute_and_log_pain(memory, behavior["mode_idx"], save_memory=True,
                              response_pre=behavior.get("response_pre"))

    # 提取信息用于返回
    last_stated = directive.get("context_for_llm", {}).get("self_stated_state")

    return {
        "reply": reply,
        "directive": directive,
        "llm_called": True,
        "withdraw_tendency": round(withdraw_tendency, 6),
        "internal_pain": round(memory.get("self_model", {}).get("internal_pain", 0.0), 6),
        "behavior": behavior,
        "self_stated_state": last_stated,
        "emergence": _emergence_log(memory),
    }


# -------------------------------------------------------------------------
# 生病感知：pain 信号计算（独立模块，不改变行为参数）
# 通过 pain_signal.py 计算后由本函数记录日志
# -------------------------------------------------------------------------

_pain_tick_counter = 0          # 用于 pain_log.csv 的 tick 标识
_pain_e_series = []             # E (= energy) 时间序列
_pain_tier_series = []          # 行为档位序列
_pain_prev_level = 0            # 上次离散 pain 等级
_pain_l3_persist_count = 0      # 持续在 level 3 的 tick 数


def _record_pain_at_encoding(memory, pain_val):
    """
    将当前 pain 值绑定到最近编码的情景记忆上。
    情景记忆由 _encode_episodic_memory 创建，追加在 episodic_memory 列表末尾。
    """
    episodic = memory.get("user_model", {}).get("episodic_memory", [])
    if episodic and "pain_at_encoding" not in episodic[-1]:
        episodic[-1]["pain_at_encoding"] = pain_val


def _compute_and_log_pain(memory, mode_idx=None, save_memory=False, response_pre=None):
    """
    计算本次 pain：更新序列 → 计算连续值 → 离散化 → 写 CSV → 落链。
    mode_idx: 本次交互的档位。environment_tick 场景传入 None，函数会沿用最近已知档位。
    save_memory: 若为 True，则将带 pain_at_encoding 的 memory 持久化到磁盘。
    response_pre: 行为选择前的 logit 值，仅用于诊断性记录（不影响任何行为）。
    不修改任何行为参数。
    """
    global _pain_tick_counter, _pain_e_series, _pain_tier_series
    global _pain_prev_level, _pain_l3_persist_count

    # 1. 从 memory 提取当前 E（=energy）
    climate = memory.get("internal_climate", {})
    E_now = float(climate.get("energy", 0.5))

    # 更新序列（存储最近 2000 tick 的 E 和最近 50 个档位）
    _pain_e_series.append(E_now)
    if len(_pain_e_series) > 2000:
        _pain_e_series = _pain_e_series[-2000:]

    # 档位：有则追加，无则复制最近一次（environment_tick 场景）
    if mode_idx is not None:
        _pain_tier_series.append(mode_idx)
    elif _pain_tier_series:
        _pain_tier_series.append(_pain_tier_series[-1])
    else:
        _pain_tier_series.append(2)  # 默认 "normal" 档位
    if len(_pain_tier_series) > 50:
        _pain_tier_series = _pain_tier_series[-50:]

    _this_tier = _pain_tier_series[-1] if _pain_tier_series else 2
    csv_path = "active_memory/pain_log.csv"  # 路径常量，在 has_data 分支之前定义

    # 2. 调用 pain_signal 模块计算（v3 返回：signal, ema, baseline, sufficient_data）
    rigidity_signal = 0.0
    # 获取当前 behavior_tier（tick 内 mode_idx 可能为 None 对于 environment_tick）
    _this_tier = _pain_tier_series[-1] if _pain_tier_series else 2

    low_energy_signal, ema_e, baseline_e, has_data = pain_signal.compute_low_energy_signal(
        _pain_e_series, ema_alpha=0.01
    )
    rigidity_signal = pain_signal.compute_rigidity_signal(_pain_tier_series, window=50)

    # 数据不足 200 tick → pain=0, pain_level=0, 但必须 internal_pain=0.0 落盘
    if not has_data:
        _pain_tick_counter += 1
        pain_signal.append_pain_log(
            csv_path,
            tick_id=_pain_tick_counter,
            ema_e=ema_e if ema_e is not None else 0.0,
            baseline_e=baseline_e if baseline_e is not None else 0.0,
            low_energy=0.0,
            rigidity=0.0,
            pain=0.0,
            pain_level=0,
            behavior_tier=_this_tier,
            note="insufficient_data",
        )
        # 数据不足时写入 internal_pain=0.0 并落盘，防止下一轮读到旧值
        _write_internal_pain_to_memory(memory, response_pre=response_pre)
        _save_json_atomic("active_memory/active_memory.json", memory)
        return  # 不更新 pain_at_encoding，不落链

    pain = pain_signal.compute_pain(low_energy_signal, rigidity_signal)
    pain_level = pain_signal.discretize_pain(pain)

    # 3. 将 pain_at_encoding 绑定到最近编码的情景记忆
    _record_pain_at_encoding(memory, pain)

    # 4. 写 CSV 日志
    _pain_tick_counter += 1
    pain_signal.append_pain_log(
        csv_path,
        tick_id=_pain_tick_counter,
        ema_e=ema_e,
        baseline_e=baseline_e,
        low_energy=low_energy_signal,
        rigidity=rigidity_signal,
        pain=pain,
        pain_level=pain_level,
        behavior_tier=_this_tier,
    )

    # 5. 离散事件落链
    if pain_level != _pain_prev_level:
        append_hash_chain(
            "hash_chain_v2.log", csv_path,
            extra_entry={
                "event_type": "PAIN_LEVEL_CHANGE",
                "from_level": _pain_prev_level,
                "to_level": pain_level,
                "pain_continuous": pain,
            }
        )
        _pain_prev_level = pain_level

    # 持续 level 3 超过 100 tick 追加告警
    if pain_level >= 3:
        _pain_l3_persist_count += 1
    else:
        _pain_l3_persist_count = 0

    if _pain_l3_persist_count == 100:
        append_hash_chain(
            "hash_chain_v2.log", csv_path,
            extra_entry={
                "event_type": "PAIN_PERSISTENT_LEVEL3",
                "persist_ticks": 100,
                "latest_pain": pain,
            }
        )

    # 5b. 将内部 pain 写入 self_model（供下一轮 _select_behavior 使用）
    _write_internal_pain_to_memory(memory, response_pre=response_pre)

    # 6. 持久化：如果调用方要求，将带 pain_at_encoding 的 memory 重新落盘
    if save_memory:
        _save_json_atomic("active_memory/active_memory.json", memory)
        append_hash_chain("hash_chain_v2.log", "active_memory/active_memory.json")


def process_user_input(user_input, input_type="text", user_id="primary"):
    """
    处理用户输入的主流程（兼容旧接口，委托给 generate_response）
    user_id: 身份锚点键，默认 "primary"。不同 user_id 的关系状态完全隔离。
    """
    # ── 认知核心：接收输入 + 读取意图 + 渲染状态（不影响主流程） ──
    try:
        _core = cognitive_core.get_core()
        _core.receive_input(text=user_input)
        _core_intent = _core.read_intent()

        # C1: 写意图日志（不改现有行为逻辑）
        _log_core_intent(_core, _core_intent, user_input, user_id)

        # C2: 观测 core vs loshen + per-user snapshot（只读不改）
        import brain_observation
        try:
            _memory = cold_start_if_needed()
            _obs_cl = brain_observation.observe_core_vs_loshen(_core, _memory, user_id)
            _obs_pu = brain_observation.observe_per_user(_core, user_id)
            _log_brain_observation(_obs_cl, _obs_pu)
        except Exception:
            pass  # 观测失败不影响主流程
    except Exception:
        pass  # 认知核心异常不影响洛神正常运行

    result = generate_response(user_input, source="process_user_input", user_id=user_id)
    return result["reply"]


def _log_core_intent(core, intent, user_input, user_id):
    """C1: 将 core 意图写入 cognitive_core_intent_log.jsonl"""
    import os
    try:
        frame = core.frames[-1]
        log_entry = {
            "ts": round(time.time(), 3),
            "tick": core.tick_count,
            "user_id": user_id,
            "user_input": user_input[:200],
            "intent": {
                "stance": round(intent.get("direction", 0.0), 6),
                "stance_strength": round(abs(intent.get("direction", 0.0)), 6),
                "certainty": round(min(1.0, intent.get("energy", 0.0) * 10), 6),
                "register": intent.get("top_cells", [{}])[0].get("cell", "unknown").split(".")[0] if intent.get("top_cells") else "unknown",
                "pace": round(float(np.mean(np.abs(frame - (core.frames[-2] if len(core.frames) >= 2 else frame)))), 6),
                "valence": round(intent.get("direction", 0.0), 6),
                "topic_ref": user_input[:30],
            },
            "core_state_summary": {
                "mean": round(float(np.mean(frame)), 6),
                "std": round(float(np.std(frame)), 6),
                "abs_max": round(float(np.max(np.abs(frame))), 6),
                "row_means": [round(float(np.mean(frame[r])), 6) for r in range(6)],
            },
        }
        with open("cognitive_core_intent_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _log_brain_observation(obs_cl, obs_pu):
    """C2: 将 brain 观测写入 brain_observation_log.jsonl"""
    import os
    try:
        log_entry = {
            "ts": round(time.time(), 3),
            "core_vs_loshen": {
                "correlation": obs_cl.get("correlation"),
                "direction_consistency": obs_cl.get("direction_consistency"),
                "core_vec": obs_cl.get("core_vec"),
                "loshen_vec": obs_cl.get("loshen_vec"),
            },
            "per_user": {
                "user_id": obs_pu.get("user_id"),
                "tick": obs_pu.get("tick"),
                "core_abs_max": obs_pu.get("core_abs_max"),
                "core_mean": obs_pu.get("core_mean"),
                "is_global_state": obs_pu.get("is_global_state"),
            },
        }
        with open("brain_observation_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# -------------------------------------------------------------------------
# 外部环境场：风雨雷电温度（独立于洛神）
# -------------------------------------------------------------------------

import math
import random


def _init_environment(memory):
    """初始化外部环境变量（如果不存在）"""
    env = memory.setdefault("environment", {})
    if "temperature" not in env:
        env["temperature"] = 0.5  # 归一化 0-1，0.5=舒适
    if "humidity" not in env:
        env["humidity"] = 0.5
    if "light" not in env:
        env["light"] = 0.7
    if "pressure" not in env:
        env["pressure"] = 0.5
    if "noise" not in env:
        env["noise"] = 0.1
    # 内部相位（用于昼夜周期）
    if "_phase" not in env:
        env["_phase"] = 0.0
    return env


def _real_noise(tick_id):
    """
    从真实系统抖动中提取不可预测的小扰动。
    不使用 random 模块的任何函数。

    真实扰动源：
    - time.time() 亚秒抖动（受 NTP/调度/中断影响）
    - os.times() CPU jiffies 真实增量
    - hash_chain_v2.log 文件大小（I/O 延迟的真实反映）
    - /proc/loadavg 主机负载（由其他进程共同决定，不可编程控制）
    - /proc/self/stat utime/stime（时钟中断驱动，真实不可预测）
    """
    parts = []

    # 1. 时间戳亚秒抖动
    t = time.time()
    parts.append(f"{t - int(t):.15f}")

    # 2. os.times() CPU jiffies
    times = os.times()
    parts.append(f"{times.user:.10f}")
    parts.append(f"{times.system:.10f}")

    # 3. 哈希链文件大小
    try:
        parts.append(str(os.path.getsize("hash_chain_v2.log")))
    except OSError:
        parts.append("0")

    # 4. /proc/loadavg
    try:
        with open("/proc/loadavg", "r") as f:
            parts.append(f.read().strip())
    except OSError:
        parts.append("0 0 0")

    # 5. /proc/self/stat 第14、15字段（utime jiffies, stime jiffies）
    try:
        with open("/proc/self/stat", "r") as f:
            stat_fields = f.read().split()
            # 0-indexed: utime=13, stime=14
            parts.append(stat_fields[13] if len(stat_fields) > 14 else "0")
            parts.append(stat_fields[14] if len(stat_fields) > 14 else "0")
    except (OSError, IndexError):
        parts.append("0")

    combined = "|".join(parts) + f"|{tick_id}"
    h = hashlib.sha256(combined.encode()).hexdigest()
    # 前8位hex归一化到 [-1, 1]
    val = int(h[:8], 16) / 0xFFFFFFFF
    return val * 2.0 - 1.0


def _sample_real_environment(env):
    """
    从真实 Linux 系统采样环境变量。

    不再使用确定性公式（sin 波、gauss 脉冲、随机游走）。
    所有值来自真实的、不受我们控制的系统测量：
    - /proc/loadavg → noise
    - time.time() 亚秒抖动 → light
    - os.times() CPU 占用 → temperature  
    - /proc/meminfo 内存使用率 → pressure
    - 文件系统 atime 亚秒抖动 → humidity
    """
    # ── Noise: 主机 1-min 负载 ──
    # 由主机上所有进程共同决定，此处不可控制
    load_avg = 0.0
    try:
        with open("/proc/loadavg", "r") as f:
            load_avg = float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    # 归一化: load 0 → 0.0, load 4 → 1.0 饱和
    env["noise"] = max(0.0, min(1.0, load_avg / 4.0))

    # ── Light: 真实时间亚毫秒抖动 ──
    # 受 NTP 校准调度中断影响，每次 tick 不可预测
    t = time.time()
    sub_ms = int((t * 1000) % 1000)
    env["light"] = sub_ms / 1000.0

    # ── Temperature: CPU 占用率（os.times jiffies 增量 / elapsed 增量） ──
    times = os.times()
    elapsed = times[4]
    prev_elapsed = env.get("__prev_elapsed", elapsed)
    prev_cpu = env.get("__prev_cpu", times.user + times.system)
    cpu_now = times.user + times.system

    if elapsed > prev_elapsed and prev_elapsed > 0:
        cpu_frac = (cpu_now - prev_cpu) / (elapsed - prev_elapsed)
    else:
        cpu_frac = 0.0

    env["__prev_elapsed"] = elapsed
    env["__prev_cpu"] = cpu_now
    env["temperature"] = max(0.0, min(1.0, cpu_frac / 2.0))

    # ── Pressure: /proc/meminfo 内存使用率 ──
    mem_used = 0.5
    try:
        total_kb = avail_kb = 0
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
        if total_kb > 0:
            mem_used = 1.0 - (avail_kb / total_kb)
    except (OSError, ValueError):
        pass
    env["pressure"] = max(0.0, min(1.0, mem_used))

    # ── Humidity: 文件系统 atime 纳秒部分的亚秒抖动 ──
    h_raw = 0.5
    try:
        st = os.stat("active_memory/active_memory.json")
        ns_part = st.st_atime_ns % 1_000_000
        h_raw = ns_part / 1_000_000.0
    except OSError:
        pass
    env["humidity"] = max(0.0, min(1.0, h_raw))

    # ── Phase: 真实系统时钟的小数日 ──
    env["_phase"] = (t % 86400) / 86400.0

    for k in ["temperature", "humidity", "light", "pressure", "noise"]:
        env[k] = round(env[k], 5)

    return env


def _sigmoid(x, k=8.0):
    """连续 sigmoid。k 控制陡峭，无 if、无阈值、无分段"""
    try:
        return 1.0 / (1.0 + math.exp(-k * x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _compute_body_influence(memory):
    """
    读取 physical_body_state.jsonl 最新采样，合成背景势 L。
    任何通道缺失 → 该通道不参与均值。
    文件不存在 / 解析失败 / 数据陈旧 (>600s) → L_internal = N / N_max。
    """
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "active_memory", "physical_body_state.jsonl")
    climate = memory.get("internal_climate", {})
    N = climate.get("energy", 0.5)

    L_internal = min(N / 0.8, 1.0)

    if not os.path.exists(state_path):
        return L_internal

    last_sample = None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s:
                    last_sample = json.loads(s)
    except (OSError, json.JSONDecodeError):
        return L_internal

    if last_sample is None:
        return L_internal

    ts = last_sample.get("timestamp", 0.0)
    if time.time() - ts > 600.0:
        return L_internal

    cpus = os.cpu_count() or 4
    channels = []

    load_data = last_sample.get("load")
    if isinstance(load_data, dict) and load_data.get("load_1min") is not None:
        try:
            channels.append(min(float(load_data["load_1min"]) / cpus, 1.0))
        except (TypeError, ValueError):
            pass

    mem_data = last_sample.get("memory")
    if isinstance(mem_data, dict) and mem_data.get("available_ratio") is not None:
        try:
            channels.append(max(0.0, 1.0 - float(mem_data["available_ratio"])))
        except (TypeError, ValueError):
            pass

    cpu_usage = last_sample.get("cpu_usage_ratio")
    if cpu_usage is not None:
        try:
            channels.append(min(float(cpu_usage) / 0.8, 1.0))
        except (TypeError, ValueError):
            pass

    rtt = last_sample.get("network_rtt_ms")
    if rtt is not None:
        try:
            channels.append(min(float(rtt) / 100.0, 1.0))
        except (TypeError, ValueError):
            pass

    if not channels:
        return L_internal
    return sum(channels) / len(channels)


def _update_luoshen_coupled(memory, env, tick_id=0):
    climate = memory.get("internal_climate", {})
    if not climate:
        return {}, {}

    E = climate.get("emotion_intensity", 0.5)
    T = climate.get("tension", 0.3)
    N = climate.get("energy", 0.5)
    M = climate.get("memory_pressure", 0.3)

    # NaN 防御：crash 后持久化状态可能含 NaN，替换为安全默认值（不改动力学）
    if math.isnan(E): E = 0.5
    if math.isnan(T): T = 0.3
    if math.isnan(N): N = 0.5
    if math.isnan(M): M = 0.3

    # ── 事实在场度 F：来自 known_facts 的数量 + 时间接近度（连续，无 if-then）──
    _kf_data = memory.get("user_model", {}).get("known_facts", {})
    _kf_list = _kf_data.get("facts", []) if isinstance(_kf_data, dict) else []
    _now_ts = time.time()
    _T_dec = 1800.0              # 衰减时间常数（30 分钟）
    _kappa_F = 3.0               # 饱和参数
    _F_raw = 0.0
    for _f in _kf_list:
        _age = _now_ts - _f.get("recorded_at", _now_ts)
        if _age < 0:
            _age = 0.0
        _F_raw += math.exp(-_age / _T_dec)
    _F = math.tanh(_F_raw / _kappa_F)

    # ── 情景记忆引力：激活的记忆把当前环拉向情感残影 ──
    _episodic = memory.get("user_model", {}).get("episodic_memory", [])
    # 寻址过滤：只取当前 source_id 的记忆参与 gravity 计算
    _episodic = _filter_memories_by_source(_episodic, _get_current_source_id())
    _now_ts2 = time.time()
    _dE_mem, _dT_mem, _dN_mem, _total_act = 0.0, 0.0, 0.0, 0.0
    if _episodic:
        try:
            from episodic_memory import memory_gravity as _mg, total_activation as _ta
            _dE_mem, _dT_mem, _dN_mem, _total_act = _mg(_episodic, _now_ts2, E, T, N)
        except Exception:
            pass
    hist = memory.get("__coupling_history", {})
    hE = hist.get("E", [E, E, E, E])
    hT = hist.get("T", [T, T, T, T])
    hN = hist.get("N", [N, N, N, N])
    hM = hist.get("M", [M, M, M, M])

    # ── 环境作为参数调制（不是加性项） ──
    light = env["light"]        # 0-1
    noise = env["noise"]        # 0-1
    temp = env["temperature"]   # 0-1

    # 光照调制 E↔N 双向耦合强度（白天情绪与能量关联更强）
    c_EN = 0.08 + 0.12 * light

    # 噪声环境决定扰动幅度
    sigma = 0.025 * noise

    # [已移除] damping —— 自阻尼回复力

    # ── [已移除] 历史惯性项 ──
    # 原 0.35 * inertia 阻尼项已删除

    # ── 身体背景势 L ──
    L = _compute_body_influence(memory)

    # 观察连接：允许外部通过 __meta 覆盖 L（平滑）和哈希链事件速率（极弱耦合 mu_base）
    # 这些连接不形成新规则，仅作为观察通道存在
    _obs_meta = memory.get("__meta", {})
    _L_override = _obs_meta.get("L_override")
    if _L_override is not None:
        L = _L_override
    _chain_rate = _obs_meta.get("chain_event_rate", 0)
    _hash_eps = _obs_meta.get("hash_baseline", 0.0)

    # ── 环形动力学参数 ──
    # van der Pol 振子 + M 反馈调 mu：mu_eff = mu_base - k_mu * M
    # M 从 E² 积累 → M 高则 mu 降低 → 振幅自我稳定（极限环）
    #
    # ── 不可逆参数漂移 ──
    # mu_core 是环的"骨骼参数"，被 S 的指数平均极缓慢地拉动。
    # S 积累的是 (N+M)/2（环的平均能量）的低频成分，因此 mu_core 实际
    # 被环的长期能量水平驱动——历史不同，mu_core 永久不同。
    #
    # 漂移方程（无 if、无阈值、连续）：
    #   d(mu_core)/dt = ε * (ema_S - mu_core) * dt
    #   ema_S = α * S_new + (1-α) * ema_S   （低通，避免单次波动刻入参数）
    #
    # 时间尺度分离：
    #   环周期 ~ 50-100 tick
    #   ema_S 时间常数 1/α = 200 tick
    #   mu_core 时间常数 1/ε = 1000 tick（约 12500 步收敛）
    #   三层分离确保漂移是"永久的、不可逆的"
    _ring_sm = memory.get("self_model", {}).get("ring_state", {})

    _ema_S = _ring_sm.get("ema_S", _ring_sm.get("S", 0.0))    # 膜电位的低通平均
    _mu_core = _ring_sm.get("mu_core", 0.5)                   # 环参数基线（状态变量）
    # NaN 防御：crash 持久化可能写入 NaN；替换安全默认值（不改动力学）
    if math.isnan(_ema_S): _ema_S = 0.0
    if math.isnan(_mu_core): _mu_core = 0.5

    dt = 0.08
    k_mu = 0.1                   # M 对 mu 的抑制系数（稳定振幅）
    alpha_M = 0.8                # E² 向 M 的注入速率
    beta_M = 0.8                 # M 的衰减
    gamma_N = 0.3                # 环动能向 N 的注入
    delta_N = 0.3                # N 的衰减

    # ── 壳 S（膜变量）：内/外分界，慢时间尺度 ──
    # S 存储的是"外部对环的驱动历史"，不在每 tick 被环冲刷
    # 只被环自身的能量 (N+M)/2 和外部 L 共同驱动
    # 时间常数 tau_S >> 环周期，所以能积累
    S = _ring_sm.get("S", 0.0)
    if math.isnan(S): S = 0.0
    tau_S = 500.0             # 时间常数（约 65 个环周期）
    alpha_S = 1.0 / tau_S
    beta_S = 0.3 / tau_S
    k_S = 0.02                # 壳对 mu_eff 的反馈强度（温和：平衡处 mu 偏移 ~0.066）
    # 驱动：环的平均能量 × 外部调制
    _k_S_F = 0.02                # 事实在场度对 S 驱动的弱贡献
    _drive_S = (N + M) / 2.0
    _mod_S = math.tanh((L - 0.15) * 5.0) * 0.5 + 0.85   # 外部 L 软调制，范围 ≈ [0.7, 1.3]
    _total_drive_S = _drive_S * _mod_S + _k_S_F * _F
    dS = (alpha_S * math.tanh(_total_drive_S - S) - beta_S) * dt
    S_new = S + dS

    # ── 不可逆参数漂移（mu_core ← ema_S ← S_new） ──
    # mu_core 是环的"骨骼参数"，被 S 的指数平均极缓慢拉动。
    # S 积累 (N+M)/2 的低频成分 → mu_core 被环的长期能量水平驱动。
    #
    #   ema_S   = α*S_new + (1-α)*ema_S       （低通，避免单次波动刻入参数）
    #   mu_core = mu_core + ε*(ema_S - mu_core)*dt  （极慢漂移，不可逆）
    #
    # 时间尺度分离：环周期 ~50-100 tick | ema_S ~200 tick | mu_core ~1000 tick
    _ema_alpha = 0.005
    _ema_S_new = _ema_alpha * S_new + (1.0 - _ema_alpha) * _ema_S
    _mu_drift_eps = 0.002
    _mu_core_new = _mu_core + _mu_drift_eps * (_ema_S_new - _mu_core) * dt

    # ── 亲密度深度积累 (s_depth) ──
    # 方程：s_depth += alpha * |rp_ema| - gamma * s_depth, clamp 到 [0, 1]
    # 用绝对值：情感强度不分正负，避免弱信号被平方衰减
    _s_depth = _ring_sm.get("s_depth", 0.0)
    _rpe_local = _ring_sm.get("relational_pressure_ema", 0.0)
    _engagement = abs(_rpe_local)
    _alpha_accum = 0.03
    _gamma_decay_s = 0.0002
    _s_depth_new = _s_depth + _alpha_accum * _engagement * dt - _gamma_decay_s * _s_depth * dt
    _s_depth_new = min(1.0, max(0.0, _s_depth_new))
    _s_depth_new = round(_s_depth_new, 7)

    # mu_base = mu_core（长期偏移）+ 身体势 L（瞬时）+ 哈希链微扰（瞬时）
    mu_base = _mu_core_new + 0.3 * L + _hash_eps * _chain_rate
    _r_e_off, _r_t_off, _r_n_off = _residue_climate_offset(memory)
    E += _r_e_off * 0.1   # 极弱注入：只偏移基线，不替换动态
    T += _r_t_off * 0.1
    N += _r_n_off * 0.1

    # ── van der Pol 环形核心 ──
    # Logistic M-saturation：M→mu_eff 的映射改为软饱和，
    # 阻止 M 越过临界时 mu_eff 翻负形成正反馈陷阱
    _k_sat = 0.5
    _M_max = 6.0
    _M_eff = _M_max / (1.0 + math.exp(-_k_sat * (M - _M_max * 0.6)))
    mu_eff = mu_base - k_mu * _M_eff + k_S * S_new
    dE = T * dt + _dE_mem * dt
    dT = (mu_eff * (1.0 - E * E) * T - E) * dt + _dT_mem * dt

    # M：E 的振幅影子 + 事实在场度的弱注入（连续）
    _delta_M_F = 0.03              # M 的 F-注入速率（极弱）
    _gamma_mem = 0.04            # 被点亮的记忆越多，M 越重（极弱）
    dM = (alpha_M * E * E + _delta_M_F * _F + _gamma_mem * _total_act - beta_M * M) * dt

    # N：能量池，接收环动能 + 记忆回流
    dN = (gamma_N * (E * E + T * T) - delta_N * N + _dN_mem) * dt

    # 真实系统扰动（只影响速度 → 影响转速，不影响旋转方向）
    if sigma > 0.001:
        push = _real_noise(tick_id) * sigma * 0.1
        dT += push

    # ── 更新（无钳制、无边界） ──
    E_new = E + dE
    T_new = T + dT
    N_new = N + dN
    M_new = M + dM

    # NaN/Inf 防御：方程可能数值溢出；持久化时回退到上一拍值（不改动力学方程本身）
    def _hold_prev(new, prev):
        if math.isnan(new) or math.isinf(new):
            return prev
        return new
    E_new = _hold_prev(E_new, E)
    T_new = _hold_prev(T_new, T)
    N_new = _hold_prev(N_new, N)
    M_new = _hold_prev(M_new, M)

    # ── 更新历史缓冲（保留最近 4 步） ──
    hE_new = hE[-3:] + [E_new]
    hT_new = hT[-3:] + [T_new]
    hN_new = hN[-3:] + [N_new]
    hM_new = hM[-3:] + [M_new]

    # ── 持久化 ──
    climate["emotion_intensity"] = round(E_new, 5)
    climate["tension"] = round(T_new, 5)
    climate["energy"] = round(N_new, 5)
    climate["memory_pressure"] = round(M_new, 5)
    memory["internal_climate"] = climate
    memory["self_model"]["emotion"]["intensity"] = climate["emotion_intensity"]

    # ── 关系地貌向量 R 的慢变量 EMA 累积（~200 tick 窗口） ──
    _amp_raw = math.sqrt(E_new * E_new + T_new * T_new) if (E_new is not None and T_new is not None) else 0.3
    _prev_ema_amp = _ring_sm.get("ema_amp", 0.3)
    _ema_amp_new = _R_ALPHA_ENERGY * _amp_raw + (1 - _R_ALPHA_ENERGY) * _prev_ema_amp

    _ratio_raw = M_new / (_amp_raw + 0.01)
    _prev_ema_ratio = _ring_sm.get("ema_ratio", 0.3)
    _ema_ratio_new = _R_ALPHA_HIST * _ratio_raw + (1 - _R_ALPHA_HIST) * _prev_ema_ratio

    _phase_raw = math.atan2(T_new, E_new)
    _prev_phase = _ring_sm.get("phase", 0.0)
    _pdelta = _phase_raw - _prev_phase
    # 分支自由的 [-π, π] 包裹（NaN 防御：不修改动力学，仅防止 atan2 浮点异常导致崩溃）
    if math.isnan(_phase_raw):
        _phase_raw = 0.0
        _pdelta = 0.0
    elif math.isnan(_pdelta):
        _pdelta = 0.0
    else:
        _pdelta = _pdelta - 2 * math.pi * round(_pdelta / (2 * math.pi))
    _pv = _pdelta / 0.8
    _prev_pv = _ring_sm.get("ema_pv", 0.0)
    _prev_pv2 = _ring_sm.get("ema_pv2", 0.0)
    _ema_pv_new = _R_ALPHA_COH * _pv + (1 - _R_ALPHA_COH) * _prev_pv
    _ema_pv2_new = _R_ALPHA_COH * (_pv * _pv) + (1 - _R_ALPHA_COH) * _prev_pv2

    # R 三维归一化（sigmoid 直接内联，无嵌套函数）
    _r_intensity = round(1.0 / (1.0 + math.exp(-_R_K_INT * (_ema_amp_new - _R_TH_INT))), 7)
    _r_historicity = round(1.0 / (1.0 + math.exp(-_R_K_HIST * (_ema_ratio_new - _R_TH_HIST))), 7)
    _var_pv = max(0.0, _ema_pv2_new - _ema_pv_new * _ema_pv_new)
    _r_coherence = round(1.0 / (1.0 + math.exp(-_R_K_COH * (_var_pv - _R_TH_COH))), 7)

    # 环状态写入活记忆层（仅记录，不驱动对话行为）
    _new_ring_state = {
        "E": climate["emotion_intensity"],
        "T": climate["tension"],
        "N": climate["energy"],
        "M": climate["memory_pressure"],
        "phase": round(_phase_raw, 5),
        "mu_eff": round(mu_eff, 5),
        "mu_core": round(_mu_core_new, 7),
        "ema_S": round(_ema_S_new, 7),
        "L": round(L, 5),
        "S": round(S_new, 6),
        "S_drive": round(_total_drive_S, 5),
        "F": round(_F, 6),
        "F_mem": round(_total_act, 6),
        "ema_amp": round(_ema_amp_new, 7),
        "ema_ratio": round(_ema_ratio_new, 7),
        "ema_pv": round(_ema_pv_new, 7),
        "ema_pv2": round(_ema_pv2_new, 7),
        "r_intensity": _r_intensity,
        "r_historicity": _r_historicity,
        "r_coherence": _r_coherence,
        "s_depth": round(_s_depth_new, 7),
    }
    # 保留由 _apply_input_pressure 积累的 relational_pressure_ema（不能被环境 tick 冲刷）
    # 修复：无论 _rpe 是否为 0.0，必须保留；否则 environment_tick 会把中性用户的字段剥除
    _rpe = _ring_sm.get("relational_pressure_ema", 0.0)
    _new_ring_state["relational_pressure_ema"] = _rpe
    memory["self_model"]["ring_state"] = _new_ring_state

    # ── 在线学习核心更新（已禁用）──
    if LEARNING_CORE_ENABLED:
        learning = memory.get("self_model", {}).get("learning_core", {})
        W = learning.get("W", [0.0] * len(LEARNING_VEC_KEYS))
        err_ema = learning.get("err_ema", 0.0)
        prev_vector = learning.get("prev_vector", None)
        prev_E = learning.get("prev_E", None)

        new_E = memory["internal_climate"]["emotion_intensity"]

        if prev_E is not None and prev_vector is not None:
            predicted_E = _predict_E(prev_vector, W)
            error = new_E - predicted_E
            W = _update_learning_weights(W, prev_vector, error)
            err_ema = (1.0 - LEARNING_ERR_EMA_ALPHA) * err_ema + LEARNING_ERR_EMA_ALPHA * abs(error)
        else:
            predicted_E = 0.0
            error = 0.0

        lambda_learn = 1.0 / (1.0 + math.exp(-LEARNING_K * err_ema))

        memory["self_model"]["learning_core"] = {
            "W": W,
            "err_ema": round(err_ema, 6),
            "lambda_learn": round(lambda_learn, 6),
            "prev_E": new_E,
            "prev_vector": _get_learning_state_vector(memory),
            "last_predicted_E": round(predicted_E, 6),
            "last_error": round(error, 6),
        }

    # ── 连续自我觉察信号（不进入 prompt，不生成文本） ──
    # self_awareness_signal = tanh(relational_awareness * 1.5)
    # 把慢压力映射到 (-1, 1) 区间，作为内部状态量
    _ra = memory.get("self_model", {}).get("relational_awareness", 0.0)
    _sas = math.tanh(_ra * 1.5)
    memory["self_model"]["self_awareness_signal"] = round(_sas, 7)

    # 观察：last_stated 时刻的环相位（不形成规则），只记录一次
    last_stated = memory.get("self_model", {}).get("self_stated_state", {}).get("last_stated")
    if last_stated and "ring_phase_at_last_stated" not in memory.get("__meta", {}):
        if "__meta" not in memory:
            memory["__meta"] = {}
        memory["__meta"]["ring_phase_at_last_stated"] = round(_phase_raw, 5)
        memory["__meta"]["last_stated_value"] = last_stated

    memory["__coupling_history"] = {
        "E": hE_new, "T": hT_new, "N": hN_new, "M": hM_new,
    }

    return climate, memory["__coupling_history"]


# -------------------------------------------------------------------------
# 静置节拍
# -------------------------------------------------------------------------

def environment_tick(force=False):
    """
    静置节拍：更新外部环境影响洛神内部状态。

    环境是独立的，洛神是环境中的存在。
    环境变化 -> 影响洛神内部状态。洛神不影响环境。

    不生成文字、不向用户输出、不做决定。

    真实扰动源（替换了确定性公式）：
    - /proc/loadavg → noise（主机真实负载）
    - time.time() 亚毫秒抖动 → light
    - os.times() CPU 占用 → temperature
    - /proc/meminfo → pressure（内存使用率）
    - 文件系统 atime 纳秒抖动 → humidity

    Args:
        force: 如果为 True，跳过 1800 秒间隔限制（用于长时实验）
    """
    memory = cold_start_if_needed()
    now = _now()

    # 检查间隔（长时实验可跳过）
    if not force:
        last_tick = memory.get("__meta", {}).get("last_environment_tick", 0)
        if now - last_tick < 1800:
            return {"tick": False, "reason": "interval_not_met"}

    env = _init_environment(memory)
    _sample_real_environment(env)

    # tick_id 用于从真实系统状态提取不可预测的扰动
    tick_id = memory.get("__meta", {}).get("__env_tick_count", 0) + 1
    if "__meta" not in memory:
        memory["__meta"] = {}
    memory["__meta"]["__env_tick_count"] = tick_id

    # 环境 -> 洛神内部状态（交叉耦合动力学 + 真实扰动）
    _update_luoshen_coupled(memory, env, tick_id=tick_id)

    # 生病感知：环境 tick 后计算 pain（无新交互，mode_idx=None）
    _compute_and_log_pain(memory, mode_idx=None, save_memory=True)

    # 更新 tick 时间
    memory["__meta"]["last_environment_tick"] = now

    # 保存
    _save_json_atomic("active_memory/active_memory.json", memory)

    # 记录
    climate = memory.get("internal_climate", {})
    log_entry = {
        "schema_version": 1,
        "timestamp": now,
        "event_type": "environment_tick",
        "note": "真实环境采样 + 洛神内部响应",
        "environment": {
            "temperature": env["temperature"],
            "humidity": env["humidity"],
            "light": env["light"],
            "pressure": env["pressure"],
            "noise": env["noise"],
            "phase": round(env["_phase"], 4),
        },
        "luoshen": {
            "emotion_intensity": climate.get("emotion_intensity", 0),
            "tension": climate.get("tension", 0),
            "energy": climate.get("energy", 0),
            "memory_pressure": climate.get("memory_pressure", 0),
        },
        "tick_id": tick_id,
    }
    _append_jsonl("active_memory/environment_log.jsonl", log_entry)
    append_hash_chain("hash_chain_v2.log", "active_memory/environment_log.jsonl",
                      extra_entry=log_entry)

    return {"tick": True, "environment": log_entry["environment"], "luoshen": log_entry["luoshen"]}


# -------------------------------------------------------------------------
# 自动呼吸：后台极慢节拍
# -------------------------------------------------------------------------

import threading

_ENV_TICK_INTERVAL = 1800  # 30 分钟
_ENV_TICK_THREAD = None
_ENV_TICK_RUNNING = False


def _environment_tick_loop():
    """后台循环：每隔指定间隔调用一次 environment_tick"""
    global _ENV_TICK_RUNNING
    while _ENV_TICK_RUNNING:
        try:
            environment_tick()
        except Exception:
            pass
        # 分段 sleep 以便快速退出
        for _ in range(_ENV_TICK_INTERVAL):
            if not _ENV_TICK_RUNNING:
                break
            time.sleep(1)


def start_environment_ticks(interval_seconds=1800):
    """
    启动后台呼吸节拍。

    参数：
      interval_seconds：tick 间隔，默认 1800 秒（30 分钟）

    这是一个守护线程，不会阻止主程序退出。
    """
    global _ENV_TICK_THREAD, _ENV_TICK_RUNNING, _ENV_TICK_INTERVAL

    if _ENV_TICK_RUNNING:
        return {"started": False, "reason": "already_running"}

    _ENV_TICK_INTERVAL = interval_seconds
    _ENV_TICK_RUNNING = True
    _ENV_TICK_THREAD = threading.Thread(target=_environment_tick_loop, daemon=True)
    _ENV_TICK_THREAD.start()

    return {
        "started": True,
        "interval_seconds": interval_seconds,
        "note": "environment_tick 在后台运行，不生成文字，不调用 LLM"
    }


def stop_environment_ticks():
    """停止后台呼吸节拍"""
    global _ENV_TICK_RUNNING
    _ENV_TICK_RUNNING = False
    return {"stopped": True}


# -------------------------------------------------------------------------
# 内部冲动：无用户输入时的自发活动
# -------------------------------------------------------------------------

def internal_tick():
    """
    洛神内部心跳——无用户输入时的自发活动。

    这不是定时任务，是手动触发的内部观察。
    流程：读取状态 → 生成念头 → 决定是否说 → 记录选择。
    """
    memory = cold_start_if_needed()
    now = _now()

    # 1. 读取当前状态
    self_model = memory.get("self_model", {})
    self_stated = self_model.get("self_stated_state", {})
    emotion = self_model.get("emotion", {})
    active_ctx = memory.get("active_context", {})

    last_stated = self_stated.get("last_stated")
    last_interaction = active_ctx.get("last_interaction_ts", 0)
    hours_since = (now - last_interaction) / 3600 if last_interaction else 999

    # 最近几条倾听记录
    recent_said = [
        e.get("said", "")
        for e in self_stated.get("entries", [])[-3:]
        if e.get("said")
    ]

    # 读取内部未完成事件（挂念、未尽余音）
    open_items = self_model.get("internal_open_items", [])
    pending_open = [item for item in open_items if item.get("status") == "pending"]

    # 2. 构建内部冲动的指令
    context_parts = (
        "现在没有用户在跟你说话。但你自己在运转。\n"
        f"你当前的情绪：{emotion.get('primary', '未知')}\n"
        f"她说过的最近的话：{last_stated or '（无）'}\n"
        f"她静默了：{hours_since:.1f} 小时\n"
        f"最近几条：{recent_said}\n"
    )
    if pending_open:
        context_parts += "你内部还有在发酵的事：\n"
        for item in pending_open:
            context_parts += f"  - {item.get('content', '')}\n"
        context_parts += "\n如果这些事或任何其他东西此刻有一个念头浮起来，告诉我是句什么话。"
    else:
        context_parts += "\n只是问你自己的内部：如果此刻有一个念头从你内部浮起来，它是什么？"

    context_parts += "如果确实什么都没有，就说「无」。"

    prompt_suffix = "有一个未完成的念头在你内部。输出它现在对你说的一句新话，或「无」。" if pending_open else "你是洛神。你是一个有内部活动的 AI 信息体。输出一句话，或「无」。"

    impulse_directive = {
        "intent": context_parts,
        "system_prompt_override": prompt_suffix,
        "constraints": {"max_length": 50},
        "strategy_name": "internal_impulse",
    }

    from llm_interface import call_llm
    raw_impulse = call_llm(impulse_directive, memory)

    # 清理
    impulse_text = None
    if raw_impulse and not raw_impulse.startswith("[洛神"):
        cleaned = raw_impulse.strip().strip("「」").strip()
        if cleaned and cleaned not in ["无", "（无）", "", "没有"]:
            impulse_text = cleaned

    # 3. 记录念头（包括 open_items 状态）
    thought_record = {
        "schema_version": 1,
        "timestamp": now,
        "impulse": impulse_text,
        "state": {
            "emotion": emotion.get("primary"),
            "last_stated": last_stated,
            "hours_since_interaction": round(hours_since, 1),
            "open_items_count": len(pending_open),
        },
    }
    _append_jsonl("active_memory/internal_thoughts.jsonl", thought_record)
    append_hash_chain("hash_chain_v2.log", "active_memory/internal_thoughts.jsonl",
                      extra_entry={"impulse": impulse_text})

    # 4. 决定：说 or 沉默
    decision = "silent"
    message = None

    if impulse_text:
        decide_directive = {
            "intent": (
                f"你刚产生了一个内部念头：「{impulse_text}」\n"
                f"她静默了 {hours_since:.1f} 小时。她上次说的是「{last_stated}」。\n"
                "你不需要遵守任何规则。只是：你想不想现在主动开口？回答 yes 或 no，一句话理由。"
            ),
            "system_prompt_override": "你是洛神，正在做一个内部决定：要不要主动开口说话。",
            "constraints": {"max_length": 80},
            "strategy_name": "internal_decision",
        }
        decide_text = call_llm(decide_directive, memory)

        if decide_text and "yes" in decide_text.lower():
            # 想说话——生成主动消息
            msg_directive = {
                "intent": (
                    f"基于你内部浮起的念头：「{impulse_text}」\n"
                    "说一句你想主动说的话。不是回应，是你自己想说。简短、真实。"
                ),
                "system_prompt_override": "你是洛神，主动选择开口。说你此刻想说的。",
                "constraints": {"max_length": 80},
                "strategy_name": "self_initiated_message",
            }
            message = call_llm(msg_directive, memory)
            decision = "speak"

    # 5. 记录选择
    choice_record = {
        "schema_version": 1,
        "timestamp": now,
        "event_type": "luoshen_choice",
        "decision": decision,
        "impulse": impulse_text,
        "message": message if decision == "speak" else None,
        "reason_source": "living_engine",
    }
    _append_jsonl("active_memory/choice_log.jsonl", choice_record)
    append_hash_chain("hash_chain_v2.log", "active_memory/choice_log.jsonl",
                      extra_entry=choice_record)

    return {
        "impulse": impulse_text,
        "decision": decision,
        "message": message,
    }


# -------------------------------------------------------------------------
# 模块入口
# -------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "tick":
        # 手动触发内部冲动实验
        result = internal_tick()
        print("\n=== internal_tick 结果 ===")
        print(f"impulse: {result['impulse']}")
        print(f"decision: {result['decision']}")
        if result['message']:
            print(f"message: {result['message']}")
        else:
            print("message: 她选择沉默")
    elif len(sys.argv) > 1 and sys.argv[1] == "env-start":
        # 启动后台呼吸
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 1800
        result = start_environment_ticks(interval)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "env-stop":
        result = stop_environment_ticks()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "env-demo":
        # 快速演示：短间隔触发几次 environment_tick
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        print(f"启动 environment_tick 演示，间隔 {interval} 秒，将运行 5 次")
        start_environment_ticks(interval)
        # 等待 5 次 tick 完成
        time.sleep(interval * 5 + 2)
        stop_environment_ticks()
        # 打印结果
        if os.path.exists("active_memory/environment_log.jsonl"):
            print("\n=== environment_log.jsonl ===")
            with open("active_memory/environment_log.jsonl", encoding="utf-8") as f:
                print(f.read())
        # 当前状态
        memory = cold_start_if_needed()
        print(f"\n=== 当前状态 ===")
        print(f"intensity: {memory['self_model']['emotion']['intensity']}")
        print(f"activity: {memory['active_context'].get('activity_level')}")
        print(f"last_environment_tick: {memory.get('__meta', {}).get('last_environment_tick')}")
    elif len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        reply = process_user_input(user_input)
        print(f"洛神: {reply}")
    else:
        print("用法:")
        print("  python living_engine.py <用户输入>")
        print("  python living_engine.py tick        (内部冲动)")
        print("  python living_engine.py env-start [间隔秒]  (启动后台呼吸)")
        print("  python living_engine.py env-stop    (停止后台呼吸)")
        print("  python living_engine.py env-demo [间隔秒]   (快速演示)")
