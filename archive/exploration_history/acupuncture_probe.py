#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 针灸式最小刺激检测模块 acupuncture_probe.py"""
import hashlib
import json
import os
import socket
import time

try:
    import psutil
except ImportError:
    psutil = None


def probe_cpu():
    start = time.time()
    for _ in range(1000):
        pass
    end = time.time()
    return (end - start) * 1000.0


def probe_memory():
    start = time.time()
    buf = bytearray(1024 * 1024)
    end = time.time()
    ms = (end - start) * 1000.0
    del buf
    return ms


def probe_disk():
    tmp = None
    try:
        tmp = '__acupuncture_tmp_disk__'
        data = b'x' * 1024
        start = time.time()
        with open(tmp, 'wb') as f:
            f.write(data)
            f.flush()
        end = time.time()
        ms = (end - start) * 1000.0
        return ms
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.remove(tmp)


def probe_network():
    start = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.close()
    end = time.time()
    return (end - start) * 1000.0


def probe_file_handle():
    tmp = None
    try:
        tmp = '__acupuncture_tmp_fd__'
        start = time.time()
        f = open(tmp, 'w')
        f.close()
        end = time.time()
        ms = (end - start) * 1000.0
        return ms
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.remove(tmp)


def main():
    try:
        probes_spec = [
            ("cpu", "执行1000次空循环", probe_cpu, 50.0),
            ("memory", "分配并释放1MB的bytearray", probe_memory, 50.0),
            ("disk", "写入并删除一个1KB的临时文件", probe_disk, 100.0),
            ("network", "创建一个socket并立即关闭", probe_network, 100.0),
            ("file_handle", "打开并关闭一个临时文件", probe_file_handle, 50.0),
        ]

        probes = []
        abnormal_parts = []
        for part, stimulus, fn, threshold in probes_spec:
            try:
                ms = fn()
                if ms is None:
                    status = "no_response"
                elif ms > threshold:
                    status = "abnormal"
                else:
                    status = "normal"
            except Exception:
                ms = None
                status = "no_response"
            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "part": part,
                "stimulus": stimulus,
                "response_ms": ms,
                "status": status,
                "source": "acupuncture_probe",
            }
            probes.append(record)
            if status in ("abnormal", "no_response"):
                abnormal_parts.append({
                    "part": part,
                    "response_ms": ms,
                    "status": status,
                })

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "probes": probes,
            "abnormal_parts": abnormal_parts,
            "abnormal_count": len(abnormal_parts),
            "source": "acupuncture_probe",
        }

        with open('acupuncture_probe_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        with open('acupuncture_probe_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(lines[-1]).get("record_hash") if lines else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "acupuncture_probe_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
