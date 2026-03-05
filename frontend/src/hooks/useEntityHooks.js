import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { keys } from "./queryKeys";

/**
 * Factory that generates standard CRUD hooks for an entity.
 *
 * @param {string} entityKey - key in queryKeys.keys (e.g. "vendors")
 * @param {object} apiMethods - api.vendors-style object with list/get/create/update/delete
 * @returns {{ useList, useDetail, useCreate, useUpdate, useDelete }}
 */
export function createEntityHooks(entityKey, apiMethods) {
  const entityKeys = keys[entityKey];

  function useList(params, options = {}) {
    return useQuery({
      queryKey: entityKeys.list ? entityKeys.list(params) : [entityKey, "list", params],
      queryFn: () => apiMethods.list(params),
      ...options,
    });
  }

  function useDetail(id) {
    return useQuery({
      queryKey: entityKeys.detail ? entityKeys.detail(id) : [entityKey, "detail", id],
      queryFn: () => apiMethods.get(id),
      enabled: !!id,
    });
  }

  function useCreate(options = {}) {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (data) => apiMethods.create(data),
      onSuccess: (...args) => {
        qc.invalidateQueries({ queryKey: entityKeys.all });
        options.onSuccess?.(...args);
      },
    });
  }

  function useUpdate(options = {}) {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: ({ id, data }) => apiMethods.update(id, data),
      onSuccess: (...args) => {
        qc.invalidateQueries({ queryKey: entityKeys.all });
        options.onSuccess?.(...args);
      },
    });
  }

  function useDelete(options = {}) {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (id) => apiMethods.delete(id),
      onSuccess: (...args) => {
        qc.invalidateQueries({ queryKey: entityKeys.all });
        options.onSuccess?.(...args);
      },
    });
  }

  return { useList, useDetail, useCreate, useUpdate, useDelete };
}
