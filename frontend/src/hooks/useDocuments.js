import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const documentKeys = {
  all: ["documents"],
  list: (params) => ["documents", "list", params],
  detail: (id) => ["documents", "detail", id],
};

export function useDocuments(params) {
  return useQuery({
    queryKey: documentKeys.list(params),
    queryFn: () => api.documents.list(params),
  });
}

export function useDocument(id) {
  return useQuery({
    queryKey: documentKeys.detail(id),
    queryFn: () => api.documents.get(id),
    enabled: !!id,
  });
}
