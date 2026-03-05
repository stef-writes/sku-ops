import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const reportKeys = {
  sales: (params) => ["reports", "sales", params],
  inventory: () => ["reports", "inventory"],
  trends: (params) => ["reports", "trends", params],
  productMargins: (params) => ["reports", "productMargins", params],
  pl: (params) => ["reports", "pl", params],
  arAging: () => ["reports", "arAging"],
};

export function useReportSales(params) {
  return useQuery({
    queryKey: reportKeys.sales(params),
    queryFn: () => api.reports.sales(params),
    enabled: !!params,
  });
}

export function useReportInventory() {
  return useQuery({
    queryKey: reportKeys.inventory(),
    queryFn: api.reports.inventory,
  });
}

export function useReportTrends(params) {
  return useQuery({
    queryKey: reportKeys.trends(params),
    queryFn: () => api.reports.trends(params),
    enabled: !!params,
  });
}

export function useReportMargins(params) {
  return useQuery({
    queryKey: reportKeys.productMargins(params),
    queryFn: () => api.reports.productMargins(params),
    enabled: !!params,
  });
}

export function useReportPL(params) {
  return useQuery({
    queryKey: reportKeys.pl(params),
    queryFn: () => api.reports.pl(params),
    enabled: !!params,
  });
}

export function useReportArAging() {
  return useQuery({
    queryKey: reportKeys.arAging(),
    queryFn: api.reports.arAging,
  });
}
