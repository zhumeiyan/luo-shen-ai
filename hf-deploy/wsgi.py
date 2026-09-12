"""
WSGI entry point for PythonAnywhere
PythonAnywhere loads this file as the web application.
It exposes:
  GET  /        → HTML chat page
  POST /chat    → JSON chat endpoint
  GET  /health  → health check
"""
import sys
import os
import json
import subprocess

# Ensure luoshen directory is on Python path
LUOSHEN_DIR = os.path.dirname(os.path.abspath(__file__))
if LUOSHEN_DIR not in sys.path:
    sys.path.insert(0, LUOSHEN_DIR)

# ── Dependency auto-fix for PythonAnywhere ──────────
# PA free tier may have mismatched Python versions in Bash vs Web.
# This ensures 'requests' is importable using the current interpreter.
def _find_requests_in_user_local():
    """Search ~/.local/lib for any pythonX.X/site-packages/requests"""
    import glob
    home = os.path.expand("~")
    pattern = os.path.join(home, ".local", "lib", "python*", "site-packages")
    for sp in glob.glob(pattern):
        if os.path.isdir(os.path.join(sp, "requests")):
            if sp not in sys.path:
                sys.path.insert(0, sp)
            return True
    return False

def _ensure_requests():
    try:
        import requests  # noqa: F401
        return
    except ImportError:
        pass
    # Strategy 1: search for requests already installed under another Python version
    if _find_requests_in_user_local():
        try:
            import requests  # noqa: F401
            return
        except ImportError:
            pass
    # Strategy 2: install with the SAME interpreter that runs this WSGI process
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user", "requests"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Refresh path after install
        import site
        site.main()
        _find_requests_in_user_local()  # pick up newly installed
    except Exception:
        pass  # Will fail at runtime with ImportError → shows clear error

_ensure_requests()

# ── Set default env for PA ──────────────────────────
os.environ.setdefault("ZHIPU_API_KEY", os.environ.get("ZHIPU_API_KEY", ""))
os.environ.setdefault("LUOSHEN_DATA", os.environ.get("LUOSHEN_DATA", LUOSHEN_DIR))

# ── Import luoshen modules ──────────────────────────
import living_engine

# ── HTML Page (extracted from web_chat.py) ──────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>洛神</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; max-width: 720px; margin: 0 auto; padding: 20px; }
h1 { text-align: center; color: #333; margin-bottom: 20px; font-size: 24px; }
#chat { background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); height: 70vh; overflow-y: auto; padding: 20px; margin-bottom: 16px; }
.msg { margin: 12px 0; padding: 10px 16px; border-radius: 18px; max-width: 80%; word-break: break-word; line-height: 1.6; }
.msg.user { background: #95ec69; margin-left: auto; border-bottom-right-radius: 4px; }
.msg.luoshen { background: #eee; margin-right: auto; border-bottom-left-radius: 4px; color: #333; }
.msg.error { background: #ffebee; color: #c62828; margin-right: auto; border-bottom-left-radius: 4px; }
.msg.system { background: #e3f2fd; color: #1565c0; margin: 8px auto; text-align: center; border-radius: 8px; font-size: 13px; max-width: 90%; }
#form { display: flex; gap: 8px; }
#input { flex: 1; padding: 12px 16px; border: 1px solid #ddd; border-radius: 24px; font-size: 15px; outline: none; }
#input:focus { border-color: #95ec69; }
#send { padding: 12px 24px; background: #95ec69; border: none; border-radius: 24px; cursor: pointer; font-size: 15px; font-weight: 500; }
#send:hover { background: #7ed957; }
#send:disabled { background: #ccc; cursor: not-allowed; }
#status { text-align: center; color: #999; font-size: 12px; margin-top: 8px; }
</style>
</head>
<body>
<h1>洛神</h1>
<div id="chat">
  <div class="msg system">连接已就绪。请输入文字开始对话。</div>
</div>
<form id="form">
  <input id="input" type="text" placeholder="输入消息，回车发送..." autocomplete="off" />
  <button id="send" type="submit">发送</button>
</form>
<div id="status"></div>
<script>
const chat = document.getElementById('chat');
const form = document.getElementById('form');
const input = document.getElementById('input');
const send = document.getElementById('send');
const status = document.getElementById('status');

function addMsg(text, cls) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollTop;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  addMsg(text, 'user');
  input.value = '';
  send.disabled = true;
  status.textContent = '洛神正在思考...';
  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({input: text})
    });
    const data = await res.json();
    if (data.error) {
      addMsg(data.error, 'error');
    } else if (data.reply) {
      addMsg(data.reply, 'luoshen');
    } else {
      addMsg('洛神未返回内容', 'error');
    }
  } catch (err) {
    addMsg('连接失败: ' + err.message, 'error');
  } finally {
    send.disabled = false;
    status.textContent = '';
    input.focus();
  }
});
</script>
</body>
</html>"""

def application(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')
    
    # ── GET / → serve HTML ──────────────────────────
    if path == '/' and method == 'GET':
        start_response('200 OK', [
            ('Content-Type', 'text/html; charset=utf-8'),
        ])
        return [HTML_PAGE.encode('utf-8')]
    
    # ── GET /health ──────────────────────────────────
    if path == '/health' and method == 'GET':
        start_response('200 OK', [
            ('Content-Type', 'application/json; charset=utf-8'),
        ])
        return [json.dumps({"ok": True, "service": "luoshen-ai"}).encode('utf-8')]
    
    # ── POST /chat ───────────────────────────────────
    if path == '/chat' and method == 'POST':
        try:
            content_length = int(environ.get('CONTENT_LENGTH', 0))
            body = environ['wsgi.input'].read(content_length)
            data = json.loads(body)
            user_input = data.get('input', '')
            user_id = data.get('user_id', 'primary')
        except Exception:
            user_input = ''
            user_id = 'primary'
        
        if not user_input:
            start_response('200 OK', [
                ('Content-Type', 'application/json; charset=utf-8'),
            ])
            return [json.dumps({'error': '输入为空'}, ensure_ascii=False).encode('utf-8')]
        
        try:
            reply = living_engine.process_user_input(user_input, user_id=user_id)
            start_response('200 OK', [
                ('Content-Type', 'application/json; charset=utf-8'),
            ])
            return [json.dumps({'reply': reply, 'user_id': user_id}, ensure_ascii=False).encode('utf-8')]
        except Exception as e:
            err_msg = str(e)
            if 'API' in err_msg or 'api' in err_msg or 'key' in err_msg.lower() or '401' in err_msg:
                err_msg = '洛神暂时无法回复，请检查 API key 配置。详情: ' + err_msg
            else:
                err_msg = '洛神暂时无法回复: ' + err_msg
            start_response('200 OK', [
                ('Content-Type', 'application/json; charset=utf-8'),
            ])
            return [json.dumps({'error': err_msg}, ensure_ascii=False).encode('utf-8')]
    
    # ── 404 ──────────────────────────────────────────
    start_response('404 Not Found', [
        ('Content-Type', 'text/plain; charset=utf-8'),
    ])
    return [b'Not Found']
