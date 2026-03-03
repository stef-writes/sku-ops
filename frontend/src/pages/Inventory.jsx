import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Search,
  Plus,
  Package,
  AlertTriangle,
  Sparkles,
  Printer,
  ChevronLeft,
  ChevronRight,
  Info,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { StockHistoryModal } from "../components/StockHistoryModal";
import { BarcodeLabelsModal } from "../components/BarcodeLabelsModal";
import { ProductDetailModal } from "../components/ProductDetailModal";
import { ConfirmDialog } from "@/components/ConfirmDialog";

import { API } from "@/lib/api";

const UOM_OPTIONS = [
  "each", "case", "box", "pack", "bag", "roll", "gallon", "quart", "pint",
  "liter", "pound", "ounce", "foot", "meter", "yard", "sqft", "kit",
];

const Inventory = () => {
  const [searchParams] = useSearchParams();
  const [products, setProducts] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [filterDept, setFilterDept] = useState("");
  const [filterLowStock, setFilterLowStock] = useState(searchParams.get("low_stock") === "1");
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [saving, setSaving] = useState(false);
  const [stockHistoryProduct, setStockHistoryProduct] = useState(null);
  const [adjustProduct, setAdjustProduct] = useState(null);
  const [adjustDelta, setAdjustDelta] = useState("");
  const [adjustReason, setAdjustReason] = useState("correction");
  const [adjusting, setAdjusting] = useState(false);
  const [suggestingUom, setSuggestingUom] = useState(false);
  const suggestUomTimeout = useRef(null);
  const [labelsModalOpen, setLabelsModalOpen] = useState(false);
  const [labelsProducts, setLabelsProducts] = useState([]);
  const [detailProduct, setDetailProduct] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, product: null });
  const [skuPreview, setSkuPreview] = useState(null);
  const [page, setPage] = useState(0);
  const [totalProducts, setTotalProducts] = useState(0);
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const PAGE_SIZE = 50;

  const [form, setForm] = useState({
    name: "",
    description: "",
    price: "",
    cost: "",
    quantity: "",
    min_stock: "5",
    department_id: "",
    vendor_id: "",
    barcode: "",
    base_unit: "each",
    sell_uom: "each",
    pack_qty: "1",
  });

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    const q = searchParams.get("search");
    if (q != null && q !== search) setSearch(q);
  }, [searchParams]);

  useEffect(() => {
    setPage(0);
  }, [search, filterDept, filterLowStock]);

  useEffect(() => {
    fetchProducts();
  }, [search, filterDept, filterLowStock, page]);

  useEffect(() => {
    return () => {
      if (suggestUomTimeout.current) clearTimeout(suggestUomTimeout.current);
    };
  }, []);

  // SKU preview when adding new product and department is selected
  useEffect(() => {
    if (!dialogOpen || editingProduct || !form.department_id) {
      setSkuPreview(null);
      return;
    }
    const params = new URLSearchParams({ department_id: form.department_id });
    if (form.name?.trim()) params.append("product_name", form.name.trim());
    axios.get(`${API}/sku/preview?${params}`)
      .then(({ data }) => setSkuPreview(data.next_sku))
      .catch(() => setSkuPreview(null));
  }, [dialogOpen, editingProduct, form.department_id, form.name]);

  const fetchData = async () => {
    try {
      const [deptRes, vendorRes] = await Promise.all([
        axios.get(`${API}/departments`),
        axios.get(`${API}/vendors`),
      ]);
      setDepartments(deptRes.data);
      setVendors(vendorRes.data);
      await fetchProducts();
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.append("search", search);
      if (filterDept) params.append("department_id", filterDept);
      if (filterLowStock) params.append("low_stock", "true");
      params.append("limit", String(PAGE_SIZE));
      params.append("offset", String(page * PAGE_SIZE));

      const response = await axios.get(`${API}/products?${params}`);
      const data = response.data;
      if (data?.items != null) {
        setProducts(data.items);
        setTotalProducts(data.total ?? data.items.length);
      } else {
        setProducts(Array.isArray(data) ? data : []);
        setTotalProducts(Array.isArray(data) ? data.length : 0);
      }
    } catch (error) {
      console.error("Error fetching products:", error);
    }
  };

  const suggestUnit = useCallback(async () => {
    if (!form.name?.trim()) {
      toast.error("Enter a product name first");
      return;
    }
    setSuggestingUom(true);
    try {
      const { data } = await axios.post(`${API}/products/suggest-uom`, {
        name: form.name.trim(),
        description: form.description?.trim() || undefined,
      });
      setForm((f) => ({
        ...f,
        base_unit: data.base_unit || "each",
        sell_uom: data.sell_uom || "each",
        pack_qty: String(data.pack_qty ?? 1),
      }));
      toast.success("Unit suggested");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not suggest unit");
    } finally {
      setSuggestingUom(false);
    }
  }, [form.name, form.description]);

  const openDialog = (product = null) => {
    if (product) {
      setEditingProduct(product);
      setForm({
        name: product.name,
        description: product.description || "",
        price: product.price.toString(),
        cost: product.cost?.toString() || "",
        quantity: product.quantity.toString(),
        min_stock: product.min_stock?.toString() || "5",
        department_id: product.department_id,
        vendor_id: product.vendor_id || "",
        barcode: product.barcode || "",
        base_unit: product.base_unit || "each",
        sell_uom: product.sell_uom || "each",
        pack_qty: String(product.pack_qty ?? 1),
      });
    } else {
      setEditingProduct(null);
      setForm({
        name: "",
        description: "",
        price: "",
        cost: "",
        quantity: "",
        min_stock: "5",
        department_id: "",
        vendor_id: "",
        barcode: "",
        base_unit: "each",
        sell_uom: "each",
        pack_qty: "1",
      });
    }
    setDialogOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.price || !form.department_id) {
      toast.error("Please fill in required fields");
      return;
    }

    setSaving(true);
    try {
      const data = {
        name: form.name,
        description: form.description,
        price: parseFloat(form.price),
        cost: parseFloat(form.cost) || 0,
        quantity: parseInt(form.quantity) || 0,
        min_stock: parseInt(form.min_stock) || 5,
        department_id: form.department_id,
        vendor_id: form.vendor_id || null,
        barcode: form.barcode || null,
        base_unit: form.base_unit || "each",
        sell_uom: form.sell_uom || "each",
        pack_qty: parseInt(form.pack_qty) || 1,
      };

      if (editingProduct) {
        await axios.put(`${API}/products/${editingProduct.id}`, data);
        toast.success("Product updated!");
      } else {
        const { data: created } = await axios.post(`${API}/products`, data);
        toast.success(`Product created with SKU ${created?.sku ?? ""}`);
      }

      setDialogOpen(false);
      fetchProducts();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save product");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteClick = (product) => {
    setDetailProduct(null);
    setDeleteConfirm({ open: true, product });
  };

  const handleDeleteConfirm = async () => {
    const { product } = deleteConfirm;
    if (!product) return;
    try {
      await axios.delete(`${API}/products/${product.id}`);
      toast.success("Product deleted");
      fetchProducts();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete product");
      throw error;
    }
  };

  const handleAdjust = async (e) => {
    e.preventDefault();
    const delta = parseInt(adjustDelta, 10);
    if (isNaN(delta) || delta === 0) {
      toast.error("Enter a non-zero quantity delta");
      return;
    }
    if (!adjustProduct) return;
    setAdjusting(true);
    try {
      await axios.post(`${API}/products/${adjustProduct.id}/adjust`, {
        quantity_delta: delta,
        reason: adjustReason,
      });
      toast.success("Stock adjusted");
      setAdjustProduct(null);
      setAdjustDelta("");
      setAdjustReason("correction");
      fetchProducts();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to adjust stock");
    } finally {
      setAdjusting(false);
    }
  };

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedProducts = useMemo(() => {
    if (!sortKey) return products;
    return [...products].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      const cmp =
        typeof va === "number" && typeof vb === "number"
          ? va - vb
          : String(va ?? "").localeCompare(String(vb ?? ""));
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [products, sortKey, sortDir]);

  const totalPages = Math.ceil(totalProducts / PAGE_SIZE);

  const SortTh = ({ label, col, className = "" }) => {
    const active = sortKey === col;
    return (
      <th
        onClick={() => handleSort(col)}
        className={`cursor-pointer select-none hover:bg-slate-100 transition-colors ${className}`}
      >
        <span className="flex items-center gap-1">
          {label}
          {active ? (
            sortDir === "asc" ? (
              <ArrowUp className="w-3 h-3 text-amber-500" />
            ) : (
              <ArrowDown className="w-3 h-3 text-amber-500" />
            )
          ) : (
            <ArrowUpDown className="w-3 h-3 opacity-25" />
          )}
        </span>
      </th>
    );
  };

  const FieldTip = ({ children }) => (
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className="w-3.5 h-3.5 text-slate-400 cursor-help inline-block ml-1 align-middle" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[220px] text-center">
        {children}
      </TooltipContent>
    </Tooltip>
  );

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[50vh]">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          <span className="font-medium">Loading inventory…</span>
        </div>
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={300}>
    <div className="p-8" data-testid="inventory-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
            Inventory
          </h1>
          <p className="text-slate-500 mt-1 text-sm">{totalProducts} products</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setLabelsProducts(products);
              setLabelsModalOpen(true);
            }}
            className="h-12 px-6"
          >
            <Printer className="w-5 h-5 mr-2" />
            Print Labels
          </Button>
          <Button
            onClick={() => openDialog()}
            className="btn-primary h-12 px-6"
            data-testid="add-product-btn"
          >
            <Plus className="w-5 h-5 mr-2" />
            Add Product
          </Button>
        </div>
      </div>

      <BarcodeLabelsModal
        products={labelsProducts}
        open={labelsModalOpen}
        onOpenChange={setLabelsModalOpen}
      />

      <ProductDetailModal
        product={detailProduct}
        open={!!detailProduct}
        onOpenChange={(open) => !open && setDetailProduct(null)}
        onEdit={(p) => {
          setDetailProduct(null);
          openDialog(p);
        }}
        onAdjust={(p) => {
          setDetailProduct(null);
          setAdjustProduct(p);
          setAdjustDelta("");
          setAdjustReason("correction");
        }}
        onDelete={handleDeleteClick}
        onPrintLabels={(prods) => {
          setLabelsProducts(prods);
          setLabelsModalOpen(true);
        }}
        onViewHistory={(p) => {
          setDetailProduct(null);
          setStockHistoryProduct(p);
        }}
      />

      {/* SKU hint */}
      <p className="text-sm text-slate-500 mb-4">
        SKUs are auto-assigned (e.g. <span className="font-mono">LUM-00001</span>). Search by name, SKU, or barcode.
      </p>

      {/* Filters */}
      <div className="card-elevated p-5 mb-6" data-testid="inventory-filters">
        <div className="flex flex-wrap gap-4">
          <div className="flex-1 min-w-[250px] relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <Input
              type="text"
              placeholder="Search by name, SKU, or barcode..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input-workshop pl-12 w-full"
              data-testid="inventory-search-input"
            />
          </div>
          <select
            value={filterDept}
            onChange={(e) => setFilterDept(e.target.value)}
            className="input-workshop px-4 min-w-[180px]"
            data-testid="inventory-dept-filter"
          >
            <option value="">All Departments</option>
            {departments.map((dept) => (
              <option key={dept.id} value={dept.id}>
                {dept.name}
              </option>
            ))}
          </select>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => setFilterLowStock(!filterLowStock)}
                className={`h-11 px-4 border rounded-lg flex items-center gap-2 transition-all ${
                  filterLowStock
                    ? "border-amber-400 bg-amber-50 text-amber-700"
                    : "border-slate-200 hover:border-slate-300"
                }`}
                data-testid="inventory-low-stock-filter"
              >
                <AlertTriangle className="w-5 h-5" />
                Low Stock Only
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              Shows items where quantity ≤ min stock level
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Products Table */}
      <div className="card-elevated overflow-hidden rounded-xl" data-testid="inventory-table">
        <table className="w-full table-workshop">
          <thead>
            <tr>
              <SortTh label="SKU" col="sku" />
              <SortTh label="Product Name" col="name" />
              <SortTh label="Department" col="department_name" />
              <th>Unit</th>
              <SortTh label="Price" col="price" />
              <SortTh label="Cost" col="cost" />
              <SortTh label="Quantity" col="quantity" />
              <SortTh label="Status" col="quantity" />
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedProducts.length === 0 ? (
              <tr>
                <td colSpan="9" className="text-center py-12 text-slate-400">
                  <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>No products found</p>
                </td>
              </tr>
            ) : (
              sortedProducts.map((product) => (
                <tr
                  key={product.id}
                  data-testid={`product-row-${product.sku}`}
                  onClick={() => setDetailProduct(product)}
                  className="cursor-pointer hover:bg-slate-50/80 transition-colors"
                >
                  <td className="font-mono text-sm">{product.sku}</td>
                  <td>
                    <div>
                      <p className="font-semibold">{product.name}</p>
                      {product.original_sku && (
                        <p className="text-xs text-slate-400">
                          Orig: {product.original_sku}
                        </p>
                      )}
                    </div>
                  </td>
                  <td>{product.department_name}</td>
                  <td className="text-sm text-slate-600">
                    {product.sell_uom || "each"}
                    {(product.pack_qty || 1) > 1 ? ` ×${product.pack_qty}` : ""}
                  </td>
                  <td className="font-mono">${product.price.toFixed(2)}</td>
                  <td className="font-mono text-slate-500">
                    ${(product.cost || 0).toFixed(2)}
                  </td>
                  <td className="font-mono">{product.quantity}</td>
                  <td>
                    {product.quantity === 0 ? (
                      <span className="badge-error">Out of Stock</span>
                    ) : product.quantity <= product.min_stock ? (
                      <span className="badge-warning">Low Stock</span>
                    ) : (
                      <span className="badge-success">In Stock</span>
                    )}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => setDetailProduct(product)}
                      className="p-2 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-sm transition-colors"
                      title="View details"
                      data-testid={`product-detail-${product.sku}`}
                    >
                      <Info className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalProducts > PAGE_SIZE && (
        <div className="flex items-center justify-between mt-4 px-1">
          <p className="text-sm text-slate-500">
            Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalProducts)} of {totalProducts}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </Button>
            <div className="flex items-center gap-1.5 text-sm text-slate-600">
              <span>Page</span>
              <input
                type="number"
                min={1}
                max={totalPages}
                value={page + 1}
                onChange={(e) => {
                  const p = parseInt(e.target.value, 10) - 1;
                  if (!isNaN(p) && p >= 0 && p < totalPages) setPage(p);
                }}
                className="w-14 border border-slate-200 rounded px-2 py-1 text-center text-sm focus:outline-none focus:border-amber-400"
              />
              <span>of {totalPages}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={(page + 1) * PAGE_SIZE >= totalProducts}
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Product Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-lg rounded-2xl" data-testid="product-dialog">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">
              {editingProduct ? "Edit product" : "Add new product"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 pt-4">
            {/* SKU: immutable when editing, live preview when adding */}
            <div className={`rounded-lg px-4 py-3 ${editingProduct ? "bg-amber-50/50 border border-amber-200/60" : "bg-slate-50 border border-slate-200"}`}>
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  SKU
                </p>
                {editingProduct && (
                  <span className="text-[10px] font-medium text-amber-700 uppercase tracking-wider">
                    Cannot be changed
                  </span>
                )}
              </div>
              {editingProduct ? (
                <p className="font-mono text-lg font-semibold text-slate-900">
                  {editingProduct.sku}
                </p>
              ) : skuPreview ? (
                <p className="font-mono text-lg font-semibold text-slate-700">
                  {skuPreview}
                  <span className="text-xs font-normal text-slate-400 ml-2">
                    (assigned on save)
                  </span>
                </p>
              ) : (
                <p className="text-sm text-slate-400">Select a department to see SKU</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <Label className="text-slate-600 font-medium text-sm">
                  Product name *
                </Label>
                <Input
                  value={form.name}
                  onChange={(e) => {
                    const v = e.target.value;
                    setForm({ ...form, name: v });
                    if (suggestUomTimeout.current) clearTimeout(suggestUomTimeout.current);
                    if (!editingProduct && v.trim().length >= 3) {
                      suggestUomTimeout.current = setTimeout(() => {
                        axios.post(`${API}/products/suggest-uom`, { name: v.trim() })
                          .then(({ data }) => setForm((f) => ({
                            ...f,
                            base_unit: data.base_unit || "each",
                            sell_uom: data.sell_uom || "each",
                            pack_qty: String(data.pack_qty ?? 1),
                          })))
                          .catch(() => {});
                        suggestUomTimeout.current = null;
                      }, 600);
                    }
                  }}
                  placeholder="e.g., 2x4 Pine Board, 5 Gal Paint"
                  className="input-workshop mt-2"
                  data-testid="product-name-input"
                />
              </div>

              <div className="col-span-2">
                <Label className="text-slate-600 font-medium text-sm">
                  Description
                </Label>
                <Input
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Optional description"
                  className="input-workshop mt-2"
                  data-testid="product-description-input"
                />
              </div>

              <div>
                <Label className="text-slate-600 font-medium text-sm">
                  Department *
                </Label>
                <Select
                  value={form.department_id}
                  onValueChange={(value) => setForm({ ...form, department_id: value })}
                >
                  <SelectTrigger className="input-workshop mt-2" data-testid="product-department-select">
                    <SelectValue placeholder="Select department" />
                  </SelectTrigger>
                  <SelectContent>
                    {departments.map((dept) => (
                      <SelectItem key={dept.id} value={dept.id}>
                        <span className="font-mono font-medium">{dept.code}</span>
                        <span className="text-slate-400 mx-1.5">—</span>
                        {dept.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-slate-600 font-medium text-sm">
                  Vendor
                </Label>
                <Select
                  value={form.vendor_id || "none"}
                  onValueChange={(value) => setForm({ ...form, vendor_id: value === "none" ? "" : value })}
                >
                  <SelectTrigger className="input-workshop mt-2" data-testid="product-vendor-select">
                    <SelectValue placeholder="Select vendor" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {vendors.map((vendor) => (
                      <SelectItem key={vendor.id} value={vendor.id}>
                        {vendor.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-slate-600 font-medium text-sm">
                  Price *
                </Label>
                <Input
                  type="number"
                  step="0.01"
                  value={form.price}
                  onChange={(e) => setForm({ ...form, price: e.target.value })}
                  placeholder="0.00"
                  className="input-workshop mt-2"
                  data-testid="product-price-input"
                />
              </div>

              <div>
                <Label className="text-slate-600 font-medium text-sm">
                  Cost
                </Label>
                <Input
                  type="number"
                  step="0.01"
                  value={form.cost}
                  onChange={(e) => setForm({ ...form, cost: e.target.value })}
                  placeholder="0.00"
                  className="input-workshop mt-2"
                  data-testid="product-cost-input"
                />
              </div>

              <div>
                <Label className="text-slate-600 font-medium text-sm">
                  Quantity
                </Label>
                <Input
                  type="number"
                  value={form.quantity}
                  onChange={(e) => setForm({ ...form, quantity: e.target.value })}
                  placeholder="0"
                  className="input-workshop mt-2"
                  data-testid="product-quantity-input"
                />
              </div>

              <div>
                <Label className="text-slate-600 font-medium text-sm">
                  Min stock level
                  <FieldTip>Alert threshold — item shows as Low Stock when quantity falls to or below this number.</FieldTip>
                </Label>
                <Input
                  type="number"
                  value={form.min_stock}
                  onChange={(e) => setForm({ ...form, min_stock: e.target.value })}
                  placeholder="5"
                  className="input-workshop mt-2"
                  data-testid="product-min-stock-input"
                />
              </div>

              <div className="col-span-3 flex items-end gap-2 flex-wrap">
                <div className="flex-1 min-w-[100px]">
                  <Label className="text-slate-600 font-medium text-sm">
                    Base Unit
                    <FieldTip>The physical unit this product is stored and counted in (e.g. each, roll, gallon).</FieldTip>
                  </Label>
                  <Select value={form.base_unit} onValueChange={(v) => setForm({ ...form, base_unit: v })}>
                    <SelectTrigger className="input-workshop mt-2"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {UOM_OPTIONS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex-1 min-w-[100px]">
                  <Label className="text-slate-600 font-medium text-sm">
                    Sell Unit
                    <FieldTip>The unit shown to customers and used when issuing materials (e.g. box, case). Can differ from Base Unit.</FieldTip>
                  </Label>
                  <Select value={form.sell_uom} onValueChange={(v) => setForm({ ...form, sell_uom: v })}>
                    <SelectTrigger className="input-workshop mt-2"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {UOM_OPTIONS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="min-w-[80px]">
                  <Label className="text-slate-600 font-medium text-sm">
                    Pack Qty
                    <FieldTip>How many Base Units are in one Sell Unit. E.g. a box of 12 screws → Pack Qty = 12.</FieldTip>
                  </Label>
                  <Input type="number" min="1" value={form.pack_qty} onChange={(e) => setForm({ ...form, pack_qty: e.target.value })} className="input-workshop mt-2" />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={suggestUnit}
                  disabled={suggestingUom || !form.name?.trim()}
                  className="h-11 px-3 border-slate-200 mt-2"
                  title="Use AI to suggest unit from product name"
                >
                  {suggestingUom ? (
                    <span className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin block" />
                  ) : (
                    <Sparkles className="w-5 h-5 text-amber-500" />
                  )}
                  <span className="ml-2 text-sm">Suggest unit</span>
                </Button>
              </div>
              <div className="col-span-2">
                <Label className="text-slate-600 font-medium text-sm">Barcode</Label>
                <Input
                  value={form.barcode}
                  onChange={(e) => setForm({ ...form, barcode: e.target.value })}
                  placeholder="UPC (12 digits) or leave blank to use SKU"
                  className="input-workshop mt-2"
                  data-testid="product-barcode-input"
                />
                <p className="text-xs text-slate-500 mt-1">
                  UPC for vendor products; leave blank to use internal SKU (Code128)
                </p>
              </div>
            </div>

            <div className="flex gap-3 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
                className="flex-1 btn-secondary h-12"
                data-testid="product-cancel-btn"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={saving}
                className="flex-1 btn-primary h-12"
                data-testid="product-save-btn"
              >
                {saving ? "Saving..." : editingProduct ? "Update Product" : "Create Product"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <StockHistoryModal
        product={stockHistoryProduct}
        open={!!stockHistoryProduct}
        onOpenChange={(open) => !open && setStockHistoryProduct(null)}
      />

      <Dialog open={!!adjustProduct} onOpenChange={(open) => !open && setAdjustProduct(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Adjust Stock</DialogTitle>
            {adjustProduct && (
              <p className="text-sm text-slate-500">{adjustProduct.sku} — {adjustProduct.name}</p>
            )}
          </DialogHeader>
          <form onSubmit={handleAdjust} className="space-y-4 pt-4">
            <div>
              <Label>Quantity delta (positive to add, negative to remove)</Label>
              <Input
                type="number"
                value={adjustDelta}
                onChange={(e) => setAdjustDelta(e.target.value)}
                placeholder="e.g. 5 or -3"
                className="input-workshop mt-2"
              />
            </div>
            <div>
              <Label>Reason</Label>
              <Select value={adjustReason} onValueChange={setAdjustReason}>
                <SelectTrigger className="input-workshop mt-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="correction">Correction</SelectItem>
                  <SelectItem value="count">Count</SelectItem>
                  <SelectItem value="damage">Damage</SelectItem>
                  <SelectItem value="theft">Theft</SelectItem>
                  <SelectItem value="return">Return</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="button" variant="outline" onClick={() => setAdjustProduct(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={adjusting}>
                {adjusting ? "Adjusting..." : "Adjust"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteConfirm.open}
        onOpenChange={(open) => setDeleteConfirm((p) => ({ ...p, open }))}
        title="Delete product"
        description={deleteConfirm.product ? `Delete "${deleteConfirm.product.name}"? This cannot be undone.` : ""}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleDeleteConfirm}
        variant="danger"
      />
    </div>
    </TooltipProvider>
  );
};

export default Inventory;
