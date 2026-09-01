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
    os.makedirs('perception_input', exist_ok=True)

    image_status = 'failed'
    try:
        resp = requests.get('https://httpbin.org/image/jpeg', timeout=15)
        if resp.status_code == 200:
            with open('perception_input/sample_image.jpg', 'wb') as f:
                f.write(resp.content)
            image_status = 'success'
    except Exception as e:
        image_status = 'failed'

    video_status = 'unavailable'
    try:
        import cv2
        cap = cv2.VideoCapture('https://www.w3schools.com/html/mov_bbb.mp4')
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                cv2.imwrite('perception_input/sample_video_frame_1.jpg', frame)
                video_status = 'success'
            else:
                video_status = 'failed'
            cap.release()
        else:
            video_status = 'failed'
    except ImportError:
        video_status = 'unavailable'
    except Exception as e:
        video_status = 'failed'

    record = {
        "schema_version": 1,
        "timestamp": time.time(),
        "source": "media_capture_channels",
        "image_status": image_status,
        "video_status": video_status,
        "files": ["perception_input/sample_image.jpg", "perception_input/sample_video_frame_1.jpg"],
        "note": "洛神外部素材采集通道测试"
    }

    manifest_path = 'perception_input/perception_input_manifest.jsonl'
    with open(manifest_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    print('image_status:', image_status)
    print('video_status:', video_status)
    print('manifest content:')
    with open(manifest_path, 'r', encoding='utf-8') as f:
        print(f.read().rstrip('\n'))

    file_hash = md5_of_file(manifest_path)
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
        "file": "perception_input/perception_input_manifest.jsonl",
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash
    }
    with open('hash_chain_v2.log', 'a') as f:
        f.write(json.dumps(chain_record) + '\n')
    print('hash chain record:', json.dumps(chain_record))


if __name__ == '__main__':
    main()
