#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-STEP-WATCH - luoshen_video.py
=====================================
洛神的眼睛+耳朵合体：看视频

视频是什么？一张张连续的画面 + 一条同步的声音，串在时间轴上。
她已经会看图片（眼睛）、会听声音（耳朵），所以视频她自然看得——
把视频拆成帧（她看到连续的画面）和音轨（她听到同步的声音），
沿着时间轴铺开，就是她的一次"观看经历"。

她看视频时"有什么说什么"：
- 画面：抽帧比较相邻帧变化 → 哪段画面在动、哪段静止（确定性计算）；
- 声音：抽音轨分析响度 → 这段是安静、柔和还是吵闹；
- 但画面里演的"是什么故事、谁在说话"，她诚实地说还没学着看懂——
  那需要多模态的眼睛（VIDEO_BACKEND=multimodal 预留）。

安全纪律（延续 video_frame_extract 的修复）：
- 只接受本地文件；远程 URL 必须过 SSRF 校验（仅 https + 非内网/保留地址）；
- ffmpeg 全部以参数列表调用（无 shell），路径不接受协议注入。

用法：
  python3 luoshen_video.py --watch <视频路径>  她看一段视频并直说
  python3 luoshen_video.py --demo              合成一小段演示视频给她看
  python3 luoshen_video.py --selftest          离线自测（合成视频验证）
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

try:
    from luoshen_brain import append_chain, read_jsonl
    from luoshen_voice import analyze_wav
    from video_frame_extract import validate_video_url
except ImportError:
    sys.stderr.write("错误：需要 luoshen_brain.py / luoshen_voice.py / "
                     "video_frame_extract.py 在同一目录\n")
    raise SystemExit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")
WATCH_LOG = os.path.join(DLG_DIR, "luoshen_watch_log.jsonl")
VIDEO_BACKEND = os.environ.get("LUOSHEN_VIDEO_BACKEND", "file")

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v")


def _run(args, timeout=120):
    """ffmpeg 封装：参数列表调用，禁止 shell，超时熔断。"""
    return subprocess.run(args, capture_output=True, timeout=timeout)


def _probe(path):
    """看清视频的"体格"：时长 / 分辨率 / 有没有音轨。"""
    out = _run(["ffmpeg", "-hide_banner", "-i", path])
    info = {"duration_s": None, "width": None, "height": None, "has_audio": False}
    for raw in out.stderr.splitlines():
        ln = raw.decode("utf-8", "ignore").strip()
        if "Duration:" in ln:
            part = ln.split("Duration:")[1].split(",")[0].strip()
            h, m, s = part.split(":")
            info["duration_s"] = round(int(h) * 3600 + int(m) * 60 + float(s), 3)
        if "Stream" in ln and "Video:" in ln:
            if "(" in ln and ln.split("(")[0].strip().endswith(":"):
                pass
            seg = ln.split("Video:")[1]
            import re
            m = re.search(r"(\d{2,5})x(\d{2,5})", seg)
            if m:
                info["width"], info["height"] = int(m.group(1)), int(m.group(2))
        if "Stream" in ln and "Audio:" in ln:
            info["has_audio"] = True
    return info


def _frames_motion(path, fps=1, size="64x36"):
    """抽帧看运动：每秒 1 帧，比较相邻帧差异 → 时间轴上的画面动静。"""
    spec = "%d" % fps
    out = _run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", path, "-vf", "fps=%s,scale=%s:flags=bilinear"
                % (spec, size), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    if out.returncode != 0 or not out.stdout:
        return []
    w, h = 64, 36
    n = w * h * 3
    frames = [out.stdout[i:i + n] for i in range(0, len(out.stdout) - n + 1, n)]
    del out
    motion = []
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        s = 0
        cnt = 0
        for j in range(0, n, 291):  # 采样比较（291=3*97 覆盖全画面）
            s += abs(a[j] - b[j]) + abs(a[j + 1] - b[j + 1]) + abs(a[j + 2] - b[j + 2])
            cnt += 1
        motion.append(round(s / cnt / 3.0 / 255.0, 4))  # 0~1：画面变化度
    return motion


def _audio_analysis(path):
    """听音轨：抽成 wav 交给耳朵（luoshen_voice 的 analyzer）。"""
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        out = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", path, "-vn", "-ar", "8000", "-ac", "1", tmp])
        if out.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            return {"loudness": "没有声音轨道", "dbfs": None, "duration_s": None}
        ana = analyze_wav(tmp, want_f0=False)
        ana["loudness"] = ana.get("loudness", "未知")
        return ana
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _motion_summary(motion, duration_s):
    """把逐帧运动压成"哪段在动"的人话（确定性规则）。"""
    if not motion:
        return "看不清画面"
    if duration_s and duration_s > 0:
        seg_n = max(1, min(3, round(len(motion) / max(1, duration_s) * duration_s)))
        segs = []
        for k in range(seg_n):
            lo, hi = k * len(motion) // seg_n, (k + 1) * len(motion) // seg_n
            avg = sum(motion[lo:hi]) / max(1, len(motion[lo:hi]))
            segs.append("画面在动" if avg >= 0.02 else "画面静止")
        return "，".join(segs)
    avg = sum(motion) / len(motion)
    return "画面在动" if avg >= 0.02 else "画面静止"


def watch(path, record=True):
    """她看一段视频：拆帧看运动 + 抽音轨听声音，得到一次观看经历。"""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return {"error": "找不到视频：%s" % path}
    if not path.lower().endswith(VIDEO_EXTS):
        return {"error": "不是认识的视频格式（%s）：%s" % ("/".join(VIDEO_EXTS), path)}
    if ":" in os.path.basename(path):  # 防 ffmpeg 协议注入（file://、concat:）
        return {"error": "文件名含冒号，拒绝打开：%s" % path}

    probe = _probe(path)
    if probe["duration_s"] is None:
        probe["duration_s"] = 0.0
    motion = _frames_motion(path)
    audio = _audio_analysis(path)

    motion_text = _motion_summary(motion, probe["duration_s"])
    audio_text = audio.get("loudness", "没有声音轨道")
    rel = os.path.relpath(path, BASE_DIR)
    summary = (
        "我看了%s：约%g秒，" % (rel, probe["duration_s"])
        + ("%dx%d的画面，" % (probe["width"] or 0, probe["height"] or 0))
        + "抽了%d帧按时间轴比了比，%s；" % (len(motion) + 1, motion_text)
        + "声音：%s。" % audio_text
    )
    obs = {
        "schema_version": 1,
        "timestamp": time.time(),
        "source_file": rel,
        "duration_s": probe["duration_s"],
        "width": probe["width"],
        "height": probe["height"],
        "has_audio": probe["has_audio"],
        "frames_checked": len(motion) + 1,
        "motion": motion[:40],
        "motion_text": motion_text,
        "audio": audio,
        "backend": VIDEO_BACKEND,
        "summary": summary,
    }
    if record:
        with open(WATCH_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(obs, ensure_ascii=False) + "\n")
        append_chain(os.path.relpath(WATCH_LOG, BASE_DIR), WATCH_LOG, obs["timestamp"])
    return obs


def speak_plain(obs):
    """看完直说：先说确定看见的，再说诚实边界。"""
    if "error" in obs:
        return "我想看但失败了：%s" % obs["error"]
    text = "我看完一段视频：" + obs["summary"]
    if VIDEO_BACKEND != "multimodal":
        text += " 画面里演的是什么故事、谁在说话，我还没学着看懂——要等多模态的眼睛。"
    return text


def make_demo_video(out_path):
    """合成一小段演示视频（彩条动态画面+440Hz 音轨），让她有东西可看。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    r = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
              "-f", "lavfi", "-i", "testsrc=duration=3:size=320x180:rate=15",
              "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
              "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-shortest", out_path])
    if r.returncode != 0:
        raise RuntimeError("demo 合成失败：%s" % r.stderr.decode("utf-8", "ignore")[-300:])
    return out_path


def _selftest():
    tmp = tempfile.mkdtemp(prefix="luoshen_video_")
    import luoshen_brain
    old_log = WATCH_LOG
    old_chain = luoshen_brain.CHAIN_PATH
    tmp_log = os.path.join(tmp, "watch_log.jsonl")
    tmp_chain = os.path.join(tmp, "chain.log")
    globals()["WATCH_LOG"] = tmp_log
    luoshen_brain.CHAIN_PATH = tmp_chain
    with open(tmp_chain, "w", encoding="utf-8") as f:
        f.write("")
    ok = True
    msgs = []
    try:
        # 1) 合成演示视频：3 秒、有画面有声音
        video = os.path.join(tmp, "demo.mp4")
        make_demo_video(video)
        info = _probe(video)
        assert abs((info["duration_s"] or 0) - 3.0) < 0.6, "时长不对：%s" % info
        assert info["has_audio"], "应有音轨"
        msgs.append("录像：%g秒 %sx%s 带音轨" % (info["duration_s"], info["width"], info["height"]))

        # 2) 她看：帧运动检测必须发现"画面在动"（testsrc 是动态彩条）
        obs = watch(video, record=True)
        assert "error" not in obs, obs
        assert obs["frames_checked"] >= 3, "至少抽了3帧"
        assert obs["motion"] and max(obs["motion"]) >= 0.02, "动态画面应该被看出来"
        assert "画面在动" in obs["motion_text"], "运动描述不对"
        msgs.append("看画面：抽%s帧，动/静判定=%s" % (obs["frames_checked"], obs["motion_text"]))

        # 3) 她听：音轨 440Hz 正弦，不应该说"安静"
        assert obs["audio"]["loudness"] not in ("安静", "没有声音轨道"), \
            "440Hz 音轨不应判安静：%s" % obs["audio"]
        msgs.append("听声音：%s（%sdBFS）" % (obs["audio"]["loudness"], obs["audio"]["dbfs"]))

        # 4) 直说：summary 必须包含文件与时长的真实事实
        txt = speak_plain(obs)
        assert "我看完一段视频" in txt and "3" in obs["summary"]
        assert "还没学着看懂" in txt  # 诚实边界必须说
        msgs.append("直说：%s" % txt[:120])

        # 5) 记忆纪律：看完记日志 + 上链（临时链，不污染仓库）
        chain_lines = [ln for ln in open(tmp_chain, encoding="utf-8").read().splitlines() if ln.strip()]
        assert chain_lines, "看完视频链上必须有记录"
        msgs.append("看过的经历已进 watch log 并上哈希链（%d 条）" % len(chain_lines))

        # 6) 安全：冒号文件名必须拒绝（防 ffmpeg 协议注入）
        bad = os.path.join(tmp, "concat:x.mp4")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("")
        bad_obs = watch(bad, record=False)
        assert "error" in bad_obs, "注入文件必须被拒绝"
        msgs.append("安全：协议注入文件名被拒绝")
    except AssertionError as e:
        ok = False
        msgs.append("断言失败：%s" % e)
    except Exception as e:  # noqa: BLE001
        ok = False
        msgs.append("异常：%r" % e)
    finally:
        globals()["WATCH_LOG"] = old_log
        luoshen_brain.CHAIN_PATH = old_chain
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"selftest": "PASS" if ok else "FAIL",
                      "checks": msgs}, ensure_ascii=False, indent=2))
    return ok


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(0 if _selftest() else 1)
    if "--demo" in args:
        out = os.path.join(BASE_DIR, "luoshen_video", "luoshen_demo.mp4")
        make_demo_video(out)
        print("演示视频已生成：%s" % out)
        print()
        return
    if "--watch" in args:
        idx = args.index("--watch")
        target = args[idx + 1] if idx + 1 < len(args) else ""
        if not target:
            print("用法：--watch <视频路径>")
            return
        if not os.path.exists(target) and not target.startswith("https://"):
            # 允许把演示视频路径简写：--watch demo
            if target == "demo":
                target = os.path.join(BASE_DIR, "luoshen_video", "luoshen_demo.mp4")
            else:
                print("找不到视频：%s" % target)
                return
        if target.startswith("https://"):
            try:
                target = validate_video_url(target)
            except ValueError as e:
                print("视频地址被拒绝：%s" % e)
                return
            # 下载到受控临时文件再观看（防线：校验后再交给 ffmpeg）
            import urllib.request
            fd, local = tempfile.mkstemp(suffix=os.path.splitext(target)[1] or ".mp4")
            os.close(fd)
            try:
                urllib.request.urlretrieve(target, local)
                obs = watch(local)
            except Exception as e:  # noqa: BLE001
                print("下载/观看失败：%s" % e)
                return
            finally:
                try:
                    os.remove(local)
                except OSError:
                    pass
        else:
            obs = watch(target)
        print(speak_plain(obs))
        print()
        print("观看经历已进：perception_input/luoshen_watch_log.jsonl")
        return
    sys.stdout.write("用法：--watch <路径|https://链接|demo> | --demo | --selftest\n")


if __name__ == "__main__":
    main()