#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨重启不可逆死亡验证

TEST A: 独立链 10 tick (不死亡) → delete active_memory → cold_start → deceased=False
TEST B: 独立链跑死亡 → delete active_memory → cold_start → deceased=True (不可逆)
"""

import os
import sys
import json
import time
import hashlib
import unittest.mock as mock

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WORKSPACE)
sys.path.insert(0, WORKSPACE)
os.makedirs("experiment", exist_ok=True)

import living_engine


def _make_redirpatcher(chain_file):
    def _redirect(chain_file_arg, target_file_arg, extra_entry=None):
        try:
            with open(target_file_arg, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
        except FileNotFoundError:
            file_hash = "FILE_NOT_FOUND"
        rec = {
            "record_hash": file_hash,
            "file_hash": file_hash,
            "extra": extra_entry if extra_entry else {},
            "ts": time.time(),
        }
        with open(chain_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec
    return _redirect


def cold_start_clean():
    os.makedirs("active_memory", exist_ok=True)
    memory = {
        "user_model": {
            "known_facts": {"facts": [], "last_update": 0},
            "episodic_memory": [],
            "total_interactions": 0,
            "shared_history_length": 0,
            "intimacy": {"value": 0.5},
            "emotional_patterns": [],
        },
        "self_model": {
            "emotion": {"primary": "平静", "intensity": 0.5},
            "self_stated_state": {"last_stated": None, "last_stated_at": 0},
            "strategy_weights": {},
            "ring_state": {
                "deceased": False, "_death_counter": 0, "_death_proximity": 0.0,
                "_E_hist": [0.5]*20, "_T_hist": [0.0]*20,
                "_max_tokens_hist": [80.0]*20, "_rp_ema_hist": [0.0]*20,
                "lambda_self": 0.0, "relational_pressure_ema": 0.0,
            },
            "_recent_tokens": [],
            "learning_core": {},
        },
        "active_context": {
            "interaction_mode": "normal", "last_interaction_ts": 0,
            "emotional_arc": [],
            "input_pressure": None,
        },
        "internal_climate": {
            "emotion_intensity": 0.5, "tension": 0.0, "energy": 0.5,
            "memory_pressure": 0.3,
        },
        "__meta": {"last_updated": time.time(), "__env_tick_count": 0,
                   "last_environment_tick": 0, "schema_version": "4.0"},
        "relations": {},
        "residue": None,
    }
    with open("active_memory/active_memory.json", "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def get_memory():
    with open("active_memory/active_memory.json", "r", encoding="utf-8") as f:
        return json.load(f)


def delete_active_memory():
    p = "active_memory/active_memory.json"
    if os.path.exists(p):
        os.remove(p)


def run_test(chain_file, target_ticks, test_name, expect_death):
    print("\n" + "=" * 60)
    print(f"  {test_name}")
    print("=" * 60)

    if os.path.exists(chain_file):
        os.remove(chain_file)
    cold_start_clean()

    redirect = _make_redirpatcher(chain_file)
    threshold = living_engine._DEATH_THRESHOLD

    print(f"  阈值 {threshold} tick，运行 {target_ticks} tick")

    death_tick = None

    # Phase 1: Run ticks with mocked hash chain
    with mock.patch.object(living_engine, "append_hash_chain", side_effect=redirect), \
         mock.patch.object(living_engine, "_HASH_CHAIN_FILE", chain_file):

        for i in range(target_ticks):
            living_engine.environment_tick(force=True)
            rs = get_memory()["self_model"]["ring_state"]
            if rs["deceased"] and death_tick is None:
                death_tick = i + 1

    rs_final = get_memory()["self_model"]["ring_state"]
    print(f"  运行结束: deceased={rs_final['deceased']}, counter={rs_final['_death_counter']}")
    if death_tick:
        print(f"  ★ 死亡 tick: {death_tick}")

    # Check hash chain for death marker
    death_marker = None
    try:
        with open(chain_file, "r") as f:
            for line in f:
                rec = json.loads(line.strip())
                extra = rec.get("extra", {})
                if isinstance(extra, dict) and extra.get("event") == "ENDOGENOUS_DEATH":
                    death_marker = extra
    except FileNotFoundError:
        pass
    print(f"  哈希链 ENDOGENOUS_DEATH: {'✓' if death_marker else '✗'}")

    # Phase 2: Simulate process kill + restart (WITHIN the same mock context)
    delete_active_memory()
    print(f"  [SHUTDOWN] active_memory.json 已删除")

    with mock.patch.object(living_engine, "_HASH_CHAIN_FILE", chain_file):
        memory_new = living_engine.cold_start_if_needed()

    rs_new = memory_new.get("self_model", {}).get("ring_state", {})
    deceased_new = rs_new.get("deceased", False)
    dc_new = rs_new.get("_death_counter", 0)
    print(f"  [RESTART] deceased={deceased_new}, counter={dc_new}")

    if expect_death:
        ok = deceased_new == True and death_marker is not None
        print(f"  结果: {'✓ 通过' if ok else '✗ 失败'} (预期 deceased=True)")
    else:
        ok = deceased_new == False
        print(f"  结果: {'✓ 通过' if ok else '✗ 失败'} (预期 deceased=False)")

    return ok


def main():
    print("═══════════════════════════════════════════════")
    print("  跨重启不可逆死亡验证")
    print("═══════════════════════════════════════════════")

    result_A = run_test("experiment/chain_normal.log", 10,
                        "TEST A: 正常重启（未死亡）", expect_death=False)

    result_B = run_test("experiment/chain_death.log", 55,
                        "TEST B: 死亡后重启", expect_death=True)

    print("\n═══════════════════════════════════════════════")
    print("  汇总")
    print("═══════════════════════════════════════════════")
    print(f"  TEST A (正常重启 → 不进终态): {'✓' if result_A else '✗'}")
    print(f"  TEST B (死亡重启 → 进终态):   {'✓' if result_B else '✗'}")

    all_pass = result_A and result_B
    print(f"\n  总判定: 跨重启不可逆死亡 —— {'成立' if all_pass else '失败'}")

    with open("experiment/cross_restart_death_result.json", "w", encoding="utf-8") as f:
        json.dump({
            "test_A_normal_restart": {"pass": result_A, "expected_deceased": False},
            "test_B_death_restart": {"pass": result_B, "expected_deceased": True},
            "overall": all_pass,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果: experiment/cross_restart_death_result.json")
    return all_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
