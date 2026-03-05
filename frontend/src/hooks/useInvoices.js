import { useQueryClient, useMutation } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList, useDetail, useCreate, useUpdate, useDelete } = createEntityHooks("invoices", api.invoices);

export { useCreate as useCreateInvoice, useUpdate as useUpdateInvoice, useDelete as useDeleteInvoice };

export function useInvoices(params) {
  return useList(params);
}

export function useInvoice(id) {
  return useDetail(id);
}

export function useSyncXero() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.invoices.syncXero(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.invoices.all }),
  });
}

export function useBulkSyncXero() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids) => api.invoices.bulkSyncXero(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.invoices.all }),
  });
}
