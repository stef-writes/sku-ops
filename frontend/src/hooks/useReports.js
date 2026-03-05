import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { keys } from "./queryKeys";

export function useReportSales(params) {
  return useQuery({
    queryKey: keys.reports.sales(params),
    queryFn: () => api.reports.sales(params),
    enabled: !!params,
  });
}

export function useReportInventory() {
  return useQuery({
    queryKey: keys.reports.inventory(),
    queryFn: api.reports.inventory,
  });
}

export function useReportTrends(params) {
  return useQuery({
    queryKey: keys.reports.trends(params),
    queryFn: () => api.reports.trends(params),
    enabled: !!params,
  });
}

export function useReportMargins(params) {
  return useQuery({
    queryKey: keys.reports.productMargins(params),
    queryFn: () => api.reports.productMargins(params),
    enabled: !!params,
  });
}

export function useReportPL(params) {
  return useQuery({
    queryKey: keys.reports.pl(params),
    queryFn: () => api.reports.pl(params),
    enabled: !!params,
  });
}

export function useReportArAging() {
  return useQuery({
    queryKey: keys.reports.arAging(),
    queryFn: api.reports.arAging,
  });
}
