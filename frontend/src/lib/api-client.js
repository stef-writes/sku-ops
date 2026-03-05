import axios from "axios";
import { toast } from "sonner";
import { API } from "./api";

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
  }
);

const api = {
  // ── Products ──────────────────────────────────────────────────────────
  products: {
    list: (params) => axios.get(`${API}/products`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/products/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/products`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/products/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/products/${id}`),
    adjust: (id, data) => axios.post(`${API}/stock/${id}/adjust`, data).then((r) => r.data),
    suggestUom: (data) => axios.post(`${API}/products/suggest-uom`, data).then((r) => r.data),
    stockHistory: (id) => axios.get(`${API}/stock/${id}/history`).then((r) => r.data),
    byBarcode: (barcode) => axios.get(`${API}/products/by-barcode`, { params: { barcode } }).then((r) => r.data),
    importCsv: (formData) => axios.post(`${API}/products/import-csv`, formData).then((r) => r.data),
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
      axios.post(`${API}/withdrawals/for-contractor`, data, { params: { contractor_id: contractorId } }).then((r) => r.data),
  },

  // ── Returns ─────────────────────────────────────────────────────────
  returns: {
    create: (data) => axios.post(`${API}/returns`, data).then((r) => r.data),
  },

  // ── Material Requests ───────────────────────────────────────────────
  materialRequests: {
    list: (params) => axios.get(`${API}/material-requests`, { params }).then((r) => r.data),
    create: (data) => axios.post(`${API}/material-requests`, data).then((r) => r.data),
    process: (id, data) => axios.post(`${API}/material-requests/${id}/process`, data).then((r) => r.data),
  },

  // ── Purchase Orders ─────────────────────────────────────────────────
  purchaseOrders: {
    list: (params) => axios.get(`${API}/purchase-orders`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/purchase-orders/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/purchase-orders`, data).then((r) => r.data),
    markDelivery: (id, data) => axios.post(`${API}/purchase-orders/${id}/delivery`, data).then((r) => r.data),
    receive: (id, data) => axios.post(`${API}/purchase-orders/${id}/receive`, data).then((r) => r.data),
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
    export: (params) => axios.get(`${API}/financials/export`, { params, responseType: "blob" }).then((r) => r.data),
  },

  // ── Invoices ────────────────────────────────────────────────────────
  invoices: {
    list: (params) => axios.get(`${API}/invoices`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/invoices/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/invoices`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/invoices/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/invoices/${id}`),
    syncXero: (id) => axios.post(`${API}/invoices/${id}/sync-xero`).then((r) => r.data),
    bulkSyncXero: (ids) => axios.post(`${API}/invoices/sync-xero-bulk`, { invoice_ids: ids }).then((r) => r.data),
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
      axios.post(`${API}/documents/parse${useAi ? "?use_ai=true" : ""}`, formData).then((r) => r.data),
  },

  // ── Dashboard ───────────────────────────────────────────────────────
  dashboard: {
    stats: (params) => axios.get(`${API}/dashboard/stats`, { params }).then((r) => r.data),
    transactions: (params) => axios.get(`${API}/dashboard/transactions`, { params }).then((r) => r.data),
  },

  // ── Reports ─────────────────────────────────────────────────────────
  reports: {
    sales: (params) => axios.get(`${API}/reports/sales`, { params }).then((r) => r.data),
    inventory: () => axios.get(`${API}/reports/inventory`).then((r) => r.data),
    trends: (params) => axios.get(`${API}/reports/trends`, { params }).then((r) => r.data),
    productMargins: (params) => axios.get(`${API}/reports/product-margins`, { params }).then((r) => r.data),
    jobPl: (params) => axios.get(`${API}/reports/job-pl`, { params }).then((r) => r.data),
    kpis: (params) => axios.get(`${API}/reports/kpis`, { params }).then((r) => r.data),
    productPerformance: (params) => axios.get(`${API}/reports/product-performance`, { params }).then((r) => r.data),
    pl: (params) => axios.get(`${API}/reports/pl`, { params }).then((r) => r.data),
    arAging: () => axios.get(`${API}/reports/ar-aging`).then((r) => r.data),
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
  },

  seed: {
    departments: () => axios.post(`${API}/seed/departments`).then((r) => r.data),
  },
};

export default api;
