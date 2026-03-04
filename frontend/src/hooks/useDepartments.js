import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const departmentKeys = {
  all: ["departments"],
  list: () => ["departments", "list"],
  skuOverview: () => ["departments", "skuOverview"],
};

export function useDepartments() {
  return useQuery({
    queryKey: departmentKeys.list(),
    queryFn: api.departments.list,
  });
}

export function useSkuOverview() {
  return useQuery({
    queryKey: departmentKeys.skuOverview(),
    queryFn: () => api.sku.overview().catch(() => null),
  });
}

export function useCreateDepartment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.departments.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: departmentKeys.all }),
  });
}

export function useUpdateDepartment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.departments.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: departmentKeys.all }),
  });
}

export function useDeleteDepartment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.departments.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: departmentKeys.all }),
  });
}
