import { useQueryClient, useMutation } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList, useDetail, useCreate } = createEntityHooks("withdrawals", api.withdrawals);

export { useCreate as useCreateWithdrawal };

export function useWithdrawals(params) {
  return useList(params);
}

export function useWithdrawal(id) {
  return useDetail(id);
}

export function useCreateWithdrawalForContractor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ contractorId, data }) => api.withdrawals.createForContractor(contractorId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.withdrawals.all }),
  });
}
