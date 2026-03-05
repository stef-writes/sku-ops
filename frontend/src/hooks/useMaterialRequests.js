import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const materialRequestKeys = {
  all: ["materialRequests"],
  list: (params) => ["materialRequests", "list", params],
};

export function useMaterialRequests(params, options) {
  return useQuery({
    queryKey: materialRequestKeys.list(params),
    queryFn: () => api.materialRequests.list(params),
    ...options,
  });
}

export function useCreateMaterialRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.materialRequests.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: materialRequestKeys.all }),
  });
}

export function useProcessMaterialRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.materialRequests.process(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: materialRequestKeys.all }),
  });
}
