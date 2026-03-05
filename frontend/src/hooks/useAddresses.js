import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList, useCreate } = createEntityHooks("addresses", api.addresses);

export { useCreate as useCreateAddress };

export function useAddresses(params) {
  return useList(params);
}

export function useAddressSearch(q) {
  return useQuery({
    queryKey: keys.addresses.search(q),
    queryFn: () => api.addresses.search({ q, limit: 20 }),
    enabled: true,
    staleTime: 10_000,
  });
}
