import { useQueryClient, useMutation } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList } = createEntityHooks("materialRequests", api.materialRequests);

export function useMaterialRequests(params, options) {
  return useList(params, options);
}

export function useCreateMaterialRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.materialRequests.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.materialRequests.all }),
  });
}

export function useProcessMaterialRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.materialRequests.process(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.materialRequests.all }),
  });
}
