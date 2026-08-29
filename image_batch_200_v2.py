#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP204 - image_batch_200_v2.py
=================================================
获取约 200 张公开小图（openclipart），转 16x16 灰度矩阵，
写入 real_object_matrix_200_v2.jsonl，扩充洛神真实视觉数据。
本批重点补充：材质纹理、食物、服饰、自然地貌、生活器物、建筑、
交通工具、植物局部等新类别，避开此前大量入库的物体。

来源说明：openclipart 服务端搜索接口已失效，改用其分页列表页
（/search?p=N，每页 32 张，页面内嵌图片标题 alt），
按标题过滤禁止物体后，经 /image/64px/{id} 直链下载小尺寸 PNG。

流程：
1) 翻页采集 (id, title) 候选；
2) 标题过滤：排除旧批次已大量入库的物体类别；
3) 纯 Python 解析 PNG（zlib + struct，支持灰度/RGB/调色板/带透明），
   转 16x16 灰度矩阵（0~255）；
4) 原始 PNG 字节打包到 real_object_pack_200_v2.zip；
5) 成功矩阵写入 real_object_matrix_200_v2.jsonl；
6) 只为 jsonl 追加一条哈希链记录。
"""
import hashlib
import json
import re
import struct
import time
import zipfile
import zlib

import requests

SIZE = 16
TARGET = 200
MAX_PER_WORD = 8          # 同一具体物体最多 8 张
PAGES_TO_SCAN = 220       # 翻页数（每页 32 张候选）
TIMEOUT = 20

# 旧批次已大量入库的物体（标题命中则排除）
BANNED = [
    "stone", "rock", "feather", "ball", "cat", "dog", "bird", "fish", "cup",
    "wood", "paper", "cloud", "fire", "water", "leaf", "flower", "butterfly",
    "moon", "star", "heart", "arrow",
]
BANNED_RE = re.compile(r"\b(?:%s)\b" % "|".join(BANNED), re.IGNORECASE)

# 本批优先新类别关键词（仅用于排序，不强制）
PREFERRED = re.compile(
    r"\b(?:bark|leather|metal|ceramic|bread|apple|banana|grape|egg|cheese|"
    r"rice|noodle|shoe|hat|scarf|glove|sock|belt|backpack|mountain|desert|"
    r"river|coast|ice|volcano|canyon|scissors|lock|socket|bulb|keychain|"
    r"brush|comb|button|window|door|roof|stair|pillar|fence|bridge|car|"
    r"bicycle|train|boat|airplane|motorcycle|root|branch|petal|pollen|"
    r"cactus|mushroom|texture|pattern|tile|brick|bamboo|rubber|chain)\b",
    re.IGNORECASE)

ZIP_FILE = "perception_input/real_object_pack_200_v2.zip"
OUTPUT_FILE = "perception_input/real_object_matrix_200_v2.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


# ---------------- PNG 纯 Python 解码 ----------------

def png_to_gray(raw):
    """解析 PNG 字节，返回灰度像素列表 [[0..255]*W]*H 或 None"""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos = 8
    width = height = bitdepth = colortype = None
    palette = None
    idat = []
    interlaced = 0
    while pos < len(raw):
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        ctype = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bitdepth, colortype, _, _, interlaced = struct.unpack(
                ">IIBBBBB", data)
        elif ctype == b"PLTE":
            palette = list(data)
        elif ctype == b"IDAT":
            idat.append(data)
        elif ctype == b"IEND":
            break
    if width is None or height is None:
        return None
    if interlaced != 0:
        return None
    try:
        scan = zlib.decompress(b"".join(idat))
    except zlib.error:
        return None

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colortype]
    bpp = channels * bitdepth
    row_len = (width * bpp + 7) // 8
    bpp_byte = max(1, bpp // 8)

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    prev = bytearray(row_len)
    rows = []
    pos = 0
    for _ in range(height):
        if pos >= len(scan):
            return None
        ft = scan[pos]
        pos += 1
        row = bytearray(scan[pos:pos + row_len])
        pos += row_len
        if len(row) != row_len:
            return None
        for i in range(row_len):
            left = row[i - bpp_byte] if i >= bpp_byte else 0
            up = prev[i]
            upleft = prev[i - bpp_byte] if i >= bpp_byte else 0
            if ft == 1:
                row[i] = (row[i] + left) & 0xFF
            elif ft == 2:
                row[i] = (row[i] + up) & 0xFF
            elif ft == 3:
                row[i] = (row[i] + (left + up) // 2) & 0xFF
            elif ft == 4:
                row[i] = (row[i] + paeth(left, up, upleft)) & 0xFF
        prev = row
        rows.append(row)

    gray_rows = []
    for r in range(height):
        row = rows[r]
        pix = []
        bits_consumed = 0
        i = 0
        while i < width:
            vals = []
            for _c in range(channels):
                if bitdepth >= 8:
                    if bitdepth == 16:
                        v = row[i * 2]
                        i += 1
                    else:
                        v = row[i]
                    i += 1
                else:
                    bitpos = 8 - bitdepth
                    byte_idx = bits_consumed // 8
                    byte = row[byte_idx] if byte_idx < len(row) else 0
                    shift = bitpos - (bits_consumed % 8)
                    v = (byte >> shift) & ((1 << bitdepth) - 1)
                    bits_consumed += bitdepth
                vals.append(v)
            pix.append(vals)
        gray = []
        for vals in pix:
            if colortype == 3:
                idx = vals[0]
                if palette and 3 * idx + 2 < len(palette):
                    rr, gg, bb = palette[3 * idx], palette[3 * idx + 1], palette[3 * idx + 2]
                    gv = int(0.299 * rr + 0.587 * gg + 0.114 * bb)
                else:
                    gv = 255
            elif colortype == 0:
                gv = vals[0]
            elif colortype == 2:
                rr, gg, bb = vals[:3]
                gv = int(0.299 * rr + 0.587 * gg + 0.114 * bb)
            elif colortype == 4:
                gv = vals[0]
                if vals[1] < 128:
                    gv = 255
            elif colortype == 6:
                rr, gg, bb, aa = vals
                if aa < 128:
                    gv = 255
                else:
                    gv = int(0.299 * rr + 0.587 * gg + 0.114 * bb)
            else:
                gv = 255
            gray.append(max(0, min(255, gv)))
        gray_rows.append(gray)
    return gray_rows


def scale_avg(gray_rows, out_size):
    """将灰度图按区域平均缩放为 out_size x out_size 的矩阵"""
    h = len(gray_rows)
    w = len(gray_rows[0])
    out = [[0] * out_size for _ in range(out_size)]
    for oy in range(out_size):
        y0 = oy * h // out_size
        y1 = (oy + 1) * h // out_size
        if y1 <= y0:
            y1 = y0 + 1
        for ox in range(out_size):
            x0 = ox * w // out_size
            x1 = (ox + 1) * w // out_size
            if x1 <= x0:
                x1 = x0 + 1
            total = 0
            cnt = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    total += gray_rows[y][x]
                    cnt += 1
            out[oy][ox] = int(round(total / cnt))
    return out


# ---------------- 采集与下载 ----------------

def collect_candidates(pages):
    """翻页采集 (id, title)，返回列表，保持先后顺序"""
    cands = []
    seen = set()
    for p in range(1, pages + 1):
        url = "https://openclipart.org/search?p={}".format(p)
        try:
            resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
            resp.raise_for_status()
            html = resp.text
            for m in re.finditer(
                    r'<a href="/detail/(\d+)/([^"]*)">\s*<img[^>]*alt="([^"]*)"',
                    html):
                cid, slug, title = m.group(1), m.group(2), m.group(3)
                if cid in seen:
                    continue
                seen.add(cid)
                cands.append((cid, title.strip() or slug))
        except Exception:
            pass
        time.sleep(0.2)
    return cands


def normalize_key(title):
    """标题规范化，作为'同一具体物体'的判键"""
    t = title.lower()
    t = re.sub(r"\b(a|an|the|of|with|and|for|on|in|red|blue|green|yellow|"
               r"black|white|brown|gray|grey|pink|orange|purple|gold|large|"
               r"small|big|old|new|funny|nice|cute|cool|beautiful)\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    t = re.sub(r"\s+(s|es)\b", "", t)
    return t


def download_png(cid):
    url = "https://openclipart.org/image/64px/{}".format(cid)
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
        if resp.content[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return resp.content
    except Exception:
        return None


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return s[:40] or "img"


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


def main():
    cands = collect_candidates(PAGES_TO_SCAN)

    # 过滤禁止物体；统计同物体数量
    chosen = []
    counts = {}
    for cid, title in cands:
        if BANNED_RE.search(title):
            continue
        key = normalize_key(title)
        if not key:
            continue
        if counts.get(key, 0) >= MAX_PER_WORD:
            continue
        counts[key] = counts.get(key, 0) + 1
        chosen.append((cid, title))
        if len(chosen) >= TARGET + 60:   # 多留余量应对下载失败
            break

    records = []
    ts = time.time()
    attempted = 0
    with zipfile.ZipFile(ZIP_FILE, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid, title in chosen:
            if len(records) >= TARGET:
                break
            raw = download_png(cid)
            attempted += 1
            if raw is None:
                continue
            gray = png_to_gray(raw)
            if gray is None:
                continue
            matrix = scale_avg(gray, SIZE)
            fname = "{}_{}.png".format(slugify(title), cid)
            zf.writestr(fname, raw)
            records.append({
                "schema_version": 2, "timestamp": ts, "file": fname,
                "width": SIZE, "height": SIZE, "matrix": matrix,
                "source": "image_batch_200_v2",
            })
            time.sleep(0.1)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("success=%d fail=%d total=%d" % (
        len(records), attempted - len(records), len(records)))

    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
