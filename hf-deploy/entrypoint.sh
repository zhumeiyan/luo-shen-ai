#!/bin/bash
# Hugging Face Spaces 持久化软链接脚本
# 将 active_memory / hash_chain 指向 HF 持久化目录 /data
# 这样核心代码不需要修改任何路径

set -e

DATA_DIR="${LUOSHEN_DATA:-/data}"

echo "[entry] DATA_DIR=$DATA_DIR"

# 确保 /data 下的目录存在
mkdir -p "$DATA_DIR/active_memory"
mkdir -p "$DATA_DIR/hospital_rules"

# 首次启动：把容器内的初始数据写入 /data
if [ ! -f "$DATA_DIR/active_memory/active_memory.json" ]; then
  echo "[entry] first run, copying initial active_memory..."
  cp /app/active_memory/*.json "$DATA_DIR/active_memory/" 2>/dev/null || true
  cp /app/active_memory/*.jsonl "$DATA_DIR/active_memory/" 2>/dev/null || true
fi

if [ ! -f "$DATA_DIR/hash_chain_v2.log" ]; then
  echo "[entry] first run, copying initial hash chains..."
  cp /app/hash_chain_v2*.log "$DATA_DIR/" 2>/dev/null || true
fi

if [ ! -f "$DATA_DIR/hospital_rules/principles.json" ]; then
  echo "[entry] first run, copying initial hospital_rules..."
  cp /app/hospital_rules/*.json "$DATA_DIR/hospital_rules/" 2>/dev/null || true
fi

# 创建软链接：让代码中的相对路径指向 /data（持久存储）
cd /app
ln -sfn "$DATA_DIR/active_memory" active_memory
ln -sfn "$DATA_DIR/hash_chain_v2.log" hash_chain_v2.log
ln -sfn "$DATA_DIR/hash_chain_v2.backup.log" hash_chain_v2.backup.log
ln -sfn "$DATA_DIR/hospital_rules" hospital_rules

echo "[entry] symlinks created:"
ls -la /app/active_memory /app/hospital_rules /app/hash_chain_v2.log 2>/dev/null || true

# 启动洛神
echo "[entry] starting luoshen..."
exec python3 web_chat.py
