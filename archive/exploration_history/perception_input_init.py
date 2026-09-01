import hashlib
import json
import os
import time


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    os.makedirs('perception_input', exist_ok=True)
    print('perception_input/ created:', os.path.isdir('perception_input'))

    manifest_path = os.path.join('perception_input', 'perception_input_manifest.jsonl')
    with open(manifest_path, 'w') as f:
        pass
    size = os.path.getsize(manifest_path)
    print('perception_input_manifest.jsonl size:', size)

    file_hash = md5_of_file(manifest_path)

    chain_path = 'hash_chain_v2.log'
    prev_hash = ''
    with open(chain_path, 'r') as f:
        lines = [line for line in f.readlines() if line.strip()]
    if lines:
        last = json.loads(lines[-1])
        prev_hash = last['record_hash']

    timestamp = time.time()
    join_prev = prev_hash if prev_hash else ''
    record_hash = hashlib.md5((file_hash + join_prev + str(timestamp)).encode('utf-8')).hexdigest()

    record = {
        "schema_version": 2,
        "timestamp": timestamp,
        "file": "perception_input_manifest.jsonl",
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash
    }
    with open(chain_path, 'a') as f:
        f.write(json.dumps(record) + '\n')

    print('hash chain record:', json.dumps(record))


if __name__ == '__main__':
    main()
