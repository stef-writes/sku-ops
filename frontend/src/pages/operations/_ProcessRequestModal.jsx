import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { JobPicker } from "@/components/JobPicker";
import { AddressPicker } from "@/components/AddressPicker";

export function ProcessRequestModal({
  open,
  onOpenChange,
  request,
  jobId,
  onJobIdChange,
  serviceAddress,
  onServiceAddressChange,
  notes,
  onNotesChange,
  onSubmit,
  isPending,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Process request</DialogTitle></DialogHeader>
        {request && (
          <div className="space-y-4 pt-2">
            <p className="text-sm text-muted-foreground">
              Processing request from <strong className="text-foreground">{request.contractor_name}</strong>
            </p>
            <div>
              <Label className="text-sm">Job ID *</Label>
              <div className="mt-1.5">
                <JobPicker value={jobId} onChange={onJobIdChange} placeholder="Job or reference number" required />
              </div>
            </div>
            <div>
              <Label className="text-sm">Service address *</Label>
              <div className="mt-1.5">
                <AddressPicker value={serviceAddress} onChange={onServiceAddressChange} placeholder="Pickup or delivery location" required />
              </div>
            </div>
            <div>
              <Label className="text-sm">Notes (optional)</Label>
              <Input value={notes} onChange={(e) => onNotesChange(e.target.value)} placeholder="Additional notes..." className="mt-1.5" />
            </div>
            <Button
              onClick={onSubmit}
              disabled={isPending || !jobId.trim() || !serviceAddress.trim()}
              className="w-full h-11"
            >
              {isPending ? "Processing…" : "Create Withdrawal"}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
