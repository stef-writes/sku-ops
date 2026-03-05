import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { keys } from "./queryKeys";

export function useDashboardStats(params = {}) {
  return useQuery({
    queryKey: keys.dashboard.stats(params),
    queryFn: () => api.dashboard.stats(params),
    refetchInterval: 60_000,
  });
}
