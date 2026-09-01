import hashlib
import json
import os
import time

import requests


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    url = 'https://www.w3schools.com/html/mov_bbb.mp4'
    video_path = 'perception_input/video_sample.mp4'

    video_status = 'download_failed'
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            with open(video_path, 'wb') as f:
                f.write(resp.content)
            video_status = 'success'
    except Exception as e:
        video_status = 'download_failed'

    matrix = []
    if video_status == 'success':
        with open(video_path, 'rb') as f:
            data = f.read(1024)
        head = data[:256]
        head = head + b'\x00' * (256 - len(head))
        for i in range(16):
            row = []
            for j in range(16):
                row.append(head[i * 16 + j])
            matrix.append(row)

    record = {
        "schema_version": 1,
        "timestamp": time.time(),
        "video_status": video_status,
        "matrix": matrix,
        "source": "video_byte_matrix"
    }

    with open('perception_input/video_byte_matrix.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

    print('video_status:', video_status)
    print('video_byte_matrix.jsonl content:')
    with open('perception_input/video_byte_matrix.jsonl', 'r', encoding='utf-8') as f:
        print(f.read().rstrip('\n'))

    file_hash = md5_of_file('perception_input/video_byte_matrix.jsonl')
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
        "file": "perception_input/video_byte_matrix.jsonl",
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash
    }
    with open('hash_chain_v2.log', 'a') as f:
        f.write(json.dumps(chain_record) + '\n')
    print('hash chain record:', json.dumps(chain_record))


if __name__ == '__main__':
    main()
