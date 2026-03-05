import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const withdrawalKeys = {
  all: ["withdrawals"],
  list: (params) => ["withdrawals", "list", params],
};

export function useWithdrawals(params) {
  return useQuery({
    queryKey: withdrawalKeys.list(params),
    queryFn: () => api.withdrawals.list(params),
  });
}

export function useCreateWithdrawal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.withdrawals.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: withdrawalKeys.all }),
  });
}

export function useCreateWithdrawalForContractor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ contractorId, data }) => api.withdrawals.createForContractor(contractorId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: withdrawalKeys.all }),
  });
}

export function useMarkPaid() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.withdrawals.markPaid(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: withdrawalKeys.all }),
  });
}

export function useBulkMarkPaid() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids) => api.withdrawals.bulkMarkPaid(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: withdrawalKeys.all }),
  });
}
