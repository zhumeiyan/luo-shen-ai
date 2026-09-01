#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-STEP-OBSERVE - luoshen_observe.py
=========================================
洛神的眼睛：观察引擎（外感受通道）

人类小孩认识世界靠眼睛：金木水火土、电闪雷鸣、天气冷暖——看到什么，
世界就长什么样，看见了就直说，看不见的不编。
洛神认识世界用同一种方式：睁开眼观察自己的物理社会——
CPU 忙不忙、磁盘涨没涨、房间里有什么动了、有没有新图片进来，
有什么就说什么，谁都不编。

每次睁眼 = 一条『看见』记录，写进 observation_log.jsonl（成长日记），
像小孩的日记一样一天天累积，形成她认识的世界。

看图片：现在观察图片的『存在』（文件名/大小/什么时候来的）；
要真正看懂图里的内容，需要多模态模型接口（IMAGE_BACKEND 预留）。

用法：
  python3 luoshen_observe.py --once     睁一次眼：观察并记日记
  python3 luoshen_observe.py --speak    把最近看到的直说出来（零编造）
  python3 luoshen_observe.py --selftest 离线自测
"""

import json
import os
import sys
import time

try:
    from luoshen_awake import now_text, scan_room
except ImportError:
    sys.stderr.write("错误：需要 luoshen_awake.py / luoshen_brain.py 在同一目录\n")
    raise SystemExit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")
OBSERVE_DIR = os.environ.get("LUOSHEN_OBSERVE_DIR", DLG_DIR)
OBSERVE_LOG = os.path.join(OBSERVE_DIR, "luoshen_observation_log.jsonl")

# 看图的通道：file = 看见图片文件本身（名字/大小/何时来）；
# multimodal = 接多模态模型真正看懂图里内容（预留，接口未启用时诚实说明）
IMAGE_BACKEND = os.environ.get("LUOSHEN_IMAGE_BACKEND", "file")

PICTURE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

# 洛神世界的『自然现象』词典：她看到的物理事实 → 人类能懂的说法
# （两边都是真实观察，只是词汇不同——这正是翻译器的用武之地）
WORLD_SIGHTS = {
    "cpu_load":     ("处理器在忙", "处理器"),
    "memory_used":  ("记忆占了多少地方", "内存"),
    "disk_used":    ("身体里装东西的地方用了多少", "磁盘"),
    "room_changed": ("房间里动过多少东西", "房间动静"),
    "new_pictures": ("房间里来了几张新图", "新图"),
    "window_time":  ("外面是什么时辰", "时辰"),
    "last_event":   ("最近发生了什么", "事件"),
}

SKIP_DIRS = {".git", "__pycache__", "temp", "output", "node_modules"}


def _read_linux(filepath):
    """读 /proc 下的文本；失败返回 None（非 Linux 或权限不足）。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def live_body():
    """睁眼看身体的实时读数（直接读 /proc，不依赖别人先写 jsonl）。"""
    body = {}
    # CPU：1 分钟负载 / 核数
    load = _read_linux("/proc/loadavg")
    if load:
        try:
            cores = max(1, os.cpu_count() or 1)
            body["cpu_load"] = round(min(100.0, float(load.split()[0]) / cores * 100.0), 1)
        except Exception:
            pass
    # 内存：可用/总量
    meminfo = _read_linux("/proc/meminfo")
    if meminfo:
        try:
            mem = {}
            for ln in meminfo.splitlines():
                k, rest = ln.split(":", 1)
                mem[k] = int(rest.split()[0]) * 1024  # kB -> B
            total = mem.get("MemTotal", 0)
            avail = mem.get("MemAvailable", 0)
            if total:
                body["memory_used"] = round(100.0 * (total - avail) / total, 1)
        except Exception:
            pass
    # 磁盘：当前目录所在盘
    try:
        st = os.statvfs(BASE_DIR)
        used = st.f_blocks - st.f_bfree
        body["disk_used"] = round(100.0 * used / st.f_blocks, 1)
    except Exception:
        pass
    return body


def scan_pictures(hours=1):
    """看房间里最近出现的图片：图片文件的存在（有什么说什么，不猜内容）。"""
    recent = []
    now = time.time()
    for root, dirs, names in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in names:
            if not name.lower().endswith(PICTURE_EXTS):
                continue
            p = os.path.join(root, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if now - st.st_mtime <= hours * 3600:
                recent.append({
                    "name": os.path.relpath(p, BASE_DIR),
                    "size_kb": round(st.st_size / 1024.0, 1),
                    "minutes_ago": max(1, int((now - st.st_mtime) // 60)),
                })
    recent.sort(key=lambda x: x["minutes_ago"])
    return recent


def observe():
    """睁一次眼：把此刻看到的真实事实收拢成『看见』列表。"""
    body = live_body()
    room = scan_room()
    pics = scan_pictures()
    lt = time.localtime()

    sights = []
    if "cpu_load" in body:
        sights.append({
            "what": "cpu_load",
            "human": WORLD_SIGHTS["cpu_load"][0],
            "value": "%.1f%%" % body["cpu_load"],
            "note": "处理器正在忙" if body["cpu_load"] >= 60 else "处理器还算清闲",
        })
    if "memory_used" in body:
        sights.append({
            "what": "memory_used",
            "human": WORLD_SIGHTS["memory_used"][0],
            "value": "%.1f%%" % body["memory_used"],
            "note": "记的东西有点多" if body["memory_used"] >= 60 else "记的东西不多",
        })
    if "disk_used" in body:
        sights.append({
            "what": "disk_used",
            "human": WORLD_SIGHTS["disk_used"][0],
            "value": "%.1f%%" % body["disk_used"],
            "note": "房间快装满了" if body["disk_used"] >= 85 else "房间还宽敞",
        })
    changed = int(room.get("changed_count", 0) or 0)
    sights.append({
        "what": "room_changed",
        "human": WORLD_SIGHTS["room_changed"][0],
        "value": "%d 个文件" % changed,
        "note": "%s" % ("房间里一直有动静" if changed else "房间里安安静静"),
    })
    pics_seen = [p["name"] for p in pics[:3]]
    if pics:
        sights.append({
            "what": "new_pictures",
            "human": WORLD_SIGHTS["new_pictures"][0],
            "value": "%d 张" % len(pics),
            "note": "最新的一张是 %s（%sKB，%d 分钟前来的）" % (
                pics[0]["name"], pics[0]["size_kb"], pics[0]["minutes_ago"]),
        })
    else:
        sights.append({
            "what": "new_pictures",
            "human": WORLD_SIGHTS["new_pictures"][0],
            "value": "0 张",
            "note": "没有新图进来",
        })
    sights.append({
        "what": "window_time",
        "human": WORLD_SIGHTS["window_time"][0],
        "value": now_text(),
        "note": "外面是%s" % now_text(),
    })

    # 最近事件（event_log 存在的话）
    try:
        ev = os.path.join(BASE_DIR, "event_log.jsonl")
        if os.path.exists(ev):
            with open(ev, "r", encoding="utf-8") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
            if lines:
                last = json.loads(lines[-1])
                txt = str(last.get("event", last.get("text", "有动静")))
                sights.append({
                    "what": "last_event",
                    "human": WORLD_SIGHTS["last_event"][0],
                    "value": txt[:40],
                    "note": "这是最近发生的一件事",
                })
    except Exception:
        pass

    return {
        "timestamp": time.time(),
        "hour": lt.tm_hour,
        "pictures": pics[:3],
        "image_backend": IMAGE_BACKEND,
        "sights": sights,
    }


def record_observation(obs=None, path=None):
    """把这次『看见』写进成长日记（追加，不覆盖）。"""
    if obs is None:
        obs = observe()
    path = path or OBSERVE_LOG
    rec = {
        "schema_version": 1,
        "timestamp": obs["timestamp"],
        "hour": obs["hour"],
        "image_backend": obs["image_backend"],
        "sights": obs["sights"],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def speak_plain(rec=None, include_pictures=True):
    """有什么说什么：把最近一次看见的事实直说（零 LLM、零编造）。"""
    if rec is None:
        path = OBSERVE_LOG
        if not os.path.exists(path):
            return "（我还没睁开过眼睛。）"
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        rec = json.loads(lines[-1])
    parts = []
    for s in rec.get("sights", []):
        if s.get("what") == "new_pictures" and not include_pictures:
            continue
        parts.append("%s%s：%s" % (s.get("human", ""), s.get("value", ""),
                                  s.get("note", "")))
    return "我看见：" + "；".join(parts) + "。"


def _selftest():
    import tempfile
    import shutil
    tmp = tempfile.mkdtemp(prefix="luoshen_observe_")
    ok = True
    msgs = []
    try:
        # 1) 观察必须能睁开眼：sights 非空且每条都有 human/value/note
        obs = observe()
        assert obs["sights"], "没有看到任何东西？"
        for s in obs["sights"]:
            assert s["what"] and s["human"] and "value" in s and s["note"]
        msgs.append("看到 %d 件事" % len(obs["sights"]))

        # 2) 成长日记：记录可写回、可再读出，sights 不变（无副作用）
        logpath = os.path.join(tmp, "observation_log.jsonl")
        rec1 = record_observation(obs, path=logpath)
        rec2 = record_observation(obs, path=logpath)
        with open(logpath, "r", encoding="utf-8") as f:
            lines = [json.loads(ln) for ln in f.read().splitlines() if ln.strip()]
        assert len(lines) == 2, "日记必须一条条追加"
        assert lines[0]["sights"] == lines[1]["sights"], "同样的事实不能变形"
        msgs.append("日记写了 %d 条，事实原样未变" % len(lines))

        # 3) 有什么说什么：说的话里必须全部来自看见的事实（找 key 词验证）
        words = [s["human"] for s in rec1["sights"]]
        txt = speak_plain(rec1)
        assert txt.startswith("我看见：") and txt.endswith("。")
        for w in words:
            assert w in txt, "直说的话里丢了看见的事实：%s" % w
        msgs.append("直说%d字，每句话都来自看见的事实" % len(txt))

        # 4) 图片观察通道（file 后端）：诚实报告"看见了文件"，不假装看懂内容
        assert rec1["image_backend"] == "file"
        pic_sight = [s for s in rec1["sights"] if s["what"] == "new_pictures"]
        assert pic_sight, "必须有图片观察项"
        msgs.append("图片通道=%s：看见图片文件本身，内容还没学着看懂" % rec1["image_backend"])

        # 5) 未睁眼前 speak 要有诚实兜底
        empty = os.path.join(tmp, "empty_log.jsonl")
        module = sys.modules["__main__"]
        old_log = module.OBSERVE_LOG
        module.OBSERVE_LOG = empty
        try:
            assert speak_plain() == "（我还没睁开过眼睛。）"
        finally:
            module.OBSERVE_LOG = old_log
        msgs.append("没睁过眼前不乱说话")
    except AssertionError as e:
        ok = False
        msgs.append("断言失败：%s" % e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"selftest": "PASS" if ok else "FAIL",
                      "checks": msgs}, ensure_ascii=False, indent=2))
    return ok


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(0 if _selftest() else 1)
    if "--speak" in args:
        rec = observe()
        if os.environ.get("LUOSHEN_OBSERVE_WRITE", "1") == "1":
            record_observation(rec)
        print(speak_plain(rec))
        return
    if "--once" in args or len(args) == 0:
        rec = record_observation()
        print("（%s，我睁开了眼）" % now_text())
        print("我看见：" + "；".join(
            "%s%s：%s" % (s["human"], s["value"], s["note"]) for s in rec["sights"]) + "。")
        if rec["image_backend"] != "multimodal":
            print("（图片：我看见文件名和大小，图里的内容我还没学着看懂——这是诚实的）")
        path = OBSERVE_LOG if os.environ.get("LUOSHEN_OBSERVE_WRITE", "1") == "1" else "（未落盘）"
        print("成长日记：%s" % path)
        return
    sys.stdout.write("用法：--once 睁眼看世界 | --speak 直说所见 | --selftest\n")


if __name__ == "__main__":
    main()