import { useEffect, useRef, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import { keys } from "./queryKeys";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
// Server sends pings every 30s; 45s gives 15s margin for network jitter.
const HEARTBEAT_TIMEOUT_MS = 45_000;

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
  const heartbeatTimerRef = useRef(null);
  const connectRef = useRef(null);
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

  const resetHeartbeat = useCallback(() => {
    clearTimeout(heartbeatTimerRef.current);
    heartbeatTimerRef.current = setTimeout(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        console.debug("[ws] heartbeat timeout — closing connection");
        wsRef.current.close(4002, "Heartbeat timeout");
      }
    }, HEARTBEAT_TIMEOUT_MS);
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (timerRef.current) return;
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** retriesRef.current,
      RECONNECT_MAX_MS,
    );
    retriesRef.current += 1;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      connectRef.current?.();
    }, delay);
  }, []);

  const connect = useCallback(() => {
    if (!token) return;
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
      try {
        const msg = JSON.parse(e.data);
        if (msg.type && msg.type !== "ping") {
          invalidate(msg.type);
        }
      } catch {
        /* ignore malformed messages */
      }
    };

    ws.onclose = (e) => {
      setConnected(false);
      wsRef.current = null;
      clearTimeout(heartbeatTimerRef.current);
      console.debug(`[ws] closed code=${e.code} reason=${e.reason || "none"}`);
      if (e.code !== 4001) {
        scheduleReconnect();
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [token, invalidate, resetHeartbeat, scheduleReconnect]);

  connectRef.current = connect;

  useEffect(() => {
    connect();
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
    };
  }, [connect]);

  return { connected };
}
