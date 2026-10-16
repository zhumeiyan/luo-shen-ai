#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP229
模块名称：luoshen_web_restart_check.py
职责：检查洛神网页服务是否运行，若停止则重启并确认本地可访问；
      同时检查 cpolar 公网穿透进程与地址是否有效。
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import time

WEB_SCRIPT = "luoshen_web_chat.py"
HOST = "127.0.0.1"
PORT = 8765
INFO_PATH = os.path.join("perception_input", "web_restart_check.jsonl")
CHAIN_PATH = "hash_chain_v2.log"
SOURCE = "luoshen_web_restart_check"


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def port_listening(host, port):
    """检查端口是否被监听。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect((host, port))
        return True
    except (OSError, socket.error):
        return False
    finally:
        s.close()


def start_web_service():
    """后台启动洛神网页服务。"""
    log = open(os.path.join("temp", "web_chat_nohup.log"), "ab")
    proc = subprocess.Popen(
        [sys.executable, WEB_SCRIPT],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    return proc


def check_cpolar():
    """检查 cpolar 进程与公网地址。"""
    try:
        out = subprocess.run(
            ["pgrep", "-af", "cpolar"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        running = bool(out.strip())
    except Exception:
        running = False

    public_url = None
    # 尝试读取已有公网地址记录
    for f in ("perception_input/luoshen_tunnel_info.jsonl",
              "perception_input/luoshen_cpolar_info.jsonl"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    url = obj.get("public_url") or obj.get("url") or obj.get("tunnel_url")
                    if url:
                        public_url = url
        except (OSError, ValueError):
            continue
    return running, public_url


def append_chain(file_path, ts):
    file_hash = file_md5(file_path)
    with open(CHAIN_PATH, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    last_record = json.loads(lines[-1])
    prev_hash = last_record["record_hash"]
    record_hash = hashlib.md5(
        (file_hash + prev_hash + str(ts)).encode("utf-8")
    ).hexdigest()
    record = {
        "schema_version": 2,
        "timestamp": ts,
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main():
    ts = time.time()
    local_url = "http://%s:%d" % (HOST, PORT)

    # 1. 检查端口
    if port_listening(HOST, PORT):
        status = "running"
        print("8765 already listening")
    else:
        print("8765 not listening, starting web service...")
        start_web_service()
        # 等待服务就绪
        started = False
        for _ in range(20):
            time.sleep(0.5)
            if port_listening(HOST, PORT):
                started = True
                break
        if started:
            status = "running"
            print("web service started")
        else:
            status = "failed"
            print("web service failed to start")

    # 2. 本地地址
    print("local_url:", local_url)

    # 3. cpolar 检查
    cpolar_running, public_url = check_cpolar()
    print("cpolar running:", cpolar_running)
    print("public_url:", public_url if public_url else "null")

    # 4. 写记录
    record = {
        "schema_version": 2,
        "timestamp": ts,
        "local_url": local_url,
        "public_url": public_url,
        "status": status,
        "source": SOURCE,
    }
    with open(INFO_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 5. 哈希链
    chain_record = append_chain(INFO_PATH, ts)

    print("=== LUOSHEN WEB RESTART CHECK ===")
    print("local_url:", local_url)
    print("public_url:", public_url if public_url else "null")
    print("status:", status)
    print("=== HASH CHAIN ===")
    print("prev_hash:", chain_record["prev_hash"])
    print("record_hash:", chain_record["record_hash"])


if __name__ == "__main__":
    main()
