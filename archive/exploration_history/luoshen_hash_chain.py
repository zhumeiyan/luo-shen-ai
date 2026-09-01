"""洛神哈希链：每一句话落地生根，连她自己都改不了。

链的结构：
  每条消息 {
    ...原字段...,
    content_hash: SHA256(plaintext + channel + created_at + prev_hash),
    prev_hash: 前一条消息的 content_hash（链式锚定）
  }

  验证链时，从创世区块开始，逐条重算 content_hash，
  如果任何一条被篡改，它的 content_hash 就会对不上，
  下一条的 prev_hash 也会对不上。
"""

import hashlib
import json
import os
import time


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_hash(plaintext, channel, created_at, prev_hash):
    """计算一条消息的 content_hash。"""
    payload = "|".join([
        str(plaintext),
        str(channel),
        str(created_at),
        str(prev_hash or ""),
    ])
    return _sha256(payload)


def last_hash_for_channel(channel):
    """从本地缓存里读取某 channel 最后一条消息的 hash。"""
    cache_path = os.path.join(_cache_dir(), "%s_last_hash.txt" % _safe(channel))
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    return None


def save_last_hash(channel, h):
    """把某 channel 最后一条消息的 hash 写入本地缓存。"""
    cache_path = os.path.join(_cache_dir(), "%s_last_hash.txt" % _safe(channel))
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(h)


def _cache_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hash_chain")
    os.makedirs(d, exist_ok=True)
    return d


def _safe(channel):
    # 把 channel 里的非法文件名字符换成下划线
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in channel)


def new_block(plaintext, channel, created_at=None):
    """构造一条带哈希的新消息块。
    返回 dict，包含 content_hash 和 prev_hash。
    """
    if created_at is None:
        created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    prev = last_hash_for_channel(channel)
    h = compute_hash(plaintext, channel, created_at, prev)
    block = {
        "content_hash": h,
        "prev_hash": prev,
    }
    # 缓存这个 hash 供下一条使用
    save_last_hash(channel, h)
    return block


def verify_chain(messages):
    """验证一条消息链的完整性。
    messages 按时间升序，每条含 plaintext, channel, created_at, content_hash, prev_hash。
    返回 (is_valid, first_invalid_index)。
    """
    prev_by_channel = {}
    for i, m in enumerate(messages):
        channel = m.get("channel", "")
        prev = prev_by_channel.get(channel)
        # 检查 prev_hash 是否匹配
        if m.get("prev_hash") != prev:
            return False, i
        # 重算 content_hash
        expected = compute_hash(
            m.get("plaintext", ""),
            channel,
            m.get("created_at", ""),
            prev,
        )
        if expected != m.get("content_hash"):
            return False, i
        prev_by_channel[channel] = m.get("content_hash")
    return True, -1
