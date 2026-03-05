import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api-client";
import { createEntityHooks } from "./useEntityHooks";
import { keys } from "./queryKeys";

const { useList, useDetail, useCreate, useUpdate } = createEntityHooks("jobs", api.jobs);

export { useCreate as useCreateJob, useUpdate as useUpdateJob };

export function useJobs(params) {
  return useList(params);
}

export function useJob(id) {
  return useDetail(id);
}

export function useJobSearch(q) {
  return useQuery({
    queryKey: keys.jobs.search(q),
    queryFn: () => api.jobs.search({ q, limit: 20 }),
    enabled: true,
    staleTime: 10_000,
  });
}
