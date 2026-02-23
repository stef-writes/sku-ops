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
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ReceiptImport = () => {
  const [departments, setDepartments] = useState([]);
  const [selectedDept, setSelectedDept] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [extractedData, setExtractedData] = useState(null);
  const [editedProducts, setEditedProducts] = useState([]);

  useEffect(() => {
    fetchDepartments();
  }, []);

  const fetchDepartments = async () => {
    try {
      const response = await axios.get(`${API}/departments`);
      setDepartments(response.data);
    } catch (error) {
      console.error("Error fetching departments:", error);
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
      editedProducts.map((p) =>
        p.id === id ? { ...p, [field]: value } : p
      )
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
      .map(({ name, quantity, price, original_sku }) => ({
        name,
        quantity: parseInt(quantity) || 1,
        price: parseFloat(price) || 0,
        original_sku,
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
      
      // Reset state
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

  return (
    <div className="p-8" data-testid="receipt-import-page">
      {/* Header */}
      <div className="mb-6">
        <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">
          Receipt Import
        </h1>
        <p className="text-slate-600 mt-1">
          Upload receipts from Home Depot, Lowes, etc. to extract and import products
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upload Section */}
        <div className="card-workshop p-6" data-testid="upload-section">
          <h2 className="font-heading font-bold text-xl text-slate-900 uppercase tracking-wider mb-4">
            1. Upload Receipt
          </h2>

          {!preview ? (
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className="border-2 border-dashed border-slate-300 rounded-md p-12 text-center hover:border-orange-400 transition-colors cursor-pointer"
              onClick={() => document.getElementById("receipt-input").click()}
              data-testid="upload-dropzone"
            >
              <Upload className="w-12 h-12 mx-auto mb-4 text-slate-400" />
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
              <div className="relative border-2 border-slate-200 rounded-md overflow-hidden">
                <img
                  src={preview}
                  alt="Receipt preview"
                  className="w-full max-h-[400px] object-contain bg-slate-50"
                  data-testid="receipt-preview"
                />
                <button
                  onClick={clearAll}
                  className="absolute top-2 right-2 p-2 bg-red-500 text-white rounded-sm hover:bg-red-600"
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
                className="w-full btn-primary h-12"
                data-testid="extract-btn"
              >
                {extracting ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Extracting Products...
                  </>
                ) : (
                  <>
                    <ArrowRight className="w-5 h-5 mr-2" />
                    Extract Products
                  </>
                )}
              </Button>
            </div>
          )}
        </div>

        {/* Extracted Products Section */}
        <div className="card-workshop p-6" data-testid="extracted-section">
          <h2 className="font-heading font-bold text-xl text-slate-900 uppercase tracking-wider mb-4">
            2. Review & Import
          </h2>

          {!extractedData ? (
            <div className="text-center py-12 text-slate-400">
              <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>Upload and extract a receipt to see products</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Store Info */}
              {extractedData.store_name && (
                <div className="p-3 bg-slate-50 rounded-sm border border-slate-200">
                  <p className="text-sm text-slate-500">Source Store</p>
                  <p className="font-semibold text-slate-900">
                    {extractedData.store_name}
                  </p>
                </div>
              )}

              {/* Department Selection */}
              <div>
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                  Import to Department *
                </Label>
                <Select value={selectedDept} onValueChange={setSelectedDept}>
                  <SelectTrigger className="input-workshop mt-2" data-testid="import-dept-select">
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

              {/* Products List */}
              <div className="space-y-3 max-h-[350px] overflow-auto" data-testid="extracted-products-list">
                {editedProducts.map((product) => (
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
                        className={`mt-1 w-5 h-5 rounded-sm border-2 flex items-center justify-center ${
                          product.selected
                            ? "bg-orange-500 border-orange-500 text-white"
                            : "border-slate-300"
                        }`}
                        data-testid={`toggle-product-${product.id}`}
                      >
                        {product.selected && <CheckCircle className="w-4 h-4" />}
                      </button>

                      <div className="flex-1 space-y-2">
                        <Input
                          value={product.name}
                          onChange={(e) =>
                            updateProduct(product.id, "name", e.target.value)
                          }
                          className="input-workshop h-10 text-sm"
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
                            className="input-workshop h-10 text-sm"
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
                            className="input-workshop h-10 text-sm"
                            placeholder="Price"
                            data-testid={`product-price-${product.id}`}
                          />
                        </div>
                        {product.original_sku && (
                          <p className="text-xs text-slate-400">
                            Original SKU: {product.original_sku}
                          </p>
                        )}
                      </div>

                      <button
                        onClick={() => removeProduct(product.id)}
                        className="p-1 text-red-500 hover:bg-red-50 rounded"
                        data-testid={`remove-product-${product.id}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {/* Import Summary */}
              <div className="p-3 bg-slate-100 rounded-sm border border-slate-200">
                <p className="text-sm text-slate-600">
                  <strong>{editedProducts.filter((p) => p.selected).length}</strong> of{" "}
                  {editedProducts.length} products selected for import
                </p>
              </div>

              {/* Import Button */}
              <Button
                onClick={importProducts}
                disabled={importing || !selectedDept}
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
                    Import Selected Products
                  </>
                )}
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Info Section */}
      <div className="card-workshop p-6 mt-6 bg-slate-50">
        <h3 className="font-heading font-bold text-lg text-slate-900 uppercase tracking-wider mb-3">
          How It Works
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-slate-600">
          <div className="flex items-start gap-3">
            <span className="w-8 h-8 bg-orange-500 text-white rounded-sm flex items-center justify-center font-bold flex-shrink-0">
              1
            </span>
            <p>Upload a receipt image from any hardware store (Home Depot, Lowes, etc.)</p>
          </div>
          <div className="flex items-start gap-3">
            <span className="w-8 h-8 bg-orange-500 text-white rounded-sm flex items-center justify-center font-bold flex-shrink-0">
              2
            </span>
            <p>AI extracts product names, quantities, and prices automatically</p>
          </div>
          <div className="flex items-start gap-3">
            <span className="w-8 h-8 bg-orange-500 text-white rounded-sm flex items-center justify-center font-bold flex-shrink-0">
              3
            </span>
            <p>Products get new SKUs in your system and are added to inventory</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReceiptImport;
