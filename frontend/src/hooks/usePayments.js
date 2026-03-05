import { useQueryClient, useMutation } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList, useDetail } = createEntityHooks("payments", api.payments);

export function usePayments(params) {
  return useList(params);
}

export function usePayment(id) {
  return useDetail(id);
}

export function useCreatePayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.payments.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.payments.all });
      qc.invalidateQueries({ queryKey: keys.withdrawals.all });
    },
  });
}
