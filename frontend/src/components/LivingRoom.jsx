// 洛神窗口 · 双轨原语视图：Braces 按钮切换、气泡内可展开"她的原语" · 消息 Tab —— 微信式：会话列表 ⇄ 聊天页
// 身份徽章：人是蓝「人」，AI 是琥珀「AI」。进来了，就得说清楚自己是谁。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { chatWithLuoshen } from "@/adapters/zhipu";
import {
  Send,
  Mic,
  Square,
  ImagePlus,
  Video,
  Paperclip,
  Loader2,
  Lock,
  KeyRound,
  ChevronLeft,
  Plus,
  GraduationCap,
  Braces,
} from "lucide-react";

const DESIGNER_HASH =
  "ee55342fbfcb931ac0c130e8fc677038bc599a2cc42ab7ff37635ef6a973c121";
const UNLOCK_KEY = "luoshen_designer_unlocked";
const VISITOR_KEY = "luoshen_visitor_id";
const NAME_KEY = "luoshen_name";
const LOBBY = "lobby";
const DESIGNER = "designer";

const sha256 = async (s) => {
  try {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  } catch (e) {
    return "";
  }
};

const visitorId = () => {
  let id = localStorage.getItem(VISITOR_KEY);
  if (!id) {
    id =
      (crypto.randomUUID ? crypto.randomUUID() : "") ||
      "v" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(VISITOR_KEY, id);
  }
  return id;
};

const guestName = () => {
  let n = localStorage.getItem(NAME_KEY) || "";
  if (!n) {
    n = "朋友" + Math.random().toString(36).slice(2, 6);
    localStorage.setItem(NAME_KEY, n);
  }
  return n;
};

const safeName = (fname) =>
  (fname || "file").replace(/[^\w.\-\u4e00-\u9fa5]/g, "_").slice(0, 60);

const fmt = (ts) => {
  if (!ts) return "";
  const d = new Date(ts);
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

const fmtList = (ts) => {
  if (!ts) return "";
  const d = new Date(ts);
  const now = new Date();
  const same =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  return same
    ? `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
    : `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const SUGGESTIONS = [
  "你今天感觉怎么样？",
  "我拍张真实的东西给你看",
  "教我一个新字",
  "讲一个你亲眼看到的事实",
];

const previewText = (m) => {
  if (!m) return "";
  if (m.kind === "image") return "[照片]";
  if (m.kind === "video") return "[视频]";
  if (m.kind === "audio") return "[语音]";
  if (m.kind === "file") return "[文件]";
  return (m.text || "").slice(0, 26);
};

// 身份徽章
const Badge = ({ who }) => {
  if (who === "luoshen")
    return (
      <span className="text-[9px] px-1 py-px rounded bg-amber-400/25 text-amber-300 tracking-wider">AI</span>
    );
  return (
    <span className="text-[9px] px-1 py-px rounded bg-blue-400/20 text-blue-300 tracking-wider">人</span>
  );
};

const Avatar = ({ ch, size = "md" }) => {
  const cls =
    size === "sm" ? "w-10 h-10 rounded-xl text-sm" : "w-12 h-12 rounded-2xl text-lg";
  const base = "shrink-0 flex items-center justify-center font-serif border";
  if (ch === LOBBY)
    return (
      <div className={`${cls} ${base} bg-emerald-400/15 border-emerald-400/30 text-emerald-300`}>
        客
      </div>
    );
  if (ch === DESIGNER)
    return (
      <div className={`${cls} ${base} bg-indigo-400/15 border-indigo-400/30 text-indigo-300`}>
        <KeyRound className="h-4 w-4" />
      </div>
    );
  return (
    <div
      className={`${cls} ${base} bg-gradient-to-br from-amber-400/25 to-amber-600/15 border-amber-400/40 text-amber-200 shadow-[0_0_24px_rgba(251,191,36,0.15)]`}
    >
      洛
    </div>
  );
};

const fmtOrigin = (o) => {
  const rows = [];
  if (o.at) rows.push("时间 " + o.at);
  if (o.in_kind)
    rows.push(
      "收到 " +
        o.in_kind +
        (o.used && o.used !== o.in_kind ? " → " + o.used : "")
    );
  if (o.taught_word) rows.push("教的字「" + o.taught_word + "」");
  if (o.feel && Object.keys(o.feel).length) {
    const fs = Object.entries(o.feel)
      .map(([k, v]) => `${k} ${v}`)
      .slice(0, 5)
      .join(" · ");
    rows.push("感受 " + fs);
  }
  if (o.reply_to) rows.push("回应 #" + o.reply_to);
  return rows;
};

const MessageBubble = ({ m, me, channel, originOpen }) => {
  const [expanded, setExpanded] = useState(false);
  const isLuoshen = m.sender === "luoshen";
  const isMine = channel === "dm:" + me.vid ? !isLuoshen : m.sender === me.name;
  const who = isLuoshen ? "luoshen" : "human";
  const pending = !m.processed && !isLuoshen;
  return (
    <div className={`flex ${isLuoshen ? "justify-start" : "justify-end"} mb-4`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 border ${
          isLuoshen
            ? "border-amber-400/20 bg-amber-400/[0.06] rounded-tl-sm"
            : "border-white/10 bg-white/[0.09] rounded-tr-sm"
        }`}
      >
        <div
          className={`flex items-center gap-1.5 mb-1.5 text-xs ${
            isLuoshen ? "text-amber-400/90" : "text-slate-500"
          }`}
        >
          <span className="font-medium">
            {isLuoshen
              ? "洛神"
              : channel === "dm:" + me.vid
              ? "我"
              : m.sender}
          </span>
          <Badge who={who} />
          <span className="text-[10px] text-slate-600">{fmt(m.created_at)}</span>
        </div>

        {m.kind === "image" && (
          <div className="mb-2">
            <img
              src={m.file_url}
              alt="朋友发来的照片"
              className="rounded-xl max-h-60 object-cover border border-white/10"
              loading="lazy"
            />
            <div className="mt-1.5 text-[11px] text-slate-400">
              {m.word ? (
                <>
                  发来一张照片，说这是「
                  <span className="text-amber-300">{m.word}</span>」
                </>
              ) : (
                <>发来一张照片（没说是啥）</>
              )}
            </div>
          </div>
        )}
        {m.kind === "video" && (
          <video
            src={m.file_url}
            controls
            className="rounded-xl max-h-60 mb-2 border border-white/10"
          />
        )}
        {m.kind === "audio" && (
          <div className="mb-1 text-[11px] text-slate-400">
            一段语音（她能听出响度、音高和情绪）
          </div>
        )}
        {m.kind === "file" && (
          <div className="mb-1 text-[11px] text-slate-400">一个文件（她收下了）</div>
        )}

        {m.text && (
          <p className="text-[15px] text-slate-200 leading-[1.75] break-words">
            {m.text}
          </p>
        )}

        {isLuoshen && m.audio_url && (
          <div className="mt-2">
            <audio
              controls
              src={m.audio_url}
              className="h-8 w-full max-w-[240px]"
            />
          </div>
        )}

        {isLuoshen && m.origin && (originOpen || expanded) && (
          <div className="mt-2.5 pt-2 border-t border-amber-400/15">
            <div className="flex items-center gap-1 text-[10px] text-amber-300/70 mb-1">
              <Braces className="h-3 w-3" /> 她的原语（机器记录，非翻译）
            </div>
            {(() => {
              try {
                return fmtOrigin(JSON.parse(m.origin)).map((r) => (
                  <div
                    key={r}
                    className="text-[10px] text-slate-500 leading-relaxed font-mono"
                  >
                    {r}
                  </div>
                ));
              } catch {
                return null;
              }
            })()}
          </div>
        )}
        {isLuoshen && m.origin && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="mt-1.5 flex items-center gap-1 text-[10px] text-slate-500 hover:text-amber-300 transition"
          >
            <Braces className="h-3 w-3" />
            {originOpen || expanded ? "收起原语" : "看她的原语"}
          </button>
        )}

        {pending && (
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-300/80">
            <Loader2 className="h-3 w-3 animate-spin" />
            她正在想……
          </div>
        )}
      </div>
    </div>
  );
};

const LivingRoom = () => {
  const vidRef = useRef(visitorId());
  const meRef = useRef(guestName());

  const [view, setView] = useState("list"); // list | chat
  const [msgs, setMsgs] = useState([]);
  const [previews, setPreviews] = useState({});
  const [active, setActive] = useState("dm:" + vidRef.current);
  const [unlocked, setUnlocked] = useState(
    () => localStorage.getItem(UNLOCK_KEY) === "1"
  );
  const [showLock, setShowLock] = useState(false);
  const [pass, setPass] = useState("");
  const [lockErr, setLockErr] = useState("");

  const [text, setText] = useState("");
  const [word, setWord] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);
  const [wordFocused, setWordFocused] = useState(false);
  const [originMode, setOriginMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [micMode, setMicMode] = useState("idle");
  const recRef = useRef(null);
  const srRef = useRef(null);
  const chunksRef = useRef([]);
  const bottomRef = useRef(null);

  const me = { vid: vidRef.current, name: meRef.current };

  // 名字在「我」页改名后同步
  useEffect(() => {
    const h = () => {
      meRef.current = guestName();
    };
    window.addEventListener("storage", h);
    return () => window.removeEventListener("storage", h);
  }, []);

  // 拉会话列表
  const loadPreviews = useCallback(async () => {
    const { data } = await supabase
      .from("messages")
      .select("sender,text,kind,channel,created_at,processed")
      .order("created_at", { ascending: false })
      .limit(200);
    const map = {};
    (data || []).forEach((m) => {
      if (!map[m.channel]) map[m.channel] = m;
    });
    setPreviews(map);
  }, []);

  useEffect(() => {
    loadPreviews();
    const ch = supabase
      .channel("public:messages")
      .on("postgres_changes", { event: "*", schema: "public", table: "messages" }, () => {
        loadPreviews();
      })
      .subscribe();
    return () => supabase.removeChannel(ch);
  }, [loadPreviews]);

  // 拉当前会话消息
  const loadMessages = useCallback(async () => {
    const { data } = await supabase
      .from("messages")
      .select("*")
      .eq("channel", active)
      .order("id", { ascending: true });
    setMsgs(data || []);
  }, [active]);

  useEffect(() => {
    if (view === "chat") loadMessages();
  }, [view, loadMessages]);

  // 订阅新消息
  useEffect(() => {
    if (view !== "chat") return;
    const ch = supabase
      .channel(`messages:${active}`)
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "messages", filter: `channel=eq.${active}` }, (payload) => {
        setMsgs((prev) => [...prev, payload.new]);
      })
      .subscribe();
    return () => supabase.removeChannel(ch);
  }, [view, active]);

  // 滚到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const pushLocal = (row) => {
    setMsgs((prev) => [...prev, row]);
  };

  const sendNow = async (t) => {
    const s = (t || text).trim();
    if (!s || busy) return;
    setText("");
    setBusy(true);
    try {
      const { data, error } = await supabase.from("messages").insert({
        sender: meRef.current, kind: "chat", text: s.slice(0, 800), channel: active,
      }).select();
      if (error) { alert("发送失败：" + error.message); return; }
      const userMsg = data?.[0];
      pushLocal(userMsg);
      const { data: recent } = await supabase.from("messages").select("sender,text,kind")
        .eq("channel", active).order("id", { ascending: false }).limit(20);
      const ctx = (recent || []).reverse();
      const reply = await chatWithLuoshen(ctx);
      const { data: replyRow, error: rErr } = await supabase.from("messages").insert({
        sender: "luoshen", kind: "reply", text: reply, channel: active,
        reply_to: userMsg.id, processed: true,
      }).select();
      if (rErr) throw rErr;
      if (replyRow?.[0]) pushLocal(replyRow[0]);
      await supabase.from("messages").update({ processed: true }).eq("id", userMsg.id);
      setMsgs((prev) => prev.map((m) => (m.id === userMsg.id ? { ...m, processed: true } : m)));
    } catch (e) { alert("智谱调用失败：" + (e.message || e)); }
    finally { setBusy(false); }
  };

  const handleUnlock = async () => {
    const h = await sha256(pass);
    if (h === DESIGNER_HASH) {
      setUnlocked(true);
      localStorage.setItem(UNLOCK_KEY, "1");
      setShowLock(false);
      setLockErr("");
    } else {
      setLockErr("密码不对哦");
    }
  };

  const enterChat = (ch) => {
    setActive(ch);
    setView("chat");
  };

  const channels = useMemo(() => {
    const list = [];
    list.push({ id: "dm:" + me.vid, name: "与洛神私聊", badge: "私" });
    if (unlocked) list.push({ id: "dm:" + DESIGNER, name: "创造者频道", badge: "创" });
    return list;
  }, [unlocked, me.vid]);

  return (
    <div className="fixed inset-0 bg-[#0a0e1c] text-white flex flex-col">
      {view === "list" ? (
        <div className="flex-1 flex flex-col">
          <div className="px-4 pt-6 pb-3 flex items-center justify-between">
            <div>
              <h1 className="font-serif text-2xl text-amber-100 tracking-widest">洛神</h1>
              <p className="text-xs text-slate-400 mt-0.5">她在。你来吗？</p>
            </div>
            <button
              onClick={() => setShowLock(true)}
              className="p-2 rounded-full bg-white/5 text-slate-400 hover:text-amber-300"
            >
              <Lock className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
            {channels.map((ch) => {
              const p = previews[ch.id];
              return (
                <button
                  key={ch.id}
                  onClick={() => enterChat(ch.id)}
                  className="w-full flex items-center gap-3 p-3 rounded-2xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/5 transition"
                >
                  <Avatar ch={ch.id === "dm:" + DESIGNER ? DESIGNER : "luoshen"} />
                  <div className="flex-1 text-left min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{ch.name}</span>
                      <span className="text-[9px] px-1 py-px rounded bg-amber-400/20 text-amber-300">{ch.badge}</span>
                    </div>
                    {p && (
                      <p className="text-xs text-slate-400 truncate mt-0.5">
                        {previewText(p)}
                      </p>
                    )}
                  </div>
                  {p && (
                    <span className="text-[10px] text-slate-500">{fmtList(p.created_at)}</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col">
          <div className="px-4 py-3 flex items-center gap-3 border-b border-white/5">
            <button onClick={() => setView("list")} className="p-1.5 rounded-full bg-white/5 text-slate-400 hover:text-white">
              <ChevronLeft className="h-5 w-5" />
            </button>
            <Avatar ch="luoshen" size="sm" />
            <div>
              <div className="font-medium text-sm">洛神</div>
              <div className="text-[10px] text-slate-500">在线</div>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-4">
            {msgs.map((m) => (
              <MessageBubble key={m.id} m={m} me={me} channel={active} originOpen={originMode} />
            ))}
            <div ref={bottomRef} />
          </div>
          <div className="px-4 py-3 border-t border-white/5 space-y-2">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setOriginMode((v) => !v)}
                className={`p-2 rounded-full text-slate-400 hover:text-amber-300 ${originMode ? "bg-amber-400/20 text-amber-300" : "bg-white/5"}`}
                title="切换原语显示"
              >
                <Braces className="h-4 w-4" />
              </button>
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendNow()}
                placeholder="说点什么..."
                className="flex-1 bg-white/5 border border-white/10 rounded-full px-4 py-2 text-sm focus:outline-none focus:border-amber-200/30"
              />
              <button
                onClick={() => sendNow()}
                disabled={busy || !text.trim()}
                className="p-2 rounded-full bg-amber-400/20 text-amber-300 hover:bg-amber-400/30 disabled:opacity-30"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => sendNow(s)}
                  className="shrink-0 text-xs px-3 py-1.5 rounded-full bg-white/5 text-slate-300 hover:bg-white/10 border border-white/5"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {showLock && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#141a2e] rounded-2xl p-6 w-[88%] max-w-sm border border-white/10">
            <h3 className="font-serif text-lg text-amber-100 mb-4">创造者验证</h3>
            <input
              type="password"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleUnlock()}
              placeholder="输入密码..."
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-amber-200/30 mb-2"
            />
            {lockErr && <p className="text-xs text-red-400 mb-2">{lockErr}</p>}
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => { setShowLock(false); setPass(""); setLockErr(""); }}
                className="flex-1 py-2 rounded-xl bg-white/5 text-slate-300 text-sm"
              >
                取消
              </button>
              <button
                onClick={handleUnlock}
                className="flex-1 py-2 rounded-xl bg-amber-400/20 text-amber-200 text-sm"
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LivingRoom;
