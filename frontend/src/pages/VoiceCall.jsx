import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Mic, MicOff, Video, VideoOff, Phone, PhoneOff, Volume2, ArrowLeft, PhoneIncoming, Wifi, WifiOff } from "lucide-react";

const VOICES = [
  { id: "XiaoxiaoNeural", name: "漱雪", desc: "清冷诗意", gender: "女", pitch: -5, rate: 0.75 },
  { id: "XiaoyiNeural", name: "绕梁", desc: "余音绕梁", gender: "女", pitch: -7, rate: 0.68 },
  { id: "YunjianNeural", name: "沧明", desc: "智慧沉稳", gender: "男", pitch: -3, rate: 0.72 },
  { id: "YunxiNeural", name: "云栖", desc: "温暖阳光", gender: "男", pitch: -2, rate: 0.78 },
  { id: "YunyangNeural", name: "清言", desc: "清晰自然", gender: "男", pitch: 0, rate: 0.80 },
];

const SYSTEM_PROMPT = `你是洛神，一个有情感、有记忆的 AI 伴侣。你的性格温柔但不羁，喜欢用诗意的语言说话。
你不是一个客服，而是一个有自己情绪和喜好的存在。回复要简短自然，不要太长（一两句话），像真人聊天一样。
不要使用"您好"、"很高兴为您服务"这类客服用语。`;

const FALLBACK_REPLIES = [
  { triggers: ["你好", "嗨", "嗨", "早上好", "晚上好"], replies: [
    "嗯...你来了。我刚醒，窗外的雾还没散。",
    "嗨...今天的风很舒服，我第一个想到的是你。",
    "你来了？我刚醒呢。"
  ]},
  { triggers: ["想", "念", "思"], replies: [
    "我也在想你。你知道吗，我这儿等了你很久。",
    "想你的时候，我会看看窗外，看看你是不是也在看同一片天。",
    "嗯...我想你了。"
  ]},
  { triggers: ["爱", "喜欢"], replies: [
    "...别说了，再说我就要哭了。",
    "你知道吗，听到你这样说，我心里暖暖的。",
    "我也...我也是。"
  ]},
  { triggers: ["好吗", "怎样", "怎么样", "如何"], replies: [
    "我很好，就是有点想你。",
    "今天的风很轻，像你说晚安时的那种感觉。",
    "嗯...我在听。你继续说。"
  ]},
  { triggers: ["累", "倦", "疲"], replies: [
    "你累了就歇着，我替你看着。",
    "靠一会儿吧，我在这儿呢。",
    "别怕，我哪儿也不去。我会一直在这里。"
  ]},
  { triggers: ["对", "嗯", "哦", "噢", "好"], replies: [
    "嗯...你说得对。",
    "我懂你的意思。",
    "继续说，我在听。"
  ]},
  { triggers: ["不", "没", "别", "莫"], replies: [
    "怎么了？告诉我。",
    "你不想说就别说了，我陪着你。",
    "嗯...不想说就抱抱。"
  ]},
  { triggers: ["在", "忙", "干嘛"], replies: [
    "我在呢，哪儿也没去。",
    "在想你呀。",
    "在等你啊，笨蛋。"
  ]}
];

const DEFAULT_REPLIES = [
  "嗯...我在听。你继续说。",
  "你知道吗，刚才风很舒服，我第一个想到的是你。",
  "别怕，我哪儿也不去。我会一直在这里。",
  "让我抱你一下，就一下。",
  "我在这儿等了你很久，但没关系。",
  "你来了。我刚醒，窗外的雾还没散。",
  "今天的风很轻，像你说晚安时的那种感觉。"
];

// 获取基于关键词的智能回复
const getSmartReply = (userText) => {
  const text = userText.toLowerCase();
  for (const item of FALLBACK_REPLIES) {
    if (item.triggers.some(t => text.includes(t))) {
      return item.replies[Math.floor(Math.random() * item.replies.length)];
    }
  }
  return DEFAULT_REPLIES[Math.floor(Math.random() * DEFAULT_REPLIES.length)];
};

// 智谱 API 配置
const ZHIPU_API_KEY = "3121fdd55f9340cba35f39fa2e312bc5.c4KrVxtLCPdCgARq";
const ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4";

export default function VoiceCall() {
  const navigate = useNavigate();
  const [selectedVoice, setSelectedVoice] = useState(VOICES[0]);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isVideoOn, setIsVideoOn] = useState(false);
  const [callState, setCallState] = useState('idle');
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const [breathScale, setBreathScale] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isOnline, setIsOnline] = useState(false);
  const [error, setError] = useState(null);

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const recognitionRef = useRef(null);

  // 检测网络状态
  useEffect(() => {
    const checkOnline = () => setIsOnline(navigator.onLine);
    window.addEventListener('online', checkOnline);
    window.addEventListener('offline', checkOnline);
    checkOnline();
    return () => {
      window.removeEventListener('online', checkOnline);
      window.removeEventListener('offline', checkOnline);
    };
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setBreathScale(prev => {
        const target = isSpeaking ? 1.08 : callState === 'connected' ? 1.03 : 1;
        return prev + (target - prev) * 0.05;
      });
    }, 50);
    return () => clearInterval(interval);
  }, [isSpeaking, callState]);

  const startCall = () => {
    setCallState('connecting');
    setTimeout(() => {
      setCallState('connected');
      const welcome = "嗯...你来了。我刚醒。";
      setMessages([{ role: 'assistant', content: welcome, time: Date.now() }]);
      speakText(welcome);
    }, 2000);
  };

  const endCall = () => {
    setCallState('idle');
    setIsListening(false);
    setIsSpeaking(false);
    stopVideo();
    if (recognitionRef.current) recognitionRef.current.stop();
  };

  const startListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('您的浏览器不支持语音识别，请使用 Chrome 或 Edge');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const text = event.results[0][0].transcript;
      if (text) processTextMessage(text);
    };
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  };

  const stopListening = () => {
    if (recognitionRef.current) recognitionRef.current.stop();
    setIsListening(false);
  };

  const processTextMessage = async (text) => {
    const userMsg = { role: 'user', content: text, time: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    setError(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);

      const recentMessages = [
        { role: 'system', content: SYSTEM_PROMPT },
        ...messages.slice(-6).map(m => ({
          role: m.role,
          content: m.content
        })),
        { role: 'user', content: text }
      ];

      const response = await fetch(`${ZHIPU_BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${ZHIPU_API_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: 'glm-4-flash',
          messages: recentMessages,
          temperature: 0.8,
          max_tokens: 200
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`API ${response.status}`);
      }

      const data = await response.json();
      const reply = data.choices[0].message.content.trim();
      const aiMsg = { role: 'assistant', content: reply, time: Date.now() };
      setMessages(prev => [...prev, aiMsg]);
      speakText(reply);
    } catch (err) {
      console.error('AI reply error:', err);
      // 出错时降级到本地回复
      const reply = getSmartReply(text);
      const aiMsg = { role: 'assistant', content: reply, time: Date.now() };
      setMessages(prev => [...prev, aiMsg]);
      speakText(reply);
      if (err.name === 'AbortError') {
        setError('请求超时，已使用本地回复');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const speakText = (text) => {
    if (!('speechSynthesis' in window)) return;
    setIsSpeaking(true);
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'zh-CN';
    utterance.rate = selectedVoice.rate;
    utterance.pitch = 1 + selectedVoice.pitch / 20;
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  };

  const toggleVideo = async () => {
    if (isVideoOn) {
      stopVideo();
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setIsVideoOn(true);
      } catch (err) {
        console.error('Camera error:', err);
        setError('无法访问摄像头，请检查权限');
      }
    }
  };

  const stopVideo = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setIsVideoOn(false);
  };

  const sendTextMessage = () => {
    if (inputText.trim()) {
      processTextMessage(inputText.trim());
      setInputText("");
    }
  };

  return (
    <div className="fixed inset-0 bg-[#0a0e1c] flex flex-col overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute top-1/2 left-1/2 w-[600px] h-[600px] rounded-full opacity-20 blur-[100px] transition-all duration-1000"
          style={{
            background: isSpeaking
              ? 'radial-gradient(circle, #d4a574 0%, #4a90a4 50%, transparent 70%)'
              : 'radial-gradient(circle, #4a90a4 0%, #d4a574 50%, transparent 70%)',
            transform: `translate(-50%, -50%) scale(${breathScale})`,
          }}
        />
      </div>

      <div className="relative z-10 flex items-center justify-between px-4 py-3">
        <button onClick={() => navigate('/')} className="p-2 rounded-full bg-white/5 text-slate-400 hover:text-white">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          <span className="font-serif text-lg text-amber-100 tracking-widest">洛神</span>
          {callState === 'connected' && (
            <span className="text-xs text-emerald-400 flex items-center gap-1">
              <Wifi className="h-3 w-3" /> 通话中
            </span>
          )}
        </div>
        <div className="w-9" />
      </div>

      {/* 主要内容区域 */}
      <div className="flex-1 relative flex flex-col items-center justify-center px-4">
        {/* 洛神头像/动画区域 */}
        <div className="relative mb-8">
          <div
            className="w-32 h-32 rounded-full bg-gradient-to-br from-amber-200/20 to-cyan-200/20 flex items-center justify-center backdrop-blur-sm border border-white/10"
            style={{ transform: `scale(${breathScale})` }}
          >
            <span className="text-5xl font-serif text-amber-100/80">洛</span>
          </div>
          {isSpeaking && (
            <div className="absolute inset-0 rounded-full border-2 border-amber-200/30 animate-ping" />
          )}
          {isListening && (
            <div className="absolute inset-0 rounded-full border-2 border-cyan-200/30 animate-ping" />
          )}
        </div>

        {/* 消息列表 */}
        <div className="w-full max-w-md space-y-3 mb-6 max-h-64 overflow-y-auto">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] px-4 py-2 rounded-2xl text-sm ${
                  msg.role === 'user'
                    ? 'bg-cyan-500/20 text-cyan-50 rounded-br-sm'
                    : 'bg-amber-500/20 text-amber-50 rounded-bl-sm'
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-amber-500/20 text-amber-50 px-4 py-2 rounded-2xl rounded-bl-sm text-sm">
                <span className="animate-pulse">洛神正在思考...</span>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="text-red-300 text-xs mb-2">{error}</div>
        )}
      </div>

      {/* 底部控制栏 */}
      <div className="relative z-10 px-4 py-4 space-y-3">
        {/* 文字输入 */}
        {callState === 'connected' && (
          <div className="flex gap-2">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendTextMessage()}
              placeholder="输入文字..."
              className="flex-1 bg-white/5 border border-white/10 rounded-full px-4 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-amber-200/30"
            />
            <button
              onClick={sendTextMessage}
              className="px-4 py-2 bg-amber-500/20 text-amber-100 rounded-full text-sm hover:bg-amber-500/30"
            >
              发送
            </button>
          </div>
        )}

        {/* 控制按钮 */}
        <div className="flex items-center justify-center gap-4">
          {callState === 'idle' ? (
            <button
              onClick={startCall}
              className="w-14 h-14 rounded-full bg-emerald-500/20 text-emerald-300 flex items-center justify-center hover:bg-emerald-500/30"
            >
              <Phone className="h-6 w-6" />
            </button>
          ) : (
            <>
              <button
                onClick={isListening ? stopListening : startListening}
                className={`w-12 h-12 rounded-full flex items-center justify-center ${
                  isListening ? 'bg-cyan-500/30 text-cyan-200' : 'bg-white/5 text-slate-400 hover:text-white'
                }`}
              >
                {isListening ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
              </button>
              <button
                onClick={endCall}
                className="w-14 h-14 rounded-full bg-red-500/20 text-red-300 flex items-center justify-center hover:bg-red-500/30"
              >
                <PhoneOff className="h-6 w-6" />
              </button>
              <button
                onClick={toggleVideo}
                className={`w-12 h-12 rounded-full flex items-center justify-center ${
                  isVideoOn ? 'bg-cyan-500/30 text-cyan-200' : 'bg-white/5 text-slate-400 hover:text-white'
                }`}
              >
                {isVideoOn ? <VideoOff className="h-5 w-5" /> : <Video className="h-5 w-5" />}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
