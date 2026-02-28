import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
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
  Minus,
  Trash2,
  ShoppingCart,
  Check,
  HardHat,
  MapPin,
  FileText,
  CreditCard,
  Clock,
  Loader2,
  Radio,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { API } from "@/lib/api";

const POS = () => {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [products, setProducts] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [contractors, setContractors] = useState([]);
  const [cart, setCart] = useState([]);
  const [search, setSearch] = useState("");
  const [selectedDept, setSelectedDept] = useState("");
  const [loading, setLoading] = useState(true);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [processing, setProcessing] = useState(false);

  // Checkout form
  const [selectedContractor, setSelectedContractor] = useState("");
  const [jobId, setJobId] = useState("");
  const [serviceAddress, setServiceAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("charge"); // "charge" or "pay_now"
  const [checkingPayment, setCheckingPayment] = useState(false);
  const [isLive, setIsLive] = useState(false);

  const isContractor = user?.role === "contractor";
  const canPoll = !isContractor && (user?.role === "warehouse_manager" || user?.role === "admin");

  // Check for payment return from Stripe
  useEffect(() => {
    const paymentStatus = searchParams.get("payment");
    const sessionId = searchParams.get("session_id");

    if (paymentStatus === "success" && sessionId) {
      setCheckingPayment(true);
      pollPaymentStatus(sessionId);
    } else if (paymentStatus === "cancelled") {
      toast.error("Payment was cancelled");
      // Clear params
      setSearchParams({});
    }
  }, [searchParams]);

  const pollPaymentStatus = async (sessionId, attempts = 0) => {
    const maxAttempts = 5;
    const pollInterval = 2000;

    if (attempts >= maxAttempts) {
      toast.error("Payment status check timed out. Please check your transaction history.");
      setCheckingPayment(false);
      setSearchParams({});
      return;
    }

    try {
      const response = await axios.get(`${API}/payments/status/${sessionId}`);
      
      if (response.data.payment_status === "paid") {
        toast.success("Payment successful! Material withdrawal completed.");
        setCheckingPayment(false);
        setSearchParams({});
        fetchProducts();
        return;
      } else if (response.data.status === "expired") {
        toast.error("Payment session expired. Please try again.");
        setCheckingPayment(false);
        setSearchParams({});
        return;
      }

      // Continue polling
      setTimeout(() => pollPaymentStatus(sessionId, attempts + 1), pollInterval);
    } catch (error) {
      console.error("Error checking payment status:", error);
      toast.error("Error checking payment status");
      setCheckingPayment(false);
      setSearchParams({});
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    fetchProducts();
  }, [search, selectedDept]);

  // Live polling for warehouse manager/admin when tab visible
  useEffect(() => {
    if (!canPoll) return;
    const poll = () => {
      if (document.visibilityState === "visible") {
        setIsLive(true);
        fetchProducts();
      } else {
        setIsLive(false);
      }
    };
    const id = setInterval(poll, 5000);
    if (document.visibilityState === "visible") setIsLive(true);
    const onVisibility = () => {
      if (document.visibilityState === "visible") setIsLive(true);
      else setIsLive(false);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [canPoll, search, selectedDept]);

  const fetchData = async () => {
    try {
      const [deptRes, productsRes] = await Promise.all([
        axios.get(`${API}/departments`),
        axios.get(`${API}/products`),
      ]);
      setDepartments(deptRes.data);
      setProducts(productsRes.data.filter((p) => p.quantity > 0));

      // Fetch contractors for warehouse manager/admin
      if (!isContractor) {
        try {
          const contractorsRes = await axios.get(`${API}/contractors`);
          setContractors(contractorsRes.data.filter((c) => c.is_active !== false));
        } catch (e) {
          // May not have permission
        }
      }
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
      if (selectedDept) params.append("department_id", selectedDept);

      const response = await axios.get(`${API}/products?${params}`);
      setProducts(response.data.filter((p) => p.quantity > 0));
    } catch (error) {
      console.error("Error fetching products:", error);
    }
  };

  const addToCart = (product) => {
    const existing = cart.find((item) => item.product_id === product.id);

    if (existing) {
      if (existing.quantity >= product.quantity) {
        toast.error("Not enough stock");
        return;
      }
      setCart(
        cart.map((item) =>
          item.product_id === product.id
            ? {
                ...item,
                quantity: item.quantity + 1,
                subtotal: (item.quantity + 1) * item.price,
              }
            : item
        )
      );
    } else {
      setCart([
        ...cart,
        {
          product_id: product.id,
          sku: product.sku,
          name: product.name,
          price: product.price,
          cost: product.cost || 0,
          quantity: 1,
          subtotal: product.price,
          max_quantity: product.quantity,
          unit: product.sell_uom || "each",
        },
      ]);
    }
    toast.success(`Added ${product.name}`);
  };

  const updateQuantity = (productId, delta) => {
    setCart(
      cart
        .map((item) => {
          if (item.product_id === productId) {
            const newQty = item.quantity + delta;
            if (newQty <= 0) return null;
            if (newQty > item.max_quantity) {
              toast.error("Not enough stock");
              return item;
            }
            return {
              ...item,
              quantity: newQty,
              subtotal: newQty * item.price,
            };
          }
          return item;
        })
        .filter(Boolean)
    );
  };

  const removeFromCart = (productId) => {
    setCart(cart.filter((item) => item.product_id !== productId));
  };

  const clearCart = () => {
    setCart([]);
  };

  const subtotal = cart.reduce((sum, item) => sum + item.subtotal, 0);
  const tax = subtotal * 0.08;
  const total = subtotal + tax;

  const openCheckout = () => {
    if (cart.length === 0) {
      toast.error("Cart is empty");
      return;
    }
    // Pre-fill contractor if user is contractor
    if (isContractor) {
      setSelectedContractor(user.id);
    }
    setCheckoutOpen(true);
  };

  const handleCheckout = async () => {
    if (!jobId.trim()) {
      toast.error("Job ID is required");
      return;
    }
    if (!serviceAddress.trim()) {
      toast.error("Service address is required");
      return;
    }
    if (!isContractor && !selectedContractor) {
      toast.error("Please select a contractor");
      return;
    }

    setProcessing(true);
    try {
      const withdrawalData = {
        items: cart.map(({ product_id, sku, name, quantity, price, cost, subtotal, unit }) => ({
          product_id,
          sku,
          name,
          quantity,
          price,
          cost,
          subtotal,
          unit: unit || "each",
        })),
        job_id: jobId.trim(),
        service_address: serviceAddress.trim(),
        notes: notes.trim() || null,
      };

      let withdrawal;
      if (isContractor) {
        const res = await axios.post(`${API}/withdrawals`, withdrawalData);
        withdrawal = res.data;
      } else {
        const res = await axios.post(
          `${API}/withdrawals/for-contractor?contractor_id=${selectedContractor}`,
          withdrawalData
        );
        withdrawal = res.data;
      }

      // If Pay Now, redirect to Stripe
      if (paymentMethod === "pay_now") {
        try {
          const paymentRes = await axios.post(`${API}/payments/create-checkout`, {
            withdrawal_id: withdrawal.id,
            origin_url: window.location.origin
          });
          
          // Redirect to Stripe checkout
          window.location.href = paymentRes.data.checkout_url;
          return;
        } catch (paymentError) {
          // If payment creation fails, the withdrawal is still logged as unpaid
          toast.error("Could not initiate payment. Withdrawal logged as 'Charge to Account'.");
          console.error("Payment error:", paymentError);
        }
      }

      // Success for Charge to Account or fallback
      toast.success("Material withdrawal logged!");
      setCart([]);
      setCheckoutOpen(false);
      setJobId("");
      setServiceAddress("");
      setNotes("");
      setSelectedContractor("");
      setPaymentMethod("charge");
      fetchProducts();
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (typeof detail === "string" && detail.includes("Insufficient stock")) {
        toast.error(detail + " Reduce quantity or remove the item and try again.");
      } else {
        toast.error(detail || "Withdrawal failed");
      }
    } finally {
      setProcessing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          <span className="font-medium">Loading materials…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen" data-testid="pos-page">
      {/* Cart Panel - Left Side */}
      <div
        className="w-1/3 bg-white border-r border-slate-200 flex flex-col shadow-sm"
        data-testid="cart-panel"
      >
        {/* Cart Header */}
        <div className="p-6 border-b border-slate-200">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">
              {isContractor ? "My Withdrawal" : "Material Withdrawal"}
            </h2>
            {cart.length > 0 && (
              <button
                onClick={clearCart}
                className="text-sm text-red-600 hover:underline"
                data-testid="clear-cart-btn"
              >
                Clear All
              </button>
            )}
          </div>
          {isContractor && (
            <p className="text-sm text-slate-500 mt-1">
              {user?.company || "Independent"}
            </p>
          )}
        </div>

        {/* Cart Items */}
        <div className="flex-1 overflow-auto p-4" data-testid="cart-items">
          {cart.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
                <ShoppingCart className="w-7 h-7 text-slate-400" />
              </div>
              <p className="font-medium">Cart is empty</p>
              <p className="text-sm mt-1">Select materials to withdraw</p>
            </div>
          ) : (
            <div className="space-y-3">
              {cart.map((item) => (
                <div
                  key={item.product_id}
                  className="bg-slate-50/80 border border-slate-200 rounded-xl p-4"
                  data-testid={`cart-item-${item.sku}`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <p className="font-mono text-xs text-slate-500">{item.sku}</p>
                      <p className="font-semibold text-slate-900">{item.name}</p>
                      {item.unit && item.unit !== "each" && (
                        <p className="text-xs text-slate-500 mt-0.5">{item.quantity} {item.unit}</p>
                      )}
                    </div>
                    <button
                      onClick={() => removeFromCart(item.product_id)}
                      className="text-red-500 hover:text-red-700 p-1"
                      data-testid={`remove-item-${item.sku}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => updateQuantity(item.product_id, -1)}
                        className="w-8 h-8 border border-slate-200 rounded-lg flex items-center justify-center hover:bg-slate-100 transition-colors"
                        data-testid={`qty-minus-${item.sku}`}
                      >
                        <Minus className="w-4 h-4" />
                      </button>
                      <span className="w-10 text-center font-mono font-bold">
                        {item.quantity}
                      </span>
                      <button
                        onClick={() => updateQuantity(item.product_id, 1)}
                        className="w-8 h-8 border border-slate-200 rounded-lg flex items-center justify-center hover:bg-slate-100 transition-colors"
                        data-testid={`qty-plus-${item.sku}`}
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>
                    <p className="font-semibold text-slate-900">
                      ${item.subtotal.toFixed(2)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Cart Summary */}
        <div className="p-6 border-t border-slate-200 bg-slate-50/80">
          <div className="space-y-2 mb-4">
            <div className="flex justify-between text-slate-600">
              <span>Subtotal</span>
              <span className="font-mono">${subtotal.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-slate-600">
              <span>Tax (8%)</span>
              <span className="font-mono">${tax.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-xl font-semibold text-slate-900 pt-2 border-t border-slate-200">
              <span>Total</span>
              <span className="font-mono">${total.toFixed(2)}</span>
            </div>
          </div>
          <Button
            onClick={openCheckout}
            disabled={cart.length === 0}
            className="w-full btn-primary h-14 text-lg"
            data-testid="checkout-btn"
          >
            <FileText className="w-5 h-5 mr-2" />
            Log Withdrawal
          </Button>
        </div>
      </div>

      {/* Products Panel - Right Side */}
      <div className="flex-1 flex flex-col bg-slate-50/80" data-testid="products-panel">
        {/* Search & Filter Bar */}
        <div className="p-6 bg-white border-b border-slate-200">
          <div className="flex items-center gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <Input
                type="text"
                placeholder="Search materials by name, SKU, or barcode..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="input-workshop pl-12 w-full"
                data-testid="pos-search-input"
              />
            </div>
            <select
              value={selectedDept}
              onChange={(e) => setSelectedDept(e.target.value)}
              className="input-workshop px-4 min-w-[200px]"
              data-testid="pos-department-filter"
            >
              <option value="">All Departments</option>
              {departments.map((dept) => (
                <option key={dept.id} value={dept.id}>
                  {dept.name}
                </option>
              ))}
            </select>
            {canPoll && (
              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${isLive ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                <Radio className={`w-4 h-4 ${isLive ? "animate-pulse" : ""}`} />
                <span>{isLive ? "Live" : "Paused"}</span>
              </div>
            )}
          </div>
        </div>

        {/* Products Grid */}
        <div className="flex-1 overflow-auto p-6" data-testid="products-grid">
          {products.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <p className="font-medium">No materials found</p>
              <p className="text-sm">Add products in Inventory</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {products.map((product) => (
                <div
                  key={product.id}
                  onClick={() => addToCart(product)}
                  className="pos-item cursor-pointer"
                  data-testid={`pos-product-${product.sku}`}
                >
                  <div className="aspect-[4/3] bg-slate-100/80 flex items-center justify-center border-b border-slate-200/80">
                    <span className="font-mono text-2xl text-slate-400 font-bold">
                      {product.department_name?.slice(0, 3).toUpperCase() || "---"}
                    </span>
                  </div>
                  <div className="p-4">
                    <p className="font-mono text-xs text-slate-500">{product.sku}</p>
                    <p
                      className="font-semibold text-slate-900 truncate"
                      title={product.name}
                    >
                      {product.name}
                    </p>
                    <div className="flex items-center justify-between mt-2">
                      <span className="font-semibold text-lg text-amber-600">
                        ${product.price.toFixed(2)}
                        <span className="text-xs font-normal text-slate-500 ml-1">/ {product.sell_uom || "each"}</span>
                      </span>
                      <span className="text-xs text-slate-400">
                        {product.quantity} in stock
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Checkout Dialog */}
      <Dialog open={checkoutOpen} onOpenChange={setCheckoutOpen}>
        <DialogContent className="sm:max-w-lg rounded-2xl" data-testid="checkout-dialog">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">
              Log material withdrawal
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 pt-4">
            {/* Contractor Selection (for warehouse manager/admin) */}
            {!isContractor && (
              <div>
                <Label className="text-slate-600 font-medium text-sm">
                  Contractor *
                </Label>
                <Select
                  value={selectedContractor}
                  onValueChange={setSelectedContractor}
                >
                  <SelectTrigger
                    className="input-workshop mt-2"
                    data-testid="select-contractor"
                  >
                    <SelectValue placeholder="Select contractor" />
                  </SelectTrigger>
                  <SelectContent>
                    {contractors.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        <div className="flex items-center gap-2">
                          <HardHat className="w-4 h-4" />
                          {c.name} ({c.company || "Independent"})
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Job ID */}
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                <FileText className="w-4 h-4 inline mr-1" />
                Job ID *
              </Label>
              <Input
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                placeholder="Enter job ID or reference number"
                className="input-workshop mt-2"
                data-testid="job-id-input"
              />
            </div>

            {/* Service Address */}
            <div>
              <Label className="text-slate-600 font-medium text-sm">
                <MapPin className="w-4 h-4 inline mr-1" />
                Service address *
              </Label>
              <Input
                value={serviceAddress}
                onChange={(e) => setServiceAddress(e.target.value)}
                placeholder="Where are these materials going?"
                className="input-workshop mt-2"
                data-testid="service-address-input"
              />
            </div>

            {/* Notes */}
            <div>
              <Label className="text-slate-600 font-medium text-sm">
                Notes (optional)
              </Label>
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Any additional notes..."
                className="input-workshop mt-2"
                data-testid="notes-input"
              />
            </div>

            {/* Payment Method Selection */}
            <div>
              <Label className="text-slate-600 font-medium text-sm mb-3 block">
                Payment method
              </Label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setPaymentMethod("pay_now")}
                  className={`p-4 rounded-xl border text-left transition-all ${
                    paymentMethod === "pay_now"
                      ? "border-amber-400 bg-amber-50/80"
                      : "border-slate-200 hover:border-slate-300"
                  }`}
                  data-testid="payment-method-pay-now"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <CreditCard className={`w-5 h-5 ${paymentMethod === "pay_now" ? "text-orange-500" : "text-slate-500"}`} />
                    <span className="font-semibold text-slate-900">Pay Now</span>
                  </div>
                  <p className="text-xs text-slate-500">Pay with company card via Stripe</p>
                </button>
                <button
                  type="button"
                  onClick={() => setPaymentMethod("charge")}
                  className={`p-4 rounded-xl border text-left transition-all ${
                    paymentMethod === "charge"
                      ? "border-amber-400 bg-amber-50/80"
                      : "border-slate-200 hover:border-slate-300"
                  }`}
                  data-testid="payment-method-charge"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Clock className={`w-5 h-5 ${paymentMethod === "charge" ? "text-amber-500" : "text-slate-500"}`} />
                    <span className="font-semibold text-slate-900">Charge to Account</span>
                  </div>
                  <p className="text-xs text-slate-500">Invoice later via Xero</p>
                </button>
              </div>
            </div>

            {/* Summary */}
            <div className="bg-slate-50/80 p-4 rounded-xl border border-slate-200">
              <div className="flex justify-between text-lg font-bold mb-2">
                <span>Total Value</span>
                <span className="font-mono">${total.toFixed(2)}</span>
              </div>
              <p className="text-xs text-slate-500">
                {paymentMethod === "pay_now" 
                  ? "Pay now via Stripe checkout" 
                  : `Charged to ${isContractor ? user?.billing_entity || user?.company : "contractor"} account`}
              </p>
            </div>
          </div>

          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => setCheckoutOpen(false)}
              className="flex-1 btn-secondary h-12"
              data-testid="checkout-cancel-btn"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCheckout}
              disabled={processing}
              className="flex-1 btn-primary h-12"
              data-testid="checkout-confirm-btn"
            >
              {paymentMethod === "pay_now" ? (
                <>
                  <CreditCard className="w-5 h-5 mr-2" />
                  {processing ? "Processing..." : "Proceed to Payment"}
                </>
              ) : (
                <>
                  <Check className="w-5 h-5 mr-2" />
                  {processing ? "Processing..." : "Confirm Withdrawal"}
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Payment Processing Overlay */}
      {checkingPayment && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" data-testid="payment-processing-overlay">
          <div className="bg-white p-8 rounded-2xl shadow-soft-lg text-center max-w-sm">
            <Loader2 className="w-12 h-12 animate-spin text-amber-500 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-slate-900 mb-2">Verifying payment</h3>
            <p className="text-slate-500 text-sm">Confirming your payment…</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default POS;
