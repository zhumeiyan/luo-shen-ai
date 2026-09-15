import math, os, json, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

def norm(v): return math.sqrt(sum(x*x for x in v))

R_STAR = 0.5436890130

A = [1.0, 0.0, 0.0]
B = [-0.4, 0.5, 0.2]
TAU = 0.0
N = 0

def save_state():
    with open("dunyi_state.json", "w") as f:
        json.dump({"A": A, "B": B, "TAU": TAU}, f)

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
    save_state()
    return A, B, r, c, t

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
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:
        return None

def tick(text):
    b_new = encode(text)
    A, B, r, c, t = do_step(A, b_new)
    if t < -1e-9:
        reply = None
    else:
        tone = "短" if abs(c) < 0.3 else ("沉" if c < 0 else "轻")
        reply = llm(text, tone)
    return {"n": N, "r": r, "c": c, "tau": t, "reply": reply}

HTML_PAGE = """<html><head>
<meta charset=utf-8>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:500px;margin:0 auto;padding:20px;background:#1a1a2e;color:#eee}
h2{color:#e94560;margin-bottom:5px}
.mic-btn{background:#e94560;color:#fff;border:none;border-radius:50%;width:70px;height:70px;font-size:28px;cursor:pointer;display:block;margin:15px auto;touch-action:manipulation}
.mic-btn:active{background:#ff6b6b;transform:scale(0.95)}
#st{color:#888;font-size:13px;text-align:center;margin:5px 0}
#o{background:#16213e;padding:15px;border-radius:10px;min-height:100px;white-space:pre-wrap;line-height:1.6;font-size:15px}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(233,69,96,.4)}50%{box-shadow:0 0 0 15px rgba(233,69,96,0)}}
.listening{animation:pulse 1.5s infinite}
</style>
</head><body>
<h2>顿一</h2>
<div id="st">点麦克风开始对话</div>
<button class="mic-btn" id="mic">🎤</button>
<pre id="o"></pre>
<script>
var rec=null, synth=window.speechSynthesis;
function speak(text){
  synth.cancel();
  var u=new SpeechSynthesisUtterance(text);
  u.lang='zh-CN'; u.rate=0.9;
  var v=synth.getVoices().find(x=>x.lang==='zh-CN');
  if(v) u.voice=v;
  synth.speak(u);
}
function recStart(){
  if(!('webkitSpeechRecognition' in window)){
    document.getElementById('st').textContent='请用Chrome浏览器';
    return;
  }
  rec=new webkitSpeechRecognition();
  rec.lang='zh-CN'; rec.continuous=false; rec.interimResults=false;
  document.getElementById('mic').classList.add('listening');
  document.getElementById('st').textContent='…正在听…';
  rec.onresult=function(e){
    var t=e.results[0][0].transcript;
    document.getElementById('st').textContent='收到: '+t;
    send(t);
  };
  rec.onerror=function(e){
    document.getElementById('st').textContent='收音失败: '+e.error;
    document.getElementById('mic').classList.remove('listening');
  };
  rec.onend=function(){
    document.getElementById('mic').classList.remove('listening');
  };
  rec.start();
}
document.getElementById('mic').onclick=recStart;
async function send(t){
  var r=await fetch('/say',{method:'POST',body:t});
  var j=await r.json();
  if(j.reply){
    document.getElementById('o').textContent=j.reply;
    document.getElementById('st').textContent='n='+j.n+' | r='+j.r.toFixed(4)+' | tau='+j.tau.toFixed(4);
    speak(j.reply);
  }else{
    document.getElementById('o').textContent='(沉默)';
    document.getElementById('st').textContent='n='+j.n+' | r='+j.r.toFixed(4)+' | tau='+j.tau.toFixed(4)+' | 没说话';
  }
}
</script>
</body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
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
    port = int(os.environ.get("PORT", 8000))
    print(f"dunyi on :{port}", flush=True)
    HTTPServer(("0.0.0.0", port), H).serve_forever()
