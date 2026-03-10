import { useState, useRef, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  X,
  Send,
  ChevronDown,
  ChevronUp,
  Plus,
  Sparkles,
  Square,
  Wifi,
  WifiOff,
  Wrench,
} from "lucide-react";
import api from "@/lib/api-client";
import { useChatSocket } from "@/hooks/useChatSocket";

const STORAGE_KEY = "sku-ops:chat:v4";

const AGENT_META = {
  inventory: {
    label: "Inventory",
    cls: "bg-info/10 text-info border border-info/30",
  },
  ops: {
    label: "Operations",
    cls: "bg-warning/10 text-category-5 border border-warning/30",
  },
  finance: {
    label: "Finance",
    cls: "bg-success/10 text-success border border-success/30",
  },
  unified: {
    label: "Assistant",
    cls: "bg-accent/10 text-accent border border-accent/30",
  },
  system: {
    label: "Assistant",
    cls: "bg-accent/10 text-accent border border-accent/30",
  },
  lookup: {
    label: "Lookup",
    cls: "bg-muted text-muted-foreground border border-border",
  },
  dag: {
    label: "Report",
    cls: "bg-category-4/10 text-category-4 border border-category-4/30",
  },
};

function agentTypeFromPath(pathname) {
  if (
    [
      "/inventory",
      "/vendors",
      "/departments",
      "/import",
      "/purchase-orders",
    ].some((p) => pathname.startsWith(p))
  )
    return "inventory";
  if (
    ["/pos", "/pending-requests", "/contractors"].some((p) =>
      pathname.startsWith(p),
    )
  )
    return "ops";
  if (
    ["/invoices", "/payments", "/billing-entities"].some((p) =>
      pathname.startsWith(p),
    )
  )
    return "finance";
  return "auto";
}

const AGENT_SUGGESTIONS = {
  auto: [
    {
      label: "Store overview",
      prompt:
        "Give me a full store overview: inventory health, this week's revenue, outstanding balances, and stockout risks",
    },
    {
      label: "Weekly summary",
      prompt:
        "Write a weekly summary covering sales, top products, outstanding payments, and any low stock alerts",
    },
    {
      label: "What needs attention?",
      prompt:
        "What needs my attention today? Any critical stock, pending requests, or outstanding invoices?",
    },
    {
      label: "Stockout forecast",
      prompt: "Which items are at risk of stocking out in the next 2 weeks?",
    },
  ],
  inventory: [
    {
      label: "Low stock alerts",
      prompt: "List all products running low that need to be reordered soon",
    },
    {
      label: "Inventory health",
      prompt:
        "Do a full inventory analysis — stock health by department, slow movers, and reorder suggestions",
    },
    {
      label: "Reorder priority",
      prompt: "What should we reorder urgently? Rank by days until stockout",
    },
    {
      label: "Slow movers",
      prompt: "Which products have stock on hand but haven't moved in 30 days?",
    },
  ],
  ops: [
    {
      label: "Recent activity",
      prompt: "Show me all withdrawals from the last 7 days",
    },
    {
      label: "Pending requests",
      prompt: "List all pending material requests awaiting approval",
    },
    {
      label: "Contractor summary",
      prompt:
        "Give me a summary of contractor activity this week — who's been active and any unpaid jobs",
    },
    {
      label: "Unpaid jobs",
      prompt: "Which jobs have outstanding unpaid balances?",
    },
  ],
  finance: [
    {
      label: "Finance overview",
      prompt:
        "Give me a finance overview: P&L summary, outstanding invoices, and who owes us the most",
    },
    {
      label: "Outstanding balances",
      prompt: "Who has outstanding unpaid balances and how much do they owe?",
    },
    {
      label: "This month's P&L",
      prompt:
        "Show me the profit and loss for the last 30 days including gross margin",
    },
    {
      label: "Weekly sales report",
      prompt:
        "Write a weekly sales report covering revenue, top-selling products, and outstanding balances",
    },
  ],
};

const AGENT_PLACEHOLDER = {
  auto: "Ask about inventory, finance, or operations…",
  inventory: "Ask about products, stock levels, reorders…",
  ops: "Ask about withdrawals, contractors, requests…",
  finance: "Ask about invoices, revenue, P&L, balances…",
};

function isNumeric(text) {
  if (!text) return false;
  const s = String(text).trim();
  return /^[$%]?[\d,]+\.?\d*[%]?$/.test(s) || /^-?\$?[\d,]+\.?\d*$/.test(s);
}

const mdComponents = {
  table: ({ children }) => (
    <div className="overflow-x-auto my-2.5 rounded-lg border border-border/60">
      <table className="min-w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-muted/60 border-b border-border/60">{children}</thead>
  ),
  tbody: ({ children }) => (
    <tbody className="divide-y divide-border/30 [&>tr:nth-child(even)]:bg-muted/20">
      {children}
    </tbody>
  ),
  th: ({ children }) => (
    <th className="px-2.5 py-1.5 text-left font-medium text-muted-foreground text-[10px] uppercase tracking-wider whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => {
    const numeric = isNumeric(children);
    return (
      <td
        className={`px-2.5 py-1.5 whitespace-nowrap ${numeric ? "text-right font-mono tabular-nums text-foreground" : "text-foreground/90"}`}
      >
        {children}
      </td>
    );
  },
  p: ({ children }) => (
    <p className="mb-1.5 last:mb-0 leading-relaxed text-[13px]">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-foreground">{children}</strong>
  ),
  ul: ({ children }) => (
    <ul className="mb-1.5 space-y-0.5 pl-4 list-disc marker:text-muted-foreground">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-1.5 space-y-0.5 pl-4 list-decimal marker:text-muted-foreground">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="text-foreground/90 leading-relaxed text-[13px]">
      {children}
    </li>
  ),
  h1: ({ children }) => (
    <h1 className="font-bold text-foreground text-sm mb-1 mt-2.5 first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="font-semibold text-foreground text-[13px] mb-1 mt-2.5 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="font-medium text-foreground text-xs mb-0.5 mt-2 first:mt-0">
      {children}
    </h3>
  ),
  pre: ({ children }) => (
    <pre className="my-2 p-2.5 bg-sidebar/80 rounded-lg overflow-x-auto text-[11px] text-foreground/80 font-mono leading-relaxed border border-border/40">
      {children}
    </pre>
  ),
  code: ({ className, children }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="px-1 py-0.5 bg-muted/80 rounded text-[11px] font-mono text-accent">
        {children}
      </code>
    ),
  hr: () => <hr className="my-2.5 border-border/40" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-accent/60 pl-3 my-2 text-muted-foreground text-xs">
      {children}
    </blockquote>
  ),
};

function AgentBubble({ msg, thinkingOpen, onToggleThinking }) {
  const meta = AGENT_META[msg.agent];
  const toolCalls = msg.tool_calls || [];
  const thinking = msg.thinking || [];

  return (
    <div className="flex flex-col gap-1 max-w-[94%]">
      <div className="bg-surface border border-border/40 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-foreground shadow-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {msg.content}
        </ReactMarkdown>
      </div>
      {(meta || toolCalls.length > 0 || thinking.length > 0) && (
        <div className="flex items-center gap-1.5 flex-wrap px-1">
          {meta && (
            <span
              className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${meta.cls}`}
            >
              {meta.label}
            </span>
          )}
          {toolCalls.map((t, i) => (
            <span
              key={t.tool || i}
              className="text-[9px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded border border-border/40"
            >
              {t.tool}
            </span>
          ))}
          {thinking.length > 0 && (
            <button
              onClick={onToggleThinking}
              className="flex items-center gap-0.5 text-[9px] text-muted-foreground hover:text-foreground transition-colors ml-auto"
            >
              {thinkingOpen ? (
                <ChevronUp className="w-2.5 h-2.5" />
              ) : (
                <ChevronDown className="w-2.5 h-2.5" />
              )}
              reasoning
            </button>
          )}
        </div>
      )}
      {thinking.length > 0 && thinkingOpen && (
        <div className="mx-1 p-2.5 bg-muted/40 border border-border/30 rounded-lg text-[10px] text-muted-foreground font-mono leading-relaxed max-h-40 overflow-y-auto whitespace-pre-wrap">
          {thinking.join("\n\n---\n\n")}
        </div>
      )}
    </div>
  );
}

function StreamingBubble({ text, tools }) {
  return (
    <div className="flex flex-col gap-1 max-w-[94%]">
      <div className="bg-surface border border-border/40 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-foreground shadow-sm">
        {text ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {text}
          </ReactMarkdown>
        ) : (
          <span className="inline-flex gap-1 items-center">
            <span
              className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce"
              style={{ animationDelay: "0ms" }}
            />
            <span
              className="w-1.5 h-1.5 bg-accent/70 rounded-full animate-bounce"
              style={{ animationDelay: "150ms" }}
            />
            <span
              className="w-1.5 h-1.5 bg-accent/40 rounded-full animate-bounce"
              style={{ animationDelay: "300ms" }}
            />
          </span>
        )}
      </div>
      {tools.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap px-1">
          <Wrench
            className="w-2.5 h-2.5 text-muted-foreground animate-spin"
            style={{ animationDuration: "3s" }}
          />
          {tools.map((tool, i) => (
            <span
              key={`${tool}-${i}`}
              className="text-[9px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded border border-border/40 animate-pulse"
            >
              {tool}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatAssistant() {
  const location = useLocation();
  const agentType = agentTypeFromPath(location.pathname);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(() => {
    try {
      return (
        JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null")?.messages ??
        []
      );
    } catch {
      return [];
    }
  });
  const [sessionId, setSessionId] = useState(() => {
    try {
      return (
        JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null")?.sessionId ??
        null
      );
    } catch {
      return null;
    }
  });
  const [input, setInput] = useState("");
  const [aiAvailable, setAiAvailable] = useState(null);
  const [setupUrl, setSetupUrl] = useState(null);
  const [openThinking, setOpenThinking] = useState(new Set());
  const [sessionCost, setSessionCost] = useState(0);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const prevAgentType = useRef(agentType);
  const sessionIdRef = useRef(sessionId);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const handleDone = useCallback((result) => {
    if (result.session_id) setSessionId(result.session_id);
    if (result.usage?.session_cost_usd != null)
      setSessionCost(result.usage.session_cost_usd);
    setMessages((m) => [
      ...m,
      {
        role: "model",
        content: result.response || "No response.",
        agent: result.agent,
        tool_calls: result.tool_calls || [],
        thinking: result.thinking || [],
      },
    ]);
  }, []);

  const handleError = useCallback((detail) => {
    setMessages((m) => [
      ...m,
      { role: "model", content: detail || "Failed to get response." },
    ]);
  }, []);

  const {
    send: wsSend,
    cancel: wsCancel,
    connected,
    streaming,
    streamText,
    activeTools,
  } = useChatSocket({
    onDone: handleDone,
    onError: handleError,
    enabled: open,
  });

  const clearSession = (sid) => {
    if (sid) api.chat.deleteSession(sid).catch(() => {});
  };

  useEffect(() => {
    if (prevAgentType.current !== agentType) {
      clearSession(sessionId);
      setMessages([]);
      setSessionId(null);
      setSessionCost(0);
      prevAgentType.current = agentType;
    }
  }, [agentType, sessionId]);

  const startNewChat = () => {
    if (streaming) wsCancel();
    clearSession(sessionId);
    setMessages([]);
    setSessionId(null);
    setSessionCost(0);
  };

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming, streamText]);

  useEffect(() => {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ messages, sessionId }),
      );
    } catch {
      /* sessionStorage may be full or disabled */
    }
  }, [messages, sessionId]);

  useEffect(() => {
    if (open && aiAvailable === null) {
      api.chat
        .status()
        .then((data) => {
          setAiAvailable(data.available);
          setSetupUrl(data.setup_url);
        })
        .catch(() => setAiAvailable(false));
    }
    if (open) setTimeout(() => inputRef.current?.focus(), 100);
  }, [open, aiAvailable]);

  const sendMessage = useCallback(
    async (text) => {
      text = (text || input).trim();
      if (!text || streaming) return;
      setMessages((m) => [...m, { role: "user", content: text }]);
      setInput("");

      const sid = sessionIdRef.current;

      if (connected) {
        wsSend(text, sid, agentType);
      } else {
        // HTTP fallback when WebSocket is not connected
        try {
          const data = await api.chat.send({
            message: text,
            session_id: sid,
            agent_type: agentType,
          });
          handleDone(data);
        } catch (err) {
          handleError(
            err.response?.data?.detail ||
              err.message ||
              "Failed to get response.",
          );
        }
      }
    },
    [input, streaming, connected, wsSend, agentType, handleDone, handleError],
  );

  const toggleThinking = (idx) => {
    setOpenThinking((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const suggestions = AGENT_SUGGESTIONS[agentType] || AGENT_SUGGESTIONS.auto;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 w-12 h-12 bg-accent hover:bg-accent/90 text-accent-foreground rounded-full shadow-lg shadow-accent/20 flex items-center justify-center transition-all z-40 hover:scale-105"
        aria-label="Open AI assistant"
      >
        <Sparkles className="w-5 h-5" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
            onClick={() => setOpen(false)}
          />
          <div className="relative w-full max-w-md bg-background shadow-2xl flex flex-col h-full border-l border-border/60">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/60 bg-surface">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 bg-accent/15 border border-accent/30 rounded-lg flex items-center justify-center">
                  <Sparkles className="w-3.5 h-3.5 text-accent" />
                </div>
                <div>
                  <h2 className="font-semibold text-foreground text-sm leading-none">
                    Assistant
                  </h2>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {connected ? (
                      <Wifi className="w-2.5 h-2.5 text-success" />
                    ) : (
                      <WifiOff className="w-2.5 h-2.5 text-muted-foreground" />
                    )}
                    {sessionCost > 0 && (
                      <p className="text-[9px] text-muted-foreground">
                        ${sessionCost.toFixed(4)}
                      </p>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                {messages.length > 0 && (
                  <button
                    type="button"
                    onClick={startNewChat}
                    title="New chat"
                    className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                )}
                <button
                  onClick={() => setOpen(false)}
                  className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
              {aiAvailable === false && (
                <div className="rounded-lg bg-warning/10 border border-warning/30 p-3">
                  <p className="font-medium text-xs text-foreground mb-1">
                    AI assistant not configured
                  </p>
                  <p className="text-[11px] text-muted-foreground mb-2">
                    Add{" "}
                    <code className="px-1 bg-muted rounded font-mono text-[10px]">
                      ANTHROPIC_API_KEY
                    </code>{" "}
                    or{" "}
                    <code className="px-1 bg-muted rounded font-mono text-[10px]">
                      OPENROUTER_API_KEY
                    </code>{" "}
                    to{" "}
                    <code className="px-1 bg-muted rounded font-mono text-[10px]">
                      backend/.env
                    </code>
                  </p>
                  {setupUrl && (
                    <a
                      href={setupUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-accent underline hover:text-foreground"
                    >
                      Get an API key
                    </a>
                  )}
                </div>
              )}

              {messages.length === 0 && aiAvailable !== false && (
                <div className="flex flex-col py-8 gap-4">
                  <div className="text-center">
                    <div className="w-10 h-10 bg-accent/10 border border-accent/20 rounded-xl flex items-center justify-center mx-auto mb-3">
                      <Sparkles className="w-5 h-5 text-accent" />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {AGENT_PLACEHOLDER[agentType]}
                    </p>
                  </div>
                  <div className="grid grid-cols-1 gap-1.5">
                    {suggestions.map((s) => (
                      <button
                        key={s.label}
                        onClick={() => sendMessage(s.prompt)}
                        disabled={streaming || aiAvailable === false}
                        className="text-xs text-left px-3 py-2 rounded-lg border border-border/50 bg-surface hover:bg-accent/5 hover:border-accent/30 text-muted-foreground hover:text-foreground transition-colors leading-snug disabled:opacity-50"
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
                    <div className="max-w-[85%] bg-accent text-accent-foreground rounded-2xl rounded-tr-sm px-3.5 py-2 text-[13px] leading-relaxed">
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

              {streaming && (
                <div className="flex justify-start">
                  <StreamingBubble text={streamText} tools={activeTools} />
                </div>
              )}

              <div ref={scrollRef} />
            </div>

            {/* Input */}
            <div className="px-3 py-2.5 border-t border-border/60 bg-surface">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  sendMessage(input);
                }}
                className="flex gap-1.5"
              >
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    aiAvailable === false
                      ? "Configure API key to enable"
                      : AGENT_PLACEHOLDER[agentType]
                  }
                  className="flex-1 px-3 py-2 bg-background border border-border/60 rounded-lg text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-accent/40 focus:border-accent/50 disabled:opacity-50 transition-colors"
                  disabled={aiAvailable === false}
                />
                {streaming ? (
                  <button
                    type="button"
                    onClick={wsCancel}
                    className="px-3 py-2 bg-destructive/90 hover:bg-destructive text-destructive-foreground rounded-lg transition-colors"
                    title="Stop generating"
                  >
                    <Square className="w-4 h-4" />
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!input.trim() || aiAvailable === false}
                    className="px-3 py-2 bg-accent hover:bg-accent/90 disabled:opacity-30 disabled:cursor-not-allowed text-accent-foreground rounded-lg transition-colors"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                )}
              </form>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
