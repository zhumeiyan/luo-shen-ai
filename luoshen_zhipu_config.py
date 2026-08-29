#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP223 - luoshen_zhipu_config.py
智谱服务配置固化 + TTS/ASR 首次连通性测试。
- 将智谱 API Key 固化到 perception_input/luoshen_service_config.json（仅首次，从环境变量读取）
- 后续所有语音能力从该统一配置读取 api_key，代码不硬编码
- 使用 GLM-TTS 合成语音、GLM-ASR 识别，记录结果到 perception_input/zhipu_voice_test_result.jsonl
- 结果文件按 hash_chain v2 公式追加一条链记录；配置文件与音频不上链
纪律：不打印 API Key；不使用绝对路径硬编码；不修改已有文件。
"""
import hashlib
import json
import os
import sys
import time
import wave

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERCEPTION_DIR = os.path.join(BASE_DIR, "perception_input")
CONFIG_PATH = os.path.join(PERCEPTION_DIR, "luoshen_service_config.json")
RESULT_PATH = os.path.join(PERCEPTION_DIR, "zhipu_voice_test_result.jsonl")
AUDIO_PATH = os.path.join(PERCEPTION_DIR, "zhipu_voice_test.wav")
CHAIN_PATH = os.path.join(BASE_DIR, "hash_chain_v2.log")

TTS_TEXT = "洛神现在能说话了，这是第一次语音测试。"
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


def load_or_create_config():
    """从统一配置读取 api_key；不存在时从环境变量固化首次写入。"""
    os.makedirs(PERCEPTION_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        print("[config] 已从统一配置读取 provider=%s" % cfg.get("provider"))
        return cfg
    key = os.environ.get("LUOSHEN_ZHIPU_API_KEY", "").strip()
    if not key:
        raise RuntimeError("配置文件不存在，且未提供 LUOSHEN_ZHIPU_API_KEY 环境变量")
    cfg = {
        "schema_version": 2,
        "provider": "zhipu",
        "api_key": key,
        "updated_at": time.time(),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print("[config] 已固化统一配置到 perception_input/luoshen_service_config.json")
    return cfg


def _post_retry(session, url, **kwargs):
    """带 429 退避重试的 POST 请求，最多 4 次。"""
    for attempt in range(1, 5):
        resp = session.post(url, timeout=180, **kwargs)
        if resp.status_code != 429 or attempt == 4:
            return resp
        print("[retry] 429 限流，等待 %ds 后重试(%d/4)..." % (10 * attempt, attempt))
        time.sleep(10 * attempt)
    return resp


def tts_synthesize(cfg, text):
    """GLM-TTS 文本转语音，输出 WAV。返回 (path, md5, duration_sec, size_bytes)。"""
    headers = {
        "Authorization": "Bearer " + cfg["api_key"],
        "Content-Type": "application/json",
    }
    payload = {
        "model": "glm-tts",
        "input": text,
        "voice": "tongtong",
        "response_format": "wav",
        "speed": 1.0,
    }
    resp = _post_retry(requests.Session(), BASE_URL + "/audio/speech",
                       headers=headers, json=payload)
    resp.raise_for_status()
    with open(AUDIO_PATH, "wb") as f:
        f.write(resp.content)
    md5 = hashlib.md5(resp.content).hexdigest()
    size = len(resp.content)
    with wave.open(AUDIO_PATH, "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        duration = frames / float(rate) if rate else 0.0
    print("[tts] 合成成功: size=%d bytes, duration=%.2fs, md5=%s" % (size, duration, md5))
    return AUDIO_PATH, md5, duration, size


def asr_recognize(cfg, audio_path):
    """GLM-ASR 语音转文本。返回识别文本。"""
    headers = {"Authorization": "Bearer " + cfg["api_key"]}
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
        data = {"model": "glm-asr-2512", "stream": "false"}
        resp = _post_retry(requests.Session(), BASE_URL + "/audio/transcriptions",
                           headers=headers, data=data, files=files)
    resp.raise_for_status()
    obj = resp.json()
    text = obj.get("text") or obj.get("output") or ""
    if isinstance(text, list):
        text = "".join(text)
    text = str(text).strip()
    print("[asr] 识别文本: %s" % text)
    return text


def append_hash_chain(result_relpath, ts):
    """按 hash_chain v2 公式追加一条链记录：record_hash=md5(file_hash+prev_hash+str(ts))。"""
    if not os.path.exists(CHAIN_PATH):
        raise RuntimeError("hash_chain_v2.log 不存在，无法读取链尾")
    prev_hash = None
    with open(CHAIN_PATH, "r", encoding="utf-8") as f:
        for ln in reversed(f.readlines()):
            ln = ln.strip()
            if ln:
                prev_hash = json.loads(ln)["record_hash"]
                break
    if prev_hash is None:
        raise RuntimeError("hash_chain_v2.log 为空，无链尾")
    with open(RESULT_PATH, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    record = {
        "schema_version": 2,
        "timestamp": ts,
        "file": result_relpath,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": hashlib.md5((file_hash + prev_hash + str(ts)).encode()).hexdigest(),
    }
    with open(CHAIN_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("[chain] prev_hash=%s" % prev_hash)
    print("[chain] record_hash=%s" % record["record_hash"])
    return record


def main():
    cfg = load_or_create_config()

    # TTS
    audio_path, audio_md5, duration, size = tts_synthesize(cfg, TTS_TEXT)

    # ASR
    asr_text = asr_recognize(cfg, audio_path)

    # 结果记录
    ts = time.time()
    match = (asr_text == TTS_TEXT)
    record = {
        "schema_version": 2,
        "timestamp": ts,
        "tts_text": TTS_TEXT,
        "tts_audio_file": os.path.basename(audio_path),
        "tts_audio_md5": audio_md5,
        "asr_text": asr_text,
        "match": match,
        "source": "luoshen_zhipu_config",
    }
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("[result] tts_audio_file=%s duration=%.2fs size=%dB" % (
        record["tts_audio_file"], duration, size))
    print("[result] match=%s" % match)

    # 哈希链追加（仅一条）
    append_hash_chain("perception_input/zhipu_voice_test_result.jsonl", ts)

    print("[done] STEP223 完成")


if __name__ == "__main__":
    main()
