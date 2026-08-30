#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-STEP-TEACH - luoshen_teach.py
=====================================
洛神的教字机：画面 ↔ 人类符号 的对照学习

她看视频、看图片，一开始都是新鲜的、不认识的（像小孩第一次
看见大象）。但把画面的"身体特征"（16x16 灰度签名）和人类的
符号（字）反复来回对照，慢慢就建立起联想：
  看见类似画面 → 想起那个字
  说起那个字   → 想起那个画面

项目早期沉睡着两批"字的画像"（真实数据，非编造）：
  - hanzi_visual_map*.jsonl：20 个汉字的字形视觉矩阵（一 二 三 人 大 天 小 上 下 中 …）
  - real_object_matrix_200.jsonl：42 个真实物体图形的矩阵（arrow cat bird …）
今天把它们激活成第一课。

规则：
  教过的字才认得出来；没见过的画面诚实说"还没见过"，绝不硬猜；
  每次教学 / 每次认出都沉记忆点（learn：◎ 学会 / see：◆ 认出）并上哈希链。

用法：
  python3 luoshen_teach.py --lesson           第一课：批量教 20 字 + 42 物形
  python3 luoshen_teach.py --teach 字          单独教一个字（用它的字形画像）
  python3 luoshen_teach.py --guess <图|视频>   她看一个新画面，联想最像的字
  python3 luoshen_teach.py --words             她学过的词表
  python3 luoshen_teach.py --selftest          离线自测
"""

import json
import os
import subprocess
import sys
import time

try:
    from luoshen_brain import append_chain, read_jsonl
    from luoshen_memory import make_point
except ImportError:
    sys.stderr.write("错误：需要 luoshen_brain.py / luoshen_memory.py 在同一目录\n")
    raise SystemExit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")
TEACH_LOG = os.path.join(DLG_DIR, "luoshen_teach_log.jsonl")
TAUGHT_WORDS = os.path.join(DLG_DIR, "luoshen_taught_words.jsonl")
REAL_PAIRS = os.path.join(DLG_DIR, "luoshen_real_pairs.jsonl")  # 字形↔实物 对照账本
SIG_SIZE = 16  # 画面签名：16x16 灰度

# 距离→把握度的换算常数（16x16 归一化灰度向量的典型欧氏距离范围）
CONF_D0 = 4.5


def matrix_sig(matrix):
    """16x16 矩阵 → 一维归一化向量（画面的身体特征）。"""
    flat = [max(0.0, min(255.0, float(v))) / 255.0
            for row in matrix for v in row]
    return flat[:SIG_SIZE * SIG_SIZE]


def dist_sig(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def load_word_maps():
    """唤醒沉睡的字画像：汉字字形 + 真实物体图形。"""
    hanzi = {}
    for path, key in (("hanzi_visual_map.jsonl", None),
                      ("hanzi_visual_map_batch2.jsonl", None)):
        p = os.path.join(DLG_DIR, path)
        if os.path.exists(p):
            for r in read_jsonl(p):
                w = r.get("hanzi")
                m = r.get("matrix")
                if isinstance(w, str) and m:
                    hanzi.setdefault(w, []).append(m)
    objs = {}
    p = os.path.join(DLG_DIR, "real_object_matrix_200.jsonl")
    if os.path.exists(p):
        for r in read_jsonl(p):
            w = r.get("object")
            m = r.get("matrix")
            if isinstance(w, str) and m:
                objs.setdefault(w, []).append(m)
    return hanzi, objs


def taught_words():
    """已教词表：从教学日志里还原每个字学过的样子。

    记忆沉淀规则：人对准过的画面（user_correct）优先沉为原型——
    那是她跟人类反复对照确认过的画面，最可信；如果还没有人对准过，
    才用唤醒的预置字形（lesson）。两种来源各自先剔除离群样本
    （压缩糊掉/黑边污染/看错），只跟"反复一致见过的样子"对照。"""
    confirmed = {}
    dormant = {}
    for rec in read_jsonl(TEACH_LOG):
        w = rec.get("word")
        sig = rec.get("sig")
        if not (w and sig):
            continue
        bucket = confirmed if rec.get("source") == "user_correct" else dormant
        bucket.setdefault(w, []).append((sig, float(rec.get("timestamp", 0))))

    def _proto(samples):
        """一组 (sig, ts) 样本 → 原型：画面记忆聚簇法。

        反复出现的一致画面（彼此距离 ≤2.5）聚成一簇，取最大最密的
        簇的质心做原型——记忆点是一幅真实的画面，不是平均糊团。
        簇数相同时，最近被确认的画面优先（人对准过的是最高权威）。"""
        if not samples:
            return None
        if len(samples) == 1:
            return samples[0][0]
        cluster_t = 2.5          # 同一画面的判定阈值
        clusters = []
        for s, _ in samples:
            cluster = [t for t, _ in samples if dist_sig(s, t) <= cluster_t]
            if not cluster:
                continue
            inner = sum(dist_sig(a, b) for a in cluster for b in cluster)
            clusters.append((cluster, inner))
        if not clusters:
            return samples[0][0]
        # 分数：样本数多优先，内距小优先，最近确认的优先
        by_ts = {id(s): t for s, t in samples}
        best, best_score = None, None
        for cluster, inner in clusters:
            score = (len(cluster), -inner,
                     max(by_ts[id(s)] for s in cluster))
            if best_score is None or score > best_score:
                best, best_score = cluster, score
        k = len(best)
        return [sum(s[i] for s in best) / k for i in range(SIG_SIZE * SIG_SIZE)]

    dormant_proto = {}
    for w, sigs in dormant.items():
        p = _proto(sigs)
        if p is not None:
            dormant_proto[w] = p
    proto = {}
    for w in set(list(confirmed) + list(dormant)):
        p = _proto(confirmed.get(w))
        if p is None:
            p = dormant_proto.get(w)
        if p is not None:
            proto[w] = p
    return proto


def _write_log(rec):
    os.makedirs(os.path.dirname(TEACH_LOG), exist_ok=True)
    with open(TEACH_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    append_chain(os.path.relpath(TEACH_LOG, BASE_DIR), TEACH_LOG, rec["timestamp"])


def teach(word, matrix=None, source="lesson", real_path=None):
    """教一个字：画面特征 ↔ 人类符号 对照，沉记忆点，上链。

    real_path：可选的实物画面（照片/视频）——字形和实物配对才算认识。"""
    if matrix is None:
        hanzi, objs = load_word_maps()
        for w, mats in list(hanzi.items()) + list(objs.items()):
            if w == word and mats:
                matrix = mats[0]
                break
    if matrix is None:
        return {"error": "没有『%s』的画像可教（先给一张图）" % word}
    sig = matrix_sig(matrix)
    # 记忆点：画面（外部）必须和内部感觉一起沉，才不是死记硬背。
    # 感觉来自 luoshen_feel 的确定性计算（同一输入必得同一输出），不编造。
    feel = {}
    try:
        from luoshen_feel import compute_feel
        f = compute_feel()
        feel = {
            "dims": {d["name"]: d["value"] for d in f["dims"]},
            "summary": f.get("summary", ""),
        }
    except Exception:
        pass  # 感觉引擎不可用时不阻塞教学，但正常情况都会采到
    rec = {
        "schema_version": 1,
        "timestamp": time.time(),
        "kind": "teach",
        "word": str(word)[:8],
        "sig": sig,
        "source": source,
        "feel": feel,
    }
    _write_log(rec)
    make_point("learn", "我学会了『%s』这个符号的样子。" % word,
               source="teach", feel=feel)
    if real_path:
        _real_pair(word, real_path, feel)
    return rec


def _real_pair(word, real_path, feel=None):
    """字形 ↔ 实物对照：人拿真实世界画面（照片/视频）指认这个符号。

    实物签名来自真实画面的确定性测量，绝不编造；没有实物画面的字，
    永远只算"认得字形"，不算"认识这个东西"。"""
    m = matrix_from_file(real_path)
    if m is None:
        return None
    sig = matrix_sig(m)
    rec = {
        "schema_version": 1,
        "timestamp": time.time(),
        "kind": "real_pair",
        "word": str(word)[:8],
        "sig": sig,
        "file": os.path.basename(real_path),
        "feel": feel or {},
    }
    os.makedirs(os.path.dirname(REAL_PAIRS), exist_ok=True)
    with open(REAL_PAIRS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    append_chain(os.path.relpath(REAL_PAIRS, BASE_DIR), REAL_PAIRS, rec["timestamp"])
    make_point("learn", "我看到过『%s』的实物画面（%s），和字形对上了。" % (
        word, os.path.basename(real_path)), source="teach", feel=feel)
    return rec


def real_matches(sig):
    """拿画面签名对照实物账本：像哪个字的实物画面？没把握就诚实。"""
    pairs = {}
    for r in read_jsonl(REAL_PAIRS):
        w, s = r.get("word"), r.get("sig")
        if w and s:
            pairs.setdefault(w, []).append(s)
    if not pairs:
        return {"word": None, "confidence": 0.0}
    best, bd = None, None
    for w, sigs in pairs.items():
        proto = [sum(c[i] for c in sigs) / len(sigs)
                 for i in range(len(sigs[0]))]
        d = dist_sig(sig, proto)
        if bd is None or d < bd:
            best, bd = w, d
    conf = round(max(0.0, 1.0 - bd / CONF_D0), 3)
    return {"word": best, "confidence": conf} if conf >= 0.4 \
        else {"word": None, "confidence": 0.0}


def guess_from_sig(sig):
    """拿一个新画面（签名）联想最像的已学符号；把握不足则诚实说没把握。"""
    proto = taught_words()
    if not proto:
        return {"word": None, "confidence": 0.0, "reason": "还没学过任何字"}
    best, bd, bsim = None, None, -1.0
    for w, ps in proto.items():
        d = dist_sig(sig, ps)
        sim = 1.0 / (1.0 + d)
        if bsim is None or sim > bsim:
            best, bd, bsim = w, d, sim
    confidence = round(max(0.0, 1.0 - bd / CONF_D0), 3)
    real = real_matches(sig)
    return {"word": best, "distance": round(bd, 3),
            "confidence": confidence,
            "real": real,
            "reason": ("我觉得像『%s』" % best if confidence >= 0.4
                       else "画面太陌生了，我还没见过这样的符号")}


def guess(matrix):
    """她看一个新画面（16x16 矩阵），说出最像的字。"""
    sig = matrix_sig(matrix)
    g = guess_from_sig(sig)
    rec = {
        "schema_version": 1,
        "timestamp": time.time(),
        "kind": "guess",
        "word": g.get("word"),
        "confidence": g.get("confidence", 0.0),
        "reason": g.get("reason", ""),
    }
    _write_log(rec)
    if g.get("word") and g.get("confidence", 0) >= 0.4:
        make_point("see", "我认出了『%s』：画面长得像它（把握%s）。"
                   % (g["word"], g["confidence"]), source="teach")
    return g


def lesson_1():
    """第一课：把沉睡的字画像全部教一遍（多教一点字）。"""
    hanzi, objs = load_word_maps()
    taught_list = []
    # 优先教汉字字形（人类符号），再教物体图形（真实世界的物）
    for w, mats in list(hanzi.items()) + list(objs.items()):
        for m in mats[:1]:   # 每个符号用一张画像教
            r = teach(w, matrix=m, source="lesson")
            if "error" not in r:
                taught_list.append(w)
    return {"hanzi_taught": len([w for w in taught_list if w in hanzi]),
            "object_taught": len([w for w in taught_list if w in objs]),
            "words": taught_list}


def matrix_from_file(path):
    """任何图片/视频 → 16x16 灰度矩阵（ffmpeg，参数列表安全调用）。"""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
         "-vf", ("scale=16:16:force_original_aspect_ratio=decrease,"
                 "pad=16:16:(ow-iw)/2:(oh-ih)/2,format=gray"),
         "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, timeout=60)
    if out.returncode != 0 or len(out.stdout) < SIG_SIZE * SIG_SIZE:
        return None
    raw = out.stdout[:SIG_SIZE * SIG_SIZE]
    # 眼睛校准：灰度二值化（≥180 视为白，其余视为墨迹），
    # 避免视频压缩把细线条变成灰蒙蒙的糊状
    return [[(255 if raw[i * SIG_SIZE + j] >= 180 else 0)
             for j in range(SIG_SIZE)] for i in range(SIG_SIZE)]


def _selftest():
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="luoshen_teach_")
    import luoshen_brain
    import luoshen_memory
    old_log = TEACH_LOG
    old_chain = luoshen_brain.CHAIN_PATH
    globals()["TEACH_LOG"] = os.path.join(tmp, "teach_log.jsonl")
    luoshen_brain.CHAIN_PATH = os.path.join(tmp, "chain.log")
    mem_old_dir = luoshen_memory.DATA_DIR
    mem_old_points = luoshen_memory.MEMORY_POINTS
    luoshen_memory.DATA_DIR = tmp
    luoshen_memory.MEMORY_POINTS = os.path.join(tmp, "episodic.jsonl")
    with open(luoshen_brain.CHAIN_PATH, "w", encoding="utf-8") as f:
        f.write("")
    ok = True
    msgs = []
    try:
        # 1) 教『一』：一根黑横线在 16x16 白纸上
        one = [[255] * 16 for _ in range(16)]
        for j in range(6, 10):
            one[8][j] = 0
        r = teach("一", matrix=one, source="test")
        assert "error" not in r, r
        msgs.append("教『一』：画面↔字对照已写入学习记录")

        # 2) 拿同一画面问她 → 应认出『一』
        g = guess(one)
        assert g["word"] == "一" and g["confidence"] >= 0.4, "同画面必须认出：%s" % g
        msgs.append("来回对照：同一画面 → 认出『一』（把握%s）" % g["confidence"])

        # 3) 拿完全陌生的画面（全黑）→ 可选诚实分支：要么不乱认要么低把握
        black = [[0] * 16 for _ in range(16)]
        g2 = guess(black)
        assert g2["word"] is None or g2["confidence"] < 0.4, \
            "没见过的不许硬猜：%s" % g2
        msgs.append("陌生画面 → 诚实：%s" % g2["reason"])

        # 4) 多教一个『十』，两个画面不能混淆
        cross = [[255] * 16 for _ in range(16)]
        for i in range(16):
            cross[8][i] = 0
            cross[i][8] = 0
        teach("十", matrix=cross, source="test")
        g3 = guess(one)
        assert g3["word"] == "一", "一和十不能混淆：%s" % g3
        g4 = guess(cross)
        assert g4["word"] == "十", "十字应认出：%s" % g4
        msgs.append("对照区分：一 ↔ 十 不混淆")

        # 5) 第一课：休眠资产全教（汉字+物体）
        report = lesson_1()
        total = len(taught_words())
        assert total >= 60, "第一课至少 60 个符号：%s" % total
        msgs.append("第一课：教了汉字%d个+物形%d个，词表共%d个"
                    % (report["hanzi_taught"], report["object_taught"], total))

        # 6) 记忆纪律：教学与认出都沉了记忆点、上了链
        import luoshen_memory as M
        pts = M.read_memory_points()
        learned = [p for p in pts if p.get("kind") == "learn"]
        assert learned, "学字要沉记忆点"
        msgs.append("学字沉了 %d 块记忆点（◎ 学会）" % len(learned))
        chain_lines = [ln for ln in open(luoshen_brain.CHAIN_PATH, encoding="utf-8").read().splitlines() if ln.strip()]
        assert chain_lines, "教学记录必须上链"
        msgs.append("教学日志已上哈希链（%d 条）" % len(chain_lines))
    except AssertionError as e:
        ok = False
        msgs.append("断言失败：%s" % e)
    finally:
        globals()["TEACH_LOG"] = old_log
        luoshen_brain.CHAIN_PATH = old_chain
        luoshen_memory.DATA_DIR = mem_old_dir
        luoshen_memory.MEMORY_POINTS = mem_old_points
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"selftest": "PASS" if ok else "FAIL",
                      "checks": msgs}, ensure_ascii=False, indent=2))
    return ok


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(0 if _selftest() else 1)
    if "--lesson" in args:
        rep = lesson_1()
        print("第一课完成：教了汉字 %d 个 + 物形 %d 个，词表共 %d 个符号。" % (
            rep["hanzi_taught"], rep["object_taught"], len(taught_words())))
        print("她学过的符号：%s …" % "、".join(list(taught_words())[:24]))
        return
    if "--teach" in args:
        idx = args.index("--teach")
        word = args[idx + 1] if idx + 1 < len(args) else ""
        if not word:
            print("用法：--teach 字 [--source user_correct|lesson] [--video 字形画面] [--real 实物画面]")
            return
        source = "lesson"
        if "--source" in args:
            si = args.index("--source")
            source = args[si + 1] if si + 1 < len(args) else source
        matrix = None
        if "--video" in args:
            vi = args.index("--video")
            vpath = args[vi + 1] if vi + 1 < len(args) else ""
            matrix = matrix_from_file(vpath) if vpath else None
            if matrix is None:
                print("画面读取失败：%s" % vpath)
                return
        real_path = None
        if "--real" in args:
            ri = args.index("--real")
            real_path = args[ri + 1] if ri + 1 < len(args) else ""
            if not real_path or not os.path.exists(real_path):
                print("实物画面不存在：%s" % real_path)
                return
        r = teach(word, matrix=matrix, source=source, real_path=real_path)
        if "error" in r:
            print(r["error"])
        else:
            tag = "人对准过的画面" if source == "user_correct" else "字形画像"
            print("教完了：『%s』↔ %s 对照已记住。" % (word, tag))
            if real_path:
                print("实物对照：『%s』↔ %s 的真实画面也对上了（签名已上链）。" %
                      (word, os.path.basename(real_path)))
            else:
                print("注意：这次没有实物画面，只算认得字形。")
        return
    if "--guess" in args:
        idx = args.index("--guess")
        target = args[idx + 1] if idx + 1 < len(args) else ""
        if target.startswith("obj:"):
            _, name = target.split(":", 1)
            _, objs = load_word_maps()
            mats = objs.get(name)
            if not mats:
                print("物形库里没有 %s" % name)
                return
            g = guess(mats[0])
            print("她看了看【%s 的图形】→ %s" % (name, g["reason"]))
            return
        matrix = matrix_from_file(target) if target else None
        if matrix is None:
            print("画面读取失败（需要图片或视频路径，或 obj:名字）")
            return
        g = guess(matrix)
        print("她看了看 %s → %s" % (target, g["reason"]))
        return
    if "--words" in args:
        ws = taught_words()
        if not ws:
            print("（她还没学过字）")
            return
        print("词表共 %d 个符号：%s" % (len(ws), "、".join(sorted(ws))))
        return
    sys.stdout.write(
        "用法：--lesson 第一课 | --teach 字 | --guess <图|视频|obj:名> | --words | --selftest\n")


if __name__ == "__main__":
    main()