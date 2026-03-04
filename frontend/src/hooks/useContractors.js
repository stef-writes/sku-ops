import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const contractorKeys = {
  all: ["contractors"],
  list: () => ["contractors", "list"],
};

export function useContractors() {
  return useQuery({
    queryKey: contractorKeys.list(),
    queryFn: api.contractors.list,
  });
}

export function useCreateContractor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.contractors.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: contractorKeys.all }),
  });
}

export function useUpdateContractor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.contractors.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: contractorKeys.all }),
  });
}

export function useDeleteContractor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.contractors.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: contractorKeys.all }),
  });
}
