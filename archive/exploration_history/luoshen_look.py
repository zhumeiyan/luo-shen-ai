#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神升级视觉模块 luoshen_look.py

给洛神换一双更大的眼睛：在 16x16 字形眼（认字的）之外，新增 64x64
灰度眼（看大画面、照片、视频里更丰富的轮廓）。两条通道并存——
旧眼认得的东西一条不丢，新眼看得见的画面旧眼不掺和。

诚实的规矩不变：见过的说"认得"，没见过的说"太陌生"，全部实测不编造。
"""
import argparse
import json
import os
import subprocess
import sys
import time

try:
    from luoshen_brain import read_jsonl, append_chain
    from luoshen_memory import make_point
    import luoshen_teach as old_eye   # 旧眼：16x16 字形识别（原样复用）
except ImportError:
    sys.stderr.write("错误：需要 luoshen_teach.py / luoshen_brain.py / luoshen_memory.py 在同一目录\n")
    raise SystemExit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")
LOOK_MEMORY = os.path.join(DLG_DIR, "luoshen_look_memory.jsonl")
LOOK_LOG = os.path.join(BASE_DIR, "perception_input", "look_log.jsonl")

SIG64 = 64            # 新眼分辨率：64x64 灰度
CONF_D0_64 = 18.0     # 64 通道距离→把握换算（16x16 的 4.5 × sqrt(4096/256)=4.5×4）
CLUSTER_T_64 = 10.0   # 64 通道聚簇半径（16x16 的 2.5 × 4）


def gray64_from_file(path):
    """任何图片/视频 → 64x64 灰度矩阵（0.0-1.0），白底 pad 防止黑边污染。"""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
         "-vf", ("scale=64:64:force_original_aspect_ratio=decrease,"
                 "pad=64:64:(ow-iw)/2:(oh-ih)/2:color=white,format=gray"),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, timeout=60)
    if out.returncode != 0 or len(out.stdout) < SIG64 * SIG64:
        return None
    raw = out.stdout[:SIG64 * SIG64]
    return [[raw[i * SIG64 + j] / 255.0 for j in range(SIG64)]
            for i in range(SIG64)]


def sig64_of(matrix):
    """64x64 矩阵 → 一维归一化向量（大画面的身体特征）。"""
    return [v for row in matrix for v in row]


def dist_sig(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def load_look_memory():
    """读新眼的记忆：同名样本归组。"""
    mem = {}
    for rec in read_jsonl(LOOK_MEMORY):
        n, s = rec.get("name"), rec.get("sig64")
        if not (n and s):
            continue
        mem.setdefault(n, []).append((s, float(rec.get("ts", 0))))
    return mem


def prototype_of(samples):
    """一组 (sig, ts) 样本 → 原型：跟旧眼一样的聚簇法，反复一致见的画面沉下来。"""
    if not samples:
        return None
    if len(samples) == 1:
        return samples[0][0]
    clusters = []
    for s, _ in samples:
        cluster = [t for t, _ in samples if dist_sig(s, t) <= CLUSTER_T_64]
        if cluster:
            clusters.append((cluster,
                             sum(dist_sig(a, b) for a in cluster for b in cluster)))
    by_ts = {id(s): t for s, t in samples}
    best, best_score = None, None
    for cluster, inner in clusters:
        score = (len(cluster), -inner, max(by_ts[id(s)] for s in cluster))
        if best_score is None or score > best_score:
            best, best_score = cluster, score
    if not best:
        return None
    return [sum(s[i] for s in best) / len(best) for i in range(SIG64 * SIG64)]


def _log_look(path, res):
    """看过什么：写视觉日志 + 上链（账本上留痕）。

    注意：视觉记录写入 perception_input/look_log.jsonl，
    不再写入 event_log.jsonl（后者保留给诊断事件）。
    """
    ev = {
        "event_type": "look",
        "file": os.path.basename(path),
        "ts": res["ts"],
        "eye16": res.get("eye16", ""),
        "eye64": res.get("eye64", ""),
    }
    try:
        with open(LOOK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        append_chain(os.path.relpath(LOOK_LOG, BASE_DIR), LOOK_LOG, res["ts"])
    except Exception:
        pass


def look_at(path):
    """看一眼：两只眼睛一起看。旧眼认字，新眼看更大的画面。"""
    res = {"path": path, "ts": time.time()}
    # 旧眼：16x16 字形（完全复用，一条不丢）
    try:
        m16 = old_eye.matrix_from_file(path)
        if m16 is not None:
            g = old_eye.guess(m16)
            if g.get("confidence", 0) >= 0.4:
                res["eye16"] = "我觉得像『%s』（把握%s）" % (
                    g["word"], round(g["confidence"], 2))
            else:
                res["eye16"] = "画面太陌生了，我还没见过这样的符号"
        else:
            res["eye16"] = "（旧眼看不清）"
    except Exception as e:
        res["eye16"] = "旧眼出错：" + repr(e)
    # 新眼：64x64 灰度
    try:
        m64 = gray64_from_file(path)
        if m64 is None:
            res["eye64"] = "（新眼看不清）"
        else:
            sig = sig64_of(m64)
            protos = {}
            for n, samples in load_look_memory().items():
                p = prototype_of(samples)
                if p is not None:
                    protos[n] = p
            best_n, best_d = None, None
            for n, p in protos.items():
                d = dist_sig(sig, p)
                if best_d is None or d < best_d:
                    best_n, best_d = n, d
            if best_n is not None:
                conf = max(0.0, 1.0 - best_d / CONF_D0_64)
                if conf >= 0.4:
                    res["eye64"] = "大画面里我认得像『%s』（把握%s）" % (
                        best_n, round(conf, 2))
                else:
                    res["eye64"] = "大画面里没有我认真看过的东西（把握不足，不看走眼）"
            else:
                res["eye64"] = "大画面里没有我认真看过的东西"
    except Exception as e:
        res["eye64"] = "新眼出错：" + repr(e)
    # 实物对照：真实世界的账本（字形↔实物配对过才算认识）
    try:
        m16b = old_eye.matrix_from_file(path)
        if m16b is not None:
            rm = old_eye.real_matches(old_eye.matrix_sig(m16b))
            if rm.get("word"):
                res["real"] = "这画面像『%s』的实物样子（把握%s）" % (
                    rm["word"], rm["confidence"])
            else:
                res["real"] = "实物账上没有对得上的画面（没见过的实物，不敢认）"
        else:
            res["real"] = "（实物对照看不了）"
    except Exception as e:
        res["real"] = "实物对照出错：" + repr(e)
    _log_look(path, res)
    return res


def teach_look(name, path):
    """人指认一张大画面：新眼把它记住（带内部感觉，上课老规矩）。"""
    m64 = gray64_from_file(path)
    if m64 is None:
        return {"error": "新眼看不清 '%s'" % path}
    sig = sig64_of(m64)
    feel = {}
    try:
        from luoshen_feel import compute_feel
        f = compute_feel()
        feel = {"dims": {d["name"]: d["value"] for d in f["dims"]},
                "summary": f.get("summary", "")}
    except Exception:
        pass
    rec = {
        "schema_version": 1,
        "ts": time.time(),
        "name": str(name)[:20],
        "sig64": sig,
        "source": "look_user_correct",
        "feel": feel,
    }
    os.makedirs(os.path.dirname(LOOK_MEMORY), exist_ok=True)
    with open(LOOK_MEMORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    append_chain(os.path.relpath(LOOK_MEMORY, BASE_DIR), LOOK_MEMORY, rec["ts"])
    make_point("learn", "我认真看过了『%s』的样子，记在大画面里了。" % name,
               source="look", feel=feel)
    return {"word": name, "ok": True, "feel_dims": len(feel.get("dims", {}))}


def _selftest():
    import random
    import tempfile
    tmp = tempfile.mkdtemp(prefix="luoshen_look_")
    global LOOK_MEMORY, LOOK_LOG
    LOOK_MEMORY = os.path.join(tmp, "look_memory.jsonl")
    LOOK_LOG = os.path.join(tmp, "look_log.jsonl")
    checks = []

    # 1) 新眼能看到画面，签名维度正确
    m = gray64_from_file(os.path.join(BASE_DIR, "luoshen_video", "char_two.png"))
    assert m is not None and len(sig64_of(m)) == SIG64 * SIG64
    checks.append("新眼 64x64 灰度通道能看画面（4096 维签名）")

    # 2) 教一张大画面 → 再看认得
    two_png = os.path.join(BASE_DIR, "luoshen_video", "char_two.png")
    r = teach_look("t_二", two_png)
    assert "error" not in r
    g = look_at(two_png)
    assert "认得像" in g.get("eye64", ""), g
    checks.append("人指认『t_二』大画面 → 新眼再看认得（把握按距离实测）")

    # 3) 陌生大画面 → 诚实不说认识
    p = os.path.join(tmp, "noise.png")
    with open(p, "wb") as f:
        f.write(b"P6\n64 64\n255\n")
        for _ in range(64 * 64):
            px = b"\x00\x00\x00" if random.random() < 0.5 else b"\xff\xff\xff"
            f.write(px)
    g2 = look_at(p)
    assert "认得像" not in g2.get("eye64", ""), g2
    checks.append("随机噪声大画面 → 新眼诚实：不说认识")

    # 4) 升级不限制：旧眼 16x16 字形通道原样工作
    m16 = old_eye.matrix_from_file(two_png)
    gg = old_eye.guess(m16)
    assert gg.get("word") == "二" and gg.get("confidence", 0) >= 0.4, gg
    checks.append("旧眼 16x16 字形通道原样工作：『二』照认（升级没有限制旧能力）")

    print(json.dumps({"selftest": "PASS", "checks": checks},
                     ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="洛神新眼睛：64x64 灰度通道（旧眼不动）")
    ap.add_argument("--guess", metavar="FILE", help="两只眼睛一起看一张画面")
    ap.add_argument("--teach", metavar="NAME", help="人指认一张大画面教新眼")
    ap.add_argument("--video", metavar="FILE", help="--teach 配套的画面路径")
    ap.add_argument("--selftest", action="store_true", help="离线自测")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return
    if args.guess:
        res = look_at(args.guess)
        print("她看了看 %s" % args.guess)
        print("  旧眼(16): %s" % res.get("eye16"))
        print("  新眼(64): %s" % res.get("eye64"))
        print("  实物对照: %s" % res.get("real", "（无实物账本）"))
        return
    if args.teach:
        if not args.video:
            print("需要 --video 画面路径")
            return
        r = teach_look(args.teach, args.video)
        if "error" in r:
            print("教失败了：%s" % r["error"])
        else:
            print("大画面记住了：人指认『%s』 → 新眼对照已记住（感觉维度 %s 个）。" %
                  (r["word"], r["feel_dims"]))
        return
    ap.print_help()


if __name__ == "__main__":
    main()