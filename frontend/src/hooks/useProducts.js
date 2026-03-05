import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList, useCreate, useUpdate, useDelete } = createEntityHooks("products", api.products);

export { useCreate as useCreateProduct, useUpdate as useUpdateProduct, useDelete as useDeleteProduct };

export function useProducts(params) {
  return useList(params);
}

export function useStockHistory(productId) {
  return useQuery({
    queryKey: keys.products.stockHistory(productId),
    queryFn: () => api.products.stockHistory(productId),
    enabled: !!productId,
  });
}

export function useAdjustStock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.products.adjust(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.products.all }),
  });
}

export function useSuggestUom() {
  return useMutation({
    mutationFn: (data) => api.products.suggestUom(data),
  });
}
