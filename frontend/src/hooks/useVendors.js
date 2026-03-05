import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";

const { useList, useCreate, useUpdate, useDelete } = createEntityHooks("vendors", api.vendors);

export { useCreate as useCreateVendor, useUpdate as useUpdateVendor, useDelete as useDeleteVendor };

export function useVendors(params) {
  return useList(params);
}
