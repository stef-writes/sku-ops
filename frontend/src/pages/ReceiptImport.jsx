import { useState, useEffect, useCallback } from "react";
import axios from "axios";
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
  CheckCircle,
  XCircle,
  Package,
  ArrowRight,
  Loader2,
  Trash2,
  Sparkles,
  FileSpreadsheet,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { API } from "@/lib/api";

const ReceiptImport = () => {
  const [departments, setDepartments] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [selectedDept, setSelectedDept] = useState("");
  const [selectedVendor, setSelectedVendor] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [extractedData, setExtractedData] = useState(null);
  const [editedProducts, setEditedProducts] = useState([]);
  const [csvFile, setCsvFile] = useState(null);
  const [csvImporting, setCsvImporting] = useState(false);
  const [csvResult, setCsvResult] = useState(null);

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

  const handleFileChange = (e) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      if (!selectedFile.type.startsWith("image/")) {
        toast.error("Please select an image file");
        return;
      }
      setFile(selectedFile);
      setPreview(URL.createObjectURL(selectedFile));
      setExtractedData(null);
      setEditedProducts([]);
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      if (!droppedFile.type.startsWith("image/")) {
        toast.error("Please select an image file");
        return;
      }
      setFile(droppedFile);
      setPreview(URL.createObjectURL(droppedFile));
      setExtractedData(null);
      setEditedProducts([]);
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
  }, []);

  const extractReceipt = async () => {
    if (!file) {
      toast.error("Please select a receipt image");
      return;
    }

    setExtracting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await axios.post(`${API}/receipts/extract`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setExtractedData(response.data);
      setEditedProducts(
        response.data.products.map((p, idx) => ({
          ...p,
          id: idx,
          selected: true,
        }))
      );
      toast.success("Receipt extracted successfully!");
    } catch (error) {
      console.error("Extraction error:", error);
      toast.error(error.response?.data?.detail || "Failed to extract receipt");
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

  const importProducts = async () => {
    if (!selectedDept) {
      toast.error("Please select a department");
      return;
    }

    const productsToImport = editedProducts
      .filter((p) => p.selected)
      .map(({ name, quantity, price, original_sku, base_unit, sell_uom, pack_qty }) => ({
        name,
        quantity: parseInt(quantity) || 1,
        price: parseFloat(price) || 0,
        original_sku,
        base_unit: base_unit || undefined,
        sell_uom: sell_uom || undefined,
        pack_qty: pack_qty != null ? parseInt(pack_qty) : undefined,
      }));

    if (productsToImport.length === 0) {
      toast.error("No products selected for import");
      return;
    }

    setImporting(true);
    try {
      const response = await axios.post(
        `${API}/receipts/import?department_id=${selectedDept}`,
        productsToImport
      );

      toast.success(`Imported ${response.data.imported} products!`);

      setFile(null);
      setPreview(null);
      setExtractedData(null);
      setEditedProducts([]);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to import products");
    } finally {
      setImporting(false);
    }
  };

  const clearAll = () => {
    setFile(null);
    setPreview(null);
    setExtractedData(null);
    setEditedProducts([]);
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
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-gradient-to-r from-violet-500/10 to-amber-500/10 border border-violet-200/50 mb-4">
          <Sparkles className="w-4 h-4 text-violet-500" />
          <span className="text-sm font-medium text-violet-700">AI-powered</span>
        </div>
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
          Receipt Import
        </h1>
        <p className="text-slate-500 mt-1 text-sm">
          Upload receipts or bulk import from CSV
        </p>
      </div>

      <Tabs defaultValue="receipt" className="mt-4">
        <TabsList className="mb-4">
          <TabsTrigger value="receipt">Receipt (AI)</TabsTrigger>
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
            Upload receipt
          </h2>

          {!preview ? (
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
                Drop receipt image here or click to browse
              </p>
              <p className="text-slate-400 text-sm mt-2">
                Supports JPG, PNG, WEBP
              </p>
              <input
                id="receipt-input"
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="hidden"
                data-testid="receipt-file-input"
              />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="relative rounded-xl overflow-hidden border border-slate-200 shadow-sm">
                <img
                  src={preview}
                  alt="Receipt preview"
                  className="w-full max-h-[400px] object-contain bg-slate-50"
                  data-testid="receipt-preview"
                />
                <button
                  onClick={clearAll}
                  className="absolute top-3 right-3 p-2 bg-white/90 backdrop-blur-sm text-slate-600 rounded-xl hover:bg-red-50 hover:text-red-600 border border-slate-200 shadow-sm transition-colors"
                  data-testid="clear-receipt-btn"
                >
                  <XCircle className="w-5 h-5" />
                </button>
              </div>

              <div className="flex items-center gap-2 text-sm text-slate-500">
                <FileImage className="w-4 h-4" />
                <span>{file?.name}</span>
              </div>

              <Button
                onClick={extractReceipt}
                disabled={extracting}
                className="w-full btn-primary h-11"
                data-testid="extract-btn"
              >
                {extracting ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    AI extracting products…
                  </>
                ) : (
                  <>
                    <Sparkles className="w-5 h-5 mr-2" />
                    Extract with AI
                  </>
                )}
              </Button>
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
              <p className="font-medium">Upload and extract a receipt to see products</p>
            </div>
          ) : (
            <div className="space-y-4">
              {extractedData.store_name && (
                <div className="p-4 bg-slate-50/80 rounded-xl border border-slate-200">
                  <p className="text-xs text-slate-500 font-medium">Source store</p>
                  <p className="font-semibold text-slate-900 mt-0.5">
                    {extractedData.store_name}
                  </p>
                </div>
              )}

              <div>
                <Label className="text-slate-600 font-medium text-sm">
                  Import to department *
                </Label>
                <Select value={selectedDept} onValueChange={setSelectedDept}>
                  <SelectTrigger
                    className="input-field mt-2"
                    data-testid="import-dept-select"
                  >
                    <SelectValue placeholder="Select department" />
                  </SelectTrigger>
                  <SelectContent>
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
                            value={product.quantity}
                            onChange={(e) =>
                              updateProduct(product.id, "quantity", e.target.value)
                            }
                            className="input-field h-10 text-sm"
                            placeholder="Qty"
                            data-testid={`product-qty-${product.id}`}
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
                onClick={importProducts}
                disabled={importing || !selectedDept}
                className="w-full btn-primary h-11"
                data-testid="import-products-btn"
              >
                {importing ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Importing…
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5 mr-2" />
                    Import selected products
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
              Upload a receipt image from any hardware store (Home Depot, Lowes,
              etc.)
            </p>
          </div>
          <div className="flex items-start gap-4">
            <span className="w-9 h-9 bg-amber-100 text-amber-600 rounded-xl flex items-center justify-center font-semibold shrink-0">
              2
            </span>
            <p>
              <strong className="text-slate-700">AI extracts</strong> product
              names, quantities, and prices automatically
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
