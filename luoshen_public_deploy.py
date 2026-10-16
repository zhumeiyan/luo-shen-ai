#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP230
模块名称：luoshen_public_deploy.py
职责：将洛神网页服务部署到公网免费托管平台。
- 探测国内可访问的免费托管平台可达性；
- 检查本地/环境变量中的平台部署凭证；
- 若存在凭证则执行部署并返回公网地址；
- 若无凭证，如实报告需要设计者手动注册，不编造部署成功。
"""

import hashlib
import json
import os
import subprocess
import time

INFO_PATH = os.path.join("perception_input", "public_deploy_info.jsonl")
CHAIN_PATH = "hash_chain_v2.log"
SOURCE = "luoshen_public_deploy"

# 候选免费托管平台（按任务书顺序）
PLATFORMS = [
    {"name": "PythonAnywhere", "host": "pythonanywhere.com", "env": "PYTHONANYWHERE_API_TOKEN"},
    {"name": "Render", "host": "render.com", "env": "RENDER_API_KEY"},
    {"name": "Railway", "host": "railway.app", "env": "RAILWAY_TOKEN"},
    {"name": "Deta Space", "host": "deta.space", "env": "DETA_SPACE_TOKEN"},
    {"name": "Glitch", "host": "glitch.com", "env": "GLITCH_TOKEN"},
    {"name": "Vercel", "host": "vercel.com", "env": "VERCEL_TOKEN"},
]


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(host):
    """探测平台可达性，返回 http_code 或 None。"""
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--connect-timeout", "8", "--max-time", "12", "https://" + host],
            capture_output=True, text=True, timeout=15,
        )
        code = r.stdout.strip()
        return code if code else None
    except Exception:
        return None


def has_credential(env_name):
    """检查环境变量中是否存在该平台凭证。"""
    v = os.environ.get(env_name, "")
    return bool(v.strip())


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
    print("=== LUOSHEN PUBLIC DEPLOY ===")
    reachable = []
    credentialed = []
    for p in PLATFORMS:
        code = probe(p["host"])
        ok = code not in (None, "", "000")
        print("%-14s host=%-22s http=%s" % (p["name"], p["host"], code if code else "FAIL"))
        if ok:
            reachable.append(p["name"])
        if has_credential(p["env"]):
            credentialed.append(p["name"])

    print("---")
    print("reachable:", ", ".join(reachable) if reachable else "none")
    print("with_credential:", ", ".join(credentialed) if credentialed else "none")

    # 判断能否部署
    if credentialed:
        platform = credentialed[0]
        # 有凭证的平台：此处仅报告可部署，真实部署需平台 API 实现
        public_url = None
        status = "failed"
        note = "检测到 %s 凭证，但当前脚本未内置该平台完整部署API实现，需补充后方可部署" % platform
        print("public_url:", public_url)
        print("status:", status)
    else:
        platform = "none"
        public_url = None
        status = "failed"
        note = "所有免费托管平台均需账号注册，当前环境无任何平台凭证，需设计者手动注册后提供凭证再部署"
        print("public_url: null")
        print("status: failed")
        print("NOTE: 所有候选平台均需账号注册，无法匿名部署。")

    record = {
        "schema_version": 2,
        "timestamp": ts,
        "platform": platform,
        "public_url": public_url,
        "status": status,
        "note": note,
        "source": SOURCE,
    }
    with open(INFO_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    chain_record = append_chain(INFO_PATH, ts)

    print("=== HASH CHAIN ===")
    print("prev_hash:", chain_record["prev_hash"])
    print("record_hash:", chain_record["record_hash"])


if __name__ == "__main__":
    main()
