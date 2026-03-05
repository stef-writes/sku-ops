import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const invoiceKeys = {
  all: ["invoices"],
  list: (params) => ["invoices", "list", params],
  detail: (id) => ["invoices", "detail", id],
};

export function useInvoices(params) {
  return useQuery({
    queryKey: invoiceKeys.list(params),
    queryFn: () => api.invoices.list(params),
  });
}

export function useInvoice(id) {
  return useQuery({
    queryKey: invoiceKeys.detail(id),
    queryFn: () => api.invoices.get(id),
    enabled: !!id,
  });
}

export function useCreateInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.invoices.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: invoiceKeys.all }),
  });
}

export function useUpdateInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.invoices.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: invoiceKeys.all }),
  });
}

export function useDeleteInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.invoices.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: invoiceKeys.all }),
  });
}

export function useSyncXero() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.invoices.syncXero(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: invoiceKeys.all }),
  });
}

export function useBulkSyncXero() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids) => api.invoices.bulkSyncXero(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: invoiceKeys.all }),
  });
}
