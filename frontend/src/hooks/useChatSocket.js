import { useRef, useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 15_000;
const HEARTBEAT_TIMEOUT_MS = 35_000;

function buildWsUrl(token) {
  const base = import.meta.env.VITE_BACKEND_URL || "";
  let wsBase;
  if (base) {
    wsBase = base.replace(/^http/, "ws");
  } else {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    wsBase = `${proto}//${location.host}`;
  }
  return `${wsBase}/api/ws/chat?token=${encodeURIComponent(token)}`;
}

/**
 * WebSocket hook for AI chat streaming.
 *
 * Returns:
 *   send(msg)     — send a chat message
 *   cancel()      — abort current generation
 *   connected     — whether the socket is open
 *   streaming     — whether a response is actively being generated
 *   streamText    — accumulated text during streaming
 *   activeTools   — tool names called during current generation
 *   lastResult    — the final chat.done payload
 *   lastError     — last error message from the server
 *   clearResult() — reset lastResult/lastError
 */
export function useChatSocket({
  onDelta,
  onToolStart,
  onDone,
  onError,
  enabled = true,
} = {}) {
  const { token } = useAuth();
  const wsRef = useRef(null);
  const retriesRef = useRef(0);
  const timerRef = useRef(null);
  const heartbeatTimerRef = useRef(null);
  const callbacksRef = useRef({ onDelta, onToolStart, onDone, onError });
  const scheduleReconnectRef = useRef(null);

  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [activeTools, setActiveTools] = useState([]);
  const [lastResult, setLastResult] = useState(null);
  const [lastError, setLastError] = useState(null);

  useEffect(() => {
    callbacksRef.current = { onDelta, onToolStart, onDone, onError };
  });

  const resetHeartbeat = useCallback(() => {
    clearTimeout(heartbeatTimerRef.current);
    heartbeatTimerRef.current = setTimeout(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close(4002, "Heartbeat timeout");
      }
    }, HEARTBEAT_TIMEOUT_MS);
  }, []);

  const connect = useCallback(() => {
    if (!token || !enabled) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = buildWsUrl(token);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retriesRef.current = 0;
      setConnected(true);
      resetHeartbeat();
    };

    ws.onmessage = (e) => {
      resetHeartbeat();
      let msg;
      try {
        msg = JSON.parse(e.data);
      } catch {
        return;
      }

      const { type } = msg;

      if (type === "ping") {
        try {
          ws.send(JSON.stringify({ type: "pong" }));
        } catch {
          /* WS may be closing */
        }
        return;
      }

      if (type === "chat.status") {
        setStreaming(true);
        setStreamText("");
        setActiveTools([]);
        setLastError(null);
        return;
      }

      if (type === "chat.delta") {
        setStreamText((prev) => prev + (msg.content || ""));
        callbacksRef.current.onDelta?.(msg.content || "");
        return;
      }

      if (type === "chat.tool_start") {
        setActiveTools((prev) => [...prev, msg.tool]);
        callbacksRef.current.onToolStart?.(msg.tool);
        return;
      }

      if (type === "chat.done") {
        setStreaming(false);
        setStreamText("");
        setActiveTools([]);
        setLastResult(msg);
        callbacksRef.current.onDone?.(msg);
        return;
      }

      if (type === "chat.error") {
        setStreaming(false);
        setStreamText("");
        setActiveTools([]);
        setLastError(msg.detail || "Unknown error");
        callbacksRef.current.onError?.(msg.detail || "Unknown error");
        return;
      }
    };

    ws.onclose = (e) => {
      setConnected(false);
      wsRef.current = null;
      clearTimeout(heartbeatTimerRef.current);
      if (e.code !== 4001 && e.code !== 4003) {
        scheduleReconnectRef.current?.();
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [token, enabled, resetHeartbeat]);

  const scheduleReconnect = useCallback(() => {
    if (timerRef.current) return;
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** retriesRef.current,
      RECONNECT_MAX_MS,
    );
    retriesRef.current += 1;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      connect();
    }, delay);
  }, [connect]);

  useEffect(() => {
    scheduleReconnectRef.current = scheduleReconnect;
  });

  useEffect(() => {
    if (enabled) {
      connect();
    }
    return () => {
      clearTimeout(timerRef.current);
      timerRef.current = null;
      clearTimeout(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
      setStreaming(false);
    };
  }, [connect, enabled]);

  const send = useCallback((message, sessionId, agentType = "auto") => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return false;
    try {
      wsRef.current.send(
        JSON.stringify({
          type: "chat",
          message,
          session_id: sessionId,
          agent_type: agentType,
        }),
      );
      return true;
    } catch {
      return false;
    }
  }, []);

  const cancel = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    try {
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
    } catch {
      /* WS may be closing */
    }
    setStreaming(false);
    setStreamText("");
    setActiveTools([]);
  }, []);

  const clearResult = useCallback(() => {
    setLastResult(null);
    setLastError(null);
  }, []);

  return {
    send,
    cancel,
    connected,
    streaming,
    streamText,
    activeTools,
    lastResult,
    lastError,
    clearResult,
  };
}
