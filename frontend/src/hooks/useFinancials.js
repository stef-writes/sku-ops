import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const financialKeys = {
  all: ["financials"],
  summary: (params) => ["financials", "summary", params],
};

export function useFinancialSummary(params) {
  return useQuery({
    queryKey: financialKeys.summary(params),
    queryFn: () => api.financials.summary(params),
  });
}

export function useExportFinancials(params) {
  return api.financials.export(params);
}
