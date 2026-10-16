#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 简易 BMP 图像解析器 bmp_to_matrix.py

功能：
    不依赖 PIL / cv2 / ffmpeg 等外部图像库，纯 Python + struct 解析
    24 位（bit_count=24）与 8 位灰度（bit_count=8）BMP 图像文件头，
    读取像素数据并缩放到 16×16（或 32×32）灰度数值矩阵，写入
    perception_input/bmp_matrix_result.jsonl。

矩阵约定：
    - 灰度 gray = (R+G+B)//3（24 位图）或直接取像素值（8 位图）
    - 元素为 0~255 整数，0=黑，255=白
    - 无输入 BMP 时生成测试记录 test_black_white.bmp（左黑右白 16×16）

BMP 头解析说明（供扩展参考）：
    - 文件头(14B)：0-1 bfType='BM'，2-5 文件大小，10-13 bfOffBits(像素偏移)
    - 信息头(40B，BITMAPINFOHEADER)：18-21 biWidth，22-25 biHeight(负=top-down)，
      28-29 biBitCount，30-33 biCompression(0=BI_RGB)
    - 24 位：每像素 BGR 3 字节，行按 4 字节对齐
    - 8 位：每像素 1 字节（标准灰度 BMP 调色板为灰阶，取索引即灰度），行 4 字节对齐
    - 默认 bottom-up（height>0 时最后一行是图像第一行）

扩展方式：
    新增位深只需扩展 SUPPORTED_BIT_COUNT 判断与 read_pixels 中的分支，
    输出矩阵尺寸可调整 TARGET_SIZE；缩放算法可替换 scale_matrix 实现。
"""
import hashlib
import json
import os
import struct
import time

RESULT_FILE = "perception_input/bmp_matrix_result.jsonl"
CHAIN_FILE = "hash_chain_v2.log"
INPUT_FILE = None          # 本次未提供外部 BMP，走测试分支
TARGET_SIZE = 16           # 输出矩阵边长 16 或 32
SUPPORTED_BIT_COUNT = {24, 8}


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def append_hash_chain(path, prev_hash):
    """为指定文件计算 md5 并按 v2 公式追加一条哈希链记录，返回新 record_hash"""
    file_hash = md5_of_file(path)
    timestamp = time.time()
    record_hash = hashlib.md5(
        (file_hash + prev_hash + str(timestamp)).encode("utf-8")
    ).hexdigest()
    with open(CHAIN_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "schema_version": 2,
            "timestamp": timestamp,
            "file": path,
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }, ensure_ascii=False) + "\n")
    print("file=%s" % path)
    print("file_hash=%s" % file_hash)
    print("prev_hash=%s" % prev_hash)
    print("record_hash=%s" % record_hash)
    print("timestamp=%s" % timestamp)
    return record_hash


def current_chain_tail():
    """读取哈希链当前链尾 record_hash；链空则返回空串"""
    prev_hash = ""
    with open(CHAIN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                prev_hash = json.loads(line)["record_hash"]
    return prev_hash


def parse_bmp_header(data):
    """解析 BMP 头，返回 (offset, width, height, bit_count)

    若文件头非法或位深不受支持则抛 ValueError。
    """
    if len(data) < 54 or data[0:2] != b"BM":
        raise ValueError("非法的 BMP 文件头（缺少 BM 标记）")
    offset = struct.unpack("<I", data[10:14])[0]
    width = struct.unpack("<i", data[18:22])[0]
    height = struct.unpack("<i", data[22:26])[0]
    bit_count = struct.unpack("<H", data[28:30])[0]
    if width <= 0:
        raise ValueError("BMP 宽度非法: %d" % width)
    if bit_count not in SUPPORTED_BIT_COUNT:
        raise ValueError("不支持的位深: %d（仅支持 %s）" %
                         (bit_count, sorted(SUPPORTED_BIT_COUNT)))
    return offset, width, height, bit_count


def read_pixels(data, offset, width, abs_height, bit_count):
    """读取像素为灰度二维数组（rows -> cols），0~255 整数"""
    # 行字节数按 4 字节对齐
    row_bytes = ((width * bit_count + 31) // 32) * 4
    matrix = []
    for r in range(abs_height):
        base = offset + r * row_bytes
        row = []
        for c in range(width):
            px = base + c * (bit_count // 8)
            if bit_count == 24:
                b, g, r_ = struct.unpack_from("<BBB", data, px)
                gray = (r_ + g + b) // 3
            else:  # bit_count == 8，标准灰度 BMP 调色板为灰阶，取索引即灰度
                gray = data[px]
            row.append(gray)
        matrix.append(row)
    return matrix


def scale_matrix(matrix, target):
    """最近邻缩放到 target×target"""
    src_h = len(matrix)
    src_w = len(matrix[0]) if src_h else 0
    out = []
    for i in range(target):
        si = min(src_h - 1, int(i * src_h / target))
        row = []
        for j in range(target):
            sj = min(src_w - 1, int(j * src_w / target))
            row.append(matrix[si][sj])
        out.append(row)
    return out


def make_test_matrix():
    """生成测试矩阵：16×16 左侧黑(0)、右侧白(255)"""
    size = TARGET_SIZE
    return [[0 if j < size // 2 else 255 for j in range(size)] for i in range(size)]


def print_preview(matrix, name):
    """控制台打印矩阵预览（# = 灰度>=128 白，. = 黑）"""
    print("=== 矩阵预览：%s (%dx%d) ===" % (name, len(matrix), len(matrix[0])))
    for row in matrix:
        print("".join("#" if v >= 128 else "." for v in row))


def main():
    # 1) 解析输入：无外部 BMP 时使用测试矩阵
    if INPUT_FILE and os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, "rb") as f:
            data = f.read()
        offset, width, height, bit_count = parse_bmp_header(data)
        abs_height = abs(height)
        raw = read_pixels(data, offset, width, abs_height, bit_count)
        if height < 0:  # top-down：无需翻转
            pass
        else:           # bottom-up：最后一行是图像第一行，翻转
            raw = raw[::-1]
        matrix = scale_matrix(raw, TARGET_SIZE)
        file_name = os.path.basename(INPUT_FILE)
        print("已解析 BMP: %s, %dx%d, bit_count=%d" % (file_name, width, abs_height, bit_count))
    else:
        matrix = make_test_matrix()
        file_name = "test_black_white.bmp"
        print("未提供输入 BMP，生成测试矩阵 test_black_white.bmp")

    # 2) 生成记录
    record = {
        "schema_version": 2,
        "timestamp": time.time(),
        "file_name": file_name,
        "width": len(matrix[0]),
        "height": len(matrix),
        "matrix": matrix,
        "source": "bmp_to_matrix",
    }

    # 3) 写入结果文件（创建/覆盖本结果文件）
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 4) 打印摘要与矩阵预览
    print("=== 解析摘要 ===")
    print("file_name=%s" % record["file_name"])
    print("size=%dx%d" % (record["width"], record["height"]))
    print("元素范围=[%d,%d]" % (min(v for row in matrix for v in row),
                                max(v for row in matrix for v in row)))
    print_preview(matrix, record["file_name"])

    # 5) 哈希链追加（仅一条）
    print("=== 哈希链追加 ===")
    append_hash_chain(RESULT_FILE, current_chain_tail())


if __name__ == "__main__":
    main()
