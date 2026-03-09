import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { keys } from "./queryKeys";

export function useXeroHealth() {
  return useQuery({
    queryKey: keys.xeroHealth.summary(),
    queryFn: api.xero.health,
    staleTime: 30_000,
  });
}

export function useTriggerXeroSync() {
  const qc = useQueryClient();
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    if (!syncing) return;
    const interval = setInterval(async () => {
      try {
        const { status } = await api.xero.syncStatus();
        if (status === "idle") {
          setSyncing(false);
          qc.invalidateQueries({ queryKey: keys.xeroHealth.all });
        }
      } catch {
        setSyncing(false);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [syncing, qc]);

  const mutation = useMutation({
    mutationFn: api.xero.triggerSync,
    onSuccess: (data) => {
      if (data?.status === "started" || data?.status === "in_progress") {
        setSyncing(true);
      } else {
        qc.invalidateQueries({ queryKey: keys.xeroHealth.all });
      }
    },
  });

  const triggerSync = useCallback(() => mutation.mutate(), [mutation]);

  return { triggerSync, syncing, ...mutation };
}
