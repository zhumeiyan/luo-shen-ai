import math, os, json, urllib.request, threading, time, asyncio, edge_tts
from http.server import BaseHTTPRequestHandler, HTTPServer

def norm(v): return math.sqrt(sum(x*x for x in v))

R_STAR = 0.5436890130

A = [1.0, 0.0, 0.0]
B = [-0.4, 0.5, 0.2]
TAU = 0.0
N = 0
lock = threading.Lock()

def load_state():
    global A, B, TAU
    if os.path.exists("dunyi_state.json"):
        with open("dunyi_state.json", "r") as f:
            s = json.load(f)
        A = s["A"]
        B = s["B"]
        TAU = s.get("TAU", 0.0)

def save_ab():
    with open("dunyi_state.json", "w") as f:
        json.dump({"A": A, "B": B, "TAU": TAU}, f)

load_state()

def step(a, b):
    delta = [b[i] - a[i] for i in range(3)]
    sigma = [a[i] + b[i] for i in range(3)]
    d = norm(delta); s = norm(sigma); tot = d + s + 1e-300
    a2 = [(s*sigma[i] + d*delta[i]) / tot for i in range(3)]
    b2 = [(s*delta[i] + d*sigma[i]) / tot for i in range(3)]
    return a2, b2, delta, sigma, d, s

def encode(text):
    h = 0
    for ch in text:
        h = (h * 131 + ord(ch)) & 0xffffffff
    return [(h % 1000)/1000.0, ((h>>10)%1000)/1000.0, ((h>>20)%1000)/1000.0]

def tau_update(d, s, r):
    global TAU
    dev = abs(r - R_STAR)
    lam = min(0.5, max(0.001, dev * 2.0))
    TAU = (1 - lam) * TAU + lam * (d - s)
    return TAU

def do_step(a, b):
    global A, B, N
    a2, b2, delta, sigma, d, s = step(a, b)
    r = d / (s + 1e-300)
    c = sum(delta[i]*sigma[i] for i in range(3)) / (d*s + 1e-300)
    t = tau_update(d, s, r)
    A, B = a2, b2
    N += 1
    save_ab()
    return r, c, t

def background_tick():
    while True:
        time.sleep(1.0)
        with lock:
            do_step(A, B[:])

def tts_generate(text):
    async def _gen():
        comm = edge_tts.Communicate(text, VOICE)
        await comm.save(TMP_MP3)
    asyncio.run(_gen())

HTML_PAGE = """<html><meta charset=utf-8><body>
<h3>遁一</h3>
<button id=mic>🎤 按住说话</button><br>
<textarea id=q rows=3 cols=40 placeholder="说点什么，或按住麦克风"></textarea><br>
<button onclick=s()>发</button><pre id=o></pre>
<script>
var rec = null;
function startRec(){
  if(!('webkitSpeechRecognition' in window)){alert("此浏览器不支持语音，用Chrome");return;}
  rec = new webkitSpeechRecognition();
  rec.lang = "zh-CN";
  rec.onresult = function(e){document.getElementById('q').value = e.results[0][0].transcript;};
  rec.start();
}
document.getElementById('mic').onmousedown = startRec;
document.getElementById('mic').onmouseup = function(){if(rec)rec.stop();};
document.getElementById('mic').ontouchstart = startRec;
document.getElementById('mic').ontouchend = function(){if(rec)rec.stop();};
async function s(){
  const t=document.getElementById('q').value;
  const r=await fetch('/say',{method:'POST',body:t});
  const j=await r.json();
  document.getElementById('o').textContent='n = '+j.n+'\\n差和比 = '+j.r.toFixed(6)+'\\n方向 = '+j.c.toFixed(6)+'\\n回声 = '+j.tau.toFixed(6)+'\\n她说：'+(j.reply===null?'（沉默）':j.reply);
  if(j.reply){
    const a=new Audio('/tts?t='+encodeURIComponent(j.reply));
    a.play();
  }
}
</script></body></html>"""

VOICE = "zh-CN-XiaoxiaoNeural"
TMP_MP3 = "/tmp/dunyi_voice.mp3"

def llm(text, tone):
    key = os.environ.get("ZHIPU_API_KEY", "3121fdd55f9340cba35f39fa2e312bc5.c4KrVxtLCPdCgARq")
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
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]

def tick(text):
    global A, B
    b_new = encode(text)
    with lock:
        r, c, t = do_step(A, b_new)
    if t < -1e-9:
        reply = None
    else:
        tone = "短" if abs(c) < 0.3 else ("沉" if c < 0 else "轻")
        reply = llm(text, tone)
        if reply and reply != "(no key)":
            tts_generate(reply)
    return {"n": N, "r": r, "c": c, "tau": t, "reply": reply}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/tts"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            text = qs.get("t", [""])[0]
            if text:
                tts_generate(text)
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.end_headers()
                with open(TMP_MP3, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
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
    threading.Thread(target=background_tick, daemon=True).start()
    print("dunyi on :8000")
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8000))), H).serve_forever()
