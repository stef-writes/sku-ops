import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const withdrawalKeys = {
  all: ["withdrawals"],
  list: (params) => ["withdrawals", "list", params],
  detail: (id) => ["withdrawals", "detail", id],
};

export function useWithdrawals(params) {
  return useQuery({
    queryKey: withdrawalKeys.list(params),
    queryFn: () => api.withdrawals.list(params),
  });
}

export function useWithdrawal(id) {
  return useQuery({
    queryKey: withdrawalKeys.detail(id),
    queryFn: () => api.withdrawals.get(id),
    enabled: !!id,
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

