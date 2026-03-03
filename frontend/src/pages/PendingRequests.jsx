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
import { HardHat, Package, Loader2, Clock, AlertTriangle } from "lucide-react";
import { API } from "@/lib/api";

const PendingRequests = () => {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processOpen, setProcessOpen] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [jobId, setJobId] = useState("");
  const [serviceAddress, setServiceAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    fetchRequests();
  }, []);

  const fetchRequests = async () => {
    try {
      const res = await axios.get(`${API}/material-requests`);
      setRequests(res.data.filter((r) => r.status === "pending"));
    } catch (error) {
      toast.error("Failed to load requests");
    } finally {
      setLoading(false);
    }
  };

  const openProcess = (req) => {
    setSelectedRequest(req);
    setJobId(req.job_id || "");
    setServiceAddress(req.service_address || "");
    setNotes(req.notes || "");
    setProcessOpen(true);
  };

  const closeProcess = () => {
    setProcessOpen(false);
    setSelectedRequest(null);
    setJobId("");
    setServiceAddress("");
    setNotes("");
  };

  const handleProcess = async () => {
    if (!selectedRequest) return;
    if (!jobId.trim()) {
      toast.error("Job ID is required");
      return;
    }
    if (!serviceAddress.trim()) {
      toast.error("Service address is required");
      return;
    }
    setProcessing(true);
    try {
      await axios.post(`${API}/material-requests/${selectedRequest.id}/process`, {
        job_id: jobId.trim(),
        service_address: serviceAddress.trim(),
        notes: notes.trim() || null,
      });
      toast.success("Request processed. Withdrawal created.");
      closeProcess();
      fetchRequests();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to process");
    } finally {
      setProcessing(false);
    }
  };

  const ageLabel = (dateStr) => {
    const ms = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(ms / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  const ageHours = (dateStr) =>
    (Date.now() - new Date(dateStr).getTime()) / 3600000;

  // Sort oldest first so staff sees the most urgent requests at the top
  const sortedRequests = [...requests].sort(
    (a, b) => new Date(a.created_at) - new Date(b.created_at)
  );

  const itemCount = (req) => {
    const items = req.items || [];
    return items.reduce((sum, i) => sum + (i.quantity || 0), 0);
  };

  const totalAmount = (req) => {
    const items = req.items || [];
    const subtotal = items.reduce((sum, i) => sum + (i.subtotal || 0), 0);
    return (subtotal * 1.08).toFixed(2);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="pending-requests-page">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Pending Material Requests</h1>
          <p className="text-slate-600 mt-1">Process contractor requests into withdrawals at pickup · Oldest first</p>
        </div>
        {requests.length > 0 && (
          <span className="text-sm font-medium text-slate-500">
            {requests.length} pending
          </span>
        )}
      </div>

      {requests.length === 0 ? (
        <div className="card-workshop p-12 text-center">
          <Package className="w-16 h-16 mx-auto text-slate-300 mb-4" />
          <p className="font-medium text-slate-600">No pending requests</p>
          <p className="text-sm text-slate-500 mt-1">Contractors will appear here when they submit requests</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {sortedRequests.map((req) => {
            const hours = ageHours(req.created_at);
            const urgentBorder =
              hours >= 48
                ? "border-red-300 bg-red-50/30"
                : hours >= 24
                ? "border-orange-300 bg-orange-50/20"
                : "border-slate-200";
            const ageBadgeClass =
              hours >= 48
                ? "text-red-600 bg-red-50 border border-red-200"
                : hours >= 24
                ? "text-orange-600 bg-orange-50 border border-orange-200"
                : "text-slate-500";
            return (
              <div
                key={req.id}
                className={`card-workshop p-6 border hover:border-amber-300 transition-colors ${urgentBorder}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
                      <HardHat className="w-6 h-6 text-amber-600" />
                    </div>
                    <div>
                      <p className="font-semibold text-slate-900">{req.contractor_name || "Unknown"}</p>
                      <p className="text-sm text-slate-500">{itemCount(req)} items · ${totalAmount(req)}</p>
                    </div>
                  </div>
                  <Button onClick={() => openProcess(req)} size="sm" data-testid={`process-request-${req.id}`}>
                    Process
                  </Button>
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Clock className="w-3.5 h-3.5" />
                    {new Date(req.created_at).toLocaleString()}
                  </div>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex items-center gap-1 ${ageBadgeClass}`}>
                    {hours >= 24 && <AlertTriangle className="w-3 h-3" />}
                    {ageLabel(req.created_at)}
                  </span>
                </div>

                {req.items && req.items.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-100">
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Items</p>
                    <ul className="space-y-0.5 text-sm text-slate-700">
                      {req.items.map((i, idx) => (
                        <li key={idx} className="flex justify-between">
                          <span>{i.name}</span>
                          <span className="font-mono text-slate-500">×{i.quantity}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={processOpen} onOpenChange={(open) => !open && closeProcess()}>
        <DialogContent className="sm:max-w-lg rounded-2xl">
          <DialogHeader>
            <DialogTitle>Process request</DialogTitle>
          </DialogHeader>
          {selectedRequest && (
            <div className="space-y-4 pt-4">
              <p className="text-sm text-slate-600">
                Processing request from <strong>{selectedRequest.contractor_name}</strong>. Enter job details below.
              </p>
              <div>
                <Label>Job ID *</Label>
                <Input
                  value={jobId}
                  onChange={(e) => setJobId(e.target.value)}
                  placeholder="Job or reference number"
                  className="mt-2"
                  data-testid="process-job-id"
                />
              </div>
              <div>
                <Label>Service address *</Label>
                <Input
                  value={serviceAddress}
                  onChange={(e) => setServiceAddress(e.target.value)}
                  placeholder="Pickup or delivery location"
                  className="mt-2"
                  data-testid="process-service-address"
                />
              </div>
              <div>
                <Label>Notes (optional)</Label>
                <Input
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Additional notes..."
                  className="mt-2"
                />
              </div>
              <Button
                onClick={handleProcess}
                disabled={processing || !jobId.trim() || !serviceAddress.trim()}
                className="w-full h-12"
              >
                {processing ? "Processing…" : "Create Withdrawal"}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PendingRequests;
