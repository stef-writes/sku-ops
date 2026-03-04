import axios from "axios";
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

const api = {
  // ── Products ──────────────────────────────────────────────────────────
  products: {
    list: (params) => axios.get(`${API}/products`, { params }).then((r) => r.data),
    get: (id) => axios.get(`${API}/products/${id}`).then((r) => r.data),
    create: (data) => axios.post(`${API}/products`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/products/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/products/${id}`),
    adjust: (id, data) => axios.post(`${API}/products/${id}/adjust`, data).then((r) => r.data),
    suggestUom: (data) => axios.post(`${API}/products/suggest-uom`, data).then((r) => r.data),
    stockHistory: (id) => axios.get(`${API}/products/${id}/stock-history`).then((r) => r.data),
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
    list: () => axios.get(`${API}/contractors`).then((r) => r.data),
    create: (data) => axios.post(`${API}/contractors`, data).then((r) => r.data),
    update: (id, data) => axios.put(`${API}/contractors/${id}`, data).then((r) => r.data),
    delete: (id) => axios.delete(`${API}/contractors/${id}`),
  },

  // ── Dashboard ─────────────────────────────────────────────────────────
  dashboard: {
    stats: () => axios.get(`${API}/dashboard/stats`).then((r) => r.data),
  },

  // ── Reports ───────────────────────────────────────────────────────────
  reports: {
    sales: (params) => axios.get(`${API}/reports/sales`, { params }).then((r) => r.data),
    inventory: () => axios.get(`${API}/reports/inventory`).then((r) => r.data),
    trends: (params) => axios.get(`${API}/reports/trends`, { params }).then((r) => r.data),
    productMargins: (params) => axios.get(`${API}/reports/product-margins`, { params }).then((r) => r.data),
    jobPl: (params) => axios.get(`${API}/reports/job-pl`, { params }).then((r) => r.data),
  },

  // ── Auth / Seed ───────────────────────────────────────────────────────
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
