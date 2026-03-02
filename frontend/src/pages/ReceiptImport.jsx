import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Upload,
  FileImage,
  ClipboardList,
  XCircle,
  CheckCircle,
  Package,
  Loader2,
  Trash2,
  Sparkles,
  FileSpreadsheet,
  FileText,
  Search,
  Link2,
  Plus,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Checkbox } from "@/components/ui/checkbox";
import { API } from "@/lib/api";

const UOM_OPTIONS = [
  "each", "foot", "sqft", "yard", "meter",
  "gallon", "quart", "pint", "liter",
  "pound", "ounce",
  "box", "pack", "bag", "case", "roll", "kit",
];

const ReceiptImport = () => {
  const navigate = useNavigate();
  const [departments, setDepartments] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [selectedDept, setSelectedDept] = useState("");
  const [selectedVendor, setSelectedVendor] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [createVendorIfMissing, setCreateVendorIfMissing] = useState(true);
  const [vendorName, setVendorName] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [extractedData, setExtractedData] = useState(null);
  const [editedProducts, setEditedProducts] = useState([]);
  const [csvFile, setCsvFile] = useState(null);
  const [csvImporting, setCsvImporting] = useState(false);
  const [csvResult, setCsvResult] = useState(null);
  // product_id → { matched: product|null, options: [], searching: false, query: "" }
  const [productMatches, setProductMatches] = useState({});

  useEffect(() => {
    fetchDepartments();
    fetchVendors();
  }, []);

  const fetchDepartments = async () => {
    try {
      const response = await axios.get(`${API}/departments`);
      setDepartments(response.data);
    } catch (error) {
      console.error("Error fetching departments:", error);
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

  const isImageOrPdf = (file) => {
    if (!file) return false;
    const t = file.type?.toLowerCase() || "";
    const n = (file.name || "").toLowerCase();
    return t.startsWith("image/") || t === "application/pdf" || n.endsWith(".pdf");
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      if (!isImageOrPdf(selectedFile)) {
        toast.error("Please select an image (JPG, PNG, WEBP) or PDF");
        return;
      }
      setFile(selectedFile);
      setPreview(selectedFile.type?.startsWith("image/") ? URL.createObjectURL(selectedFile) : null);
      setExtractedData(null);
      setEditedProducts([]);
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      if (!isImageOrPdf(droppedFile)) {
        toast.error("Please select an image (JPG, PNG, WEBP) or PDF");
        return;
      }
      setFile(droppedFile);
      setPreview(droppedFile.type?.startsWith("image/") ? URL.createObjectURL(droppedFile) : null);
      setExtractedData(null);
      setEditedProducts([]);
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
  }, []);

  const extractReceipt = async (useAi = false) => {
    if (!file) {
      toast.error("Please select a document (image or PDF)");
      return;
    }

    setExtracting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const url = `${API}/documents/parse${useAi ? "?use_ai=true" : ""}`;
      const response = await axios.post(url, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setExtractedData(response.data);
      setVendorName(response.data.vendor_name || "");
      const mapped = (response.data.products || []).map((p, idx) => ({
        ...p,
        id: idx,
        selected: true,
        quantity: p.quantity ?? 1,
        ordered_qty: p.ordered_qty ?? p.quantity ?? 1,
        delivered_qty: p.delivered_qty ?? p.quantity ?? 1,
        base_unit: p.base_unit || "each",
        pack_qty: p.pack_qty ?? 1,
        min_stock: 5,
        matched_product: null,
      }));
      setEditedProducts(mapped);
      toast.success("Document extracted successfully!");
      autoMatch(mapped);
    } catch (error) {
      console.error("Extraction error:", error);
      const detail = error.response?.data?.detail || "Failed to extract document";
      if (error.response?.status === 503) {
        toast.error("AI not configured — add ANTHROPIC_API_KEY to backend/.env, or use free OCR instead");
      } else {
        toast.error(detail);
      }
    } finally {
      setExtracting(false);
    }
  };

  const updateProduct = (id, field, value) => {
    setEditedProducts(
      editedProducts.map((p) => (p.id === id ? { ...p, [field]: value } : p))
    );
  };

  const toggleProduct = (id) => {
    setEditedProducts(
      editedProducts.map((p) =>
        p.id === id ? { ...p, selected: !p.selected } : p
      )
    );
  };

  const removeProduct = (id) => {
    setEditedProducts(editedProducts.filter((p) => p.id !== id));
  };

  const saveAsPurchaseOrder = async () => {
    const vName = (vendorName || extractedData?.vendor_name || "").trim();
    if (!vName) {
      toast.error("Vendor name is required");
      return;
    }

    const productsToSave = editedProducts
      .filter((p) => p.selected)
      .map((p) => ({
        name: p.name,
        quantity: parseInt(p.quantity) || 1,
        ordered_qty: p.ordered_qty != null ? parseInt(p.ordered_qty) : parseInt(p.quantity) || 1,
        delivered_qty: p.delivered_qty != null ? parseInt(p.delivered_qty) : parseInt(p.quantity) || 1,
        price: parseFloat(p.price) || 0,
        cost: p.cost != null ? parseFloat(p.cost) : undefined,
        original_sku: p.original_sku,
        base_unit: p.base_unit || undefined,
        sell_uom: p.sell_uom || p.base_unit || undefined,
        pack_qty: p.pack_qty != null ? parseInt(p.pack_qty) : undefined,
        suggested_department: p.suggested_department || undefined,
        min_stock: p.min_stock != null ? parseInt(p.min_stock) : 5,
        product_id: p.matched_product?.id || undefined,
        _ai_parsed: p._ai_parsed || false,
        selected: true,
      }));

    if (productsToSave.length === 0) {
      toast.error("No products selected");
      return;
    }

    setImporting(true);
    try {
      await axios.post(`${API}/purchase-orders`, {
        vendor_name: vName,
        create_vendor_if_missing: createVendorIfMissing,
        department_id: selectedDept || null,
        document_date: extractedData?.document_date || null,
        total: extractedData?.total || null,
        products: productsToSave,
      });

      toast.success(`Purchase order saved — ${productsToSave.length} item(s) pending receipt`);
      setFile(null);
      setPreview(null);
      setExtractedData(null);
      setEditedProducts([]);
      setVendorName("");
      navigate("/purchase-orders");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save purchase order");
    } finally {
      setImporting(false);
    }
  };

  const clearAll = () => {
    setFile(null);
    setPreview(null);
    setExtractedData(null);
    setEditedProducts([]);
    setVendorName("");
    setProductMatches({});
  };

  // Fire a name search for every extracted item in parallel to find inventory matches
  const autoMatch = async (products) => {
    const updates = {};
    await Promise.all(
      products.map(async (p) => {
        if (!p.name?.trim()) return;
        try {
          const res = await axios.get(`${API}/products?search=${encodeURIComponent(p.name)}&limit=5`);
          const options = Array.isArray(res.data) ? res.data : (res.data?.items || []);
          updates[p.id] = { matched: null, options, searching: false, query: "" };
        } catch {
          updates[p.id] = { matched: null, options: [], searching: false, query: "" };
        }
      })
    );
    setProductMatches((prev) => ({ ...prev, ...updates }));
  };

  const searchMatch = async (itemId, query) => {
    setProductMatches((prev) => ({ ...prev, [itemId]: { ...prev[itemId], searching: true, query } }));
    try {
      const res = await axios.get(`${API}/products?search=${encodeURIComponent(query)}&limit=5`);
      const options = Array.isArray(res.data) ? res.data : (res.data?.items || []);
      setProductMatches((prev) => ({ ...prev, [itemId]: { ...prev[itemId], options, searching: false } }));
    } catch {
      setProductMatches((prev) => ({ ...prev, [itemId]: { ...prev[itemId], searching: false } }));
    }
  };

  const confirmMatch = (itemId, product) => {
    setEditedProducts((prev) => prev.map((p) => p.id === itemId ? { ...p, matched_product: product } : p));
    setProductMatches((prev) => ({ ...prev, [itemId]: { ...prev[itemId], matched: product, query: "", options: [] } }));
  };

  const clearMatch = (itemId) => {
    setEditedProducts((prev) => prev.map((p) => p.id === itemId ? { ...p, matched_product: null } : p));
    setProductMatches((prev) => ({ ...prev, [itemId]: { ...prev[itemId], matched: null } }));
  };

  const handleCsvFileChange = (e) => {
    const selected = e.target.files?.[0];
    if (selected?.name?.toLowerCase().endsWith(".csv")) {
      setCsvFile(selected);
      setCsvResult(null);
    } else if (selected) {
      toast.error("Please select a CSV file");
    }
  };

  const importCsv = async () => {
    if (!csvFile || !selectedDept) {
      toast.error("Select a department and CSV file");
      return;
    }
    setCsvImporting(true);
    setCsvResult(null);
    try {
      const formData = new FormData();
      formData.append("file", csvFile);
      formData.append("department_id", selectedDept);
      if (selectedVendor) formData.append("vendor_id", selectedVendor);

      const response = await axios.post(`${API}/products/import-csv`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setCsvResult(response.data);
      toast.success(`Imported ${response.data.imported} products`);
      if (response.data.errors > 0) {
        toast.warning(`${response.data.errors} rows had errors`);
      }
      if (response.data.warnings?.length > 0) {
        toast.info(`${response.data.warnings.length} product(s) had invalid barcode; SKU used instead`);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "CSV import failed");
    } finally {
      setCsvImporting(false);
    }
  };

  return (
    <div className="p-8" data-testid="receipt-import-page">
      {/* Header with AI badge */}
      <div className="mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-100 border border-slate-200 mb-4">
          <Package className="w-4 h-4 text-slate-600" />
          <span className="text-sm font-medium text-slate-700">Inventory</span>
        </div>
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
          Receive Inventory
        </h1>
        <p className="text-slate-500 mt-1 text-sm">
          Upload a delivery receipt or vendor invoice to add products to stock; or bulk import from CSV
        </p>
      </div>

      <Tabs defaultValue="receipt" className="mt-4">
        <TabsList className="mb-4">
          <TabsTrigger value="receipt">Document</TabsTrigger>
          <TabsTrigger value="csv">CSV Bulk Import</TabsTrigger>
        </TabsList>

        <TabsContent value="receipt">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upload Section */}
        <div
          className="card-elevated p-6 border-violet-100"
          data-testid="upload-section"
        >
          <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <span className="w-7 h-7 rounded-lg bg-violet-100 text-violet-600 flex items-center justify-center text-sm font-bold">
              1
            </span>
            Upload document
          </h2>

          {!file ? (
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className="border-2 border-dashed border-slate-200 rounded-2xl p-12 text-center hover:border-violet-300 hover:bg-violet-50/30 transition-all cursor-pointer group"
              onClick={() => document.getElementById("receipt-input").click()}
              data-testid="upload-dropzone"
            >
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-100 to-amber-50 flex items-center justify-center mx-auto mb-4 group-hover:scale-105 transition-transform">
                <Upload className="w-7 h-7 text-violet-500" />
              </div>
              <p className="text-slate-600 font-medium">
                Drop document here or click to browse
              </p>
              <p className="text-slate-400 text-sm mt-2">
                Supports JPG, PNG, WEBP, PDF
              </p>
              <input
                id="receipt-input"
                type="file"
                accept="image/*,application/pdf"
                onChange={handleFileChange}
                className="hidden"
                data-testid="receipt-file-input"
              />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="relative rounded-xl overflow-hidden border border-slate-200 shadow-sm">
                {preview ? (
                  <img
                    src={preview}
                    alt="Document preview"
                    className="w-full max-h-[400px] object-contain bg-slate-50"
                    data-testid="receipt-preview"
                  />
                ) : (
                  <div className="w-full h-48 bg-slate-50 flex flex-col items-center justify-center gap-2">
                    <FileText className="w-12 h-12 text-slate-400" />
                    <span className="text-slate-600 font-medium">{file.name}</span>
                    <span className="text-slate-400 text-sm">PDF document</span>
                  </div>
                )}
                <button
                  onClick={clearAll}
                  className="absolute top-3 right-3 p-2 bg-white/90 backdrop-blur-sm text-slate-600 rounded-xl hover:bg-red-50 hover:text-red-600 border border-slate-200 shadow-sm transition-colors"
                  data-testid="clear-receipt-btn"
                >
                  <XCircle className="w-5 h-5" />
                </button>
              </div>

              <div className="flex items-center gap-2 text-sm text-slate-500">
                {preview ? <FileImage className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                <span>{file?.name}</span>
              </div>

              <div className="grid grid-cols-2 gap-2" data-testid="extract-btn">
                <Button
                  onClick={() => extractReceipt(true)}
                  disabled={extracting}
                  className="btn-primary h-11"
                >
                  {extracting ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4 mr-2" />
                  )}
                  Extract with AI
                </Button>
                <Button
                  onClick={() => extractReceipt(false)}
                  disabled={extracting}
                  variant="outline"
                  className="h-11 text-slate-600"
                >
                  {extracting ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <FileText className="w-4 h-4 mr-2" />
                  )}
                  Free OCR
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Extracted Products Section */}
        <div className="card-elevated p-6" data-testid="extracted-section">
          <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <span className="w-7 h-7 rounded-lg bg-amber-100 text-amber-600 flex items-center justify-center text-sm font-bold">
              2
            </span>
            Review & import
          </h2>

          {!extractedData ? (
            <div className="text-center py-16 text-slate-400">
              <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
                <Package className="w-7 h-7 text-slate-400" />
              </div>
              <p className="font-medium">Upload and extract a document to see products</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <Label className="text-slate-600 font-medium text-sm">Vendor *</Label>
                <Input
                  value={vendorName}
                  onChange={(e) => setVendorName(e.target.value)}
                  className="input-field mt-2"
                  placeholder="Vendor / store name"
                  data-testid="vendor-name-input"
                />
              </div>

              <div className="flex items-center gap-2">
                <Checkbox
                  id="create-vendor"
                  checked={createVendorIfMissing}
                  onCheckedChange={(c) => setCreateVendorIfMissing(c === true)}
                />
                <Label htmlFor="create-vendor" className="text-sm text-slate-600 cursor-pointer">
                  Create vendor if missing
                </Label>
              </div>

              <div>
                <Label className="text-slate-600 font-medium text-sm">Department override (optional)</Label>
                <Select value={selectedDept || "none"} onValueChange={(v) => setSelectedDept(v === "none" ? "" : v)}>
                  <SelectTrigger
                    className="input-field mt-2"
                    data-testid="import-dept-select"
                  >
                    <SelectValue placeholder="Use suggested per product" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Use suggested per product</SelectItem>
                    {departments.map((dept) => (
                      <SelectItem key={dept.id} value={dept.id}>
                        {dept.name} ({dept.code})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div
                className="space-y-3 max-h-[350px] overflow-auto"
                data-testid="extracted-products-list"
              >
                {editedProducts.map((product) => (
                  <div
                    key={product.id}
                    className={`p-4 rounded-xl border transition-all ${
                      product.selected
                        ? "border-amber-200 bg-amber-50/50"
                        : "border-slate-200 bg-slate-50/50 opacity-60"
                    }`}
                    data-testid={`extracted-product-${product.id}`}
                  >
                    <div className="flex items-start gap-3">
                      <button
                        onClick={() => toggleProduct(product.id)}
                        className={`mt-1 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-colors ${
                          product.selected
                            ? "bg-amber-500 border-amber-500 text-white"
                            : "border-slate-300"
                        }`}
                        data-testid={`toggle-product-${product.id}`}
                      >
                        {product.selected && (
                          <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                        )}
                      </button>

                      <div className="flex-1 min-w-0 space-y-2">
                        <Input
                          value={product.name}
                          onChange={(e) =>
                            updateProduct(product.id, "name", e.target.value)
                          }
                          className="input-field h-10 text-sm"
                          placeholder="Product name"
                          data-testid={`product-name-${product.id}`}
                        />
                        <div className="grid grid-cols-2 gap-2">
                          <Input
                            type="number"
                            value={product.delivered_qty ?? product.quantity ?? 1}
                            onChange={(e) =>
                              updateProduct(product.id, "delivered_qty", e.target.value)
                            }
                            className="input-field h-10 text-sm"
                            placeholder="Delivered"
                            data-testid={`product-delivered-${product.id}`}
                          />
                          <Input
                            type="number"
                            step="0.01"
                            value={product.price}
                            onChange={(e) =>
                              updateProduct(product.id, "price", e.target.value)
                            }
                            className="input-field h-10 text-sm"
                            placeholder="Price"
                            data-testid={`product-price-${product.id}`}
                          />
                          <Input
                            type="number"
                            step="0.01"
                            value={product.cost ?? ""}
                            onChange={(e) =>
                              updateProduct(product.id, "cost", e.target.value ? parseFloat(e.target.value) : null)
                            }
                            className="input-field h-10 text-sm"
                            placeholder="Cost"
                            data-testid={`product-cost-${product.id}`}
                          />
                          <Input
                            value={product.suggested_department ?? ""}
                            onChange={(e) =>
                              updateProduct(product.id, "suggested_department", e.target.value || null)
                            }
                            className="input-field h-10 text-sm"
                            placeholder="Dept (PLU, HDW…)"
                            data-testid={`product-dept-${product.id}`}
                          />
                        </div>
                        {/* UOM row — always show so user can verify/correct */}
                        <div className="grid grid-cols-[1fr_auto] gap-2 items-center">
                          <select
                            value={product.base_unit || "each"}
                            onChange={(e) =>
                              updateProduct(product.id, "base_unit", e.target.value)
                            }
                            className="input-field h-10 text-sm bg-white"
                            data-testid={`product-unit-${product.id}`}
                          >
                            {UOM_OPTIONS.map((u) => (
                              <option key={u} value={u}>{u}</option>
                            ))}
                          </select>
                          <Input
                            type="number"
                            min="1"
                            value={product.pack_qty ?? 1}
                            onChange={(e) =>
                              updateProduct(product.id, "pack_qty", parseInt(e.target.value) || 1)
                            }
                            className="input-field h-10 text-sm w-20"
                            placeholder="Qty"
                            data-testid={`product-packqty-${product.id}`}
                          />
                        </div>
                        {product.original_sku && (
                          <p className="text-xs text-slate-400 font-mono">
                            Original: {product.original_sku}
                          </p>
                        )}
                      </div>

                      <button
                        onClick={() => removeProduct(product.id)}
                        className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0"
                        data-testid={`remove-product-${product.id}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-200">
                <p className="text-sm text-slate-600">
                  <strong>{editedProducts.filter((p) => p.selected).length}</strong> of{" "}
                  {editedProducts.length} products selected for import
                </p>
              </div>

              <Button
                onClick={saveAsPurchaseOrder}
                disabled={importing || !(vendorName || "").trim()}
                className="w-full btn-primary h-11"
                data-testid="import-products-btn"
              >
                {importing ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Saving…
                  </>
                ) : (
                  <>
                    <ClipboardList className="w-5 h-5 mr-2" />
                    Save as Purchase Order
                  </>
                )}
              </Button>
            </div>
          )}
        </div>
      </div>
        </TabsContent>

        <TabsContent value="csv">
          <div className="card-elevated p-6 max-w-2xl border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5 text-emerald-600" />
              Bulk import from CSV
            </h2>
            <p className="text-slate-600 text-sm mb-4">
              Supply Yard format: Product, SKU, Barcode, On hand, Reorder point, Unit cost, Retail price, Department
            </p>

            <div className="space-y-4">
              <div>
                <Label className="text-slate-600 font-medium text-sm">Department *</Label>
                <Select value={selectedDept} onValueChange={setSelectedDept}>
                  <SelectTrigger className="input-field mt-2">
                    <SelectValue placeholder="Select department" />
                  </SelectTrigger>
                  <SelectContent>
                    {departments.map((d) => (
                      <SelectItem key={d.id} value={d.id}>
                        {d.name} ({d.code})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-slate-600 font-medium text-sm">Vendor (optional)</Label>
                <Select value={selectedVendor} onValueChange={setSelectedVendor}>
                  <SelectTrigger className="input-field mt-2">
                    <SelectValue placeholder="None" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">None</SelectItem>
                    {vendors.map((v) => (
                      <SelectItem key={v.id} value={v.id}>
                        {v.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files?.[0];
                  if (f?.name?.toLowerCase().endsWith(".csv")) {
                    setCsvFile(f);
                    setCsvResult(null);
                  }
                }}
                onDragOver={(e) => e.preventDefault()}
                className="border-2 border-dashed border-slate-200 rounded-xl p-8 text-center hover:border-emerald-300 cursor-pointer"
                onClick={() => document.getElementById("csv-input").click()}
              >
                <input
                  id="csv-input"
                  type="file"
                  accept=".csv"
                  onChange={handleCsvFileChange}
                  className="hidden"
                />
                <FileSpreadsheet className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
                <p className="text-slate-600 font-medium">
                  {csvFile ? csvFile.name : "Drop CSV or click to browse"}
                </p>
              </div>

              {csvResult && (
                <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-sm">
                  <p className="font-medium text-slate-900">
                    Imported {csvResult.imported} products
                    {csvResult.errors > 0 && ` · ${csvResult.errors} errors`}
                    {csvResult.warnings?.length > 0 && ` · ${csvResult.warnings.length} barcode warnings`}
                  </p>
                  {csvResult.error_details?.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-slate-500">View errors</summary>
                      <ul className="mt-2 space-y-1 text-slate-600 text-xs max-h-32 overflow-auto">
                        {csvResult.error_details.map((e, i) => (
                          <li key={i}>{e.product}: {e.error}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {csvResult.warnings?.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-amber-600">View barcode warnings</summary>
                      <ul className="mt-2 space-y-1 text-slate-600 text-xs max-h-32 overflow-auto">
                        {csvResult.warnings.map((w, i) => (
                          <li key={i}>{w.product}: {w.warning}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}

              <Button
                onClick={importCsv}
                disabled={csvImporting || !csvFile || !selectedDept}
                className="w-full btn-primary h-11"
              >
                {csvImporting ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Importing…
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5 mr-2" />
                    Import CSV
                  </>
                )}
              </Button>
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* How It Works - AI focus */}
      <div className="card-elevated p-6 mt-8 bg-gradient-to-br from-slate-50 to-violet-50/30 border-violet-100/50">
        <h3 className="text-base font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-violet-500" />
          How it works
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm text-slate-600">
          <div className="flex items-start gap-4">
            <span className="w-9 h-9 bg-violet-100 text-violet-600 rounded-xl flex items-center justify-center font-semibold shrink-0">
              1
            </span>
            <p>
              Upload a receipt, invoice, or PDF from any hardware store (Home
              Depot, Lowes, etc.)
            </p>
          </div>
          <div className="flex items-start gap-4">
            <span className="w-9 h-9 bg-amber-100 text-amber-600 rounded-xl flex items-center justify-center font-semibold shrink-0">
              2
            </span>
            <p>
              <strong className="text-slate-700">AI extracts</strong> vendor,
              items, UOM, costs, and quantities
            </p>
          </div>
          <div className="flex items-start gap-4">
            <span className="w-9 h-9 bg-emerald-100 text-emerald-600 rounded-xl flex items-center justify-center font-semibold shrink-0">
              3
            </span>
            <p>
              Products get new SKUs in your system and are added to inventory
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReceiptImport;
