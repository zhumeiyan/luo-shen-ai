#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP198 - image_batch_200.py
=======================================
洛神 200 图矩阵库构建模块：
1) 依据候选 id 清单（temp/cand_ids_*.json + 补采 key/small_ball），
   全局去重（跨词撞 id 移除）后每词取前 5 个 id；
2) 从 openclipart 渲染接口 /image/400px/<id> 下载 PNG 至 temp/pack_src_200/；
3) 打包为 perception_input/real_object_pack_200.zip（仅成功图，命名 <word>_NN.png）；
4) 纯 Python（zlib+struct，无 PIL/cv2）解码，缩放 16×16 灰度矩阵，
   写 perception_input/real_object_matrix_200.jsonl（每条含 object/adjectives/source_url/matrix）；
5) 按 v2 公式追加 hash_chain_v2.log（仅 jsonl 上链，zip 不上链）。

约束: 禁绝对路径 / 禁外部大模型 / 仅纯 Python 解 PNG / 同一物体图<=10 张 / 禁重复复制
"""
import hashlib
import json
import os
import re
import struct
import time
import urllib.request
import zipfile
import zlib

SIZE = 16
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

SRC_DIR = "temp/pack_src_200"
PACK_FILE = "perception_input/real_object_pack_200.zip"
RESULT_FILE = "perception_input/real_object_matrix_200.jsonl"
CHAIN_FILE = "hash_chain_v2.log"
PER_WORD = 5   # 每词取前 5 个 id

# 词 -> 形容词（沿用 STEP194 语感，供后续语义层使用）
ADJ = {
    "stone":["重","硬"], "leaf":["轻","薄"], "feather":["轻","软"], "cotton":["轻","软"],
    "cloud":["轻","柔"], "water":["凉","动"], "fire":["热","亮"], "flower":["香","美"],
    "tree":["高","大"], "snow":["冷","白"],
    "wood":["硬"], "iron":["重","硬"], "glass":["脆","透"], "paper":["轻","薄"],
    "cloth":["软"], "cup":["圆"], "stick":["长","细"], "ball":["圆"],
    "brick":["硬","方"], "spoon":["小","金属"], "key":["小","金属"], "small_ball":["小","圆"],
    "cat":["小","活"], "dog":["忠"], "bird":["飞","轻"], "fish":["游","滑"],
    "butterfly":["轻","美"], "bee":["小","飞"], "horse":["大","快"], "duck":["游"],
    "frog":["跳"], "mouse":["小"],
    "circle":["圆"], "square":["方"], "triangle":["尖"], "star":["亮"],
    "heart":["美"], "cross":["直"], "arrow":["尖"], "moon":["弯"],
    "diamond":["尖"], "spiral":["曲"],
}

# 候选 id 池：合并两类探测结果 + key/small_ball 补采
def load_candidates():
    cand = {}
    for p in ["temp/cand_ids_1.json", "temp/cand_ids_2.json"]:
        cand.update(json.load(open(p, encoding="utf-8")))
    cand.setdefault("manmade|key", []).extend(
        ['347691','301341','283518','261937','221657','213432','212622','212621','212620','212619'])
    cand.setdefault("manmade|small_ball", []).extend(
        ['354719','354718','351882','350838','344723','340688','327361','323144','306239','297341'])
    return cand

def build_manifest():
    cand = load_candidates()
    # 全局撞 id 去重：id 出现在多个词 -> 从所有词移除（保守）
    word_of = {}
    for word, ids in cand.items():
        for i in ids:
            word_of.setdefault(i, []).append(word)
    banned = {i for i, ws in word_of.items() if len(ws) > 1}
    manifest = {}
    for word, ids in cand.items():
        cat, w = word.split("|", 1)
        # 路径安全：词键仅保留字母/数字/下划线，防止目录穿越
        w = re.sub(r"[^A-Za-z0-9_]", "", w) or "unknown"
        keep = []
        for i in ids:
            if i in banned:
                continue
            if i not in keep:
                keep.append(i)
        manifest[w] = keep[:PER_WORD]
    return manifest

# ---------- 纯 Python PNG 解码（与 STEP194 相同实现） ----------
def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c

def decode_png(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "非法 PNG 签名"
    pos = 8
    idat = b""
    width = height = bit_depth = color_type = 0
    plte = None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            (width, height, bit_depth, color_type,
             _c, _f, interlace) = struct.unpack(">IIBBBBB", chunk)
            assert interlace == 0, "不支持的隔行"
        elif typ == b"PLTE":
            plte = chunk
        elif typ == b"IDAT":
            idat += chunk
        pos += 12 + ln
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    if color_type != 3:
        assert bit_depth == 8, "仅支持非调色板 bit_depth=8"
    raw = zlib.decompress(idat)
    bpp = channels if bit_depth == 8 else 1
    stride = (width * channels * bit_depth + 7) // 8
    rows = []
    prev = [0] * stride
    off = 0
    for _ in range(height):
        ft = raw[off]; off += 1
        line = list(raw[off:off + stride]); off += stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                ul = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], ul)) & 255
        prev = line[:]
        rows.append(line)
    gray_rows = []
    for y in range(height):
        row = rows[y]
        g = []
        for x in range(width):
            if color_type == 0:
                gv = row[x]
            elif color_type == 2:
                r, gg, b = row[x * 3], row[x * 3 + 1], row[x * 3 + 2]
                gv = (r + gg + b) // 3
            elif color_type == 3:
                if bit_depth == 8:
                    idx = row[x]
                else:
                    bits = bit_depth
                    pxs = 8 // bits
                    byte = row[x // pxs]
                    shift = 8 - bits * (x % pxs + 1)
                    idx = (byte >> shift) & ((1 << bits) - 1)
                r, gg, b = plte[idx * 3], plte[idx * 3 + 1], plte[idx * 3 + 2]
                gv = (r + gg + b) // 3
            elif color_type == 4:
                gv, a = row[x * 2], row[x * 2 + 1]
                gv = 255 if a < 128 else gv
            else:
                r, gg, b, a = (row[x * 4], row[x * 4 + 1], row[x * 4 + 2], row[x * 4 + 3])
                gv = (r + gg + b) // 3 if a >= 128 else 255
            g.append(gv)
        gray_rows.append(g)
    return width, height, gray_rows

def scale_avg(gray_rows, w, h, target):
    out = []
    for i in range(target):
        r0, r1 = i * h // target, (i + 1) * h // target
        r1 = max(r1, r0 + 1)
        row = []
        for j in range(target):
            c0, c1 = j * w // target, (j + 1) * w // target
            c1 = max(c1, c0 + 1)
            s = 0
            for rr in range(r0, r1):
                for cc in range(c0, c1):
                    s += gray_rows[rr][cc]
            row.append(s // ((r1 - r0) * (c1 - c0)))
        out.append(row)
    return out

# ---------- 下载 ----------
def download(word, cid, idx):
    os.makedirs(SRC_DIR, exist_ok=True)
    path = os.path.join(SRC_DIR, "%s_%02d.png" % (word, idx))
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path, True
    url = "https://openclipart.org/image/400px/%s" % cid
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 100:
            with open(path, "wb") as f:
                f.write(data)
            return path, True
        return None, False
    except Exception:
        return None, False

# ---------- 哈希链（与 STEP194 一致） ----------
def md5_of_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def read_chain_tail(chain_file):
    tail = None
    with open(chain_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        raise RuntimeError("hash_chain_v2.log 无记录")
    return tail["record_hash"]

def append_hash_chain(chain_file, target_file, prev_hash):
    ts = time.time()
    file_hash = md5_of_file(target_file)
    record_hash = hashlib.md5(
        "{}{}{}".format(file_hash, prev_hash, str(ts)).encode("utf-8")).hexdigest()
    entry = {"schema_version": 2, "timestamp": ts, "file": target_file,
             "file_hash": file_hash, "prev_hash": prev_hash, "record_hash": record_hash}
    with open(chain_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

# ---------- 主流程 ----------
def main():
    manifest = build_manifest()
    total = sum(len(v) for v in manifest.values())
    print("=== 候选清单: %d 词, %d 个 id ===" % (len(manifest), total), flush=True)

    # 1) 下载
    ok_map = {}
    idx_counter = {}
    n_ok = 0
    for word, ids in sorted(manifest.items()):
        n = 0
        for cid in ids:
            path, ok = download(word, cid, n + 1)
            if ok:
                n += 1
                n_ok += 1
                ok_map[(word, n)] = path
                print("DL %-12s %02d id=%s OK" % (word, n, cid), flush=True)
            else:
                print("DL %-12s id=%s FAIL" % (word, cid), flush=True)
            time.sleep(0.08)
        idx_counter[word] = n
    print("=== 下载成功 %d 张 ===" % n_ok, flush=True)

    # 2) 打包 zip
    with zipfile.ZipFile(PACK_FILE, "w", zipfile.ZIP_DEFLATED) as z:
        for (word, n), path in sorted(ok_map.items()):
            z.write(path, "%s_%02d.png" % (word, n))
    print("=== 打包 %s 完成 ===" % PACK_FILE, flush=True)

    # 3) 解码 -> 矩阵 jsonl
    ts = time.time()
    records = []
    for (word, n), path in sorted(ok_map.items()):
        with open(path, "rb") as f:
            data = f.read()
        try:
            w, h, gray = decode_png(data)
            matrix = scale_avg(gray, w, h, SIZE)
        except Exception as e:
            print("%s_%02d DECODE FAIL(%s)" % (word, n, type(e).__name__), flush=True)
            continue
        url = "https://openclipart.org/image/400px/%s" % manifest[word][n - 1]
        records.append({
            "schema_version": 2, "timestamp": ts, "object": word,
            "adjectives": ADJ.get(word, []), "source_url": url,
            "width": SIZE, "height": SIZE, "matrix": matrix,
            "source": "image_batch_200",
        })
    print("=== 解码成功 %d 条 ===" % len(records), flush=True)
    assert len(records) >= 150, "有效矩阵不足 150 条"

    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("=== 写入 %s : %d 条 ===" % (RESULT_FILE, len(records)), flush=True)

    # 4) 上链（仅 jsonl）
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, RESULT_FILE, prev_hash)
    print("--- hash_chain appended ---", flush=True)
    print(json.dumps(entry, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
