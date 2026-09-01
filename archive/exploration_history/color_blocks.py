import hashlib
import json
import time

COLORS = [
    ("红", [255, 0, 0]),
    ("绿", [0, 255, 0]),
    ("蓝", [0, 0, 255]),
    ("黄", [255, 255, 0]),
    ("青", [0, 255, 255]),
    ("紫", [255, 0, 255]),
    ("白", [255, 255, 255]),
    ("黑", [0, 0, 0]),
    ("灰", [128, 128, 128]),
    ("橙", [255, 165, 0]),
]

JSONL_PATH = "perception_input/color_blocks.jsonl"
CHAIN_PATH = "hash_chain_v2.log"


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    for color_name, rgb in COLORS:
        matrix = [[rgb for _ in range(16)] for _ in range(16)]
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "color_name": color_name,
            "rgb": rgb,
            "width": 16,
            "height": 16,
            "matrix": matrix,
            "source": "color_blocks"
        }
        with open(JSONL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("color_blocks.jsonl content:")
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        print(f.read().rstrip("\n"))

    file_hash = md5_of_file(JSONL_PATH)
    prev_hash = ""
    with open(CHAIN_PATH, "r") as f:
        lines = [line for line in f.readlines() if line.strip()]
    if lines:
        last = json.loads(lines[-1])
        prev_hash = last["record_hash"]

    timestamp = time.time()
    join_prev = prev_hash if prev_hash else ""
    record_hash = hashlib.md5((file_hash + join_prev + str(timestamp)).encode("utf-8")).hexdigest()

    chain_record = {
        "schema_version": 2,
        "timestamp": timestamp,
        "file": "perception_input/color_blocks.jsonl",
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash
    }
    with open(CHAIN_PATH, "a") as f:
        f.write(json.dumps(chain_record) + "\n")
    print("hash chain record:", json.dumps(chain_record))


if __name__ == "__main__":
    main()
