import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";

const { useList, useDetail } = createEntityHooks("documents", api.documents);

export function useDocuments(params) {
  return useList(params);
}

export function useDocument(id) {
  return useDetail(id);
}
