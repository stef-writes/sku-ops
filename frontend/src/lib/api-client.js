import axios from "axios";
import { toast } from "sonner";

const base = import.meta.env.VITE_BACKEND_URL || "";
export const API = base ? `${base}/api` : "/api";

/**
 * Extract a human-readable error message from an Axios error.
 */
export function getErrorMessage(error) {
  if (error.response?.data?.detail) {
    const detail = error.response.data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg || d).join(", ");
    return JSON.stringify(detail);
  }
  return error.response?.data?.message || error.message || "Something went wrong";
}

axios.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error.response?.status;
    const url = error.config?.url || "";

    if (status >= 500) {
      console.error(`[API] ${status} on ${url}`, error.response?.data);
      toast.error("Something went wrong — please try again");
    }

    return Promise.reject(error);
  },
);

const api = {
  // ── SKUs ──────────────────────────────────────────────────────────────
  products: {
    list: (params) => axios.get(`${API}/catalog/skus`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/catalog/skus/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/catalog/skus`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/catalog/skus/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/catalog/skus/${id}`),
    adjust: (id, data) => axios.post(`${API}/stock/${id}/adjust`, data).then((r) => r.data),
    suggestUom: (data) => axios.post(`${API}/catalog/skus/suggest-uom`, data).then((r) => r.data),
    stockHistory: (id) => axios.get(`${API}/stock/${id}/history`).then((r) => r.data),
    byBarcode: (barcode) =>
      axios.get(`${API}/catalog/skus/by-barcode`, { params: { barcode } }).then((r) => r.data),
    importCsv: (formData) =>
      axios.post(`${API}/catalog/skus/import-csv`, formData).then((r) => r.data),
  },

  // ── Catalog (new ontology) ──────────────────────────────────────────
  catalog: {
    products: {
      list: (params) => axios.get(`${API}/catalog/products`, { params }).then((r) => r.data),
      get: (id) => axios.get(`${API}/catalog/products/${id}`).then((r) => r.data),
      create: (data) => axios.post(`${API}/catalog/products`, data).then((r) => r.data),
      update: (id, data) => axios.put(`${API}/catalog/products/${id}`, data).then((r) => r.data),
      delete: (id) => axios.delete(`${API}/catalog/products/${id}`),
      skus: (productId) =>
        axios.get(`${API}/catalog/products/${productId}/skus`).then((r) => r.data),
      createSku: (productId, data) =>
        axios.post(`${API}/catalog/products/${productId}/skus`, data).then((r) => r.data),
    },
    vendorItems: {
      list: (skuId) => axios.get(`${API}/catalog/skus/${skuId}/vendors`).then((r) => r.data),
      create: (skuId, data) =>
        axios.post(`${API}/catalog/skus/${skuId}/vendors`, data).then((r) => r.data),
      update: (skuId, itemId, data) =>
        axios.put(`${API}/catalog/skus/${skuId}/vendors/${itemId}`, data).then((r) => r.data),
      delete: (skuId, itemId) => axios.delete(`${API}/catalog/skus/${skuId}/vendors/${itemId}`),
      setPreferred: (skuId, itemId) =>
        axios
          .post(`${API}/catalog/skus/${skuId}/vendors/${itemId}/set-preferred`)
          .then((r) => r.data),
    },
  },

  // ── SKU ───────────────────────────────────────────────────────────────
  sku: {
    preview: (params) => axios.get(`${API}/sku/preview`, { params }).then((r) => r.data),
    overview: () => axios.get(`${API}/sku/overview`).then((r) => r.data),
  },

  // ── Departments ───────────────────────────────────────────────────────
  departments: {
    list: () => axios.get(`${API}/departments`).then((r) => r.data),
    create: (data) => axios.post(`${API}/departments`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/departments/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/departments/${id}`),
  },

  // ── Vendors ───────────────────────────────────────────────────────────
  vendors: {
    list: () => axios.get(`${API}/vendors`).then((r) => r.data),
    create: (data) => axios.post(`${API}/vendors`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/vendors/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/vendors/${id}`),
  },

  // ── Contractors ───────────────────────────────────────────────────────
  contractors: {
    list: (params) => axios.get(`${API}/contractors`, { params }).then((r) => r.data),
    create: (data) => axios.post(`${API}/contractors`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/contractors/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/contractors/${id}`),
  },

  // ── Withdrawals ─────────────────────────────────────────────────────
  withdrawals: {
    list: (params) => axios.get(`${API}/withdrawals`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/withdrawals/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/withdrawals`, data).then((r) => r.data),
    createForContractor: (contractorId, data) =>
      axios
        .post(`${API}/withdrawals/for-contractor`, data, {
          params: { contractor_id: contractorId },
        })
        .then((r) => r.data),
  },

  // ── Returns ─────────────────────────────────────────────────────────
  returns: {
    create: (data) => axios.post(`${API}/returns`, data).then((r) => r.data),
  },

  // ── Material Requests ───────────────────────────────────────────────
  materialRequests: {
    list: (params) => axios.get(`${API}/material-requests`, { params }).then((r) => r.data),
    create: (data) => axios.post(`${API}/material-requests`, data).then((r) => r.data),
    process: (id, data) =>
      axios.post(`${API}/material-requests/${id}/process`, data).then((r) => r.data),
  },

  // ── Purchase Orders ─────────────────────────────────────────────────
  purchaseOrders: {
    list: (params) => axios.get(`${API}/purchase-orders`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/purchase-orders/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/purchase-orders`, data).then((r) => r.data),
    markDelivery: (id, data) =>
      axios.post(`${API}/purchase-orders/${id}/delivery`, data).then((r) => r.data),
    receive: (id, data) =>
      axios.post(`${API}/purchase-orders/${id}/receive`, data).then((r) => r.data),
  },

  // ── Payments ───────────────────────────────────────────────────────
  payments: {
    list: (params) => axios.get(`${API}/payments`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/payments/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/payments`, data).then((r) => r.data),
  },

  // ── Financials ──────────────────────────────────────────────────────
  financials: {
    summary: (params) => axios.get(`${API}/financials/summary`, { params }).then((r) => r.data),
    export: (params) =>
      axios.get(`${API}/financials/export`, { params, responseType: "blob" }).then((r) => r.data),
  },

  // ── Invoices ────────────────────────────────────────────────────────
  invoices: {
    list: (params) => axios.get(`${API}/invoices`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/invoices/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/invoices`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/invoices/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/invoices/${id}`),
    syncXero: (id) => axios.post(`${API}/invoices/${id}/sync-xero`).then((r) => r.data),
    bulkSyncXero: (ids) =>
      axios.post(`${API}/invoices/sync-xero-bulk`, { invoice_ids: ids }).then((r) => r.data),
  },

  // ── Addresses ──────────────────────────────────────────────────────
  addresses: {
    list: (params) => axios.get(`${API}/addresses`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/addresses/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/addresses`, data).then((r) => r.data),
    search: (params) => axios.get(`${API}/addresses/search`, { params }).then((r) => r.data),
  },

  // ── Billing Entities ────────────────────────────────────────────────
  billingEntities: {
    list: (params) => axios.get(`${API}/billing-entities`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/billing-entities/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/billing-entities`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/billing-entities/${id}`, data).then((r) => r.data),
    search: (params) => axios.get(`${API}/billing-entities/search`, { params }).then((r) => r.data),
  },

  // ── Jobs ────────────────────────────────────────────────────────────
  jobs: {
    list: (params) => axios.get(`${API}/jobs`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/jobs/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/jobs`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/jobs/${id}`, data).then((r) => r.data),
    search: (params) => axios.get(`${API}/jobs/search`, { params }).then((r) => r.data),
  },

  // ── Documents ───────────────────────────────────────────────────────
  documents: {
    list: (params) => axios.get(`${API}/documents`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/documents/${id}`).then((r) => r.data),
    parse: (formData, useAi) =>
      axios
        .post(`${API}/documents/parse${useAi ? "?use_ai=true" : ""}`, formData)
        .then((r) => r.data),
  },

  // ── Dashboard ───────────────────────────────────────────────────────
  dashboard: {
    stats: (params) => axios.get(`${API}/dashboard/stats`, { params }).then((r) => r.data),
    transactions: (params) =>
      axios.get(`${API}/dashboard/transactions`, { params }).then((r) => r.data),
  },

  // ── Reports ─────────────────────────────────────────────────────────
  reports: {
    sales: (params) => axios.get(`${API}/reports/sales`, { params }).then((r) => r.data),
    inventory: () => axios.get(`${API}/reports/inventory`).then((r) => r.data),
    trends: (params) => axios.get(`${API}/reports/trends`, { params }).then((r) => r.data),
    productMargins: (params) =>
      axios.get(`${API}/reports/product-margins`, { params }).then((r) => r.data),
    jobPl: (params) => axios.get(`${API}/reports/job-pl`, { params }).then((r) => r.data),
    kpis: (params) => axios.get(`${API}/reports/kpis`, { params }).then((r) => r.data),
    productPerformance: (params) =>
      axios.get(`${API}/reports/product-performance`, { params }).then((r) => r.data),
    pl: (params) => axios.get(`${API}/reports/pl`, { params }).then((r) => r.data),
    arAging: (params) => axios.get(`${API}/reports/ar-aging`, { params }).then((r) => r.data),
    reorderUrgency: (params) =>
      axios.get(`${API}/reports/reorder-urgency`, { params }).then((r) => r.data),
    productActivity: (params) =>
      axios.get(`${API}/reports/product-activity`, { params }).then((r) => r.data),
  },

  // ── Cycle Counts ────────────────────────────────────────────────────
  cycleCounts: {
    list: (params) => axios.get(`${API}/cycle-counts`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/cycle-counts/${id}`).then((r) => r.data),
    open: (data) => axios.post(`${API}/cycle-counts`, data).then((r) => r.data),
    updateItem: (countId, itemId, data) =>
      axios.patch(`${API}/cycle-counts/${countId}/items/${itemId}`, data).then((r) => r.data),
    commit: (id) => axios.post(`${API}/cycle-counts/${id}/commit`).then((r) => r.data),
  },

  // ── Chat ────────────────────────────────────────────────────────────
  chat: {
    status: () => axios.get(`${API}/chat/status`).then((r) => r.data),
    send: (data) => axios.post(`${API}/chat`, data).then((r) => r.data),
    deleteSession: (id) => axios.delete(`${API}/chat/sessions/${id}`),
  },

  // ── Auth / Seed ─────────────────────────────────────────────────────
  auth: {
    me: () => axios.get(`${API}/auth/me`).then((r) => r.data),
    login: (data) => axios.post(`${API}/auth/login`, data).then((r) => r.data),
    register: (data) => axios.post(`${API}/auth/register`, data).then((r) => r.data),
    refresh: () => axios.post(`${API}/auth/refresh`).then((r) => r.data),
  },

  seed: {
    departments: () => axios.post(`${API}/seed/departments`).then((r) => r.data),
  },

  // ── Org Settings ────────────────────────────────────────────────────
  settings: {
    xero: () => axios.get(`${API}/settings/xero`).then((r) => r.data),
    updateXero: (data) => axios.put(`${API}/settings/xero`, data).then((r) => r.data),
  },

  // ── Xero ──────────────────────────────────────────────────────────────
  xero: {
    health: () => axios.get(`${API}/xero/health`).then((r) => r.data),
    triggerSync: () => axios.post(`${API}/xero/sync`).then((r) => r.data),
    syncStatus: () => axios.get(`${API}/xero/sync-status`).then((r) => r.data),
    tenants: () => axios.get(`${API}/xero/tenants`).then((r) => r.data),
    selectTenant: (id) =>
      axios
        .post(`${API}/xero/select-tenant`, null, { params: { tenant_id: id } })
        .then((r) => r.data),
    disconnect: () => axios.post(`${API}/xero/disconnect`).then((r) => r.data),
    trackingCategories: () => axios.get(`${API}/xero/tracking-categories`).then((r) => r.data),
    selectTrackingCategory: (id) =>
      axios
        .post(`${API}/xero/select-tracking-category`, null, {
          params: { tracking_category_id: id },
        })
        .then((r) => r.data),
  },
};

export default api;
