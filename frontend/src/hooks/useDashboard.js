import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const dashboardKeys = {
  stats: (params) => ["dashboard", "stats", params],
  transactions: (params) => ["dashboard", "transactions", params],
};

export function useDashboardStats(params = {}) {
  return useQuery({
    queryKey: dashboardKeys.stats(params),
    queryFn: () => api.dashboard.stats(params),
    refetchInterval: 60_000,
  });
}

