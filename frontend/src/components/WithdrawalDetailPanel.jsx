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
            <p className="text-xs text-slate-500">Contractor</p>
            <div className="flex items-center gap-2 mt-1">
              <HardHat className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-sm font-medium text-slate-900">{wd?.contractor_name || "—"}</span>
            </div>
            {wd?.contractor_company && (
              <p className="text-xs text-slate-400 ml-5.5">{wd.contractor_company}</p>
            )}
          </div>
          <DetailField
            label="Date"
            value={wd?.created_at ? format(new Date(wd.created_at), "MMM d, yyyy h:mm a") : undefined}
          />
          <div>
            <p className="text-xs text-slate-500">Job</p>
            {wd?.job_id ? (
              <button
                type="button"
                onClick={() => onViewJob?.(wd.job_id)}
                className="text-sm font-mono text-blue-600 hover:text-blue-800 hover:underline mt-0.5 flex items-center gap-1.5"
              >
                <Briefcase className="w-3.5 h-3.5" />
                {wd.job_id}
              </button>
            ) : (
              <p className="text-sm text-slate-900 mt-0.5">—</p>
            )}
          </div>
          <div>
            <p className="text-xs text-slate-500">Billing Entity</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <Building2 className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-sm text-slate-900">{wd?.billing_entity || "—"}</span>
            </div>
          </div>
        </div>
      </DetailSection>

      {wd?.service_address && (
        <DetailSection label="Service Address">
          <div className="flex items-start gap-2">
            <MapPin className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
            <p className="text-sm text-slate-700">{wd.service_address}</p>
          </div>
        </DetailSection>
      )}

      <DetailSection label="Line Items">
        <div className="border border-slate-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50/80 border-b border-slate-200">
                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Item</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider w-16">Qty</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider w-24">Unit $</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider w-24">Amount</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <tr key={idx} className="border-b border-slate-100 last:border-b-0">
                  <td className="px-3 py-2">
                    <p className="font-medium text-slate-800">{item.product_name || item.description || "—"}</p>
                    {item.sku && <p className="text-[10px] text-slate-400 font-mono">{item.sku}</p>}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-600">{item.quantity}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-600">${(item.unit_price ?? 0).toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-mono font-semibold text-slate-900">
                    ${((item.quantity ?? 0) * (item.unit_price ?? 0)).toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex justify-end mt-3">
          <div className="text-right">
            <p className="text-xs text-slate-400 uppercase tracking-wider">Total</p>
            <p className="text-lg font-bold font-mono text-slate-900">${total.toFixed(2)}</p>
          </div>
        </div>
      </DetailSection>

      {wd?.invoice_id && (
        <DetailSection label="Invoice">
          <button
            type="button"
            onClick={() => onViewInvoice?.(wd.invoice_id)}
            className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800 hover:underline"
          >
            <FileText className="w-4 h-4" />
            View Invoice
          </button>
        </DetailSection>
      )}

      {wd?.notes && (
        <DetailSection label="Notes">
          <p className="text-sm text-slate-600 whitespace-pre-wrap">{wd.notes}</p>
        </DetailSection>
      )}
    </DetailPanel>
  );
}
