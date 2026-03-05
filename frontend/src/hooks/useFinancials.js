import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { keys } from "./queryKeys";

export function useFinancialSummary(params) {
  return useQuery({
    queryKey: keys.financials.summary(params),
    queryFn: () => api.financials.summary(params),
  });
}

export function exportFinancials(params) {
  return api.financials.export(params);
}
