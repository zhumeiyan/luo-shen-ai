"""
Terrarium 调度器
- 循环调用 /tick 端点
- 每次 tick 之间间隔若干秒
- 记录每轮结果
"""
import json
import sys
import os
import time
import urllib.request
import urllib.error

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TICK_URL = os.environ.get("TICK_URL", "http://127.0.0.1:8766/tick")
STATE_URL = os.environ.get("STATE_URL", "http://127.0.0.1:8766/state")
INTERVAL_SECONDS = int(os.environ.get("TICK_INTERVAL", "30"))  # 每次 tick 间隔


def http_get_json(url):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url):
    req = urllib.request.Request(url, method="POST",
                                 data=b"{}",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_state():
    try:
        return http_get_json(STATE_URL)
    except Exception as e:
        print(f"[scheduler] state check failed: {e}", flush=True)
        return None


def tick():
    try:
        return http_get_json(TICK_URL)
    except Exception as e:
        print(f"[scheduler] tick failed: {e}", flush=True)
        return {"status": "error", "error": str(e)}


def main():
    print(f"[scheduler] 启动", flush=True)
    print(f"[scheduler] TICK_URL = {TICK_URL}", flush=True)
    print(f"[scheduler] INTERVAL  = {INTERVAL_SECONDS}s", flush=True)
    print(f"", flush=True)

    round_num = 0
    max_retries = 3

    while True:
        round_num += 1
        print(f"\n{'='*60}", flush=True)
        print(f"[scheduler] Round {round_num} — calling /tick ...", flush=True)

        # 检查 state
        state = check_state()
        if state:
            print(f"[scheduler] current state: turn={state.get('turn')}, speaker={state.get('speaker')}", flush=True)
            if state.get("turn", 0) >= state.get("max_turns", 10):
                print(f"[scheduler] max_turns reached. Exiting.", flush=True)
                break

        # 调用 /tick (with retries)
        result = None
        for attempt in range(max_retries):
            try:
                result = tick()
                break
            except Exception as e:
                print(f"[scheduler] tick attempt {attempt+1} failed: {e}", flush=True)
                time.sleep(5)

        if result is None:
            print(f"[scheduler] tick failed after {max_retries} attempts. Exiting.", flush=True)
            break

        status = result.get("status", "?")
        if status == "finished":
            print(f"[scheduler] tick returned 'finished': {result.get('message', '')}", flush=True)
            break
        elif status == "error":
            print(f"[scheduler] tick error: {result.get('error', '')}", flush=True)
            print(f"[scheduler] stopping due to error.", flush=True)
            break
        elif status == "ok":
            speaker = result.get("speaker", "?")
            next_s = result.get("next_speaker", "?")
            energy = result.get("energy", "?")
            preview = result.get("reply_preview", "")[:150].replace("\n", " ")
            print(f"[scheduler] ✓ round {result.get('round_executed')}, speaker={speaker}, next={next_s}", flush=True)
            print(f"[scheduler]   energy={energy}", flush=True)
            print(f"[scheduler]   reply: {preview}...", flush=True)

        # 检查是否完成
        state = check_state()
        if state and state.get("turn", 0) >= state.get("max_turns", 10):
            print(f"\n[scheduler] === ALL {state.get('max_turns')} ROUNDS COMPLETE ===", flush=True)
            break

        # 等下一轮
        print(f"[scheduler] waiting {INTERVAL_SECONDS}s ...", flush=True)
        time.sleep(INTERVAL_SECONDS)

    print(f"\n[scheduler] done. Total rounds: {round_num}", flush=True)


if __name__ == "__main__":
    main()
