import hashlib
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import time
from urllib.parse import urlparse


def validate_video_url(url):
    """只允许 https 且目标 IP 非内网/回环/保留地址，
    防止 SSRF 与 ffmpeg 本地文件读取（file://、concat: 等协议）。"""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("VIDEO_URL 仅允许 https 协议，收到: %r" % parsed.scheme)
    host = parsed.hostname
    if not host:
        raise ValueError("VIDEO_URL 缺少主机名")
    try:
        addrinfos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError("VIDEO_URL 无法解析域名: %s" % host)
    for info in addrinfos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("VIDEO_URL 不允许访问内网/保留地址: %s (%s)" % (host, ip))
    return url


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    url = os.environ.get('VIDEO_URL', '')
    if not url:
        url = 'https://www.w3schools.com/html/mov_bbb.mp4'
    try:
        url = validate_video_url(url)
    except ValueError as e:
        print('video_status: blocked')
        print('note:', e)
        return

    video_status = 'no_tool'
    tool = 'none'

    has_ffmpeg = shutil.which('ffmpeg') is not None
    has_cv2 = False
    try:
        r = subprocess.run(
            ['python', '-c', 'import cv2'],
            capture_output=True, text=True, timeout=15
        )
        has_cv2 = (r.returncode == 0)
    except Exception:
        has_cv2 = False

    if has_ffmpeg:
        tool = 'ffmpeg'
        try:
            r = subprocess.run(
                ['ffmpeg', '-y', '-ss', '1', '-i', url, '-frames:v', '1',
                 'perception_input/video_frame.jpg'],
                capture_output=True, text=True, timeout=60
            )
            if r.returncode == 0 and os.path.exists('perception_input/video_frame.jpg'):
                video_status = 'success'
            else:
                video_status = 'failed'
        except Exception:
            video_status = 'failed'
    elif has_cv2:
        tool = 'cv2'
        try:
            import cv2
            cap = cv2.VideoCapture(url)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    cv2.imwrite('perception_input/video_frame.jpg', frame)
                    video_status = 'success'
                else:
                    video_status = 'failed'
                cap.release()
            else:
                video_status = 'failed'
        except Exception:
            video_status = 'failed'
    else:
        tool = 'none'
        video_status = 'no_tool'

    if video_status == 'success':
        with open('perception_input/video_frame.jpg', 'rb') as f:
            data = f.read()[:256]
        data = data + b'\x00' * (256 - len(data))
        matrix = []
        for i in range(16):
            row = []
            for j in range(16):
                row.append(data[i * 16 + j])
            matrix.append(row)
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "source": "video_frame_extract",
            "video_status": "success",
            "matrix": matrix
        }
    else:
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "video_status": video_status,
            "note": "无可用视频处理工具"
        }

    with open('perception_input/video_frame_matrix.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

    print('video_status:', video_status)
    print('tool:', tool)
    print('video_frame_matrix.jsonl content:')
    with open('perception_input/video_frame_matrix.jsonl', 'r', encoding='utf-8') as f:
        print(f.read().rstrip('\n'))

    file_hash = md5_of_file('perception_input/video_frame_matrix.jsonl')
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
        "file": "perception_input/video_frame_matrix.jsonl",
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash
    }
    with open('hash_chain_v2.log', 'a') as f:
        f.write(json.dumps(chain_record) + '\n')
    print('hash chain record:', json.dumps(chain_record))


if __name__ == '__main__':
    main()
