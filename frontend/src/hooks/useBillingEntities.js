import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const billingEntityKeys = {
  all: ["billingEntities"],
  list: (params) => ["billingEntities", "list", params],
  search: (q) => ["billingEntities", "search", q],
  detail: (id) => ["billingEntities", "detail", id],
};

export function useBillingEntities(params) {
  return useQuery({
    queryKey: billingEntityKeys.list(params),
    queryFn: () => api.billingEntities.list(params),
  });
}

export function useBillingEntity(id) {
  return useQuery({
    queryKey: billingEntityKeys.detail(id),
    queryFn: () => api.billingEntities.get(id),
    enabled: !!id,
  });
}

export function useBillingEntitySearch(q) {
  return useQuery({
    queryKey: billingEntityKeys.search(q),
    queryFn: () => api.billingEntities.search({ q, limit: 20 }),
    enabled: true,
    staleTime: 10_000,
  });
}

export function useCreateBillingEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.billingEntities.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: billingEntityKeys.all }),
  });
}

export function useUpdateBillingEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.billingEntities.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: billingEntityKeys.all }),
  });
}
