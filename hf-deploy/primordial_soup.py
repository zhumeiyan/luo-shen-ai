#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
primordial_soup.py v3 - 含催化互作的原始汤

设计变更（v3）：
  - 新增 CATALYZE 指令：消耗自身能量，给汤中所有"标签匹配"的单元加能量
  - 催化是无差别的、无目标的——单元自己不知道被喂养的是谁
  - 收到催化帮助的单元，年龄税降低 50%（互作者更长寿）
  - 标签 = code hash & 0xF（4-bit，16 种可能），催化指令的 arg 指定目标标签
  - 如果 A 变异出 CATALYZE_7，而汤里有 B 的标签正好是 7，A 就会喂养 B
  - 不需要设计者指定谁帮助谁，网络是涌现的
"""

import json
import os
import random
import time
import math

# Paths
SOUP_STATE_PATH = "active_memory/primordial_soup.json"
SOUP_EVENT_LOG = "active_memory/soup_events.jsonl"

# 参数
MAX_UNITS = 100
MAX_UNIT_SIZE = 32
POOL_TOTAL = 200
TICK_INTERVAL = 300
MUTATION_RATE = 0.05
POOL_DIMS = 8
CATALYZE_COST = 2        # 催化消耗
CATALYZE_GIFT  = 1       # 被催化者获得的能量
IMMUNITY_WINDOW = 5      # 收到催化后 5 tick 内年龄税减半

OPCODES = [
    "NOP",
    "EAT",
    "EMIT",
    "DUP",
    "SWAP",
    "SPAWN",
    "CATALYZE",   # v3 新增
]


def unit_tag(unit):
    """用 code hash 最后 4 位作为标签（0-15）"""
    return hash(tuple(tuple(i) for i in unit["code"])) & 0xF


def random_instruction():
    weights = [0.18, 0.22, 0.18, 0.15, 0.10, 0.08, 0.09]  # 给 CATALYZE 留出权重
    op = random.choices(OPCODES, weights=weights, k=1)[0]
    if op in ("NOP", "DUP"):
        return [op, 0, 0]
    elif op in ("EAT", "EMIT", "SPAWN", "CATALYZE"):
        return [op, random.randint(0, POOL_DIMS - 1), 0]
    elif op == "SWAP":
        return [op, random.randint(0, POOL_DIMS - 1), random.randint(0, POOL_DIMS - 1)]
    return ["NOP", 0, 0]


def random_unit(id_hint=None):
    size = random.randint(2, 6)
    return {
        "id": id_hint if id_hint is not None else random.randint(10000, 99999),
        "code": [random_instruction() for _ in range(size)],
        "energy": 20,
        "age": 0,
        "replications": 0,
        "birth_tick": 0,
        "last_catalyzed": -999,   # 上次收到催化是什么时候
        "tag": -1,                # 缓存，每 tick 重算
    }


def mutate_unit(unit):
    new_code = [list(instr) for instr in unit["code"]]
    for i in range(len(new_code)):
        if random.random() < MUTATION_RATE:
            new_code[i] = random_instruction()
    if random.random() < MUTATION_RATE and len(new_code) < MAX_UNIT_SIZE:
        new_code.insert(random.randint(0, len(new_code)), random_instruction())
    if random.random() < MUTATION_RATE and len(new_code) > 1:
        del new_code[random.randint(0, len(new_code) - 1)]
    if len(new_code) > MAX_UNIT_SIZE:
        new_code = new_code[:MAX_UNIT_SIZE]
    return {
        "id": random.randint(10000, 99999),
        "code": new_code,
        "energy": 10,
        "age": 0,
        "replications": 0,
        "birth_tick": 0,
        "last_catalyzed": -999,
        "tag": -1,
    }


class PrimordialSoup:
    def __init__(self, state_path=None, event_log_path=None):
        self.state_path = state_path or SOUP_STATE_PATH
        self.event_log_path = event_log_path or SOUP_EVENT_LOG
        self.load()

    def load(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r") as f:
                    state = json.load(f)
                self.units = state.get("units", [])
                self.pool = state.get("pool", [0.0] * POOL_DIMS)
                self.tick_count = state.get("tick_count", 0)
                self.history = state.get("history", {})
                return
            except Exception:
                pass
        self.units = [random_unit(i + 1) for i in range(8)]
        self.pool = [5.0] * POOL_DIMS
        self.tick_count = 0
        self.history = {}

    def save(self):
        state = {
            "units": self.units,
            "pool": self.pool,
            "tick_count": self.tick_count,
            "history": self.history,
        }
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, self.state_path)

    def log_event(self, entry):
        entry.setdefault("tick", self.tick_count)
        entry.setdefault("ts", time.time())
        with open(self.event_log_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def execute_unit(self, unit, all_units):
        """执行一个单元，返回 (produced, consumed, wants_replication)"""
        produced = []
        consumed = []
        wants_replication = False

        for instr in unit["code"]:
            op = instr[0]
            arg1 = instr[1] if len(instr) > 1 else 0

            if op == "NOP":
                pass

            elif op == "EAT":
                if self.pool[arg1] >= 1.0:
                    self.pool[arg1] -= 1.0
                    unit["energy"] += 1
                    consumed.append((arg1, 1.0))
                else:
                    unit["energy"] -= 1

            elif op == "EMIT":
                if unit["energy"] >= 1:
                    self.pool[arg1] += 0.8
                    unit["energy"] -= 1
                    produced.append((arg1, 0.8))

            elif op == "SWAP":
                transfer = min(1.0, self.pool[arg1])
                if transfer > 0:
                    self.pool[arg1] -= transfer
                    self.pool[instr[2]] += transfer

            elif op == "DUP":
                wants_replication = True

            elif op == "SPAWN":
                if unit["energy"] >= 5 and len(unit["code"]) < MAX_UNIT_SIZE:
                    unit["code"].append(random_instruction())
                    unit["energy"] -= 5

            elif op == "CATALYZE":
                # 消耗自身能量，喂养汤里所有标签匹配 arg 的其他单元
                if unit["energy"] >= CATALYZE_COST:
                    unit["energy"] -= CATALYZE_COST
                    for other in all_units:
                        if other is unit:
                            continue
                        if other["tag"] < 0:
                            other["tag"] = hash(tuple(tuple(i) for i in other["code"])) & 0xF
                        if other["tag"] == arg1:
                            other["energy"] += CATALYZE_GIFT
                            other["last_catalyzed"] = self.tick_count

        return produced, consumed, wants_replication

    def step_tick(self):
        self.tick_count += 1

        # 计算每个标签有多少单元（用于统计）
        tag_counts = {}
        for u in self.units:
            tag = unit_tag(u)
            u["tag"] = tag
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # 1. 环境注入：中等强度，不无限支持
        total_bio = sum(u["energy"] for u in self.units)
        env_factor = max(0.2, 1.0 - total_bio / 600.0)
        for d in range(POOL_DIMS):
            self.pool[d] = max(0, self.pool[d] * 0.85 + env_factor * 1.2 + random.gauss(0, 0.2))

        # 2. 年龄税：互作者减半
        for u in self.units:
            age = u["age"]
            tax = 0.015 * math.log1p(age)
            ticks_since_catalyzed = self.tick_count - u["last_catalyzed"]
            if ticks_since_catalyzed <= IMMUNITY_WINDOW:
                tax *= 0.5
            u["energy"] -= tax

        # 3. 执行
        random.shuffle(self.units)
        replication_requests = []
        for idx, unit in enumerate(self.units):
            if unit["energy"] <= 0:
                continue
            unit["age"] = unit.get("age", 0) + 1
            _, _, wants_rep = self.execute_unit(unit, self.units)
            if wants_rep and unit["energy"] >= 15:
                replication_requests.append(idx)

        # 4. 复制
        new_units = []
        for idx in replication_requests:
            if len(self.units) + len(new_units) >= MAX_UNITS:
                break
            parent = self.units[idx]
            cost = 8 + len(parent["code"])
            if parent["energy"] >= cost:
                parent["energy"] -= cost
                parent["replications"] = parent.get("replications", 0) + 1
                child = mutate_unit(parent)
                child["birth_tick"] = self.tick_count
                child["tag"] = -1
                new_units.append(child)

        self.units.extend(new_units)

        # 5. 死亡
        self.units = [u for u in self.units if u["energy"] > 0]
        while len(self.units) > MAX_UNITS:
            worst = min(range(len(self.units)), key=lambda i: self.units[i]["energy"])
            del self.units[worst]

        # 6. 记录
        tag_str = ",".join(f"{t}:{c}" for t, c in sorted(tag_counts.items()))
        self.history[self.tick_count] = {
            "unit_count": len(self.units),
            "pool_sum": round(sum(self.pool), 2),
            "avg_energy": round(sum(u["energy"] for u in self.units) / max(1, len(self.units)), 2),
            "max_age": max((u["age"] for u in self.units), default=0),
            "total_replications": sum(u.get("replications", 0) for u in self.units),
            "unique_codes": len(set(tuple(tuple(instr) for instr in u["code"]) for u in self.units)),
            "catalyzed_this_tick": sum(1 for u in self.units if self.tick_count - u.get("last_catalyzed", -999) <= IMMUNITY_WINDOW),
            "tag_distribution": tag_str,
        }

        self.save()
        return self.history[self.tick_count]


if __name__ == "__main__":
    import sys
    soup = PrimordialSoup()
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        soup.units = [random_unit(i + 1) for i in range(8)]
        soup.pool = [5.0] * POOL_DIMS
        soup.tick_count = 0
        soup.history = {}
        soup.save()
        print("原始汤已初始化：8 个随机单元")
    elif len(sys.argv) > 1 and sys.argv[1] == "tick":
        result = soup.step_tick()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"unit 数: {len(soup.units)}")
        for u in soup.units:
            codes = " ".join(f"{i[0]}{i[1]}" if len(i) > 1 else i[0] for i in u["code"])
            print(f"  #{u['id']}  E={u['energy']:.1f}  age={u['age']}  rep={u['replications']}  tag={u['tag']}  code=[{codes}]")
    else:
        print("Usage: python3 primordial_soup.py init | tick")
