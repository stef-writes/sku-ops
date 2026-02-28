import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import {
  Package,
  Calendar,
  MapPin,
  FileText,
  DollarSign,
  Clock,
  CheckCircle,
} from "lucide-react";

import { API } from "@/lib/api";

const MyHistory = () => {
  const { user } = useAuth();
  const [withdrawals, setWithdrawals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    fetchWithdrawals();
  }, []);

  const fetchWithdrawals = async () => {
    try {
      const response = await axios.get(`${API}/withdrawals`);
      setWithdrawals(response.data);
    } catch (error) {
      console.error("Error fetching withdrawals:", error);
      toast.error("Failed to load history");
    } finally {
      setLoading(false);
    }
  };

  // Calculate totals
  const totalSpent = withdrawals.reduce((sum, w) => sum + w.total, 0);
  const totalUnpaid = withdrawals
    .filter((w) => w.payment_status === "unpaid")
    .reduce((sum, w) => sum + w.total, 0);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">
          Loading History...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="my-history-page">
      {/* Header */}
      <div className="mb-6">
        <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">
          My Withdrawal History
        </h1>
        <p className="text-slate-600 mt-1">
          {user?.name} • {user?.company || "Independent"}
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="card-workshop p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-blue-100 rounded-sm flex items-center justify-center">
              <Package className="w-5 h-5 text-blue-600" />
            </div>
            <span className="text-sm text-slate-500 uppercase tracking-wide">
              Total Withdrawals
            </span>
          </div>
          <p className="text-3xl font-heading font-bold text-slate-900">
            {withdrawals.length}
          </p>
        </div>

        <div className="card-workshop p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-green-100 rounded-sm flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-green-600" />
            </div>
            <span className="text-sm text-slate-500 uppercase tracking-wide">
              Total Value
            </span>
          </div>
          <p className="text-3xl font-heading font-bold text-green-600">
            ${totalSpent.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
        </div>

        <div className="card-workshop p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-orange-100 rounded-sm flex items-center justify-center">
              <Clock className="w-5 h-5 text-orange-600" />
            </div>
            <span className="text-sm text-slate-500 uppercase tracking-wide">
              Unpaid Balance
            </span>
          </div>
          <p className="text-3xl font-heading font-bold text-orange-600">
            ${totalUnpaid.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
        </div>
      </div>

      {/* Withdrawals List */}
      <div className="space-y-4" data-testid="withdrawals-list">
        {withdrawals.length === 0 ? (
          <div className="card-workshop p-12 text-center">
            <Package className="w-16 h-16 mx-auto mb-4 text-slate-300" />
            <p className="text-slate-500 font-medium">No withdrawals yet</p>
            <p className="text-slate-400 text-sm">
              Your material withdrawals will appear here
            </p>
          </div>
        ) : (
          withdrawals.map((w) => (
            <div
              key={w.id}
              className="card-workshop overflow-hidden"
              data-testid={`withdrawal-${w.id}`}
            >
              {/* Header */}
              <div
                className="p-4 flex items-center justify-between cursor-pointer hover:bg-slate-50"
                onClick={() => setExpandedId(expandedId === w.id ? null : w.id)}
              >
                <div className="flex items-center gap-4">
                  <div
                    className={`w-12 h-12 rounded-sm flex items-center justify-center ${
                      w.payment_status === "paid"
                        ? "bg-green-100"
                        : "bg-orange-100"
                    }`}
                  >
                    {w.payment_status === "paid" ? (
                      <CheckCircle className="w-6 h-6 text-green-600" />
                    ) : (
                      <Clock className="w-6 h-6 text-orange-600" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-slate-500">
                        {w.id.slice(0, 8).toUpperCase()}
                      </span>
                      {w.payment_status === "paid" ? (
                        <span className="badge-success">Paid</span>
                      ) : (
                        <span className="badge-warning">Unpaid</span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-sm text-slate-600">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-4 h-4" />
                        {new Date(w.created_at).toLocaleDateString()}
                      </span>
                      <span className="flex items-center gap-1">
                        <FileText className="w-4 h-4" />
                        Job: {w.job_id}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <p className="font-heading font-bold text-xl text-slate-900">
                    ${w.total.toFixed(2)}
                  </p>
                  <p className="text-sm text-slate-400">
                    {w.items?.length || 0} items
                  </p>
                </div>
              </div>

              {/* Expanded Details */}
              {expandedId === w.id && (
                <div className="border-t border-slate-200 p-4 bg-slate-50">
                  {/* Service Address */}
                  <div className="flex items-start gap-2 mb-4">
                    <MapPin className="w-4 h-4 text-slate-400 mt-0.5" />
                    <div>
                      <p className="text-xs text-slate-500 uppercase">Service Address</p>
                      <p className="text-slate-700">{w.service_address}</p>
                    </div>
                  </div>

                  {/* Items */}
                  <div className="space-y-2">
                    <p className="text-xs text-slate-500 uppercase font-semibold">
                      Materials Withdrawn
                    </p>
                    {w.items?.map((item, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-3 bg-white rounded-sm border border-slate-200"
                      >
                        <div>
                          <p className="font-mono text-xs text-slate-400">
                            {item.sku}
                          </p>
                          <p className="font-medium text-slate-800">{item.name}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-mono">
                            {item.quantity} × ${item.price.toFixed(2)}
                          </p>
                          <p className="font-bold text-slate-900">
                            ${item.subtotal.toFixed(2)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Summary */}
                  <div className="mt-4 pt-4 border-t border-slate-200 space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Subtotal</span>
                      <span className="font-mono">${w.subtotal.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Tax (8%)</span>
                      <span className="font-mono">${w.tax.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between font-bold text-lg pt-2">
                      <span>Total</span>
                      <span className="font-mono">${w.total.toFixed(2)}</span>
                    </div>
                  </div>

                  {w.notes && (
                    <div className="mt-4 p-3 bg-yellow-50 rounded-sm border border-yellow-200">
                      <p className="text-xs text-yellow-700 uppercase font-semibold mb-1">
                        Notes
                      </p>
                      <p className="text-sm text-yellow-800">{w.notes}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default MyHistory;
