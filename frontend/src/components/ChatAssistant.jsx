import { useState, useRef, useEffect } from "react";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { MessageCircle, X, Send, ChevronDown, ChevronUp } from "lucide-react";
import { API } from "@/lib/api";

const STORAGE_KEY = "sku-ops:chat:v2";

const AGENT_META = {
  inventory: { label: "Inventory", cls: "bg-blue-50 text-blue-700 border border-blue-200" },
  ops:       { label: "Operations", cls: "bg-orange-50 text-orange-700 border border-orange-200" },
  finance:   { label: "Finance",    cls: "bg-emerald-50 text-emerald-700 border border-emerald-200" },
  insights:  { label: "Insights",   cls: "bg-purple-50 text-purple-700 border border-purple-200" },
};

const SUGGESTIONS = [
  { label: "Weekly sales report", prompt: "Write a weekly sales report covering revenue, top-selling products, and outstanding balances" },
  { label: "Inventory deep-dive", prompt: "Do a deep inventory analysis — stock health by department, slow movers, and reorder suggestions" },
  { label: "Stockout forecast", prompt: "Which items are at risk of stocking out in the next 2 weeks based on usage velocity?" },
  { label: "Finance summary", prompt: "Give me a finance overview: P&L summary, outstanding invoices, and who owes us the most" },
  { label: "Low stock alerts", prompt: "List all products running low that need to be reordered soon" },
  { label: "Contractor activity", prompt: "Show recent contractor withdrawals and any pending material requests" },
];

// Markdown component overrides for chat bubble context
const mdComponents = {
  table: ({ children }) => (
    <div className="overflow-x-auto my-2 rounded-lg border border-slate-200 shadow-sm">
      <table className="min-w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-slate-100 border-b border-slate-200">{children}</thead>
  ),
  tbody: ({ children }) => (
    <tbody className="divide-y divide-slate-100">{children}</tbody>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-medium text-slate-500 text-[10px] uppercase tracking-wider whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-1.5 text-slate-700 whitespace-nowrap">{children}</td>
  ),
  p: ({ children }) => (
    <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900">{children}</strong>
  ),
  ul: ({ children }) => (
    <ul className="mb-2 space-y-0.5 pl-4 list-disc">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2 space-y-0.5 pl-4 list-decimal">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="text-slate-700 leading-relaxed">{children}</li>
  ),
  h1: ({ children }) => (
    <h1 className="font-bold text-slate-900 text-sm mb-1.5 mt-3 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="font-semibold text-slate-900 text-sm mb-1 mt-3 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="font-medium text-slate-800 text-xs mb-1 mt-2 first:mt-0">{children}</h3>
  ),
  // pre wraps code blocks; code handles inline vs block
  pre: ({ children }) => (
    <pre className="my-2 p-3 bg-slate-800 rounded-lg overflow-x-auto text-xs text-slate-100 font-mono leading-relaxed">
      {children}
    </pre>
  ),
  code: ({ className, children }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="px-1 py-0.5 bg-slate-200 rounded text-[11px] font-mono text-slate-700">
        {children}
      </code>
    ),
  hr: () => <hr className="my-3 border-slate-200" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-amber-400 pl-3 my-2 text-slate-500 italic text-xs">
      {children}
    </blockquote>
  ),
};

function AgentBubble({ msg, thinkingOpen, onToggleThinking }) {
  const meta = AGENT_META[msg.agent];
  const toolCalls = msg.tool_calls || [];
  const thinking = msg.thinking || [];

  return (
    <div className="flex flex-col gap-1.5 max-w-[92%]">
      {/* Agent badge + tool pills */}
      {(meta || toolCalls.length > 0) && (
        <div className="flex items-center gap-1.5 flex-wrap">
          {meta && (
            <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${meta.cls}`}>
              {meta.label}
            </span>
          )}
          {toolCalls.map((t) => (
            <span
              key={t.name || t}
              className="text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200"
            >
              {t.name || t}
            </span>
          ))}
        </div>
      )}

      {/* Response bubble */}
      <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-800">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {msg.content}
        </ReactMarkdown>
      </div>

      {/* Thinking collapsible */}
      {thinking.length > 0 && (
        <div>
          <button
            onClick={onToggleThinking}
            className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-600 transition-colors"
          >
            {thinkingOpen ? (
              <ChevronUp className="w-3 h-3" />
            ) : (
              <ChevronDown className="w-3 h-3" />
            )}
            {thinkingOpen ? "Hide" : "View"} reasoning
          </button>
          {thinkingOpen && (
            <div className="mt-1.5 p-3 bg-slate-50 border border-slate-200 rounded-xl text-[11px] text-slate-500 font-mono leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap">
              {thinking.join("\n\n---\n\n")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatAssistant() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null")?.messages ?? [];
    } catch {
      return [];
    }
  });
  const [agentHistory, setAgentHistory] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null")?.history ?? null;
    } catch {
      return null;
    }
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(null);
  const [setupUrl, setSetupUrl] = useState(null);
  const [openThinking, setOpenThinking] = useState(new Set());
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ messages, history: agentHistory }));
    } catch {}
  }, [messages, agentHistory]);

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
    if (open) setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  const sendMessage = async (text) => {
    text = (text || input).trim();
    if (!text || loading) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    try {
      const prior = messages.map((m) => ({ role: m.role, content: m.content }));
      const { data } = await axios.post(`${API}/chat`, {
        message: text,
        messages: prior,
        history: agentHistory,
      });
      if (data.history?.length) setAgentHistory(data.history);
      setMessages((m) => [
        ...m,
        {
          role: "model",
          content: data.response || "No response.",
          agent: data.agent,
          tool_calls: data.tool_calls || [],
          thinking: data.thinking || [],
        },
      ]);
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

  const toggleThinking = (idx) => {
    setOpenThinking((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
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
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 bg-amber-500 rounded-lg flex items-center justify-center shrink-0">
                  <MessageCircle className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h2 className="font-semibold text-slate-900 text-sm leading-tight">
                    AI Assistant
                  </h2>
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    Inventory · Operations · Finance · Insights
                  </p>
                </div>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {aiAvailable === false && (
                <div className="rounded-xl bg-amber-50 border border-amber-200 p-4">
                  <p className="font-medium text-sm text-amber-900 mb-1">
                    AI assistant not configured
                  </p>
                  <p className="text-xs text-amber-700 mb-3">
                    Add <code className="px-1 bg-amber-100 rounded font-mono">ANTHROPIC_API_KEY</code> to{" "}
                    <code className="px-1 bg-amber-100 rounded font-mono">backend/.env</code> to enable.
                  </p>
                  {setupUrl && (
                    <a
                      href={setupUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-amber-600 underline hover:text-amber-900"
                    >
                      Get an API key →
                    </a>
                  )}
                </div>
              )}

              {messages.length === 0 && aiAvailable !== false && (
                <div className="flex flex-col items-center py-6 gap-4">
                  <p className="text-xs text-slate-400 text-center">
                    Ask about inventory, finances, operations, or trends
                  </p>
                  <div className="grid grid-cols-2 gap-2 w-full">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s.label}
                        onClick={() => sendMessage(s.prompt)}
                        disabled={loading || aiAvailable === false}
                        className="text-xs text-left px-3 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-amber-50 hover:border-amber-300 text-slate-600 transition-colors leading-snug disabled:opacity-50"
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  {m.role === "user" ? (
                    <div className="max-w-[85%] bg-amber-500 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
                      {m.content}
                    </div>
                  ) : (
                    <AgentBubble
                      msg={m}
                      thinkingOpen={openThinking.has(i)}
                      onToggleThinking={() => toggleThinking(i)}
                    />
                  )}
                </div>
              ))}

              {loading && (
                <div className="flex justify-start">
                  <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3">
                    <span className="inline-flex gap-1 items-center">
                      <span
                        className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
                        style={{ animationDelay: "0ms" }}
                      />
                      <span
                        className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
                        style={{ animationDelay: "150ms" }}
                      />
                      <span
                        className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
                        style={{ animationDelay: "300ms" }}
                      />
                    </span>
                  </div>
                </div>
              )}

              <div ref={scrollRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t border-slate-200 bg-white">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  sendMessage(input);
                }}
                className="flex gap-2"
              >
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    aiAvailable === false
                      ? "Configure ANTHROPIC_API_KEY to enable"
                      : "Ask anything…"
                  }
                  className="flex-1 px-4 py-2.5 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-400 disabled:bg-slate-50 disabled:text-slate-400"
                  disabled={loading || aiAvailable === false}
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim() || aiAvailable === false}
                  className="p-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl transition-colors"
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
}
