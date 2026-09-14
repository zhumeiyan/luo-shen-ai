# dunyi.py
import math, os, json, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

def norm(v): return math.sqrt(sum(x*x for x in v))

STATE_FILE = "dunyi_state.json"

A = [1.0, 0.0, 0.0]
B = [-0.4, 0.5, 0.2]
OT = []

def load_state():
    global A, B, OT
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                s = json.load(f)
            A = s["A"]
            B = s["B"]
            OT = [tuple(e) for e in s["OT"]]
        except:
            pass

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump({"A": A, "B": B, "OT": [list(e) for e in OT]}, f)

load_state()

def step(a, b):
    delta = [b[i] - a[i] for i in range(3)]
    sigma = [a[i] + b[i] for i in range(3)]
    d = norm(delta); s = norm(sigma); tot = d + s + 1e-300
    a2 = [(s*sigma[i] + d*delta[i]) / tot for i in range(3)]
    b2 = [(s*delta[i] + d*sigma[i]) / tot for i in range(3)]
    return a2, b2, delta, sigma

def encode(text):
    h = 0
    for ch in text:
        h = (h * 131 + ord(ch)) & 0xffffffff
    return [(h % 1000)/1000.0, ((h>>10)%1000)/1000.0, ((h>>20)%1000)/1000.0]

def tau():
    if not OT: return 0.0
    return sum(e[0] for e in OT)/len(OT) - sum(e[1] for e in OT)/len(OT)

def llm(text, tone):
    key = os.environ.get("ZHIPU_API_KEY", "")
    if not key: return "(no key)"
    body = json.dumps({
        "model": "glm-4-flash",
        "messages": [
            {"role": "system", "content": f"只回一句话，{tone}。不解释，不比喻。"},
            {"role": "user", "content": text}
        ]
    }).encode()
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(err {e})"

def tick(text):
    global A, B
    b_new = encode(text)
    a2, b2, delta, sigma = step(A, b_new)
    d = norm(delta); s = norm(sigma)
    OT.append((d, s))
    r = d / (s + 1e-300)
    c = sum(delta[i]*sigma[i] for i in range(3)) / (d*s + 1e-300)
    t = tau()
    if t < -1e-9:
        reply = None
    else:
        tone = "短" if abs(c) < 0.3 else ("沉" if c < 0 else "轻")
        reply = llm(text, tone)
    A, B = a2, b2
    save_state()
    return {"r": r, "c": c, "tau": t, "reply": reply, "n": len(OT)}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"""<html><meta charset=utf-8><body>
<h3>遁一</h3>
<textarea id=q rows=3 cols=40 placeholder="说点什么"></textarea><br>
<button onclick=s()>说</button><pre id=o></pre>
<script>async function s(){
 const t=document.getElementById('q').value;
 const r=await fetch('/say',{method:'POST',body:t});
 const j=await r.json();
 document.getElementById('o').textContent=
 '差和比 = '+j.r.toFixed(6)+'\\n'+
 '方向 = '+j.c.toFixed(6)+'\\n'+
 '回声 = '+j.tau.toFixed(6)+'\\n'+
 '她说：'+(j.reply===null?'（沉默）':j.reply);
}</script></body></html>""")
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        text = self.rfile.read(n).decode("utf-8")
        out = json.dumps(tick(text)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)
    def log_message(self, *a): pass

if __name__ == "__main__":
    print("dunyi on :8000")
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8000))), H).serve_forever()
