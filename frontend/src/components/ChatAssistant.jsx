import { useState, useRef, useEffect } from "react";
import { useLocation } from "react-router-dom";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { MessageCircle, X, Send, ChevronDown, ChevronUp, Zap, Brain, Plus } from "lucide-react";
import { API } from "@/lib/api";

const STORAGE_KEY = "sku-ops:chat:v3";

const AGENT_META = {
  general:   { label: "General",    cls: "bg-amber-50 text-amber-700 border border-amber-200" },
  inventory: { label: "Inventory",  cls: "bg-blue-50 text-blue-700 border border-blue-200" },
  ops:       { label: "Operations", cls: "bg-orange-50 text-orange-700 border border-orange-200" },
  finance:   { label: "Finance",    cls: "bg-emerald-50 text-emerald-700 border border-emerald-200" },
  insights:  { label: "Insights",   cls: "bg-purple-50 text-purple-700 border border-purple-200" },
};

function agentTypeFromPath(pathname) {
  if (pathname === "/" || pathname.startsWith("/dashboard")) return "general";
  if (["/inventory", "/vendors", "/departments", "/import", "/purchase-orders"].some((p) => pathname.startsWith(p))) return "inventory";
  if (["/pos", "/pending-requests", "/contractors"].some((p) => pathname.startsWith(p))) return "ops";
  if (["/financials", "/invoices"].some((p) => pathname.startsWith(p))) return "finance";
  if (pathname.startsWith("/reports")) return "insights";
  return "general";
}

const AGENT_SUGGESTIONS = {
  general: [
    { label: "Store overview", prompt: "Give me a full store overview: inventory health, this week's revenue, outstanding balances, and stockout risks" },
    { label: "Weekly summary", prompt: "Write a weekly summary covering sales, top products, outstanding payments, and any low stock alerts" },
    { label: "What needs attention?", prompt: "What needs my attention today? Any critical stock, pending requests, or outstanding invoices?" },
    { label: "Stockout forecast", prompt: "Which items are at risk of stocking out in the next 2 weeks?" },
  ],
  inventory: [
    { label: "Low stock alerts", prompt: "List all products running low that need to be reordered soon" },
    { label: "Inventory health", prompt: "Do a full inventory analysis — stock health by department, slow movers, and reorder suggestions" },
    { label: "Reorder priority", prompt: "What should we reorder urgently? Rank by days until stockout" },
    { label: "Slow movers", prompt: "Which products have stock on hand but haven't moved in 30 days?" },
  ],
  ops: [
    { label: "Recent activity", prompt: "Show me all withdrawals from the last 7 days" },
    { label: "Pending requests", prompt: "List all pending material requests awaiting approval" },
    { label: "Contractor summary", prompt: "Give me a summary of contractor activity this week — who's been active and any unpaid jobs" },
    { label: "Unpaid jobs", prompt: "Which jobs have outstanding unpaid balances?" },
  ],
  finance: [
    { label: "Finance overview", prompt: "Give me a finance overview: P&L summary, outstanding invoices, and who owes us the most" },
    { label: "Outstanding balances", prompt: "Who has outstanding unpaid balances and how much do they owe?" },
    { label: "This month's P&L", prompt: "Show me the profit and loss for the last 30 days including gross margin" },
    { label: "Weekly sales report", prompt: "Write a weekly sales report covering revenue, top-selling products, and outstanding balances" },
  ],
  insights: [
    { label: "Top products", prompt: "What are the top 10 products by revenue over the last 30 days?" },
    { label: "Stockout forecast", prompt: "Which items are at risk of stocking out in the next 2 weeks based on usage velocity?" },
    { label: "Department trends", prompt: "Which departments are most active and which are underperforming?" },
    { label: "Usage velocity", prompt: "What are the fastest-moving products right now?" },
  ],
};

const AGENT_PLACEHOLDER = {
  general:   "Ask about inventory, finance, operations, or trends…",
  inventory: "Ask about products, stock levels, reorders…",
  ops:       "Ask about withdrawals, contractors, material requests…",
  finance:   "Ask about invoices, revenue, P&L, balances…",
  insights:  "Ask about trends, top products, stockout risks…",
};

const mdComponents = {
  table: ({ children }) => (
    <div className="overflow-x-auto my-2 rounded-lg border border-slate-200 shadow-sm">
      <table className="min-w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-100 border-b border-slate-200">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-slate-100">{children}</tbody>,
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-medium text-slate-500 text-[10px] uppercase tracking-wider whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="px-3 py-1.5 text-slate-700 whitespace-nowrap">{children}</td>,
  p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  ul: ({ children }) => <ul className="mb-2 space-y-0.5 pl-4 list-disc">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 space-y-0.5 pl-4 list-decimal">{children}</ol>,
  li: ({ children }) => <li className="text-slate-700 leading-relaxed">{children}</li>,
  h1: ({ children }) => <h1 className="font-bold text-slate-900 text-sm mb-1.5 mt-3 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="font-semibold text-slate-900 text-sm mb-1 mt-3 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="font-medium text-slate-800 text-xs mb-1 mt-2 first:mt-0">{children}</h3>,
  pre: ({ children }) => (
    <pre className="my-2 p-3 bg-slate-800 rounded-lg overflow-x-auto text-xs text-slate-100 font-mono leading-relaxed">
      {children}
    </pre>
  ),
  code: ({ className, children }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="px-1 py-0.5 bg-slate-200 rounded text-[11px] font-mono text-slate-700">{children}</code>
    ),
  hr: () => <hr className="my-3 border-slate-200" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-amber-400 pl-3 my-2 text-slate-500 italic text-xs">{children}</blockquote>
  ),
};

function AgentBubble({ msg, thinkingOpen, onToggleThinking }) {
  const meta = AGENT_META[msg.agent];
  const toolCalls = msg.tool_calls || [];
  const thinking = msg.thinking || [];

  return (
    <div className="flex flex-col gap-1.5 max-w-[92%]">
      {(meta || toolCalls.length > 0) && (
        <div className="flex items-center gap-1.5 flex-wrap">
          {meta && (
            <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${meta.cls}`}>
              {meta.label}
            </span>
          )}
          {toolCalls.map((t, i) => (
            <span key={t.tool || i} className="text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
              {t.tool}
            </span>
          ))}
        </div>
      )}
      <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-800">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {msg.content}
        </ReactMarkdown>
      </div>
      {thinking.length > 0 && (
        <div>
          <button
            onClick={onToggleThinking}
            className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-600 transition-colors"
          >
            {thinkingOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
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
  const location = useLocation();
  const agentType = agentTypeFromPath(location.pathname);
  const agentMeta = AGENT_META[agentType];

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null")?.messages ?? []; }
    catch { return []; }
  });
  const [sessionId, setSessionId] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null")?.sessionId ?? null; }
    catch { return null; }
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(null);
  const [setupUrl, setSetupUrl] = useState(null);
  const [openThinking, setOpenThinking] = useState(new Set());
  const [sessionCost, setSessionCost] = useState(0);
  const [mode, setMode] = useState("fast");
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const prevAgentType = useRef(agentType);

  const clearSession = (sid) => {
    if (sid) axios.delete(`${API}/chat/sessions/${sid}`).catch(() => {});
  };

  // Clear session when navigating between sections
  useEffect(() => {
    if (prevAgentType.current !== agentType) {
      clearSession(sessionId);
      setMessages([]);
      setSessionId(null);
      setSessionCost(0);
      prevAgentType.current = agentType;
    }
  }, [agentType]);

  const startNewChat = () => {
    clearSession(sessionId);
    setMessages([]);
    setSessionId(null);
    setSessionCost(0);
  };

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ messages, sessionId }));
    } catch {}
  }, [messages, sessionId]);

  useEffect(() => {
    if (open && aiAvailable === null) {
      axios.get(`${API}/chat/status`)
        .then(({ data }) => { setAiAvailable(data.available); setSetupUrl(data.setup_url); })
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
      const { data } = await axios.post(`${API}/chat`, {
        message: text,
        session_id: sessionId,
        mode,
        agent_type: agentType,
      });
      if (data.session_id) setSessionId(data.session_id);
      if (data.usage?.session_cost_usd != null) setSessionCost(data.usage.session_cost_usd);
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
        { role: "model", content: err.response?.data?.detail || err.message || "Failed to get response." },
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

  const suggestions = AGENT_SUGGESTIONS[agentType] || AGENT_SUGGESTIONS.general;

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
          <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} />
          <div className="relative w-full max-w-md bg-white shadow-xl flex flex-col h-full animate-slide-in-right">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 bg-amber-500 rounded-lg flex items-center justify-center shrink-0">
                  <MessageCircle className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h2 className="font-semibold text-slate-900 text-sm leading-tight">
                    {agentMeta.label} Assistant
                  </h2>
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-medium ${agentMeta.cls}`}>
                      {agentMeta.label}
                    </span>
                    {sessionCost > 0 && (
                      <span className="ml-2 text-slate-300">· ${sessionCost.toFixed(4)} session</span>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {messages.length > 0 && (
                  <button
                    type="button"
                    onClick={startNewChat}
                    title="New chat"
                    className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                )}
                <div className="flex rounded-lg border border-slate-200 bg-white p-0.5" role="group">
                  <button
                    type="button"
                    onClick={() => setMode("fast")}
                    className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium transition-colors ${
                      mode === "fast"
                        ? "bg-amber-100 text-amber-800 border border-amber-200"
                        : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                    }`}
                    title="Fast: quick answers, lower cost"
                  >
                    <Zap className="w-3 h-3" />
                    Fast
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode("deep")}
                    className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium transition-colors ${
                      mode === "deep"
                        ? "bg-slate-800 text-white border border-slate-700"
                        : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                    }`}
                    title="Deep: more reasoning, higher cost"
                  >
                    <Brain className="w-3 h-3" />
                    Deep
                  </button>
                </div>
                <button
                  onClick={() => setOpen(false)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {aiAvailable === false && (
                <div className="rounded-xl bg-amber-50 border border-amber-200 p-4">
                  <p className="font-medium text-sm text-amber-900 mb-1">AI assistant not configured</p>
                  <p className="text-xs text-amber-700 mb-3">
                    Add <code className="px-1 bg-amber-100 rounded font-mono">ANTHROPIC_API_KEY</code> to{" "}
                    <code className="px-1 bg-amber-100 rounded font-mono">backend/.env</code> to enable.
                  </p>
                  {setupUrl && (
                    <a href={setupUrl} target="_blank" rel="noopener noreferrer" className="text-xs text-amber-600 underline hover:text-amber-900">
                      Get an API key →
                    </a>
                  )}
                </div>
              )}

              {messages.length === 0 && aiAvailable !== false && (
                <div className="flex flex-col items-center py-6 gap-4">
                  <p className="text-xs text-slate-400 text-center">{AGENT_PLACEHOLDER[agentType]}</p>
                  <div className="grid grid-cols-2 gap-2 w-full">
                    {suggestions.map((s) => (
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
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  {m.role === "user" ? (
                    <div className="max-w-[85%] bg-amber-500 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
                      {m.content}
                    </div>
                  ) : (
                    <AgentBubble msg={m} thinkingOpen={openThinking.has(i)} onToggleThinking={() => toggleThinking(i)} />
                  )}
                </div>
              ))}

              {loading && (
                <div className="flex justify-start">
                  <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3">
                    <span className="inline-flex gap-1 items-center">
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </span>
                  </div>
                </div>
              )}

              <div ref={scrollRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t border-slate-200 bg-white">
              <form onSubmit={(e) => { e.preventDefault(); sendMessage(input); }} className="flex gap-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={aiAvailable === false ? "Configure ANTHROPIC_API_KEY to enable" : AGENT_PLACEHOLDER[agentType]}
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
