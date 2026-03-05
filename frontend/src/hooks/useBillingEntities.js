import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList, useDetail, useCreate, useUpdate } = createEntityHooks("billingEntities", api.billingEntities);

export { useCreate as useCreateBillingEntity, useUpdate as useUpdateBillingEntity };

export function useBillingEntities(params) {
  return useList(params);
}

export function useBillingEntity(id) {
  return useDetail(id);
}

export function useBillingEntitySearch(q) {
  return useQuery({
    queryKey: keys.billingEntities.search(q),
    queryFn: () => api.billingEntities.search({ q, limit: 20 }),
    enabled: true,
    staleTime: 10_000,
  });
}
