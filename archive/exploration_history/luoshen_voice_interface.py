#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP224
模块名称：luoshen_voice_interface.py
职责：为洛神提供统一的、可替换的语音接口层。
- speak(text)：将文字转成声音，返回 (音频文件路径, md5)。
- listen(audio_file)：读取音频文件，提取声学特征，返回特征字典。

占位实现：本地纯 Python 正弦波合成 + WAV 声学特征提取。
未来接入真实 TTS/ASR 时，仅需替换这两个函数的内部实现，
保持函数名与返回结构不变，核心代码无需改动。
"""

import hashlib
import json
import math
import os
import struct
import time
import wave

CONFIG_PATH = os.path.join("perception_input", "luoshen_voice_config.json")
TEST_PATH = os.path.join("perception_input", "luoshen_voice_interface_test.jsonl")
CHAIN_PATH = "hash_chain_v2.log"

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_AMPLITUDE = 16000  # 16-bit PCM 幅值


def write_config():
    """写入语音提供方配置文件（不上链、不交付内容）。"""
    config = {
        "schema_version": 2,
        "provider": "local_synth",
        "mode": "offline_placeholder",
        "updated_at": time.time(),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return config


def file_md5(path):
    """计算文件 md5。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def synth_sine_wav(path, freq, duration_sec, sample_rate=DEFAULT_SAMPLE_RATE,
                   amplitude=DEFAULT_AMPLITUDE):
    """纯 Python 合成正弦波 WAV（16-bit PCM，单声道）。"""
    n_frames = int(sample_rate * duration_sec)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_frames):
            sample = amplitude * math.sin(2.0 * math.pi * freq * i / sample_rate)
            frames += struct.pack("<h", int(sample))
        w.writeframes(bytes(frames))


def read_wav_params(path):
    """读取 WAV 基础参数。"""
    with wave.open(path, "rb") as w:
        return {
            "channels": w.getnchannels(),
            "sample_width": w.getsampwidth(),
            "sample_rate": w.getframerate(),
            "n_frames": w.getnframes(),
        }


def speak(text):
    """
    统一语音输出接口：将文字转成声音。

    占位实现：根据文本长度决定正弦波频率与时长，生成 WAV 文件。
    返回 (音频文件名, md5)。
    未来替换为真实 TTS：调用外部 TTS 服务得到音频文件，其余保持不变。
    """
    text_len = len(text)
    # 频率随文本长度在 220~440Hz 间变化，时长 0.4~1.2s
    freq = 220.0 + (text_len % 10) * 20.0
    duration = 0.4 + min((text_len / 40.0), 0.8)

    audio_file = os.path.join("perception_input", "luoshen_voice_test.wav")
    synth_sine_wav(audio_file, freq, duration)
    audio_md5 = file_md5(audio_file)
    return audio_file, audio_md5, freq, duration


def listen(audio_file):
    """
    统一语音输入接口：读取音频文件，提取声学特征。

    占位实现：读取 WAV，提取时长、采样率、平均音量、峰值音量、近似音高。
    返回特征字典。
    未来替换为真实 ASR：调用外部 ASR 服务得到文本与更多特征，其余保持不变。
    """
    params = read_wav_params(audio_file)
    channels = params["channels"]
    sample_width = params["sample_width"]
    sample_rate = params["sample_rate"]
    n_frames = params["n_frames"]
    duration = n_frames / sample_rate

    with wave.open(audio_file, "rb") as w:
        raw = w.readframes(n_frames)

    # 解析 PCM 样本（假定 16-bit 单声道）
    n_samples = len(raw) // (sample_width * channels)
    total = 0.0
    peak = 0
    for i in range(n_samples):
        offset = i * sample_width * channels
        # 取第一通道样本
        sample = struct.unpack_from("<h", raw, offset)[0]
        total += abs(sample)
        if abs(sample) > peak:
            peak = abs(sample)

    avg_volume = total / n_samples if n_samples else 0.0

    # 近似音高：过零率估计法（每周期两次过零，freq = zeros / 2 / duration）
    zero_cross = 0
    prev = 0
    for i in range(n_samples):
        offset = i * sample_width * channels
        sample = struct.unpack_from("<h", raw, offset)[0]
        if prev <= 0 < sample or prev > 0 >= sample:
            zero_cross += 1
        prev = sample

    approx_pitch = (zero_cross / 2.0 / duration) if duration > 0 else 0.0

    features = {
        "duration_sec": round(duration, 4),
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_count": n_samples,
        "avg_volume": round(avg_volume, 2),
        "peak_volume": peak,
        "approx_pitch_hz": round(approx_pitch, 2),
    }
    return features


def append_chain(file_path, ts):
    """按哈希链 v2 公式追加一条记录。"""
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
    write_config()

    test_text = "洛神现在能说话了，这是第一次语音测试。"

    # 测试 speak
    audio_file, audio_md5, freq, duration = speak(test_text)
    speak_record = {
        "schema_version": 2,
        "timestamp": ts,
        "test_type": "speak",
        "input_text": test_text,
        "audio_file": audio_file,
        "audio_md5": audio_md5,
        "source": "luoshen_voice_interface",
    }

    # 测试 listen
    features = listen(audio_file)
    listen_record = {
        "schema_version": 2,
        "timestamp": ts,
        "test_type": "listen",
        "audio_file": audio_file,
        "features": features,
        "source": "luoshen_voice_interface",
    }

    # 写测试结果文件（仅追加：文件不存在，新建）
    with open(TEST_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(speak_record, ensure_ascii=False) + "\n")
        f.write(json.dumps(listen_record, ensure_ascii=False) + "\n")

    # 控制台打印（不打印任何密钥或敏感配置）
    print("=== LUOSHEN VOICE INTERFACE TEST ===")
    print("speak -> audio_file:", audio_file)
    print("speak -> audio_md5:", audio_md5)
    print("speak -> synth freq(hz):", round(freq, 2), "duration(s):", round(duration, 2))
    print("listen -> features:", json.dumps(features, ensure_ascii=False))

    # 哈希链追加（仅测试结果文件上链）
    chain_record = append_chain(TEST_PATH, ts)
    print("=== HASH CHAIN ===")
    print("prev_hash:", chain_record["prev_hash"])
    print("record_hash:", chain_record["record_hash"])


if __name__ == "__main__":
    main()
