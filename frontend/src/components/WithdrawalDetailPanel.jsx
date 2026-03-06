import { Link } from "react-router-dom";
import { ShoppingCart, HardHat, Briefcase, Building2, MapPin, FileText } from "lucide-react";
import { format } from "date-fns";
import { DetailPanel, DetailSection, DetailField } from "./DetailPanel";
import { StatusBadge } from "./StatusBadge";
import { useWithdrawal } from "@/hooks/useWithdrawals";

export function WithdrawalDetailPanel({ withdrawalId, open, onOpenChange, onViewInvoice, onViewJob }) {
  const { data: wd, isLoading } = useWithdrawal(withdrawalId);

  const items = wd?.items || [];
  const total = wd?.total || items.reduce((s, i) => s + (i.quantity * i.unit_price), 0);

  return (
    <DetailPanel
      open={open}
      onOpenChange={onOpenChange}
      title={`Withdrawal`}
      subtitle={wd?.id ? wd.id.slice(0, 12) + "…" : undefined}
      status={wd?.invoice_id ? "invoiced" : "uninvoiced"}
      icon={ShoppingCart}
      loading={isLoading}
      width="lg"
    >
      <DetailSection label="Details">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Contractor</p>
            <div className="flex items-center gap-2 mt-1">
              <HardHat className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="text-sm font-medium text-foreground">{wd?.contractor_name || "—"}</span>
            </div>
            {wd?.contractor_company && (
              <p className="text-xs text-muted-foreground ml-5.5">{wd.contractor_company}</p>
            )}
          </div>
          <DetailField
            label="Date"
            value={wd?.created_at ? format(new Date(wd.created_at), "MMM d, yyyy h:mm a") : undefined}
          />
          <div>
            <p className="text-xs text-muted-foreground">Job</p>
            {wd?.job_id ? (
              <button
                type="button"
                onClick={() => onViewJob?.(wd.job_id)}
                className="text-sm font-mono text-info hover:text-info hover:underline mt-0.5 flex items-center gap-1.5"
              >
                <Briefcase className="w-3.5 h-3.5" />
                {wd.job_id}
              </button>
            ) : (
              <p className="text-sm text-foreground mt-0.5">—</p>
            )}
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Billing Entity</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="text-sm text-foreground">{wd?.billing_entity || "—"}</span>
            </div>
          </div>
        </div>
      </DetailSection>

      {wd?.service_address && (
        <DetailSection label="Service Address">
          <div className="flex items-start gap-2">
            <MapPin className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" />
            <p className="text-sm text-foreground">{wd.service_address}</p>
          </div>
        </DetailSection>
      )}

      <DetailSection label="Line Items">
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/80 border-b border-border">
                <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">Item</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider w-14">Qty</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider w-20">Unit $</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider w-20">Cost</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider w-20">Amount</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider w-16">Margin</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => {
                const unitPrice = item.unit_price ?? 0;
                const unitCost = item.cost ?? 0;
                const marginPct = unitPrice > 0 ? ((unitPrice - unitCost) / unitPrice * 100) : 0;
                return (
                  <tr key={idx} className="border-b border-border/50 last:border-b-0">
                    <td className="px-3 py-2">
                      <p className="font-medium text-foreground">{item.product_name || item.description || "—"}</p>
                      {item.sku && <p className="text-[10px] text-muted-foreground font-mono">{item.sku}</p>}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-muted-foreground">{item.quantity}</td>
                    <td className="px-3 py-2 text-right font-mono text-muted-foreground">${unitPrice.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right font-mono text-muted-foreground">${unitCost.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right font-mono font-semibold text-foreground">
                      ${((item.quantity ?? 0) * unitPrice).toFixed(2)}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono text-xs font-bold ${marginPct >= 40 ? "text-success" : marginPct < 30 ? "text-category-5" : "text-info"}`}>
                      {marginPct.toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex justify-end mt-3 gap-6">
          <div className="text-right">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">COGS</p>
            <p className="text-sm font-semibold font-mono text-muted-foreground">${(wd?.cost_total ?? 0).toFixed(2)}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Revenue</p>
            <p className="text-sm font-semibold font-mono text-foreground">${total.toFixed(2)}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Margin</p>
            <p className={`text-sm font-bold font-mono ${total > 0 && ((total - (wd?.cost_total ?? 0)) / total * 100) >= 40 ? "text-success" : "text-category-5"}`}>
              {total > 0 ? ((total - (wd?.cost_total ?? 0)) / total * 100).toFixed(1) : "0.0"}%
            </p>
          </div>
        </div>
      </DetailSection>

      {wd?.invoice_id && (
        <DetailSection label="Invoice">
          <button
            type="button"
            onClick={() => onViewInvoice?.(wd.invoice_id)}
            className="flex items-center gap-2 text-sm text-info hover:text-info hover:underline"
          >
            <FileText className="w-4 h-4" />
            View Invoice
          </button>
        </DetailSection>
      )}

      {wd?.notes && (
        <DetailSection label="Notes">
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{wd.notes}</p>
        </DetailSection>
      )}
    </DetailPanel>
  );
}
