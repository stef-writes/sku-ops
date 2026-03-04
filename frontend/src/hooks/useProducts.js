import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const productKeys = {
  all: ["products"],
  list: (params) => ["products", "list", params],
  detail: (id) => ["products", "detail", id],
  stockHistory: (id) => ["products", "stockHistory", id],
};

export function useProducts(params) {
  return useQuery({
    queryKey: productKeys.list(params),
    queryFn: () => api.products.list(params),
  });
}

export function useStockHistory(productId) {
  return useQuery({
    queryKey: productKeys.stockHistory(productId),
    queryFn: () => api.products.stockHistory(productId),
    enabled: !!productId,
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.products.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export function useUpdateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.products.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export function useDeleteProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.products.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export function useAdjustStock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.products.adjust(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export function useSuggestUom() {
  return useMutation({
    mutationFn: (data) => api.products.suggestUom(data),
  });
}
