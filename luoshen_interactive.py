#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 人机交互模块 luoshen_interactive.py"""
import hashlib
import json
import time


def read_last_line(file_path):
    """读取 jsonl 文件最后一条记录，不存在返回 None。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    return json.loads(lines[-1])


def main():
    try:
        # 2.1 读取洛神当前内部状态
        # 时间感
        last_time = read_last_line('time_gap_log.jsonl')
        if last_time is None:
            gap_message = "首次"
        else:
            gap_message = last_time.get("gap_message", "首次")

        # 身体状态
        last_phys = read_last_line('physical_state.jsonl')
        if last_phys is None:
            phys_unknown = True
        else:
            phys_unknown = False
            dynamic_usage = last_phys.get("dynamic_usage", {})

        # 能量状态
        last_energy = read_last_line('energy_awareness_log.jsonl')
        if last_energy is None:
            energy_unknown = True
        else:
            energy_unknown = False
            cost_per_day = last_energy.get("cost_per_day", 0)

        # 骨字库
        try:
            with open('core_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
        except FileNotFoundError:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return
        if not lexicon:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return
        entries = lexicon.get("entries", {})
        if not isinstance(entries, dict) or not entries:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return
        bone_count = len(entries)

        # 记忆链已学字
        mem_lines = read_last_line('memory_chain.jsonl')
        try:
            with open('memory_chain.jsonl', 'r', encoding='utf-8') as f:
                mlines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            mlines = []
        mem_words = []
        for ln in mlines:
            obj = json.loads(ln)
            if "taught_word" in obj:
                mem_words.append(obj["taught_word"])
        mem_count = len(mem_words)

        # 2.2 生成开场表达
        # 身体状态映射
        if phys_unknown:
            cpu_state = mem_state = disk_state = "未知"
        else:
            cpu_percent = dynamic_usage.get("cpu_percent", 0)
            memory_percent = dynamic_usage.get("memory_percent", 0)
            disk_percent = dynamic_usage.get("disk_percent", 0)
            cpu_state = "紧" if cpu_percent >= 50 else "静"
            mem_state = "满" if memory_percent >= 60 else "轻"
            disk_state = "满" if disk_percent >= 80 else "空"

        # 能量状态映射
        if energy_unknown:
            energy_state = "未知"
        else:
            energy_state = "贵" if cost_per_day > 1 else "轻"

        opening = (
            "距离上次：{gap}。我的身体：{cpu}，{mem}，{disk}。我的能耗：{energy}。"
            "我这里有{bone}个骨字，{memc}个记忆字。"
        ).format(
            gap=gap_message,
            cpu=cpu_state,
            mem=mem_state,
            disk=disk_state,
            energy=energy_state,
            bone=bone_count,
            memc=mem_count,
        )
        print(opening)

        # 2.3 等待用户输入
        while True:
            print("你可以和洛神说话了。输入'退出'结束对话。")
            try:
                user_input = input()
            except EOFError:
                break
            user_input = (user_input or "").strip()
            if not user_input:
                continue
            if user_input == "退出":
                break

            # 2.4 洛神对用户输入做出回应
            first_char = user_input[0]
            if first_char in mem_words:
                reply = "我认识这个字：{c}。它在我记忆里。".format(c=first_char)
            else:
                reply = "这个字我还没学过。它不在我记忆里。"

            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "user_input": user_input,
                "luoshen_reply": reply,
                "source": "luoshen_interactive",
            }
            # 2.5 追加写入 interactive_session_log.jsonl
            with open('interactive_session_log.jsonl', 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
            print(reply)

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        try:
            with open('interactive_session_log.jsonl', 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except FileNotFoundError:
            file_hash = hashlib.md5(b'').hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "interactive_session_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出：哈希链记录 JSON
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
