import { useState, useRef, useEffect } from "react";
import axios from "axios";
import { MessageCircle, X, Send } from "lucide-react";
import { API } from "@/lib/api";

const ChatAssistant = () => {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(null);
  const [setupUrl, setSetupUrl] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (open && aiAvailable === null) {
      axios
        .get(`${API}/chat/status`)
        .then(({ data }) => {
          setAiAvailable(data.available);
          setSetupUrl(data.setup_url);
        })
        .catch(() => setAiAvailable(false));
    }
  }, [open]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: "user", content: text };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const prior = messages.map((m) => ({ role: m.role, content: m.content }));
      const { data } = await axios.post(`${API}/chat`, {
        message: text,
        messages: prior,
      });
      setMessages((m) => [...m, { role: "model", content: data.response || "No response." }]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "model",
          content: err.response?.data?.detail || err.message || "Failed to get response.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 w-14 h-14 bg-amber-500 hover:bg-amber-600 text-white rounded-full shadow-lg flex items-center justify-center transition-colors z-40"
        aria-label="Open AI assistant"
      >
        <MessageCircle className="w-6 h-6" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setOpen(false)}
          />
          <div className="relative w-full max-w-md bg-white shadow-xl flex flex-col h-full animate-slide-in-right">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-amber-500 rounded-lg flex items-center justify-center">
                  <MessageCircle className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h2 className="font-semibold text-slate-900">AI Assistant</h2>
                  <p className="text-xs text-slate-500">Search products, inventory, low stock</p>
                </div>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-200 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {aiAvailable === false && (
                <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-900">
                  <p className="font-medium mb-2">AI assistant not configured</p>
                  <p className="text-amber-800 mb-3">
                    Add LLM_API_KEY to backend/.env to enable the chat assistant, document parsing, and UOM classification.
                  </p>
                  {setupUrl && (
                    <a
                      href={setupUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-amber-700 underline hover:text-amber-900"
                    >
                      Get a free Gemini API key →
                    </a>
                  )}
                </div>
              )}
              {messages.length === 0 && aiAvailable !== false && (
                <p className="text-sm text-slate-500 text-center py-8">
                  Ask about inventory, products, low stock, departments, or vendors.
                </p>
              )}
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                      m.role === "user"
                        ? "bg-amber-500 text-white"
                        : "bg-slate-100 text-slate-800"
                    }`}
                  >
                    <span className="whitespace-pre-wrap">{m.content}</span>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-slate-100 rounded-2xl px-4 py-2.5 text-sm text-slate-500">
                    <span className="inline-flex gap-1">
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </span>
                  </div>
                </div>
              )}
              <div ref={scrollRef} />
            </div>

            <div className="p-4 border-t border-slate-200 bg-white">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  send();
                }}
                className="flex gap-2"
              >
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={aiAvailable === false ? "Configure LLM_API_KEY to enable" : "Ask about inventory..."}
                  className="flex-1 px-4 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"
                  disabled={loading || aiAvailable === false}
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  className="p-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition-colors"
                >
                  <Send className="w-5 h-5" />
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default ChatAssistant;
