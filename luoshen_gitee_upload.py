#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP228
模块名称：luoshen_gitee_upload.py
职责：将洛神系统完整上传到设计者的 Gitee 仓库，实现云端备份。
- 凭证从环境变量读取（GITEE_USER / GITEE_TOKEN），不落盘、不打印。
- 使用 dulwich（纯 Python git 实现）clone/add/commit/push。
- 遵守 .gitignore：排除敏感配置、密钥、wav/mp4/jpg/zip、回滚点、缓存等。
- 生成 gitee_upload_info.jsonl 记录并追加哈希链。
"""

import hashlib
import json
import os
import shutil
import time

from dulwich import ignore, porcelain
from dulwich.repo import Repo

BASE_DIR = "."
CLONE_DIR = os.path.join("temp", "luoshen_gitee_clone")
INFO_PATH = os.path.join("perception_input", "gitee_upload_info.jsonl")
CHAIN_PATH = "hash_chain_v2.log"
SOURCE = "luoshen_gitee_upload"
REPO_URL = "https://gitee.com/zhu-meiyan1/luo-shen-ai.git"


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_gitignore_rules():
    ignore_path = os.path.join(BASE_DIR, ".gitignore")
    return ignore.IgnoreFilter.from_path(ignore_path)


def is_ignored(path, matcher):
    rel = path.replace(os.sep, "/")
    # IgnoreFilter.is_ignored 返回 True 表示被忽略
    return matcher.is_ignored(rel)


def collect_files(matcher):
    """收集工作区中未被 gitignore 忽略、非 .git/temp/output 的文件。"""
    results = []
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "temp", "output")]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, BASE_DIR).replace(os.sep, "/")
            if rel.startswith(".git") or rel.startswith("temp/") or rel.startswith("output/"):
                continue
            if rel == INFO_PATH:
                continue
            if is_ignored(rel, matcher):
                continue
            results.append(rel)
    return sorted(results)


def get_credentials():
    user = os.environ.get("GITEE_USER", "")
    token = os.environ.get("GITEE_TOKEN", "")
    if not user or not token:
        raise RuntimeError("缺少 Gitee 凭证：请设置环境变量 GITEE_USER 与 GITEE_TOKEN")
    return user, token


def url_with_credentials(user, token):
    return "https://%s:%s@gitee.com/zhu-meiyan1/luo-shen-ai.git" % (user, token)


def append_chain(file_path, ts):
    file_hash = file_md5(file_path)
    with open(CHAIN_PATH, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    last_record = json.loads(lines[-1])
    prev_hash = last_record["record_hash"]
    record_hash = hashlib.md5(
        (file_hash + prev_hash + str(ts)).encode("utf-8")
    ).hexdigest()
    record = {
        "schema_version": 2,
        "timestamp": ts,
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main():
    ts = time.time()
    user, token = get_credentials()
    auth_url = url_with_credentials(user, token)

    # 1. 清理旧克隆并 clone 远端
    if os.path.exists(CLONE_DIR):
        shutil.rmtree(CLONE_DIR)
    os.makedirs(os.path.dirname(CLONE_DIR), exist_ok=True)
    porcelain.clone(auth_url, CLONE_DIR)
    print("clone ok")

    # 2. 收集并复制洛神文件到克隆目录
    matcher = load_gitignore_rules()
    files = collect_files(matcher)
    for rel in files:
        src = os.path.join(BASE_DIR, rel)
        dst = os.path.join(CLONE_DIR, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    print("files to upload:", len(files))

    # 3. 在克隆目录 add + commit + push
    repo = Repo(CLONE_DIR)
    try:
        porcelain.add(repo, paths=None)
        cid = porcelain.commit(
            repo,
            message="LUOSHEN-L1-STEP228: 洛神系统云端备份 upload",
            author="朱美岩 <778131400@qq.com>",
            committer="朱美岩 <778131400@qq.com>",
        )
        print("commit:", cid.decode("utf-8")[:12])
        porcelain.push(repo, "origin", "master")
        print("push ok")
    finally:
        repo.close()

    # 4. 写记录（仓库地址脱敏）
    info_record = {
        "schema_version": 2,
        "timestamp": ts,
        "repo": "gitee.com/zhu-meiyan1/luo-shen-ai.git",
        "files_uploaded": len(files),
        "status": "success",
        "source": SOURCE,
    }
    with open(INFO_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(info_record, ensure_ascii=False) + "\n")

    # 5. 追加哈希链
    chain_record = append_chain(INFO_PATH, ts)

    print("=== LUOSHEN GITEE UPLOAD ===")
    print("repo (masked): gitee.com/zhu-meiyan1/luo-shen-ai.git")
    print("files_uploaded:", len(files))
    print("status: success")
    print("=== HASH CHAIN ===")
    print("prev_hash:", chain_record["prev_hash"])
    print("record_hash:", chain_record["record_hash"])


if __name__ == "__main__":
    main()
