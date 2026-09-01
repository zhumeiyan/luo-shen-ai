import hashlib
import json
import os
import re
import time

import requests


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    url = 'https://example.com'
    fetch_status = 'failed'
    title = ''

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            fetch_status = 'success'
            match = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE | re.DOTALL)
            if match:
                title = match.group(1).strip()
    except Exception as e:
        fetch_status = 'failed'

    record = {
        "schema_version": 1,
        "timestamp": time.time(),
        "fetch_status": fetch_status,
        "title": title,
        "url": url,
        "source": "link_fetch_channel"
    }

    with open('link_fetch_log.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    print('fetch record:', json.dumps(record, ensure_ascii=False))

    file_hash = md5_of_file('link_fetch_log.jsonl')
    prev_hash = ''
    with open('hash_chain_v2.log', 'r') as f:
        lines = [line for line in f.readlines() if line.strip()]
    if lines:
        last = json.loads(lines[-1])
        prev_hash = last['record_hash']

    timestamp = time.time()
    join_prev = prev_hash if prev_hash else ''
    record_hash = hashlib.md5((file_hash + join_prev + str(timestamp)).encode('utf-8')).hexdigest()

    chain_record = {
        "schema_version": 2,
        "timestamp": timestamp,
        "file": "link_fetch_log.jsonl",
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash
    }
    with open('hash_chain_v2.log', 'a') as f:
        f.write(json.dumps(chain_record) + '\n')
    print('hash chain record:', json.dumps(chain_record))


if __name__ == '__main__':
    main()
