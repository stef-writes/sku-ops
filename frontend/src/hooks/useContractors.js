import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";

const { useList, useCreate, useUpdate, useDelete } = createEntityHooks("contractors", api.contractors);

export { useCreate as useCreateContractor, useUpdate as useUpdateContractor, useDelete as useDeleteContractor };

export function useContractors(params) {
  return useList(params);
}
