import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { withdrawalKeys } from "./useWithdrawals";

export const paymentKeys = {
  all: ["payments"],
  list: (params) => ["payments", "list", params],
  detail: (id) => ["payments", "detail", id],
};

export function usePayments(params) {
  return useQuery({
    queryKey: paymentKeys.list(params),
    queryFn: () => api.payments.list(params),
  });
}

export function usePayment(id) {
  return useQuery({
    queryKey: paymentKeys.detail(id),
    queryFn: () => api.payments.get(id),
    enabled: !!id,
  });
}

export function useCreatePayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.payments.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: paymentKeys.all });
      qc.invalidateQueries({ queryKey: withdrawalKeys.all });
    },
  });
}
