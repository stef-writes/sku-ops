import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Checkbox } from "@/components/ui/checkbox";
import api from "@/lib/api-client";
import { getErrorMessage } from "@/lib/api-client";
import { useDepartments } from "@/hooks/useDepartments";
import { useVendors } from "@/hooks/useVendors";
import { useProductMatch } from "@/hooks/useProductMatch";
import { ProductMatchPicker } from "@/components/ProductMatchPicker";
import { ProductFields } from "@/components/ProductFields";

const ReceiptImport = () => {
  const navigate = useNavigate();
  const { data: departments = [] } = useDepartments();
  const { data: vendors = [] } = useVendors();
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
  const {
    matches: productMatches,
    autoMatch,
    searchMatch,
    confirmMatch,
    clearMatch,
    reset: resetMatches,
  } = useProductMatch();

  const isImageOrPdf = (file) => {
    if (!file) return false;
    const t = file.type?.toLowerCase() || "";
    const n = (file.name || "").toLowerCase();
    return (
      t.startsWith("image/") || t === "application/pdf" || n.endsWith(".pdf")
    );
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      if (!isImageOrPdf(selectedFile)) {
        toast.error("Please select an image (JPG, PNG, WEBP) or PDF");
        return;
      }
      setFile(selectedFile);
      setPreview(
        selectedFile.type?.startsWith("image/")
          ? URL.createObjectURL(selectedFile)
          : null,
      );
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
      setPreview(
        droppedFile.type?.startsWith("image/")
          ? URL.createObjectURL(droppedFile)
          : null,
      );
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

      const response = await api.documents.parse(formData, useAi);

      setExtractedData(response);
      setVendorName(response.vendor_name || "");
      const mapped = (response.products || []).map((p, idx) => ({
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
      const detail =
        error.response?.data?.detail || "Failed to extract document";
      if (error.response?.status === 503) {
        toast.error(
          "AI not configured — add ANTHROPIC_API_KEY to backend/.env, or use free OCR instead",
        );
      } else {
        toast.error(detail);
      }
    } finally {
      setExtracting(false);
    }
  };

  const updateProduct = (id, field, value) => {
    setEditedProducts(
      editedProducts.map((p) => (p.id === id ? { ...p, [field]: value } : p)),
    );
  };

  const toggleProduct = (id) => {
    setEditedProducts(
      editedProducts.map((p) =>
        p.id === id ? { ...p, selected: !p.selected } : p,
      ),
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
        quantity: parseFloat(p.quantity) || 1,
        ordered_qty:
          p.ordered_qty != null
            ? parseFloat(p.ordered_qty)
            : parseFloat(p.quantity) || 1,
        delivered_qty:
          p.delivered_qty != null
            ? parseFloat(p.delivered_qty)
            : parseFloat(p.quantity) || 1,
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
      await api.purchaseOrders.create({
        vendor_name: vName,
        create_vendor_if_missing: createVendorIfMissing,
        department_id: selectedDept || null,
        document_date: extractedData?.document_date || null,
        total: extractedData?.total || null,
        products: productsToSave,
      });

      toast.success(
        `Purchase order saved — ${productsToSave.length} item(s) pending receipt`,
      );
      setFile(null);
      setPreview(null);
      setExtractedData(null);
      setEditedProducts([]);
      setVendorName("");
      navigate("/purchase-orders");
    } catch (error) {
      toast.error(getErrorMessage(error));
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
    resetMatches();
  };

  const handleConfirmMatch = (itemId, product) => {
    setEditedProducts((prev) =>
      prev.map((p) =>
        p.id === itemId ? { ...p, matched_product: product } : p,
      ),
    );
    confirmMatch(itemId, product);
  };

  const handleClearMatch = (itemId) => {
    setEditedProducts((prev) =>
      prev.map((p) => (p.id === itemId ? { ...p, matched_product: null } : p)),
    );
    clearMatch(itemId);
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

      const result = await api.products.importCsv(formData);

      setCsvResult(result);
      toast.success(`Imported ${result.imported} products`);
      if (result.errors > 0) toast.warning(`${result.errors} rows had errors`);
      if (result.warnings?.length > 0)
        toast.info(`${result.warnings.length} product(s) had invalid barcode`);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setCsvImporting(false);
    }
  };

  return (
    <div className="p-8" data-testid="receipt-import-page">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-foreground tracking-tight">
          Receive / Import
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Upload a delivery receipt or vendor invoice to add products, or bulk
          import from CSV
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
              className="card-elevated p-6 border-primary/20"
              data-testid="upload-section"
            >
              <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <span className="w-7 h-7 rounded-lg bg-primary/15 text-primary flex items-center justify-center text-sm font-bold">
                  1
                </span>
                Upload document
              </h2>

              {!file ? (
                <div
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  className="border-2 border-dashed border-border rounded-2xl p-12 text-center hover:border-primary/30 hover:bg-primary/5 transition-all cursor-pointer group"
                  onClick={() =>
                    document.getElementById("receipt-input").click()
                  }
                  data-testid="upload-dropzone"
                >
                  <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary/15 to-warning/10 flex items-center justify-center mx-auto mb-4 group-hover:scale-105 transition-transform">
                    <Upload className="w-7 h-7 text-primary" />
                  </div>
                  <p className="text-muted-foreground font-medium">
                    Drop document here or click to browse
                  </p>
                  <p className="text-muted-foreground text-sm mt-2">
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
                  <div className="relative rounded-xl overflow-hidden border border-border shadow-sm">
                    {preview ? (
                      <img
                        src={preview}
                        alt="Document preview"
                        className="w-full max-h-[400px] object-contain bg-muted"
                        data-testid="receipt-preview"
                      />
                    ) : (
                      <div className="w-full h-48 bg-muted flex flex-col items-center justify-center gap-2">
                        <FileText className="w-12 h-12 text-muted-foreground" />
                        <span className="text-muted-foreground font-medium">
                          {file.name}
                        </span>
                        <span className="text-muted-foreground text-sm">
                          PDF document
                        </span>
                      </div>
                    )}
                    <button
                      onClick={clearAll}
                      className="absolute top-3 right-3 p-2 bg-white/90 backdrop-blur-sm text-muted-foreground rounded-xl hover:bg-destructive/10 hover:text-destructive border border-border shadow-sm transition-colors"
                      data-testid="clear-receipt-btn"
                    >
                      <XCircle className="w-5 h-5" />
                    </button>
                  </div>

                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    {preview ? (
                      <FileImage className="w-4 h-4" />
                    ) : (
                      <FileText className="w-4 h-4" />
                    )}
                    <span>{file?.name}</span>
                  </div>

                  <div
                    className="grid grid-cols-2 gap-2"
                    data-testid="extract-btn"
                  >
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
                      className="h-11 text-muted-foreground"
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
              <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <span className="w-7 h-7 rounded-lg bg-warning/15 text-accent flex items-center justify-center text-sm font-bold">
                  2
                </span>
                Review & import
              </h2>

              {!extractedData ? (
                <div className="text-center py-16 text-muted-foreground">
                  <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-4">
                    <Package className="w-7 h-7 text-muted-foreground" />
                  </div>
                  <p className="font-medium">
                    Upload and extract a document to see products
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <Label className="text-muted-foreground font-medium text-sm">
                      Vendor *
                    </Label>
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
                      onCheckedChange={(c) =>
                        setCreateVendorIfMissing(c === true)
                      }
                    />
                    <Label
                      htmlFor="create-vendor"
                      className="text-sm text-muted-foreground cursor-pointer"
                    >
                      Create vendor if missing
                    </Label>
                  </div>

                  <div>
                    <Label className="text-muted-foreground font-medium text-sm">
                      Department override (optional)
                    </Label>
                    <Select
                      value={selectedDept || "none"}
                      onValueChange={(v) =>
                        setSelectedDept(v === "none" ? "" : v)
                      }
                    >
                      <SelectTrigger
                        className="input-field mt-2"
                        data-testid="import-dept-select"
                      >
                        <SelectValue placeholder="Use suggested per product" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">
                          Use suggested per product
                        </SelectItem>
                        {departments.map((dept) => (
                          <SelectItem key={dept.id} value={dept.id}>
                            {dept.name} ({dept.code})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div
                    className="space-y-3 max-h-[400px] overflow-auto"
                    data-testid="extracted-products-list"
                  >
                    {editedProducts.map((product) => {
                      const matchState = productMatches[product.id] || {};
                      const matched =
                        matchState.matched || product.matched_product;

                      return (
                        <div
                          key={product.id}
                          className={`p-4 rounded-xl border transition-all ${
                            product.selected
                              ? "border-warning/30 bg-warning/10"
                              : "border-border bg-muted/50 opacity-60"
                          }`}
                          data-testid={`extracted-product-${product.id}`}
                        >
                          <div className="flex items-start gap-3">
                            <button
                              onClick={() => toggleProduct(product.id)}
                              className={`mt-1 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-colors ${
                                product.selected
                                  ? "bg-accent border-accent text-white"
                                  : "border-border"
                              }`}
                              data-testid={`toggle-product-${product.id}`}
                            >
                              {product.selected && (
                                <svg
                                  className="w-3 h-3 text-white"
                                  fill="currentColor"
                                  viewBox="0 0 20 20"
                                >
                                  <path
                                    fillRule="evenodd"
                                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                    clipRule="evenodd"
                                  />
                                </svg>
                              )}
                            </button>

                            <div className="flex-1 min-w-0 space-y-2">
                              <ProductMatchPicker
                                matched={matched}
                                options={matchState.options || []}
                                searching={matchState.searching || false}
                                onSearch={(q) => searchMatch(product.id, q)}
                                onConfirm={(p) =>
                                  handleConfirmMatch(product.id, p)
                                }
                                onClear={() => handleClearMatch(product.id)}
                              />

                              {matched ? (
                                <div className="space-y-2">
                                  <div className="grid grid-cols-2 gap-2">
                                    <div>
                                      <Label className="text-xs text-muted-foreground">
                                        Delivered qty
                                      </Label>
                                      <Input
                                        type="number"
                                        step="any"
                                        value={
                                          product.delivered_qty ??
                                          product.quantity ??
                                          1
                                        }
                                        onChange={(e) =>
                                          updateProduct(
                                            product.id,
                                            "delivered_qty",
                                            e.target.value,
                                          )
                                        }
                                        className="input-field h-9 text-sm"
                                      />
                                    </div>
                                    <div>
                                      <Label className="text-xs text-muted-foreground">
                                        Cost
                                      </Label>
                                      <Input
                                        type="number"
                                        step="0.01"
                                        value={product.cost ?? ""}
                                        onChange={(e) =>
                                          updateProduct(
                                            product.id,
                                            "cost",
                                            e.target.value
                                              ? parseFloat(e.target.value)
                                              : null,
                                          )
                                        }
                                        className="input-field h-9 text-sm"
                                      />
                                    </div>
                                  </div>
                                  {product.original_sku && (
                                    <p className="text-xs text-muted-foreground font-mono">
                                      Original: {product.original_sku}
                                    </p>
                                  )}
                                </div>
                              ) : (
                                <ProductFields
                                  compact
                                  fields={{
                                    name: product.name || "",
                                    price: product.price ?? "",
                                    cost: product.cost ?? "",
                                    base_unit: product.base_unit || "each",
                                    sell_uom: product.sell_uom || "each",
                                    pack_qty: product.pack_qty ?? 1,
                                    barcode: product.barcode || "",
                                    department_id:
                                      product.suggested_department || "",
                                    quantity:
                                      product.delivered_qty ??
                                      product.quantity ??
                                      1,
                                  }}
                                  onChange={(field, value) => {
                                    const mapped =
                                      field === "department_id"
                                        ? "suggested_department"
                                        : field === "quantity"
                                          ? "delivered_qty"
                                          : field;
                                    updateProduct(product.id, mapped, value);
                                  }}
                                  departments={departments}
                                  hiddenFields={[
                                    "description",
                                    "vendor_id",
                                    "min_stock",
                                    "sell_uom",
                                    "pack_qty",
                                  ]}
                                />
                              )}
                            </div>

                            <button
                              onClick={() => removeProduct(product.id)}
                              className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors shrink-0"
                              data-testid={`remove-product-${product.id}`}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="p-4 bg-muted/80 rounded-xl border border-border">
                    <p className="text-sm text-muted-foreground">
                      <strong>
                        {editedProducts.filter((p) => p.selected).length}
                      </strong>{" "}
                      of {editedProducts.length} products selected for import
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
          <div className="card-elevated p-6 max-w-2xl border-border">
            <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5 text-success" />
              Bulk import from CSV
            </h2>
            <p className="text-muted-foreground text-sm mb-4">
              Supply Yard format: Product, SKU, Barcode, On hand, Reorder point,
              Unit cost, Retail price, Department
            </p>

            <div className="space-y-4">
              <div>
                <Label className="text-muted-foreground font-medium text-sm">
                  Department *
                </Label>
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
                <Label className="text-muted-foreground font-medium text-sm">
                  Vendor (optional)
                </Label>
                <Select
                  value={selectedVendor}
                  onValueChange={setSelectedVendor}
                >
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
                className="border-2 border-dashed border-border rounded-xl p-8 text-center hover:border-success/30 cursor-pointer"
                onClick={() => document.getElementById("csv-input").click()}
              >
                <input
                  id="csv-input"
                  type="file"
                  accept=".csv"
                  onChange={handleCsvFileChange}
                  className="hidden"
                />
                <FileSpreadsheet className="w-12 h-12 text-success mx-auto mb-3" />
                <p className="text-muted-foreground font-medium">
                  {csvFile ? csvFile.name : "Drop CSV or click to browse"}
                </p>
              </div>

              {csvResult && (
                <div className="p-4 bg-muted rounded-xl border border-border text-sm">
                  <p className="font-medium text-foreground">
                    Imported {csvResult.imported} products
                    {csvResult.errors > 0 && ` · ${csvResult.errors} errors`}
                    {csvResult.warnings?.length > 0 &&
                      ` · ${csvResult.warnings.length} barcode warnings`}
                  </p>
                  {csvResult.error_details?.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-muted-foreground">
                        View errors
                      </summary>
                      <ul className="mt-2 space-y-1 text-muted-foreground text-xs max-h-32 overflow-auto">
                        {csvResult.error_details.map((e, i) => (
                          <li key={i}>
                            {e.product}: {e.error}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {csvResult.warnings?.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-accent">
                        View barcode warnings
                      </summary>
                      <ul className="mt-2 space-y-1 text-muted-foreground text-xs max-h-32 overflow-auto">
                        {csvResult.warnings.map((w, i) => (
                          <li key={i}>
                            {w.product}: {w.warning}
                          </li>
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
      <div className="card-elevated p-6 mt-8 bg-gradient-to-br from-muted to-primary/5 border-primary/10">
        <h3 className="text-base font-semibold text-foreground mb-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" />
          How it works
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm text-muted-foreground">
          <div className="flex items-start gap-4">
            <span className="w-9 h-9 bg-primary/15 text-primary rounded-xl flex items-center justify-center font-semibold shrink-0">
              1
            </span>
            <p>
              Upload a receipt, invoice, or PDF from any hardware store (Home
              Depot, Lowes, etc.)
            </p>
          </div>
          <div className="flex items-start gap-4">
            <span className="w-9 h-9 bg-warning/15 text-accent rounded-xl flex items-center justify-center font-semibold shrink-0">
              2
            </span>
            <p>
              <strong className="text-foreground">AI extracts</strong> vendor,
              items, UOM, costs, and quantities
            </p>
          </div>
          <div className="flex items-start gap-4">
            <span className="w-9 h-9 bg-success/15 text-success rounded-xl flex items-center justify-center font-semibold shrink-0">
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
