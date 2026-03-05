import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const poKeys = {
  all: ["purchaseOrders"],
  list: () => ["purchaseOrders", "list"],
  detail: (id) => ["purchaseOrders", "detail", id],
};

export function usePurchaseOrders() {
  return useQuery({
    queryKey: poKeys.list(),
    queryFn: api.purchaseOrders.list,
  });
}

export function usePOItems(id) {
  return useQuery({
    queryKey: poKeys.detail(id),
    queryFn: () => api.purchaseOrders.get(id),
    enabled: !!id,
  });
}

export function useCreatePurchaseOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.purchaseOrders.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: poKeys.all }),
  });
}

export function useMarkDelivery() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.purchaseOrders.markDelivery(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: poKeys.all }),
  });
}

export function useReceivePO() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.purchaseOrders.receive(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: poKeys.all }),
  });
}
