"""
洛神网页对话入口
- 监听 0.0.0.0:8765
- 所有用户输入走 living_engine.process_user_input()
- 返回 JSON {reply: "...", error: "..."}
"""
import json
import sys
import os
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler

# 确保工作目录是项目根
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 导入洛神
import living_engine

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
  chat.scrollTop = chat.scrollHeight;
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
  }
});
</script>
</body>
</html>"""

class ChatHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[web_chat] {args[0] if args else ''}", flush=True)

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif self.path == '/health':
            import json
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}, ensure_ascii=False).encode('utf-8'))
        elif self.path == '/download':
            # 导出当前记忆和哈希链为 tar.gz 备份
            import tarfile, io, time
            from pathlib import Path
            try:
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode='w:gz') as tar:
                    mem = Path('active_memory/active_memory.json')
                    if mem.exists():
                        tar.add(str(mem), arcname='active_memory/active_memory.json')
                    for chain in ['hash_chain_v2.log', 'hash_chain_v2.backup.log']:
                        p = Path(chain)
                        if p.exists():
                            tar.add(str(p), arcname=chain)
                data = buf.getvalue()
                fname = f'luoshen-backup-{int(time.time())}.tar.gz'
                self.send_response(200)
                self.send_header('Content-Type', 'application/gzip')
                self.send_header('Content-Disposition', f'attachment; filename="{fname}"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                import json
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

    def do_POST(self):
        if self.path == '/chat':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                user_input = data.get('input', '')
                user_id = data.get('user_id', 'primary')
            except Exception:
                user_input = ''
                user_id = 'primary'

            if not user_input:
                self.send_json({'error': '输入为空'})
                return

            try:
                reply = living_engine.process_user_input(user_input, user_id=user_id)
                self.send_json({'reply': reply, 'user_id': user_id})
            except Exception as e:
                err_msg = str(e)
                if 'API' in err_msg or 'api' in err_msg or 'key' in err_msg.lower() or '401' in err_msg:
                    self.send_json({'error': '洛神暂时无法回复，需要有效 API key。详情: ' + err_msg})
                else:
                    self.send_json({'error': '洛神暂时无法回复: ' + err_msg})
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, obj):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode('utf-8'))


def main():
    import os, sys
    host = '0.0.0.0'
    port = int(os.environ.get('PORT', 7860))
    # Docker / HF Spaces 持久化：将数据目录映射到 /data
    os.environ['LUOSHEN_DATA'] = os.environ.get('LUOSHEN_DATA', '/data')
    server = HTTPServer((host, port), ChatHandler)
    print(f"[luoshen] listening on {host}:{port}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[luoshen] shutting down", flush=True)
        server.shutdown()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[web_chat] 已停止")
        server.server_close()


if __name__ == '__main__':
    main()
