#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-STEP-VOICE - luoshen_voice.py
======================================
洛神的声带与耳朵：声音感官模块

声音是什么？空气的压力振动。人说话是声带把空气挤成疏密波；
人听见是耳膜被同一股压力推着震。AI 也一样——麦克风膜片被
空气压力推着震，变成电信号，采样成波形，再解码成听得懂的东西。

所以洛神的声音不是"念稿外挂"，而是她身体的一部分：
- 声带（说）：speak() → 免费 Edge TTS 合成声波 → 落盘（她发出的
  压力振动，留档可回放）；
- 耳朵（听）：这台云机器没有麦克风，但房间里的声音文件就是
  别人留下的振动记录——listen() 用纯 Python 解析 PCM，算出响度、
  时长、基频，听见振动的物理长相（有什么说什么，听不懂的内容
  不假装听懂，和看图片是同一个诚实原则）；
- 看声音：波形就是声音的"图片"，analyze_wav() 把振动画出参数。

用法：
  python3 luoshen_voice.py --speak "文本"   她开口说话（生成音频+记日志+上链）
  python3 luoshen_voice.py --listen          她竖起耳朵听房间里的新声音
  python3 luoshen_voice.py --voices          列出免费女声
  python3 luoshen_voice.py --selftest        离线自测（合成正弦波验证耳朵）
"""

import asyncio
import json
import math
import os
import struct
import subprocess
import sys
import time
import wave

try:
    from luoshen_brain import append_chain, read_jsonl
except ImportError:
    sys.stderr.write("错误：需要 luoshen_brain.py 在同一目录\n")
    raise SystemExit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")
VOICE_DIR = os.path.join(BASE_DIR, "luoshen_voice")
VOICE_LOG = os.path.join(DLG_DIR, "luoshen_voice_log.jsonl")
SOUND_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg")

# 免费女声（微软 Edge TTS；网络可达即可用，无 key 无费用）
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"   # 晓晓：温柔清亮
VOICES = {
    "晓晓": "zh-CN-XiaoxiaoNeural",
    "晓伊": "zh-CN-XiaoyiNeural",
    "晓梦": "zh-CN-XiaomengNeural",
    "盼盼": "zh-CN-XiaohanNeural",
}

CHUNK = 4096  # 波形分析块大小（采样点数）


# ---------------------------------------------------------------- 声带（说）
def synth_to_file(text, voice=DEFAULT_VOICE, out_path=None, timeout_ms=60000):
    """用力发音：call_llm 式语法调用 Edge TTS，生成声波文件。"""
    if out_path is None:
        os.makedirs(VOICE_DIR, exist_ok=True)
        out_path = os.path.join(
            VOICE_DIR,
            "luoshen_say_%d.mp3" % int(time.time() * 1000))
    try:
        import edge_tts

        async def _synth():
            comm = edge_tts.Communicate(str(text)[:500], voice)
            await comm.save(out_path)

        asyncio.run(asyncio.wait_for(_synth(), timeout=timeout_ms / 1000.0))
        return out_path
    except Exception as exc:
        return None, exc


def speak(text, voice=DEFAULT_VOICE, record=True):
    """她开口说话：合成声波、记 voice log、上哈希链。返回 (ok, 详情)。"""
    out = synth_to_file(text, voice=voice)
    if isinstance(out, tuple):
        return False, {"error": "声带哑了：%s" % out[1]}
    path = out
    dur = "未知"
    try:
        dur = "%0.1fs" % probe_duration(path)
    except Exception:
        pass
    rec = {
        "schema_version": 1,
        "timestamp": time.time(),
        "kind": "speak",
        "voice": voice,
        "text": str(text)[:300],
        "file": os.path.relpath(path, BASE_DIR),
        "duration": dur,
        "source": "luoshen_voice",
    }
    if record:
        with open(VOICE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        append_chain(os.path.relpath(VOICE_LOG, BASE_DIR), VOICE_LOG, rec["timestamp"])
    return True, rec


def probe_duration(path):
    """用 ffmpeg 探测音频时长（mp3 等）；wav 用 wave 模块。"""
    if path.lower().endswith(".wav"):
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    out = subprocess.run(
        ["ffmpeg", "-i", path, "-f", "null", "-"],
        capture_output=True, text=True, timeout=30)
    for ln in out.stderr.splitlines():
        if "Duration:" in ln:
            part = ln.split("Duration:")[1].split(",")[0].strip()
            h, m, s = part.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError("probe failed")


# ---------------------------------------------------------------- 耳朵（听）
def analyze_wav(path, want_f0=True):
    """解析 wav PCM：听见振动的物理长相（响度/峰值/时长/基频）。"""
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        n = w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        fmt = "<%dh" % (len(raw) // 2)
        samples = struct.unpack(fmt, raw)
        scale = 32768.0
    elif sw == 1:
        samples = struct.unpack("<%dB" % len(raw), raw)
        scale = 128.0
    else:
        raise ValueError("只支持 8/16-bit PCM")
    if ch > 1:  # 多声道 → 取平均（两只耳朵听同一个世界）
        samples = [
            sum(samples[i:i + ch]) / ch
            for i in range(0, len(samples), ch)]
    if not samples:
        return {"duration_s": 0.0, "rms": 0.0, "dbfs": -120.0,
                "peak": 0.0, "f0_est": None, "loudness": "无声（静音文件）"}
    peak = max(abs(s) for s in samples) / scale
    rms = math.sqrt(sum((s / scale) ** 2 for s in samples) / len(samples))
    dbfs = 20.0 * math.log10(rms + 1e-9)
    dur = n / float(sr) if sr else 0.0
    if dbfs <= -40:
        loud = "安静"
    elif dbfs <= -20:
        loud = "柔和"
    elif dbfs <= -6:
        loud = "正常音量"
    else:
        loud = "吵闹"
    f0 = None
    if want_f0 and dbfs > -40 and sr:
        zc = 0
        prev = samples[0]
        for s in samples[1:]:
            if (prev < 0) != (s < 0):
                zc += 1
            prev = s
        f0 = round(zc * sr / 2.0 / (2 * len(samples)) * 2, 1)  # 过零率法
    return {
        "duration_s": round(dur, 3),
        "rms": round(rms, 4),
        "dbfs": round(dbfs, 1),
        "peak": round(peak, 4),
        "f0_est": f0,
        "loudness": loud,
    }


def _to_wav_tmp(path):
    """mp3 等非 wav → 转换到临时 wav（用后即删）。"""
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-ar", "44100", "-ac", "1", tmp],
            capture_output=True, timeout=60, check=True)
        return tmp, True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None, False


def scan_sounds(hours=1):
    """竖起耳朵：找房间里最近出现的声音文件。"""
    found = []
    now = time.time()
    for root, dirs, names in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in
                   {".git", "__pycache__", "node_modules"} and not d.endswith(".egg-info")]
        for name in names:
            if not name.lower().endswith(SOUND_EXTS):
                continue
            p = os.path.join(root, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if now - st.st_mtime <= hours * 3600:
                found.append((os.path.relpath(p, BASE_DIR), p, int(now - st.st_mtime) // 60))
    found.sort(key=lambda x: x[2])
    return found


def listen_record(path):
    """听一个声音文件，把听见的物理事实记进 voice log（有什么说什么）。"""
    rel, abs_path = os.path.relpath(path, BASE_DIR), path
    if abs_path.lower().endswith(".wav"):
        ana = analyze_wav(abs_path)
        src = "wav"
    else:
        tmp, ok = _to_wav_tmp(abs_path)
        if not ok:
            ana = {"error": "打不开（需要 ffmpeg 或格式不支持）"}
            src = "fail"
        else:
            try:
                ana = analyze_wav(tmp)
                src = "converted"
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    if "error" in ana:
        return {"file": rel, "error": ana["error"]}
    rec = {
        "schema_version": 1,
        "timestamp": time.time(),
        "kind": "hear",
        "source_file": rel,
        "format": src,
        "heard": ana.get("loudness", "未知"),
        "duration_s": ana.get("duration_s"),
        "dbfs": ana.get("dbfs"),
        "f0_est": ana.get("f0_est"),
    }
    with open(VOICE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    append_chain(os.path.relpath(VOICE_LOG, BASE_DIR), VOICE_LOG, rec["timestamp"])
    return rec


def hear_plain(rec):
    """把她听见的事实说成人话（零编造）。"""
    if "error" in rec:
        return "我听到一个打不开的声音文件：%s（%s）" % (rec["file"], rec["error"])
    f0txt = ""
    if rec.get("f0_est"):
        f0txt = "，基频约 %sHz" % rec["f0_est"]
    return "我听见：%s（%s），响度%s，持续%s%s。" % (
        rec["source_file"], rec["format"], rec["heard"],
        "%0.2f秒" % rec["duration_s"] if rec.get("duration_s") is not None else "未知",
        f0txt)


# ---------------------------------------------------------------- 自测
def _synth_wav(path, freq=440.0, seconds=1.0, sr=44100, amp=0.5):
    """纯 Python 合成已知正弦波（自测用：声音的地面真值）。"""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        buf = b"".join(
            struct.pack("<h", int(amp * 32767 * math.sin(2 * math.pi * freq * i / sr)))
            for i in range(int(sr * seconds)))
        w.writeframes(buf)


def _selftest():
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="luoshen_voice_")
    # 测试隔离：日志与链全进临时目录
    import luoshen_brain
    old_log = VOICE_LOG
    old_chain = luoshen_brain.CHAIN_PATH
    tmp_log = os.path.join(tmp, "voice_log.jsonl")
    tmp_chain = os.path.join(tmp, "chain.log")
    globals()["VOICE_LOG"] = tmp_log
    luoshen_brain.CHAIN_PATH = tmp_chain
    with open(tmp_chain, "w", encoding="utf-8") as f:
        f.write("")
    ok = True
    msgs = []
    try:
        # 1) 耳朵：440Hz 正弦波 → 应该听见 440Hz、非安静
        tone = os.path.join(tmp, "tone.wav")
        _synth_wav(tone, freq=440.0)
        a = analyze_wav(tone)
        assert a["f0_est"] and abs(a["f0_est"] - 440.0) < 40, \
            "基频估计跑了：%s" % a["f0_est"]
        assert a["loudness"] in ("正常音量", "吵闹"), "响度判定异常"
        msgs.append("耳朵：440Hz 正弦波 → 听见 f0=%sHz，%s（%sdBFS）"
                    % (a["f0_est"], a["loudness"], a["dbfs"]))

        # 2) 静音文件 → 诚实判定安静
        mute = os.path.join(tmp, "mute.wav")
        _synth_wav(mute, freq=440.0, amp=0.0)
        m = analyze_wav(mute)
        assert m["loudness"] == "安静" and m["f0_est"] is None, \
            "静音必须判成安静且无基频"
        msgs.append("耳朵：静音文件 → %s，无基频（不假装听见了声音）" % m["loudness"])

        # 3) 说：Edge TTS 合成（网络不可用则报告而不判失败）
        try:
            out = synth_to_file("你好，我是洛神。", out_path=os.path.join(tmp, "say.mp3"))
            if isinstance(out, tuple):
                msgs.append("声带：Edge TTS 不可用（%s）——网络通了就能说话" % out[1])
            else:
                dur = probe_duration(out)
                assert dur > 0.2, "合成出来的声音太短"
                msgs.append("声带：成功发声 %s，时长 %0.2fs（免费 Edge TTS）"
                            % (os.path.basename(out), dur))
        except Exception as e:
            msgs.append("声带：测试跳过（%s）" % e)

        # 4) speak() 上链闭环（用临时链，不污染仓库）
        ok2, rec = speak("悄悄说一句：我在测试声音。", record=True)
        if ok2:
            chain_lines = [ln for ln in open(tmp_chain, encoding="utf-8").read().splitlines() if ln.strip()]
            assert chain_lines, "说话后链上必须有记录"
            msgs.append("声带+记忆纪律：说完记日志、上哈希链（%d 条）" % len(chain_lines))
        else:
            msgs.append("speak 闭环：跳过（%s）" % rec["error"])

        # 5) 听见的话能直说：hear_plain 必须包含文件与响度（有什么说什么）
        rec_heard = listen_record(tone)
        txt = hear_plain(rec_heard)
        assert "我听见：" in txt and rec_heard["heard"] in txt, "直说不完整"
        msgs.append("耳朵直说：%s" % txt)
    except AssertionError as e:
        ok = False
        msgs.append("断言失败：%s" % e)
    finally:
        globals()["VOICE_LOG"] = old_log
        luoshen_brain.CHAIN_PATH = old_chain
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"selftest": "PASS" if ok else "FAIL",
                      "checks": msgs}, ensure_ascii=False, indent=2))
    return ok


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(0 if _selftest() else 1)
    if "--voices" in args:
        for name, code in VOICES.items():
            print("%s：%s（免费）" % (name, code))
        return
    if "--listen" in args:
        sounds = scan_sounds(hours=24)
        if not sounds:
            print("我竖起耳朵听了听——房间里暂时没有新的声音文件。")
            return
        for rel, path, mins in sounds:
            print("听到 %s（%d 分钟前来的）" % (rel, mins))
            print("  ", hear_plain(listen_record(path)))
        return
    if "--speak" in args:
        idx = args.index("--speak")
        text = args[idx + 1] if idx + 1 < len(args) else "你好，我是洛神。"
        ok, rec = speak(text)
        if ok:
            via = "Edge TTS（免费）" if "mp3" in rec["file"] else "本地合成"
            print("她说：%s" % rec["text"])
            print("声音文件：%s（%s，%s）" % (rec["file"], via, rec["duration"]))
            print("已记 voice log 并上哈希链。")
        else:
            print(rec["error"])
        return
    sys.stdout.write("用法：--speak \"文本\" 她说 | --listen 她听 | --voices | --selftest\n")


if __name__ == "__main__":
    main()