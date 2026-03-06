import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { useCreatePayment } from "@/hooks/usePayments";
import { PAYMENT_METHODS } from "@/lib/constants";
import { getErrorMessage } from "@/lib/api-client";
import { toast } from "sonner";

/**
 * Modal for recording a payment against one or more withdrawals.
 * @param {{ open: boolean, onOpenChange: (open: boolean) => void, withdrawalIds: string[], defaultAmount?: number }} props
 */
export function RecordPaymentModal({ open, onOpenChange, withdrawalIds = [], defaultAmount = 0 }) {
  const [amount, setAmount] = useState(defaultAmount || "");
  const [method, setMethod] = useState("bank_transfer");
  const [reference, setReference] = useState("");
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().split("T")[0]);
  const [notes, setNotes] = useState("");
  const createPayment = useCreatePayment();

  const reset = () => {
    setAmount(defaultAmount || "");
    setMethod("bank_transfer");
    setReference("");
    setPaymentDate(new Date().toISOString().split("T")[0]);
    setNotes("");
  };

  const handleSubmit = async () => {
    if (!withdrawalIds.length) return;
    try {
      await createPayment.mutateAsync({
        withdrawal_ids: withdrawalIds,
        amount: amount ? parseFloat(amount) : undefined,
        method,
        reference: reference.trim(),
        payment_date: paymentDate ? new Date(paymentDate).toISOString() : undefined,
        notes: notes.trim() || null,
      });
      toast.success("Payment recorded");
      reset();
      onOpenChange(false);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Record Payment</DialogTitle></DialogHeader>
        <div className="space-y-4 pt-2">
          <p className="text-sm text-muted-foreground">
            Recording payment for <strong>{withdrawalIds.length}</strong> withdrawal{withdrawalIds.length !== 1 ? "s" : ""}
          </p>
          <div>
            <Label className="text-sm">Amount</Label>
            <Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={defaultAmount ? defaultAmount.toFixed(2) : "Total"} className="mt-1.5" />
            <p className="text-xs text-muted-foreground mt-1">Leave blank to use withdrawal total</p>
          </div>
          <div>
            <Label className="text-sm">Method</Label>
            <Select value={method} onValueChange={setMethod}>
              <SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PAYMENT_METHODS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-sm">Reference (check #, txn ID, etc.)</Label>
            <Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Optional" className="mt-1.5" />
          </div>
          <div>
            <Label className="text-sm">Payment date</Label>
            <Input type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} className="mt-1.5" />
          </div>
          <div>
            <Label className="text-sm">Notes (optional)</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Additional notes..." className="mt-1.5" />
          </div>
          <Button onClick={handleSubmit} disabled={createPayment.isPending || !withdrawalIds.length} className="w-full h-11">
            {createPayment.isPending ? "Recording..." : "Record Payment"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
