const base = import.meta.env.VITE_BACKEND_URL || "";
export const API = base ? `${base}/api` : "/api";
