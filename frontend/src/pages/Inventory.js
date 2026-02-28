import { useState, useEffect, useCallback, useRef } from "react";
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
  Edit2,
  Trash2,
  Package,
  AlertTriangle,
  X,
  History,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { StockHistoryModal } from "../components/StockHistoryModal";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const UOM_OPTIONS = [
  "each", "case", "box", "pack", "bag", "roll", "gallon", "quart", "pint",
  "liter", "pound", "ounce", "foot", "meter", "yard", "sqft", "kit",
];

const Inventory = () => {
  const [searchParams] = useSearchParams();
  const [products, setProducts] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [search, setSearch] = useState("");
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
    fetchProducts();
  }, [search, filterDept, filterLowStock]);

  useEffect(() => {
    return () => {
      if (suggestUomTimeout.current) clearTimeout(suggestUomTimeout.current);
    };
  }, []);

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

      const response = await axios.get(`${API}/products?${params}`);
      setProducts(response.data);
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
        await axios.post(`${API}/products`, data);
        toast.success("Product created!");
      }

      setDialogOpen(false);
      fetchProducts();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save product");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (product) => {
    if (!window.confirm(`Delete "${product.name}"?`)) return;

    try {
      await axios.delete(`${API}/products/${product.id}`);
      toast.success("Product deleted");
      fetchProducts();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete product");
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
    <div className="p-8" data-testid="inventory-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
            Inventory
          </h1>
          <p className="text-slate-500 mt-1 text-sm">{products.length} products</p>
        </div>
        <Button
          onClick={() => openDialog()}
          className="btn-primary h-12 px-6"
          data-testid="add-product-btn"
        >
          <Plus className="w-5 h-5 mr-2" />
          Add Product
        </Button>
      </div>

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
        </div>
      </div>

      {/* Products Table */}
      <div className="card-elevated overflow-hidden rounded-xl" data-testid="inventory-table">
        <table className="w-full table-workshop">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Product Name</th>
              <th>Department</th>
              <th>Unit</th>
              <th>Price</th>
              <th>Cost</th>
              <th>Quantity</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {products.length === 0 ? (
              <tr>
                <td colSpan="9" className="text-center py-12 text-slate-400">
                  <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>No products found</p>
                </td>
              </tr>
            ) : (
              products.map((product) => (
                <tr key={product.id} data-testid={`product-row-${product.sku}`}>
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
                  <td>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setStockHistoryProduct(product)}
                        className="p-2 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-sm transition-colors"
                        title="Stock history"
                      >
                        <History className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          setAdjustProduct(product);
                          setAdjustDelta("");
                          setAdjustReason("correction");
                        }}
                        className="p-2 text-slate-600 hover:text-green-600 hover:bg-green-50 rounded-sm transition-colors"
                        title="Adjust stock"
                      >
                        <SlidersHorizontal className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => openDialog(product)}
                        className="p-2 text-slate-600 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors"
                        data-testid={`edit-product-${product.sku}`}
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(product)}
                        className="p-2 text-slate-600 hover:text-red-500 hover:bg-red-50 rounded-sm transition-colors"
                        data-testid={`delete-product-${product.sku}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Product Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-lg rounded-2xl" data-testid="product-dialog">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">
              {editingProduct ? "Edit product" : "Add new product"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 pt-4">
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
                  <Label className="text-slate-600 font-medium text-sm">Base Unit</Label>
                  <Select value={form.base_unit} onValueChange={(v) => setForm({ ...form, base_unit: v })}>
                    <SelectTrigger className="input-workshop mt-2"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {UOM_OPTIONS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex-1 min-w-[100px]">
                  <Label className="text-slate-600 font-medium text-sm">Sell Unit</Label>
                  <Select value={form.sell_uom} onValueChange={(v) => setForm({ ...form, sell_uom: v })}>
                    <SelectTrigger className="input-workshop mt-2"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {UOM_OPTIONS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="min-w-[80px]">
                  <Label className="text-slate-600 font-medium text-sm">Pack Qty</Label>
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
                <Input value={form.barcode} onChange={(e) => setForm({ ...form, barcode: e.target.value })} placeholder="Optional barcode" className="input-workshop mt-2" data-testid="product-barcode-input" />
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
    </div>
  );
};

export default Inventory;
