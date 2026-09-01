#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 零件数字视觉库 STEP176 —— part_image_fetch_and_matrix.py

功能：
    联网下载 5 类电脑硬件零件公开图片（CPU / 内存条 / 硬盘 / 主板 / 芯片），
    纯 Python（zlib + struct，无 PIL/cv2）解码 PNG，转 8 位灰度 BMP 保存到
    perception_input/parts/，复用 bmp_to_matrix.py 的解析逻辑缩放为 16×16
    灰度矩阵，写入 perception_input/part_matrix.jsonl（5 条，含 source_url），
    并按 v2 公式追加哈希链记录。

约束遵循：
    - 相对路径（相对工作目录运行）
    - 不修改已有脚本；仅创建本脚本、part_matrix.jsonl、5 个 BMP
    - 禁止调用外部大模型
    - 图片来源 source_url 全程可追溯
"""
import hashlib
import json
import os
import struct
import time
import zlib

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request

import bmp_to_matrix  # 复用既有 BMP 解析逻辑（parse_bmp_header/read_pixels/scale_matrix）

UA = "Mozilla/5.0 (compatible; LuoshenSTEP176/1.0; educational)"
PART_DIR = "perception_input/parts"
PNG_DIR = "temp/png"
RESULT_FILE = "perception_input/part_matrix.jsonl"
TARGET = 16
PRE_SCALE = 128  # 先块平均缩到 128×128 再写 BMP，再由 bmp_to_matrix 最近邻缩到 16×16

# 5 类零件：part_name -> (下载 URL, 目标 BMP 文件名)
SOURCES = {
    "cpu": {
        "url": "https://pngimg.com/uploads/cpu/cpu_PNG61.png",
        "bmp": "cpu.bmp",
    },
    "memory": {
        "url": "https://www.pngall.com/wp-content/uploads/5/RAM-PNG.png",
        "bmp": "memory.bmp",
    },
    "disk": {
        "url": "https://pngimg.com/uploads/hard_disc/Hard disc PNG, hard drive PNG images free download, HDD PNG_PNG12075.png",
        "bmp": "disk.bmp",
    },
    "motherboard": {
        "url": "https://pngimg.com/uploads/motherboard/motherboard_PNG41.png",
        "bmp": "motherboard.bmp",
    },
    "chip": {
        "url": "https://pngimg.com/uploads/circuit/circuit_PNG34.png",
        "bmp": "chip.bmp",
    },
}


# --------------------------------------------------------------------------
# PNG 解码（纯 Python，支持 color_type 0/2/3/4/6，bit_depth 8（调色板允许 1/2/4/8），
# 非隔行；透明像素按白底(255)处理）
# --------------------------------------------------------------------------
def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data):
    """解码 PNG 返回 (rows, cols, gray_rows)。gray_rows: list[list[int]] 0~255。
    透明(alpha<128)像素视为白(255)。"""
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
             compression, filt, interlace) = struct.unpack(">IIBBBBB", chunk)
            assert compression == 0 and filt == 0 and interlace == 0, "不支持的压缩/过滤/隔行"
        elif typ == b"PLTE":
            plte = chunk
        elif typ == b"IDAT":
            idat += chunk
        pos += 12 + ln

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    if color_type != 3:
        assert bit_depth == 8, "仅支持 bit_depth=8（非调色板）"
    raw = zlib.decompress(idat)

    bpp = channels if bit_depth == 8 else 1          # 每像素字节数（过滤时用）
    stride = (width * channels * bit_depth + 7) // 8  # 每行像素数据字节数
    rows = []                                         # 每行 filter 后字节
    prev = [0] * stride
    off = 0
    for _ in range(height):
        ft = raw[off]; off += 1
        line = list(raw[off:off + stride]); off += stride
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

    # 行字节 -> 像素灰度
    gray_rows = []
    n = width * channels
    for y in range(height):
        row = rows[y]
        g = []
        for x in range(width):
            if color_type == 0:                        # 灰度
                gray = row[x]
            elif color_type == 2:                      # RGB
                r, gg, b = row[x * 3], row[x * 3 + 1], row[x * 3 + 2]
                gray = (r + gg + b) // 3
            elif color_type == 3:                      # 调色板
                if bit_depth == 8:
                    idx = row[x]
                else:
                    bits = bit_depth
                    pxs = 8 // bits
                    byte = row[x // pxs]
                    shift = 8 - bits * (x % pxs + 1)
                    idx = (byte >> shift) & ((1 << bits) - 1)
                r, g_, b = plte[idx * 3], plte[idx * 3 + 1], plte[idx * 3 + 2]
                gray = (r + g_ + b) // 3
            elif color_type == 4:                      # 灰度+alpha
                gray, a = row[x * 2], row[x * 2 + 1]
                if a < 128:
                    gray = 255
            else:                                      # RGBA
                r, gg, b, a = (row[x * 4], row[x * 4 + 1],
                               row[x * 4 + 2], row[x * 4 + 3])
                gray = (r + gg + b) // 3 if a >= 128 else 255
            g.append(gray)
        gray_rows.append(g)
    return width, height, gray_rows


def scale_avg(gray_rows, w, h, target):
    """块平均缩放到 target×target"""
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


def write_gray_bmp8(path, cols, rows_, pixels):
    """写 8 位灰度 BMP（256 灰阶调色板，bottom-up，4 字节行对齐）"""
    row_size = (cols + 3) // 4 * 4
    pad = b"\x00" * (row_size - cols)
    offset = 14 + 40 + 1024
    file_size = offset + row_size * rows_
    header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, offset)
    info = struct.pack("<IiiHHIIiiII", 40, cols, rows_, 1, 8, 0,
                       row_size * rows_, 2835, 2835, 0, 0)
    palette = bytes(v for i in range(256) for v in (i, i, i, 0))
    body = b""
    for r in range(rows_ - 1, -1, -1):   # bottom-up
        body += bytes(pixels[r]) + pad
    with open(path, "wb") as f:
        f.write(header + info + palette + body)


# --------------------------------------------------------------------------
# 下载
# --------------------------------------------------------------------------
def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    if HAS_REQUESTS:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        content = r.content
    else:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        content = urllib.request.urlopen(req, timeout=60).read()
    with open(path, "wb") as f:
        f.write(content)
    assert open(path, "rb").read(8) == b"\x89PNG\r\n\x1a\n", "下载内容非 PNG: %s" % url


# --------------------------------------------------------------------------
# 单类处理
# --------------------------------------------------------------------------
def process(part):
    src = SOURCES[part]
    png_path = os.path.join(PNG_DIR, part + ".png")
    bmp_path = os.path.join(PART_DIR, src["bmp"])

    download(src["url"], png_path)
    with open(png_path, "rb") as f:
        w, h, gray = decode_png(f.read())
    g128 = scale_avg(gray, w, h, PRE_SCALE)
    write_gray_bmp8(bmp_path, PRE_SCALE, PRE_SCALE, g128)

    # 复用 bmp_to_matrix 的解析逻辑
    with open(bmp_path, "rb") as f:
        data = f.read()
    offset, width, height, bit_count = bmp_to_matrix.parse_bmp_header(data)
    raw = bmp_to_matrix.read_pixels(data, offset, width, abs(height), bit_count)
    if height > 0:                       # bottom-up 翻转
        raw = raw[::-1]
    matrix = bmp_to_matrix.scale_matrix(raw, TARGET)

    return matrix, src["url"], src["bmp"]


def print_preview(matrix, name):
    print("=== 矩阵预览：%s (%dx%d) ===" % (name, len(matrix), len(matrix[0])))
    for row in matrix:
        print("".join("#" if v >= 128 else "." for v in row))


def main():
    print("STEP176 part_image_fetch_and_matrix start @ %s" %
          time.strftime("%Y-%m-%d %H:%M:%S"))
    os.makedirs(PART_DIR, exist_ok=True)
    os.makedirs(PNG_DIR, exist_ok=True)

    records = []
    for part in ["cpu", "memory", "disk", "motherboard", "chip"]:
        print(">>> 处理零件: %s" % part)
        matrix, url, bmpname = process(part)
        records.append({
            "schema_version": 2,
            "timestamp": time.time(),
            "part_name": part,
            "file_name": bmpname,
            "source_url": url,
            "width": len(matrix[0]),
            "height": len(matrix),
            "matrix": matrix,
            "source": "part_image_fetch_and_matrix",
        })
        vals = [v for row in matrix for v in row]
        print("  file=%s range=[%d,%d] avg=%.1f" %
              (bmpname, min(vals), max(vals), sum(vals) / len(vals)))
        print_preview(matrix, part)

    # 校验：互异 且 非全0/全255
    sigs = [json.dumps(r["matrix"], sort_keys=True) for r in records]
    assert len(set(sigs)) == 5, "5 个矩阵存在重复！"
    for r in records:
        vals = {v for row in r["matrix"] for v in row}
        assert vals != {0} and vals != {255}, "矩阵全0或全255: %s" % r["part_name"]
    print("=== 校验通过：5 个矩阵互异且非全0/全255 ===")

    # 写入 part_matrix.jsonl（恰好 5 条，覆盖本交付文件）
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 哈希链追加
    print("=== 哈希链追加 ===")
    bmp_to_matrix.append_hash_chain(RESULT_FILE, bmp_to_matrix.current_chain_tail())

    print("STEP176 done @ %s" % time.strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
