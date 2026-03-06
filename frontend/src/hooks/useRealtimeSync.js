import { useEffect, useRef, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import { keys } from "./queryKeys";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

const EVENT_KEY_MAP = {
  "inventory.updated": [
    keys.products.all,
    keys.dashboard.stats({}),
    keys.reports.inventory(),
  ],
  "withdrawal.created": [
    keys.withdrawals.all,
    keys.dashboard.stats({}),
    keys.dashboard.transactions({}),
    keys.products.all,
  ],
  "withdrawal.updated": [
    keys.withdrawals.all,
    keys.dashboard.stats({}),
  ],
  "material_request.created": [
    keys.materialRequests.all,
    keys.dashboard.stats({}),
  ],
  "material_request.processed": [
    keys.materialRequests.all,
    keys.withdrawals.all,
    keys.dashboard.stats({}),
    keys.products.all,
  ],
};

function buildWsUrl(token) {
  const base = import.meta.env.VITE_BACKEND_URL || "";
  let wsBase;
  if (base) {
    wsBase = base.replace(/^http/, "ws");
  } else {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    wsBase = `${proto}//${location.host}`;
  }
  return `${wsBase}/api/ws?token=${encodeURIComponent(token)}`;
}

export function useRealtimeSync() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const wsRef = useRef(null);
  const retriesRef = useRef(0);
  const timerRef = useRef(null);
  const [connected, setConnected] = useState(false);

  const invalidate = useCallback(
    (eventType) => {
      const queryKeys = EVENT_KEY_MAP[eventType];
      if (!queryKeys) return;
      for (const key of queryKeys) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
    [queryClient],
  );

  const connect = useCallback(() => {
    if (!token) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = buildWsUrl(token);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retriesRef.current = 0;
      setConnected(true);
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type && msg.type !== "ping") {
          invalidate(msg.type);
        }
      } catch {
        /* ignore malformed messages */
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [token, invalidate]);

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
    connect();
    return () => {
      clearTimeout(timerRef.current);
      timerRef.current = null;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
    };
  }, [connect]);

  return { connected };
}
