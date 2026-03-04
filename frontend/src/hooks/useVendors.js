import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const vendorKeys = {
  all: ["vendors"],
  list: () => ["vendors", "list"],
};

export function useVendors() {
  return useQuery({
    queryKey: vendorKeys.list(),
    queryFn: api.vendors.list,
  });
}

export function useCreateVendor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.vendors.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: vendorKeys.all }),
  });
}

export function useUpdateVendor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.vendors.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: vendorKeys.all }),
  });
}

export function useDeleteVendor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api.vendors.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: vendorKeys.all }),
  });
}
