import hashlib
import json
import os
import time


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def append_hash_chain(file_path, file_hash):
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
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash
    }
    with open('hash_chain_v2.log', 'a') as f:
        f.write(json.dumps(chain_record) + '\n')
    return chain_record


def main():
    src = 'perception_input/sample_image.jpg'
    if not os.path.exists(src):
        print(json.dumps({"error": "sample_image.jpg not found"}))
        return

    matrix_mode = 'raw_bytes_16x16'
    avg_brightness = 0.0
    color_variance = 0.0
    matrix = []

    try:
        from PIL import Image
        img = Image.open(src).convert('RGB').resize((16, 16))
        pixels = list(img.getdata())
        matrix = []
        for i in range(16):
            row = []
            for j in range(16):
                row.append(list(pixels[i * 16 + j]))
            matrix.append(row)
        matrix_mode = 'rgb_16x16'

        all_vals = [v for row in matrix for px in row for v in px]
        avg_brightness = round(sum(all_vals) / len(all_vals), 2)
        diffs = []
        for row in matrix:
            for r, g, b in row:
                diffs.append(max(r, g, b) - min(r, g, b))
        color_variance = round(sum(diffs) / len(diffs), 2)
    except ImportError:
        with open(src, 'rb') as f:
            data = f.read()[:256]
        data = data + b'\x00' * (256 - len(data))
        matrix = []
        for i in range(16):
            row = []
            for j in range(16):
                row.append(data[i * 16 + j])
            matrix.append(row)
        matrix_mode = 'raw_bytes_16x16'
        avg_brightness = round(sum(data) / 256, 2)
        color_variance = 0.0
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return

    record = {
        "schema_version": 1,
        "timestamp": time.time(),
        "source": "image_to_matrix",
        "matrix_mode": matrix_mode,
        "width": 16,
        "height": 16,
        "matrix": matrix,
        "avg_brightness": avg_brightness,
        "color_variance": color_variance
    }
    with open('perception_input/sample_image_matrix.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

    memory_point = {
        "schema_version": 1,
        "timestamp": time.time(),
        "memory_point": {
            "type": "image",
            "avg_brightness": avg_brightness,
            "color_variance": color_variance,
            "note": "真实图片矩阵特征"
        },
        "source": "image_to_matrix"
    }
    with open('memory_points.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(memory_point, ensure_ascii=False) + '\n')

    print('matrix_mode:', matrix_mode)
    print('avg_brightness:', avg_brightness)
    print('color_variance:', color_variance)
    print('sample_image_matrix.jsonl content:')
    with open('perception_input/sample_image_matrix.jsonl', 'r', encoding='utf-8') as f:
        print(f.read().rstrip('\n'))
    print('memory_points.jsonl last record:')
    with open('memory_points.jsonl', 'r', encoding='utf-8') as f:
        lines = [line for line in f.readlines() if line.strip()]
        print(lines[-1].rstrip('\n'))

    chain1 = append_hash_chain('perception_input/sample_image_matrix.jsonl',
                               md5_of_file('perception_input/sample_image_matrix.jsonl'))
    chain2 = append_hash_chain('memory_points.jsonl', md5_of_file('memory_points.jsonl'))
    print('hash chain record 1:', json.dumps(chain1))
    print('hash chain record 2:', json.dumps(chain2))


if __name__ == '__main__':
    main()
