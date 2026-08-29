#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP222  luoshen_ear.py
==================================
用途：给洛神装上最基础的"耳朵"——用纯 Python 标准库 wave + struct
读取 WAV 音频文件，提取声音的事实性物理特征（音量/音高/时长等），
写入结果文件。本阶段不解析语音内容，只"听见"声学事实。

特征定义：
  - avg_volume     平均音量 = 所有样本绝对值的平均
  - peak_volume    峰值音量 = 所有样本绝对值的最大值
  - approx_pitch   近似音高（Hz）= 过零率估算：在 ± 静音阈值范围内
                   不计过零，避免噪声导致音高虚高；再乘静音占比修正。

未来扩展：
  1) 更多特征：频谱重心、包络、谐波比、响度（RMS dB）等；
  2) 接入真实语音识别：把 approx_pitch 替换为 FFT/自相关基频估计，
     并将音频帧送入 ASR 模型做转写，从"听见"升级为"听懂"；
  3) 与对话流/注意力点联动：识别说话人音色变化、情绪语调等。

仅依赖：hashlib / json / time / wave / struct / math（标准库）。
仅允许追加 hash_chain_v2.log，不修改任何已有文件，全程相对路径。
"""

import hashlib
import json
import math
import struct
import time
import wave

# ---------- 路径常量（相对路径） ----------
CHAIN_LOG = "hash_chain_v2.log"
OUT_FILE = "perception_input/luoshen_hearing_test.jsonl"

SAMPLE_RATE = 16000          # 采样率（Hz）
WAV_FILES = [                # (文件名, 频率Hz, 时长秒, 振幅, 描述)
    ("test_low_long.wav",   220.0, 3.0, 0.70, "低音长音"),
    ("test_high_short.wav", 880.0, 0.6, 0.55, "高音短音"),
    ("test_mid_mid.wav",    440.0, 1.5, 0.60, "中音中长"),
]


def synth_wav(path, freq, dur, amp, rate):
    """
    纯 Python 合成正弦波并写入 16bit 单声道 WAV。
    样本值 = amp * 32767 * sin(2*pi*freq*t)，外加淡入淡出 10ms 防爆音。
    """
    n = int(rate * dur)
    fade = int(rate * 0.01)                      # 10ms 淡入淡出样本数
    frames = bytearray()
    for i in range(n):
        t = i / rate
        v = amp * 32767 * math.sin(2.0 * math.pi * freq * t)
        if i < fade:
            v *= i / fade
        elif i > n - fade:
            v *= (n - i) / fade
        frames += struct.pack("<h", int(v))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def read_wav_samples(path):
    """读取 WAV，返回 (sample_rate, channels, samples)。samples 为 16bit int 列表。"""
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        n = w.getnframes()
        raw = w.readframes(n)
    fmt = "<{}h".format(n * channels) if channels == 1 else "<{}h".format(n)
    # 单声道直接解包；多声道取左声道
    if channels == 1:
        samples = list(struct.unpack("<{}h".format(n), raw))
    else:
        allv = list(struct.unpack("<{}h".format(n * channels), raw))
        samples = allv[::channels]
    return rate, channels, samples


def analyze(path):
    """提取单个 WAV 的声学特征。"""
    rate, channels, samples = read_wav_samples(path)
    dur = len(samples) / rate if rate else 0.0
    abs_vals = [abs(s) for s in samples]
    avg_volume = sum(abs_vals) / len(abs_vals) if abs_vals else 0.0
    peak_volume = max(abs_vals) if abs_vals else 0.0

    # 过零率估算近似音高（Hz）
    zero_cross = 0
    noise_count = 0
    threshold = max(1, int(peak_volume * 0.02))      # 2% 峰值作为静音阈值
    for i in range(1, len(samples)):
        if abs(samples[i]) < threshold:
            noise_count += 1
        if samples[i - 1] > 0 > samples[i] or samples[i - 1] < 0 < samples[i]:
            zero_cross += 1
    voiced_ratio = 1.0 - (noise_count / len(samples)) if samples else 0.0
    approx_pitch = (zero_cross * rate / (2 * len(samples))) * voiced_ratio

    return {
        "file": path,
        "duration": round(dur, 4),
        "sample_rate": rate,
        "channels": channels,
        "sample_count": len(samples),
        "avg_volume": round(avg_volume, 2),
        "peak_volume": peak_volume,
        "approx_pitch": round(approx_pitch, 2),
    }


def read_chain_tail(log_path):
    tail = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        raise RuntimeError("{} 为空，无法读取链尾".format(log_path))
    return tail


def compute_record_hash(file_hash, prev_hash, ts):
    return hashlib.md5((file_hash + prev_hash + str(ts)).encode()).hexdigest()


def main():
    # 1. 生成 3 个测试 WAV（正弦波，16000Hz 单声道）
    for name, freq, dur, amp, _desc in WAV_FILES:
        synth_wav(name, freq, dur, amp, SAMPLE_RATE)
        print("synthesized =", name, "freq=", freq, "Hz dur=", dur, "s")

    # 2-4. 逐个提取特征并写入结果文件
    results = []
    for name, freq, dur, amp, desc in WAV_FILES:
        feats = analyze(name)
        rec = {
            "schema_version": 2,
            "timestamp": time.time(),
            "file": feats["file"],
            "duration": feats["duration"],
            "sample_rate": feats["sample_rate"],
            "channels": feats["channels"],
            "sample_count": feats["sample_count"],
            "avg_volume": feats["avg_volume"],
            "peak_volume": feats["peak_volume"],
            "approx_pitch": feats["approx_pitch"],
            "source": "luoshen_ear",
        }
        results.append(rec)
        print("hearing = {} | dur={}s rate={} ch={} n={} avg={} peak={} pitch={}Hz".format(
            desc, rec["duration"], rec["sample_rate"], rec["channels"],
            rec["sample_count"], rec["avg_volume"], rec["peak_volume"],
            rec["approx_pitch"]))

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 6. 哈希链追加（仅一条）
    tail = read_chain_tail(CHAIN_LOG)
    file_hash = hashlib.md5(open(OUT_FILE, "rb").read()).hexdigest()
    ts = time.time()
    rec = {
        "schema_version": 2,
        "timestamp": ts,
        "file": OUT_FILE,
        "file_hash": file_hash,
        "prev_hash": tail["record_hash"],
        "record_hash": compute_record_hash(file_hash, tail["record_hash"], ts),
    }
    with open(CHAIN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("chain_append =", rec["record_hash"], "prev =", tail["record_hash"])


if __name__ == "__main__":
    main()
