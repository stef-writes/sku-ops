import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { JobPicker } from "@/components/JobPicker";
import { AddressPicker } from "@/components/AddressPicker";

export function SubmitRequestModal({
  open,
  onOpenChange,
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
        <DialogHeader><DialogTitle>Submit material request</DialogTitle></DialogHeader>
        <div className="space-y-4 pt-2">
          <div>
            <Label className="text-sm">Job ID (optional)</Label>
            <div className="mt-1.5">
              <JobPicker value={jobId} onChange={onJobIdChange} placeholder="Job or reference number" />
            </div>
          </div>
          <div>
            <Label className="text-sm">Service address (optional)</Label>
            <div className="mt-1.5">
              <AddressPicker value={serviceAddress} onChange={onServiceAddressChange} placeholder="Pickup or delivery location" />
            </div>
          </div>
          <div>
            <Label className="text-sm">Notes (optional)</Label>
            <Input value={notes} onChange={(e) => onNotesChange(e.target.value)} placeholder="Additional notes..." className="mt-1.5" />
          </div>
          <Button onClick={onSubmit} disabled={isPending} className="w-full h-11">
            {isPending ? "Submitting…" : "Submit Request"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
