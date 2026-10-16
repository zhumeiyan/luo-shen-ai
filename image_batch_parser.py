#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP194 - image_batch_parser.py
==========================================
洛神批量图片解析模块：
从一个 zip 打包盒（perception_input/real_object_pack.zip）中批量读取 PNG，
使用纯 Python（zipfile + zlib + struct，无 PIL/cv2）解码每张 PNG，
缩放为 16×16 灰度矩阵（0 黑 ~ 255 白），为每个物体生成一条记录，
写入 perception_input/real_object_matrix.jsonl，并按 v2 公式追加哈希链。

仅允许:
  - 创建 image_batch_parser.py（本文件）
  - 创建 perception_input/real_object_pack.zip（打包盒，由本任务准备）
  - 创建 perception_input/real_object_matrix.jsonl（输出）
  - 创建 perception_input/real_object_images/（如需要，本模块不落盘图片）
  - 追加 hash_chain_v2.log（仅一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型

扩展说明:
  1) 支持更多图片格式: 在 decode_image() 中按文件扩展名分发（如 JPG 可接入纯
     Python 解码器），matrix 归一逻辑不变；
  2) 调整矩阵尺寸: 修改 SIZE 常量即可（缩放使用块平均，自动适配任意目标尺寸）；
  3) 扩展物体与形容词: 在 OBJECT_ADJECTIVES / SOURCE_URLS 中新增键值对即可。
"""

import hashlib
import json
import os
import struct
import time
import zipfile
import zlib

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
PACK_FILE = "perception_input/real_object_pack.zip"
RESULT_FILE = "perception_input/real_object_matrix.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

SIZE = 16
META_FIELDS = {"timestamp", "schema_version", "source"}

# 物体名(文件名去扩展名) -> 形容词
OBJECT_ADJECTIVES = {
    "stone":       ["重", "硬"],
    "iron_block":  ["重", "硬"],
    "wood":        ["重", "硬"],
    "feather":     ["轻", "软"],
    "paper":       ["轻"],
    "sponge":      ["轻", "软"],
    "cotton":      ["轻", "软"],
    "glass":       ["硬"],
    "big_ball":    ["大"],
    "small_ball":  ["小"],
    "elephant":    ["大"],
    "mouse":       ["小"],
    "long_stick":  ["长"],
    "short_stick": ["短"],
    "wide_board":  ["宽"],
    "narrow_strip":["窄"],
    "tall_tower":  ["高"],
    "low_stool":   ["低"],
    "full_cup":    ["满"],
    "empty_cup":   ["空"],
}

# 每个物体实际下载的图片来源 URL（openclipart 400px PNG 渲染地址，可追溯）
SOURCE_URLS = {
    "stone":        "https://openclipart.org/image/400px/264736",
    "iron_block":   "https://openclipart.org/image/400px/320589",
    "wood":         "https://openclipart.org/image/400px/345881",
    "feather":      "https://openclipart.org/image/400px/289939",
    "paper":        "https://openclipart.org/image/400px/349771",
    "sponge":       "https://openclipart.org/image/400px/355409",
    "cotton":       "https://openclipart.org/image/400px/178215",
    "glass":        "https://openclipart.org/image/400px/13842",
    "big_ball":     "https://openclipart.org/image/400px/205569",
    "small_ball":   "https://openclipart.org/image/400px/332530",
    "elephant":     "https://openclipart.org/image/400px/355447",
    "mouse":        "https://openclipart.org/image/400px/319521",
    "long_stick":   "https://openclipart.org/image/400px/254273",
    "short_stick":  "https://openclipart.org/image/400px/315479",
    "wide_board":   "https://openclipart.org/image/400px/345899",
    "narrow_strip": "https://openclipart.org/image/400px/336200",
    "tall_tower":   "https://openclipart.org/image/400px/345985",
    "low_stool":    "https://openclipart.org/image/400px/192578",
    "full_cup":     "https://openclipart.org/image/400px/331780",
    "empty_cup":    "https://openclipart.org/image/400px/263941",
}


# ----------------------------------------------------------------------
# PNG 解码（纯 Python，zlib+struct）
# 支持 color_type 0/2/3/4/6，非调色板要求 bit_depth=8，调色板允许 1/2/4/8，
# 非隔行；透明像素按白底(255)处理。
# ----------------------------------------------------------------------
def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data):
    """解码 PNG 返回 (width, height, gray_rows)。gray_rows: list[list[int]] 0~255。"""
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
        ft = raw[off]
        off += 1
        line = list(raw[off:off + stride])
        off += stride
        if ft == 1:                                   # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:                                 # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:                                 # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:                                 # Paeth
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
            if color_type == 0:                       # 灰度
                gv = row[x]
            elif color_type == 2:                     # RGB
                r, gg, b = row[x * 3], row[x * 3 + 1], row[x * 3 + 2]
                gv = (r + gg + b) // 3
            elif color_type == 3:                     # 调色板
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
            elif color_type == 4:                     # 灰度+alpha
                gv, a = row[x * 2], row[x * 2 + 1]
                gv = 255 if a < 128 else gv
            else:                                     # RGBA
                r, gg, b, a = (row[x * 4], row[x * 4 + 1],
                               row[x * 4 + 2], row[x * 4 + 3])
                gv = (r + gg + b) // 3 if a >= 128 else 255
            g.append(gv)
        gray_rows.append(g)
    return width, height, gray_rows


def decode_image(name, data):
    """按扩展名分发解码；当前仅支持 .png。返回 (w, h, gray_rows)。"""
    if name.lower().endswith(".png"):
        return decode_png(data)
    raise ValueError("不支持的图片格式: %s" % name)


def scale_avg(gray_rows, w, h, target):
    """块平均缩放到 target×target（0~255 整数）"""
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


# ----------------------------------------------------------------------
# 哈希链
# ----------------------------------------------------------------------
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
        "{}{}{}".format(file_hash, prev_hash, str(ts)).encode("utf-8")
    ).hexdigest()
    entry = {
        "schema_version": 2,
        "timestamp": ts,
        "file": target_file,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(chain_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main():
    ts = time.time()
    records = []
    with zipfile.ZipFile(PACK_FILE, "r") as z:
        entries = sorted(n for n in z.namelist() if n.lower().endswith(".png"))
        print("=== 打包盒图片数量: %d ===" % len(entries))
        for name in entries:
            base = os.path.splitext(os.path.basename(name))[0]
            data = z.read(name)
            ok = False
            w = h = 0
            matrix = None
            try:
                w, h, gray = decode_image(name, data)
                matrix = scale_avg(gray, w, h, SIZE)
                ok = True
            except Exception as e:
                print("%-14s %-16s FAIL(%s)" % (base, name, type(e).__name__))
                continue
            adj = OBJECT_ADJECTIVES.get(base, [])
            url = SOURCE_URLS.get(base, "pack")
            records.append({
                "schema_version": 2,
                "timestamp": ts,
                "object": base,
                "adjectives": adj,
                "source_url": url,
                "width": SIZE,
                "height": SIZE,
                "matrix": matrix,
                "source": "image_batch_parser",
            })
            vals = [v for row in matrix for v in row]
            print("%-14s %-16s %dx%d -> %dx%d SUCCESS (range=[%d,%d] avg=%.1f)" %
                  (base, name, w, h, len(matrix), len(matrix[0]),
                   min(vals), max(vals), sum(vals) / len(vals)))

    assert len(records) >= 20, "有效物体不足 20 个"

    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("=== 写入 %s : %d 条 ===" % (RESULT_FILE, len(records)))

    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, RESULT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
