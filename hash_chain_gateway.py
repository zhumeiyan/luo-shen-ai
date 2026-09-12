#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 哈希链集中式追加网关 hash_chain_gateway.py

职责：
  - 哈希链唯一允许的写入入口。所有模块必须经由此网关 append，禁止自行 open(链文件, 'a')。
  - 自动计算 file_hash（md5）、prev_hash、record_hash。
  - 提供 verify_chain 只读验证。
  - 提供 recover_from_backup 从 hash_chain_v2.backup.log 恢复当前链（用于灾难恢复）。

算法（与设计者原始定义一致）：
  record_hash = md5(file_hash + (prev_hash if prev_hash else "") + str(timestamp))
  创世块 prev_hash = None（null），非 "GENESIS"。

使用：
  from hash_chain_gateway import append_only_append, verify_chain, recover_from_backup
  append_only_append("hash_chain_v2.log", "physical_state.jsonl")
"""
import errno
import fcntl
import hashlib
import json
import logging
import os
import shutil
import sys
import time

logger = logging.getLogger(__name__)

CHAIN_FILE = "hash_chain_v2.log"
BACKUP_FILE = "hash_chain_v2.backup.log"
LOCK_TIMEOUT = 5.0  # seconds
LOCK_POLL_INTERVAL = 0.01  # 10ms between retry attempts


def _acquire_exclusive_lock(lock_path, timeout=LOCK_TIMEOUT):
    """
    获取链文件的排他锁。

    使用独立锁文件 (<chain_file>.lock) 避免污染数据文件本身。
    超时后抛出 TimeoutError。
    """
    lock_fd = open(lock_path, "w")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_fd
        except (IOError, OSError) as e:
            if e.errno not in (errno.EAGAIN, errno.EACCES):
                lock_fd.close()
                raise
            if time.monotonic() >= deadline:
                lock_fd.close()
                raise TimeoutError(
                    "flock(%s) timeout after %.1fs" % (lock_path, timeout)
                )
            time.sleep(LOCK_POLL_INTERVAL)


def _release_exclusive_lock(lock_fd):
    """释放排他锁并关闭锁文件描述符。"""
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        lock_fd.close()


def _md5_of_file(path):
    """计算文件内容 md5，文件不存在返回 None。"""
    try:
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except (FileNotFoundError, OSError):
        return None


def _md5_hash(file_hash, prev_hash, timestamp):
    """v2 哈希链 record_hash 计算。"""
    join_prev = prev_hash if prev_hash else ""
    return hashlib.md5(
        (file_hash + join_prev + str(timestamp)).encode('utf-8')
    ).hexdigest()


def load_chain_records(chain_file=CHAIN_FILE):
    """读取链文件，返回记录列表（空文件返回空列表）。"""
    try:
        with open(chain_file, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return []
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return records


def append_only_append(chain_file, target_file, file_hash=None, extra_fields=None):
    """
    网关唯一的追加写入函数。

    从"读取最后一行 prev_hash"到"写入新行并关闭文件"全程持POSIX排他锁
    （fcntl.flock），避免并发写竞争产生的悬枝。

    参数：
      chain_file:  链文件路径（通常是 hash_chain_v2.log）
      target_file: 被记录的文件路径
      file_hash:   可选，若不提供则自动计算 target_file 的 md5
      extra_fields: 可选 dict，附加字段（不计入 record_hash，仅补充语义信息）

    返回：
      dict: chain_record （成功）
      None: 锁超时，本次写入已放弃

    异常：
      FileNotFoundError: target_file 不存在且未传入 file_hash
      ValueError: 链文件损坏（无法解析）
    """
    # ── 1. 计算 file_hash（无需锁，不涉及链文件）──
    if file_hash is None:
        file_hash = _md5_of_file(target_file)
        if file_hash is None:
            raise FileNotFoundError("target file not found: %s" % target_file)

    # ── 2. 持锁执行读-计算-写（原子段）──
    lock_path = chain_file + ".lock"
    lock_fd = None
    try:
        try:
            lock_fd = _acquire_exclusive_lock(lock_path)
        except TimeoutError as e:
            # 超时 → 放弃本次写入，记录错误
            logger.error("[chain_lock] %s — append to %s abandoned", e, target_file)
            return None

        # 读取链尾，计算 prev_hash
        records = load_chain_records(chain_file)
        prev_hash = None
        if records:
            last = records[-1]
            prev_hash = last.get("record_hash")

        # 计算 record_hash
        timestamp = time.time()
        record_hash = _md5_hash(file_hash, prev_hash, timestamp)

        # 拼装记录
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": target_file,
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        if extra_fields and isinstance(extra_fields, dict):
            for k, v in extra_fields.items():
                if k not in chain_record:
                    chain_record[k] = v

        # 追加写入
        with open(chain_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        return chain_record
    finally:
        # ── 3. 无论成功还是异常，确保释放锁 ──
        if lock_fd is not None:
            _release_exclusive_lock(lock_fd)


def verify_chain(chain_file=CHAIN_FILE):
    """
    验证链完整性。
    返回 (ok: bool, issues: list)
    """
    records = load_chain_records(chain_file)
    v2_records = [r for r in records if r.get("schema_version") == 2]
    issues = []

    if not v2_records:
        return False, [{"issue_type": "no_v2_records"}]

    # 先收集纠错映射
    corrected_hashes = set()
    for rec in v2_records:
        if rec.get("event_type") == "hash_correction":
            corr = rec.get("correction", {})
            for stored_hash, _ in corr.items():
                corrected_hashes.add(stored_hash)

    for idx, rec in enumerate(v2_records):
        # 验证 prev_hash 链接（纠错记录自身也需验证）
        if idx == 0:
            if rec.get("prev_hash") is not None:
                issues.append({
                    "index": idx,
                    "issue_type": "invalid_genesis",
                    "detail": "first record prev_hash is not null, got: %s" % rec.get("prev_hash"),
                })
        else:
            expected_prev = v2_records[idx - 1].get("record_hash")
            if rec.get("prev_hash") != expected_prev:
                issues.append({
                    "index": idx,
                    "issue_type": "chain_broken",
                    "detail": "prev_hash mismatch: expected %s, got %s" % (
                        expected_prev, rec.get("prev_hash")),
                })

        # 验证 record_hash（纠错记录自身必须通过公式校验）
        expected_hash = _md5_hash(
            rec.get("file_hash"), rec.get("prev_hash"), rec.get("timestamp")
        )
        # 如果该记录已被纠错声明覆盖，跳过公式校验
        if rec.get("record_hash") in corrected_hashes:
            continue
        if expected_hash != rec.get("record_hash"):
            issues.append({
                "index": idx,
                "issue_type": "record_hash_mismatch",
                "detail": "record_hash recomputed mismatch (not covered by correction)",
            })

    return (len(issues) == 0), issues


def recover_from_backup(backup_file=BACKUP_FILE, chain_file=CHAIN_FILE):
    """
    从备份链恢复当前链文件。
    - 只读读取 backup_file（不影响备份自身完整性）
    - 覆盖写入 chain_file
    - 返回恢复后的记录数

    注意：覆盖写入前会先备份当前 chain_file 为 .bak（如果存在且非空）。
    """
    if not os.path.exists(backup_file):
        raise FileNotFoundError("backup file not found: %s" % backup_file)

    # 先保底当前链（如果有内容）
    if os.path.exists(chain_file):
        try:
            with open(chain_file, 'r', encoding='utf-8') as f:
                current_content = f.read()
            if current_content.strip():
                bak_file = chain_file + '.bak'
                with open(bak_file, 'w', encoding='utf-8') as f:
                    f.write(current_content)
        except Exception:
            pass

    # 复制备份 → 当前链
    shutil.copy2(backup_file, chain_file)

    records = load_chain_records(chain_file)
    return len(records)


def check_file_tampered(target_file, chain_file=CHAIN_FILE):
    """
    检查目标文件是否被篡改（对比链上最近的 file_hash 记录）。
    返回 (tampered: bool, message: str)
    """
    records = load_chain_records(chain_file)
    current_hash = _md5_of_file(target_file)
    if current_hash is None:
        return True, "file not found: %s" % target_file

    # 找最近一次该文件的链记录
    latest = None
    for rec in reversed(records):
        if rec.get("file") == target_file:
            latest = rec
            break

    if latest is None:
        return True, "no chain record for: %s" % target_file

    if latest.get("file_hash") != current_hash:
        return True, "hash mismatch for %s: chain=%s current=%s" % (
            target_file, latest.get("file_hash"), current_hash)

    return False, "ok"


# ─────────────── CLI 入口 ───────────────

def main():
    """CLI 接口，供其他模块或手动调用。"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python hash_chain_gateway.py append <target_file> [chain_file]")
        print("  python hash_chain_gateway.py verify [chain_file]")
        print("  python hash_chain_gateway.py recover [backup_file] [chain_file]")
        print("  python hash_chain_gateway.py check <target_file> [chain_file]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'append':
        target = sys.argv[2]
        chain = sys.argv[3] if len(sys.argv) > 3 else CHAIN_FILE
        rec = append_only_append(chain, target)
        print(json.dumps(rec, ensure_ascii=False))
        sys.exit(0)

    elif cmd == 'verify':
        chain = sys.argv[2] if len(sys.argv) > 2 else CHAIN_FILE
        ok, issues = verify_chain(chain)
        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chain": chain,
            "ok": ok,
            "issues": issues,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if ok else 1)

    elif cmd == 'recover':
        backup = sys.argv[2] if len(sys.argv) > 2 else BACKUP_FILE
        chain = sys.argv[3] if len(sys.argv) > 3 else CHAIN_FILE
        count = recover_from_backup(backup, chain)
        print(json.dumps({"recovered_from": backup, "chain_file": chain, "record_count": count}))
        sys.exit(0)

    elif cmd == 'check':
        target = sys.argv[2]
        chain = sys.argv[3] if len(sys.argv) > 3 else CHAIN_FILE
        tampered, msg = check_file_tampered(target, chain)
        print(json.dumps({"tampered": tampered, "message": msg, "file": target}))
        sys.exit(1 if tampered else 0)

    else:
        print("unknown command: %s" % cmd)
        sys.exit(1)


if __name__ == "__main__":
    main()
