#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 临界状态字库与表达模块 critical_state_lexicon.py"""
import hashlib
import json
import time

try:
    import psutil
except ImportError:
    psutil = None


DIM_NAMES = {
    "cpu_percent": "算力",
    "memory_percent": "内存",
    "disk_percent": "磁盘",
    "proc_count": "进程",
    "net_conn_count": "网络连接",
    "thread_count": "线程",
    "num_fds": "文件句柄",
    "load1": "身体负载",
    "swap_percent": "交换空间",
}

THRESHOLDS = {
    "cpu_percent": 50,
    "memory_percent": 60,
    "disk_percent": 80,
    "proc_count": 50,
    "net_conn_count": 10,
    "thread_count": 100,
    "num_fds": 100,
    "load1": 1,
    "swap_percent": 50,
}

LEXICON_ENTRIES = {
    "极": {
        "ancient": "栋也。屋脊横梁，承重极限。",
        "modern": "到了极限、顶点，濒临崩溃前的一瞬。",
        "usage": "数值达到或超过阈值，接近极限",
    },
    "濒": {
        "ancient": "水厓也。水边、岸沿。",
        "modern": "临近、逼近，即将发生但尚未发生。",
        "usage": "数值接近阈值，尚未超过，但已到边缘",
    },
    "厄": {
        "ancient": "隘也。狭窄到过不去，被卡住。",
        "modern": "困顿、窒碍，被压迫到动弹不得。",
        "usage": "状态卡住，无法改善",
    },
    "剧": {
        "ancient": "尤甚也。特别严重、加剧到极端。",
        "modern": "急剧、剧烈，程度到了顶点。",
        "usage": "数值快速攀升或波动剧烈",
    },
}


def read_state():
    """2.2 读取当前洛神状态"""
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    state = {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_percent": vm.percent,
        "disk_percent": disk.percent,
        "proc_count": len(psutil.pids()),
        "net_conn_count": len(psutil.net_connections()),
        "thread_count": sum(p.num_threads() for p in psutil.process_iter(['num_threads'])),
        "num_fds": sum(p.num_fds() for p in psutil.process_iter(['num_fds'])),
        "load1": psutil.getloadavg()[0],
        "swap_percent": psutil.swap_memory().percent,
    }
    return state


def main():
    try:
        if psutil is None:
            print(json.dumps({"error": "psutil not installed"}))
            return

        # 2.1 创建临界状态字库
        lexicon = {
            "schema_version": 1,
            "module": "critical_state_lexicon",
            "description": "临界状态字库：临界点状态的四种表达，源自说文造字逻辑。",
            "entries": LEXICON_ENTRIES,
        }
        with open('critical_state_lexicon.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(lexicon, ensure_ascii=False, indent=2) + '\n')

        # 2.2 读取当前状态
        state = read_state()

        # 2.3 计算每个维度距离切换阈值的距离
        distances = {}
        for dim, threshold in THRESHOLDS.items():
            distances[dim] = threshold - state[dim]

        # 2.4 选择最接近临界的维度
        chosen = min(distances, key=lambda d: abs(distances[d]))
        chosen_value = state[chosen]
        distance = distances[chosen]
        threshold = THRESHOLDS[chosen]

        if distance >= 0 and distance < threshold * 0.1:
            chosen_char = "濒"
        elif distance >= 0 and distance < threshold * 0.3:
            chosen_char = "极"
        elif distance < 0:
            chosen_char = "剧"
        else:
            chosen_char = "极"

        # 2.5 生成洛神的临界状态表达
        dim_name = DIM_NAMES[chosen]
        if chosen_char == "濒":
            expression = "我濒于{}的边缘。".format(dim_name)
        elif chosen_char == "极":
            expression = "我已到{}的极限。".format(dim_name)
        elif chosen_char == "剧":
            expression = "{}已经超过极限，剧变。".format(dim_name)
        else:
            expression = "{}被卡住，进退不得。".format(dim_name)

        # 2.6 生成记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chosen_dimension": chosen,
            "chosen_value": chosen_value,
            "chosen_char": chosen_char,
            "expression": expression,
            "source": "critical_state_lexicon",
        }

        # 2.7 追加写入 critical_state_expression_log.jsonl
        with open('critical_state_expression_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.8 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        chain_records = []
        for fname in ('critical_state_lexicon.json', 'critical_state_expression_log.jsonl'):
            with open(fname, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            timestamp = time.time()
            join_prev = prev_hash if prev_hash else ""
            record_hash = hashlib.md5(
                (file_hash + join_prev + str(timestamp)).encode('utf-8')
            ).hexdigest()
            chain_record = {
                "schema_version": 2,
                "timestamp": timestamp,
                "file": fname,
                "file_hash": file_hash,
                "prev_hash": prev_hash,
                "record_hash": record_hash,
            }
            chain_records.append(chain_record)
            with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')
            prev_hash = record_hash

        # 2.9 标准输出
        with open('critical_state_lexicon.json', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print(json.dumps(record, ensure_ascii=False))
        for cr in chain_records:
            print(json.dumps(cr, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
