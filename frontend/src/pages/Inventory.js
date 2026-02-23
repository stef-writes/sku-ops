import { useState, useEffect } from "react";
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
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Inventory = () => {
  const [products, setProducts] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [search, setSearch] = useState("");
  const [filterDept, setFilterDept] = useState("");
  const [filterLowStock, setFilterLowStock] = useState(false);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [saving, setSaving] = useState(false);

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
  });

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    fetchProducts();
  }, [search, filterDept, filterLowStock]);

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

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">
          Loading Inventory...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="inventory-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">
            Inventory
          </h1>
          <p className="text-slate-600 mt-1">{products.length} products</p>
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
      <div className="card-workshop p-4 mb-6" data-testid="inventory-filters">
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
            className={`h-12 px-4 border-2 rounded-sm flex items-center gap-2 transition-colors ${
              filterLowStock
                ? "border-orange-500 bg-orange-50 text-orange-700"
                : "border-slate-300 hover:border-slate-400"
            }`}
            data-testid="inventory-low-stock-filter"
          >
            <AlertTriangle className="w-5 h-5" />
            Low Stock Only
          </button>
        </div>
      </div>

      {/* Products Table */}
      <div className="card-workshop overflow-hidden" data-testid="inventory-table">
        <table className="w-full table-workshop">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Product Name</th>
              <th>Department</th>
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
                <td colSpan="8" className="text-center py-12 text-slate-400">
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
                        onClick={() => openDialog(product)}
                        className="p-2 text-slate-600 hover:text-orange-500 hover:bg-orange-50 rounded-sm transition-colors"
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
        <DialogContent className="sm:max-w-lg" data-testid="product-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
              {editingProduct ? "Edit Product" : "Add New Product"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 pt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                  Product Name *
                </Label>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g., 2x4 Pine Board"
                  className="input-workshop mt-2"
                  data-testid="product-name-input"
                />
              </div>

              <div className="col-span-2">
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
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
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
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
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                  Vendor
                </Label>
                <Select
                  value={form.vendor_id}
                  onValueChange={(value) => setForm({ ...form, vendor_id: value })}
                >
                  <SelectTrigger className="input-workshop mt-2" data-testid="product-vendor-select">
                    <SelectValue placeholder="Select vendor" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">None</SelectItem>
                    {vendors.map((vendor) => (
                      <SelectItem key={vendor.id} value={vendor.id}>
                        {vendor.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
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
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
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
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
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
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                  Min Stock Level
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

              <div className="col-span-2">
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                  Barcode
                </Label>
                <Input
                  value={form.barcode}
                  onChange={(e) => setForm({ ...form, barcode: e.target.value })}
                  placeholder="Optional barcode"
                  className="input-workshop mt-2"
                  data-testid="product-barcode-input"
                />
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
    </div>
  );
};

export default Inventory;
