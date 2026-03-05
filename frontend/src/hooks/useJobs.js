import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api-client";

export const jobKeys = {
  all: ["jobs"],
  list: (params) => ["jobs", "list", params],
  search: (q) => ["jobs", "search", q],
  detail: (id) => ["jobs", "detail", id],
};

export function useJobs(params) {
  return useQuery({
    queryKey: jobKeys.list(params),
    queryFn: () => api.jobs.list(params),
  });
}

export function useJobSearch(q) {
  return useQuery({
    queryKey: jobKeys.search(q),
    queryFn: () => api.jobs.search({ q, limit: 20 }),
    enabled: true,
    staleTime: 10_000,
  });
}

export function useJob(id) {
  return useQuery({
    queryKey: jobKeys.detail(id),
    queryFn: () => api.jobs.get(id),
    enabled: !!id,
  });
}

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => api.jobs.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: jobKeys.all }),
  });
}

export function useUpdateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => api.jobs.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: jobKeys.all }),
  });
}
