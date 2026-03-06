import { DollarSign, FileText, CreditCard } from "lucide-react";
import { format } from "date-fns";
import { DetailPanel, DetailSection, DetailField } from "@/components/DetailPanel";
import { usePayment } from "@/hooks/usePayments";
import { PAYMENT_METHODS } from "@/lib/constants";

export function PaymentDetailPanel({ paymentId, open, onOpenChange, onViewInvoice }) {
  const { data: payment, isLoading } = usePayment(paymentId);

  const methodLabel = PAYMENT_METHODS.find((m) => m.value === payment?.method)?.label || payment?.method || "—";

  return (
    <DetailPanel
      open={open}
      onOpenChange={onOpenChange}
      title="Payment"
      subtitle={payment?.id ? payment.id.slice(0, 12) + "…" : undefined}
      icon={DollarSign}
      loading={isLoading}
      width="md"
    >
      <DetailSection label="Payment Details">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Amount</p>
            <p className="text-2xl font-bold font-mono text-foreground mt-0.5">
              ${(payment?.amount ?? 0).toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Method</p>
            <div className="flex items-center gap-2 mt-1">
              <CreditCard className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium text-foreground">{methodLabel}</span>
            </div>
          </div>
          <DetailField
            label="Payment Date"
            value={payment?.payment_date ? format(new Date(payment.payment_date), "MMM d, yyyy") : undefined}
          />
          <DetailField label="Reference" value={payment?.reference} mono />
        </div>
      </DetailSection>

      {payment?.invoice_id && (
        <DetailSection label="Linked Invoice">
          <button
            type="button"
            onClick={() => onViewInvoice?.(payment.invoice_id)}
            className="flex items-center gap-2 text-sm text-info hover:text-info hover:underline"
          >
            <FileText className="w-4 h-4" />
            View Invoice
          </button>
        </DetailSection>
      )}

      {payment?.notes && (
        <DetailSection label="Notes">
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{payment.notes}</p>
        </DetailSection>
      )}

      <DetailSection label="Record Info">
        <div className="grid grid-cols-2 gap-4">
          <DetailField
            label="Recorded"
            value={payment?.created_at ? format(new Date(payment.created_at), "MMM d, yyyy h:mm a") : undefined}
          />
          <DetailField label="Xero ID" value={payment?.xero_payment_id} mono />
        </div>
      </DetailSection>
    </DetailPanel>
  );
}
