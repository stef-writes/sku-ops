import { useState, useEffect, useCallback } from "react";
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
  Plus,
  Edit2,
  Trash2,
  Users,
  Mail,
  Phone,
  MapPin,
  FileUp,
  Loader2,
  CheckCircle,
  Package,
  FileText,
} from "lucide-react";
import { EmptyState } from "../components/EmptyState";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Vendors = () => {
  const [vendors, setVendors] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState(null);
  const [saving, setSaving] = useState(false);

  // PDF Import State
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [selectedVendor, setSelectedVendor] = useState(null);
  const [pdfFile, setPdfFile] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [extractedProducts, setExtractedProducts] = useState([]);
  const [importing, setImporting] = useState(false);

  const [form, setForm] = useState({
    name: "",
    contact_name: "",
    email: "",
    phone: "",
    address: "",
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [vendorRes, deptRes] = await Promise.all([
        axios.get(`${API}/vendors`),
        axios.get(`${API}/departments`),
      ]);
      setVendors(vendorRes.data);
      setDepartments(deptRes.data);
    } catch (error) {
      console.error("Error fetching data:", error);
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const fetchVendors = async () => {
    try {
      const response = await axios.get(`${API}/vendors`);
      setVendors(response.data);
    } catch (error) {
      console.error("Error fetching vendors:", error);
    }
  };

  const openDialog = (vendor = null) => {
    if (vendor) {
      setEditingVendor(vendor);
      setForm({
        name: vendor.name,
        contact_name: vendor.contact_name || "",
        email: vendor.email || "",
        phone: vendor.phone || "",
        address: vendor.address || "",
      });
    } else {
      setEditingVendor(null);
      setForm({
        name: "",
        contact_name: "",
        email: "",
        phone: "",
        address: "",
      });
    }
    setDialogOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name) {
      toast.error("Vendor name is required");
      return;
    }

    setSaving(true);
    try {
      if (editingVendor) {
        await axios.put(`${API}/vendors/${editingVendor.id}`, form);
        toast.success("Vendor updated!");
      } else {
        await axios.post(`${API}/vendors`, form);
        toast.success("Vendor created!");
      }

      setDialogOpen(false);
      fetchVendors();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save vendor");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (vendor) => {
    if (!window.confirm(`Delete vendor "${vendor.name}"?`)) return;

    try {
      await axios.delete(`${API}/vendors/${vendor.id}`);
      toast.success("Vendor deleted");
      fetchVendors();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete vendor");
    }
  };

  // PDF Import Functions
  const openImportDialog = (vendor) => {
    setSelectedVendor(vendor);
    setPdfFile(null);
    setExtractedProducts([]);
    setImportDialogOpen(true);
  };

  const handlePdfChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.type !== "application/pdf") {
        toast.error("Please select a PDF file");
        return;
      }
      setPdfFile(file);
      setExtractedProducts([]);
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      if (file.type !== "application/pdf") {
        toast.error("Please select a PDF file");
        return;
      }
      setPdfFile(file);
      setExtractedProducts([]);
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
  }, []);

  const extractFromPdf = async () => {
    if (!pdfFile || !selectedVendor) return;

    setExtracting(true);
    try {
      const formData = new FormData();
      formData.append("file", pdfFile);

      const response = await axios.post(
        `${API}/vendors/${selectedVendor.id}/import-pdf`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );

      const products = response.data.products.map((p, idx) => ({
        ...p,
        id: idx,
        selected: true,
      }));

      setExtractedProducts(products);
      toast.success(`Extracted ${products.length} products from PDF`);
    } catch (error) {
      console.error("PDF extraction error:", error);
      toast.error(error.response?.data?.detail || "Failed to extract from PDF");
    } finally {
      setExtracting(false);
    }
  };

  const updateExtractedProduct = (id, field, value) => {
    setExtractedProducts(
      extractedProducts.map((p) =>
        p.id === id ? { ...p, [field]: value } : p
      )
    );
  };

  const toggleProduct = (id) => {
    setExtractedProducts(
      extractedProducts.map((p) =>
        p.id === id ? { ...p, selected: !p.selected } : p
      )
    );
  };

  const importProducts = async () => {
    if (!selectedVendor) return;

    const productsToImport = extractedProducts.filter((p) => p.selected);
    if (productsToImport.length === 0) {
      toast.error("No products selected");
      return;
    }

    setImporting(true);
    try {
      const response = await axios.post(
        `${API}/vendors/${selectedVendor.id}/import-products`,
        productsToImport
      );

      toast.success(`Imported ${response.data.imported} products!`);
      if (response.data.errors > 0) {
        toast.warning(`${response.data.errors} products failed to import`);
      }

      setImportDialogOpen(false);
      fetchVendors();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to import products");
    } finally {
      setImporting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">
          Loading Vendors...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="vendors-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">
            Vendors
          </h1>
          <p className="text-slate-600 mt-1">{vendors.length} vendors</p>
        </div>
        <Button
          onClick={() => openDialog()}
          className="btn-primary h-12 px-6"
          data-testid="add-vendor-btn"
        >
          <Plus className="w-5 h-5 mr-2" />
          Add Vendor
        </Button>
      </div>

      {/* Vendors Grid */}
      {vendors.length === 0 ? (
        <div className="card-workshop p-12">
          <EmptyState
            icon={Users}
            title="No vendors yet"
            description="Add vendors to track your suppliers"
            action={
              <Button onClick={() => openDialog()} className="btn-primary">
                <Plus className="w-5 h-5 mr-2" />
                Add First Vendor
              </Button>
            }
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="vendors-grid">
          {vendors.map((vendor) => (
            <div
              key={vendor.id}
              className="card-workshop p-6"
              data-testid={`vendor-card-${vendor.id}`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-slate-100 rounded-sm flex items-center justify-center">
                  <Users className="w-6 h-6 text-slate-600" />
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => openImportDialog(vendor)}
                    className="p-2 text-slate-600 hover:text-green-500 hover:bg-green-50 rounded-sm transition-colors"
                    title="Import PDF Invoice"
                    data-testid={`import-pdf-${vendor.id}`}
                  >
                    <FileUp className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => openDialog(vendor)}
                    className="p-2 text-slate-600 hover:text-orange-500 hover:bg-orange-50 rounded-sm transition-colors"
                    data-testid={`edit-vendor-${vendor.id}`}
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(vendor)}
                    className="p-2 text-slate-600 hover:text-red-500 hover:bg-red-50 rounded-sm transition-colors"
                    data-testid={`delete-vendor-${vendor.id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <h3 className="font-heading font-bold text-xl text-slate-900 uppercase tracking-wide mb-2">
                {vendor.name}
              </h3>

              {vendor.contact_name && (
                <p className="text-slate-600 mb-3">{vendor.contact_name}</p>
              )}

              <div className="space-y-2 text-sm text-slate-500">
                {vendor.email && (
                  <div className="flex items-center gap-2">
                    <Mail className="w-4 h-4" />
                    <span>{vendor.email}</span>
                  </div>
                )}
                {vendor.phone && (
                  <div className="flex items-center gap-2">
                    <Phone className="w-4 h-4" />
                    <span>{vendor.phone}</span>
                  </div>
                )}
                {vendor.address && (
                  <div className="flex items-center gap-2">
                    <MapPin className="w-4 h-4" />
                    <span className="truncate">{vendor.address}</span>
                  </div>
                )}
              </div>

              <div className="mt-4 pt-4 border-t border-slate-200 flex items-center justify-between">
                <span className="text-xs text-slate-400 uppercase tracking-wide">
                  {vendor.product_count || 0} products
                </span>
                <button
                  onClick={() => openImportDialog(vendor)}
                  className="text-xs text-orange-500 hover:text-orange-600 font-semibold flex items-center gap-1"
                  data-testid={`import-btn-${vendor.id}`}
                >
                  <FileText className="w-3 h-3" />
                  Import PDF
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Vendor Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="vendor-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
              {editingVendor ? "Edit Vendor" : "Add New Vendor"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 pt-4">
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Company Name *
              </Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g., ABC Hardware Supply"
                className="input-workshop mt-2"
                data-testid="vendor-name-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Contact Name
              </Label>
              <Input
                value={form.contact_name}
                onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
                placeholder="e.g., John Smith"
                className="input-workshop mt-2"
                data-testid="vendor-contact-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Email
              </Label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="vendor@example.com"
                className="input-workshop mt-2"
                data-testid="vendor-email-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Phone
              </Label>
              <Input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="(555) 123-4567"
                className="input-workshop mt-2"
                data-testid="vendor-phone-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Address
              </Label>
              <Input
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder="123 Main St, City, State"
                className="input-workshop mt-2"
                data-testid="vendor-address-input"
              />
            </div>

            <div className="flex gap-3 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
                className="flex-1 btn-secondary h-12"
                data-testid="vendor-cancel-btn"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={saving}
                className="flex-1 btn-primary h-12"
                data-testid="vendor-save-btn"
              >
                {saving ? "Saving..." : editingVendor ? "Update Vendor" : "Create Vendor"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* PDF Import Dialog */}
      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="import-pdf-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
              Import from PDF - {selectedVendor?.name}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-6 pt-4">
            {/* Upload Section */}
            {!pdfFile ? (
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onClick={() => document.getElementById("pdf-input").click()}
                className="border-2 border-dashed border-slate-300 rounded-md p-8 text-center hover:border-orange-400 transition-colors cursor-pointer"
                data-testid="pdf-dropzone"
              >
                <FileUp className="w-12 h-12 mx-auto mb-3 text-slate-400" />
                <p className="text-slate-600 font-medium">
                  Drop vendor invoice PDF here or click to browse
                </p>
                <p className="text-slate-400 text-sm mt-1">
                  Supports invoices from Home Depot, Lowes, and other suppliers
                </p>
                <input
                  id="pdf-input"
                  type="file"
                  accept=".pdf"
                  onChange={handlePdfChange}
                  className="hidden"
                  data-testid="pdf-file-input"
                />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-slate-50 rounded-sm border-2 border-slate-200">
                  <div className="flex items-center gap-3">
                    <FileText className="w-8 h-8 text-orange-500" />
                    <div>
                      <p className="font-medium text-slate-900">{pdfFile.name}</p>
                      <p className="text-xs text-slate-500">
                        {(pdfFile.size / 1024).toFixed(1)} KB
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setPdfFile(null);
                      setExtractedProducts([]);
                    }}
                    className="text-slate-400 hover:text-red-500"
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                </div>

                {extractedProducts.length === 0 && (
                  <Button
                    onClick={extractFromPdf}
                    disabled={extracting}
                    className="w-full btn-primary h-12"
                    data-testid="extract-pdf-btn"
                  >
                    {extracting ? (
                      <>
                        <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                        Analyzing PDF with AI...
                      </>
                    ) : (
                      <>
                        <Package className="w-5 h-5 mr-2" />
                        Extract Products
                      </>
                    )}
                  </Button>
                )}
              </div>
            )}

            {/* Extracted Products */}
            {extractedProducts.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-heading font-bold text-lg text-slate-900 uppercase tracking-wider">
                    Extracted Products ({extractedProducts.filter((p) => p.selected).length}/{extractedProducts.length})
                  </h3>
                </div>

                <div className="space-y-3 max-h-[400px] overflow-auto" data-testid="extracted-products">
                  {extractedProducts.map((product) => (
                    <div
                      key={product.id}
                      className={`p-4 border-2 rounded-sm transition-colors ${
                        product.selected
                          ? "border-orange-300 bg-orange-50"
                          : "border-slate-200 bg-slate-50 opacity-60"
                      }`}
                      data-testid={`extracted-product-${product.id}`}
                    >
                      <div className="flex items-start gap-3">
                        <button
                          onClick={() => toggleProduct(product.id)}
                          className={`mt-1 w-5 h-5 rounded-sm border-2 flex items-center justify-center flex-shrink-0 ${
                            product.selected
                              ? "bg-orange-500 border-orange-500 text-white"
                              : "border-slate-300"
                          }`}
                        >
                          {product.selected && <CheckCircle className="w-4 h-4" />}
                        </button>

                        <div className="flex-1 space-y-3">
                          <div>
                            <Input
                              value={product.name}
                              onChange={(e) =>
                                updateExtractedProduct(product.id, "name", e.target.value)
                              }
                              className="input-workshop h-10"
                              placeholder="Product name"
                            />
                            {product.original_sku && (
                              <p className="text-xs text-slate-400 mt-1">
                                Original SKU: {product.original_sku}
                              </p>
                            )}
                          </div>

                          <div className="grid grid-cols-4 gap-2">
                            <div>
                              <Label className="text-xs text-slate-500">Qty</Label>
                              <Input
                                type="number"
                                value={product.quantity}
                                onChange={(e) =>
                                  updateExtractedProduct(product.id, "quantity", e.target.value)
                                }
                                className="input-workshop h-10 text-sm"
                              />
                            </div>
                            <div>
                              <Label className="text-xs text-slate-500">Price</Label>
                              <Input
                                type="number"
                                step="0.01"
                                value={product.price}
                                onChange={(e) =>
                                  updateExtractedProduct(product.id, "price", e.target.value)
                                }
                                className="input-workshop h-10 text-sm"
                              />
                            </div>
                            <div>
                              <Label className="text-xs text-slate-500">Cost</Label>
                              <Input
                                type="number"
                                step="0.01"
                                value={product.cost || ""}
                                onChange={(e) =>
                                  updateExtractedProduct(product.id, "cost", e.target.value)
                                }
                                className="input-workshop h-10 text-sm"
                              />
                            </div>
                            <div>
                              <Label className="text-xs text-slate-500">Dept</Label>
                              <Select
                                value={product.suggested_department || "HDW"}
                                onValueChange={(value) =>
                                  updateExtractedProduct(product.id, "suggested_department", value)
                                }
                              >
                                <SelectTrigger className="input-workshop h-10 text-sm">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {departments.map((dept) => (
                                    <SelectItem key={dept.code} value={dept.code}>
                                      {dept.code}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <Button
                  onClick={importProducts}
                  disabled={importing || extractedProducts.filter((p) => p.selected).length === 0}
                  className="w-full btn-primary h-12"
                  data-testid="import-products-btn"
                >
                  {importing ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                      Importing...
                    </>
                  ) : (
                    <>
                      <CheckCircle className="w-5 h-5 mr-2" />
                      Import {extractedProducts.filter((p) => p.selected).length} Products to Inventory
                    </>
                  )}
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Vendors;
