import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { HardHat, Package, Clock, AlertTriangle } from "lucide-react";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { useMaterialRequests, useProcessMaterialRequest } from "@/hooks/useMaterialRequests";
import { getErrorMessage } from "@/lib/api-client";
import { ProcessRequestModal } from "./_ProcessRequestModal";

const PendingRequests = () => {
  const { data: allRequests, isLoading } = useMaterialRequests(undefined, { refetchInterval: 30000 });
  const processRequest = useProcessMaterialRequest();

  const [processOpen, setProcessOpen] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [jobId, setJobId] = useState("");
  const [serviceAddress, setServiceAddress] = useState("");
  const [notes, setNotes] = useState("");

  const requests = (allRequests || []).filter((r) => r.status === "pending");
  const sorted = [...requests].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

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
    setJobId(""); setServiceAddress(""); setNotes("");
  };

  const handleProcess = async () => {
    if (!selectedRequest || !jobId.trim() || !serviceAddress.trim()) return;
    try {
      await processRequest.mutateAsync({
        id: selectedRequest.id,
        data: { job_id: jobId.trim(), service_address: serviceAddress.trim(), notes: notes.trim() || null },
      });
      toast.success("Request processed. Withdrawal created.");
      closeProcess();
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const ageLabel = (dateStr) => {
    const mins = Math.floor((Date.now() - new Date(dateStr).getTime()) / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const ageHours = (dateStr) => (Date.now() - new Date(dateStr).getTime()) / 3600000;

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="pending-requests-page">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Pending Requests</h1>
          <p className="text-slate-500 mt-1 text-sm">Process contractor requests into withdrawals at pickup</p>
        </div>
        {requests.length > 0 && <span className="text-sm font-medium text-slate-400">{requests.length} pending</span>}
      </div>

      {requests.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-16 text-center shadow-sm">
          <Package className="w-12 h-12 mx-auto text-slate-300 mb-3" />
          <p className="font-medium text-slate-600">No pending requests</p>
          <p className="text-sm text-slate-400 mt-1">Requests appear here when contractors submit them</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sorted.map((req) => {
            const hours = ageHours(req.created_at);
            const border = hours >= 48 ? "border-red-200 bg-red-50/30" : hours >= 24 ? "border-orange-200 bg-orange-50/20" : "border-slate-200";
            const ageCls = hours >= 48 ? "text-red-600 bg-red-50" : hours >= 24 ? "text-orange-600 bg-orange-50" : "text-slate-500";
            const itemCount = (req.items || []).reduce((s, i) => s + (i.quantity || 0), 0);
            return (
              <div key={req.id} className={`bg-white border rounded-xl p-5 shadow-sm ${border}`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center shrink-0">
                      <HardHat className="w-5 h-5 text-amber-600" />
                    </div>
                    <div>
                      <p className="font-semibold text-slate-900 text-sm">{req.contractor_name || "Unknown"}</p>
                      <p className="text-xs text-slate-500">{itemCount} items</p>
                    </div>
                  </div>
                  <Button onClick={() => openProcess(req)} size="sm" data-testid={`process-request-${req.id}`}>Process</Button>
                </div>
                {req.items?.length > 0 && (
                  <div className="border-t border-slate-100 pt-2 mb-2">
                    <ul className="space-y-0.5 text-xs text-slate-600">
                      {req.items.map((i, idx) => (
                        <li key={idx} className="flex justify-between"><span className="truncate">{i.name}</span><span className="font-mono text-slate-400 ml-2 shrink-0">x{i.quantity}</span></li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="flex items-center justify-between text-xs text-slate-400 pt-1">
                  <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(req.created_at).toLocaleDateString()}</span>
                  <span className={`font-semibold px-2 py-0.5 rounded-full flex items-center gap-1 ${ageCls}`}>
                    {hours >= 24 && <AlertTriangle className="w-3 h-3" />}{ageLabel(req.created_at)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ProcessRequestModal
        open={processOpen}
        onOpenChange={(open) => !open && closeProcess()}
        request={selectedRequest}
        jobId={jobId}
        onJobIdChange={setJobId}
        serviceAddress={serviceAddress}
        onServiceAddressChange={setServiceAddress}
        notes={notes}
        onNotesChange={setNotes}
        onSubmit={handleProcess}
        isPending={processRequest.isPending}
      />
    </div>
  );
};

export default PendingRequests;
