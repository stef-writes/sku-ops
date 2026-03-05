import { useQueryClient, useMutation } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList, useDetail, useCreate } = createEntityHooks("purchaseOrders", api.purchaseOrders);

export { useCreate as useCreatePurchaseOrder };

export function usePurchaseOrders(params) {
  return useList(params);
}

export function usePOItems(id) {
  return useDetail(id);
}

export function useMarkDelivery() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.purchaseOrders.markDelivery(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.purchaseOrders.all }),
  });
}

export function useReceivePO() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.purchaseOrders.receive(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.purchaseOrders.all }),
  });
}
