export const keys = {
  products: {
    all: ["products"],
    list: (params) => ["products", "list", params],
    detail: (id) => ["products", "detail", id],
    stockHistory: (id) => ["products", "stockHistory", id],
  },
  invoices: {
    all: ["invoices"],
    list: (params) => ["invoices", "list", params],
    detail: (id) => ["invoices", "detail", id],
  },
  withdrawals: {
    all: ["withdrawals"],
    list: (params) => ["withdrawals", "list", params],
    detail: (id) => ["withdrawals", "detail", id],
  },
  payments: {
    all: ["payments"],
    list: (params) => ["payments", "list", params],
    detail: (id) => ["payments", "detail", id],
  },
  purchaseOrders: {
    all: ["purchaseOrders"],
    list: (params) => ["purchaseOrders", "list", params],
    detail: (id) => ["purchaseOrders", "detail", id],
  },
  materialRequests: {
    all: ["materialRequests"],
    list: (params) => ["materialRequests", "list", params],
  },
  contractors: {
    all: ["contractors"],
    list: (params) => ["contractors", "list", params],
    detail: (id) => ["contractors", "detail", id],
  },
  vendors: {
    all: ["vendors"],
    list: (params) => ["vendors", "list", params],
    detail: (id) => ["vendors", "detail", id],
  },
  departments: {
    all: ["departments"],
    list: () => ["departments", "list"],
    skuOverview: () => ["departments", "skuOverview"],
  },
  billingEntities: {
    all: ["billingEntities"],
    list: (params) => ["billingEntities", "list", params],
    detail: (id) => ["billingEntities", "detail", id],
    search: (q) => ["billingEntities", "search", q],
  },
  addresses: {
    all: ["addresses"],
    list: (params) => ["addresses", "list", params],
    search: (q) => ["addresses", "search", q],
  },
  jobs: {
    all: ["jobs"],
    list: (params) => ["jobs", "list", params],
    detail: (id) => ["jobs", "detail", id],
    search: (q) => ["jobs", "search", q],
  },
  documents: {
    all: ["documents"],
    list: (params) => ["documents", "list", params],
    detail: (id) => ["documents", "detail", id],
  },
  financials: {
    all: ["financials"],
    summary: (params) => ["financials", "summary", params],
  },
  dashboard: {
    stats: (params) => ["dashboard", "stats", params],
    transactions: (params) => ["dashboard", "transactions", params],
  },
  reports: {
    sales: (params) => ["reports", "sales", params],
    inventory: () => ["reports", "inventory"],
    trends: (params) => ["reports", "trends", params],
    productMargins: (params) => ["reports", "productMargins", params],
    pl: (params) => ["reports", "pl", params],
    arAging: () => ["reports", "arAging"],
  },
};
