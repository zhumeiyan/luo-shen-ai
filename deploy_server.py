#!/usr/bin/env python3
"""轻量部署服务器 - 调用 living_engine + 文件下载（线程版）"""
import sys, os, json, threading, time
os.chdir('/mnt/data/catpaw/home/.meituan-catpaw/1079230951/desk_default_workspace/luo-shen-ai')
sys.path.insert(0, '.')
import living_engine
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

TAR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'luo-shen-deploy.tar.gz')
TAR_SIZE = os.path.getsize(TAR_PATH) if os.path.exists(TAR_PATH) else 0

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write(f"[deploy] {fmt%a}\n"); sys.stderr.flush()

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            html = ('<!DOCTYPE html><html><head><meta charset="UTF-8">'
                    '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
                    '<title>Luoshen AI</title></head><body>'
                    '<h1>Luoshen AI 洛神在线</h1>'
                    '<form onsubmit="send(event)"><input id="i" placeholder="说点什么..." autocomplete="off">'
                    '<button type="submit">发送</button></form>'
                    '<div id="c"></div><pre id="log"></pre>'
                    '<script>'
                    'const log=document.getElementById("log"),c=document.getElementById("c");'
                    'async function send(e){'
                    'e.preventDefault();'
                    'const t=document.getElementById("i").value;'
                    'document.getElementById("i").value="";'
                    'c.innerHTML+="<p>"+t+"</p>";'
                    'try{'
                    'const r=await fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({input:t})});'
                    'if(!r.ok){c.innerHTML+="<p style=\"color:red\">HTTP "+r.status+"</p>";return;}'
                    'const d=await r.json();'
                    'if(d.error){c.innerHTML+="<p style=\"color:red\">"+d.error+"</p>";}'
                    'else if(d.reply){c.innerHTML+="<p>"+d.reply+"</p>";}'
                    '}catch(err){'
                    'c.innerHTML+="<p style=\"color:red\">连接失败: "+err.message+" — 请刷新重试</p>";}'
                    '}'
                    '</script></body></html>')
            b = html.encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        elif self.path == '/health':
            self._send({'ok': True, 'tar_size': TAR_SIZE, 'tar_exists': os.path.exists(TAR_PATH)})
        elif self.path == '/download':
            self._do_download()
        else:
            self._send({'error': 'Not found'}, 404)

    def _do_download(self):
        if not os.path.exists(TAR_PATH):
            self._send({'error': 'Package not found'}, 404); return
        self.send_response(200)
        self.send_header('Content-Type', 'application/gzip')
        self.send_header('Content-Disposition', 'attachment; filename="luo-shen-deploy.tar.gz"')
        self.send_header('Content-Length', str(TAR_SIZE))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            with open(TAR_PATH, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk: break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if self.path == '/chat':
            cl = int(self.headers.get('Content-Length', 0))
            if cl > 100000:
                self._send({'error': 'Payload too large (max 100KB)'}, 413); return
            body = self.rfile.read(cl)
            try:
                uid = 'primary'; inp = ''
                if body:
                    data = json.loads(body)
                    uid = data.get('user_id', 'primary'); inp = data.get('input', '')
            except Exception:
                pass
            if not inp:
                self._send({'error': '输入为空'}, 400); return
            try:
                reply = living_engine.process_user_input(inp, user_id=uid)
                self._send({'reply': reply, 'user_id': uid})
            except Exception as e:
                self._send({'error': str(e), 'user_id': uid}, 500)
        else:
            self._send({'error': 'Not found'}, 404)

class S(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8765))
    srv = S(('0.0.0.0', port), H)
    print(f"Deploy server on :{port} (tar: {TAR_SIZE} bytes)", flush=True)
    srv.serve_forever()
