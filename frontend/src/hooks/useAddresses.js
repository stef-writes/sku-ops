import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const addressKeys = {
  all: ["addresses"],
  list: (params) => ["addresses", "list", params],
  search: (q) => ["addresses", "search", q],
};

export function useAddresses(params) {
  return useQuery({
    queryKey: addressKeys.list(params),
    queryFn: () => api.addresses.list(params),
  });
}

export function useAddressSearch(q) {
  return useQuery({
    queryKey: addressKeys.search(q),
    queryFn: () => api.addresses.search({ q, limit: 20 }),
    enabled: true,
    staleTime: 10_000,
  });
}

export function useCreateAddress() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.addresses.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: addressKeys.all }),
  });
}
