import { useState } from "react";
import { Building2, Save, Mail, User, CreditCard } from "lucide-react";
import { toast } from "sonner";
import { format } from "date-fns";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { DetailPanel, DetailSection, DetailField } from "./DetailPanel";
import { StatusBadge } from "./StatusBadge";
import { useBillingEntity, useUpdateBillingEntity } from "@/hooks/useBillingEntities";

export function BillingEntityDetailPanel({ entityId, open, onOpenChange }) {
  const { data: entity, isLoading } = useBillingEntity(entityId);
  const updateEntity = useUpdateBillingEntity();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});

  const startEditing = () => {
    setForm({
      contact_name: entity?.contact_name || "",
      contact_email: entity?.contact_email || "",
      billing_address: entity?.billing_address || "",
      payment_terms: entity?.payment_terms || "",
      xero_contact_id: entity?.xero_contact_id || "",
    });
    setEditing(true);
  };

  const handleSave = async () => {
    try {
      await updateEntity.mutateAsync({ id: entityId, data: form });
      toast.success("Billing entity updated");
      setEditing(false);
    } catch {
      toast.error("Failed to update billing entity");
    }
  };

  return (
    <DetailPanel
      open={open}
      onOpenChange={onOpenChange}
      title={entity?.name || "Billing Entity"}
      status={entity?.is_active === false ? "inactive" : "active"}
      icon={Building2}
      loading={isLoading}
      width="md"
      actions={
        editing ? (
          <>
            <Button variant="outline" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
            <Button size="sm" onClick={handleSave} disabled={updateEntity.isPending} className="gap-1.5">
              <Save className="w-3.5 h-3.5" />
              {updateEntity.isPending ? "Saving…" : "Save"}
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" onClick={startEditing}>Edit</Button>
        )
      }
    >
      {editing ? (
        <DetailSection label="Details">
          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-500">Contact Name</label>
              <Input value={form.contact_name} onChange={(e) => setForm((f) => ({ ...f, contact_name: e.target.value }))} className="mt-1" />
            </div>
            <div>
              <label className="text-xs text-slate-500">Contact Email</label>
              <Input type="email" value={form.contact_email} onChange={(e) => setForm((f) => ({ ...f, contact_email: e.target.value }))} className="mt-1" />
            </div>
            <div>
              <label className="text-xs text-slate-500">Billing Address</label>
              <Input value={form.billing_address} onChange={(e) => setForm((f) => ({ ...f, billing_address: e.target.value }))} className="mt-1" />
            </div>
            <div>
              <label className="text-xs text-slate-500">Payment Terms</label>
              <Select value={form.payment_terms || "none"} onValueChange={(v) => setForm((f) => ({ ...f, payment_terms: v === "none" ? "" : v }))}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="due_on_receipt">Due on Receipt</SelectItem>
                  <SelectItem value="net_15">Net 15</SelectItem>
                  <SelectItem value="net_30">Net 30</SelectItem>
                  <SelectItem value="net_45">Net 45</SelectItem>
                  <SelectItem value="net_60">Net 60</SelectItem>
                  <SelectItem value="net_90">Net 90</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Xero Contact ID</label>
              <Input value={form.xero_contact_id} onChange={(e) => setForm((f) => ({ ...f, xero_contact_id: e.target.value }))} className="mt-1" placeholder="Optional" />
            </div>
          </div>
        </DetailSection>
      ) : (
        <>
          <DetailSection label="Contact">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-slate-500">Contact Name</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <User className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-sm text-slate-900">{entity?.contact_name || "—"}</span>
                </div>
              </div>
              <div>
                <p className="text-xs text-slate-500">Contact Email</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Mail className="w-3.5 h-3.5 text-slate-400" />
                  {entity?.contact_email ? (
                    <a href={`mailto:${entity.contact_email}`} className="text-sm text-blue-600 hover:underline">{entity.contact_email}</a>
                  ) : (
                    <span className="text-sm text-slate-900">—</span>
                  )}
                </div>
              </div>
            </div>
          </DetailSection>

          <DetailSection label="Billing">
            <div className="grid grid-cols-2 gap-4">
              <DetailField label="Billing Address" value={entity?.billing_address} />
              <div>
                <p className="text-xs text-slate-500">Payment Terms</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <CreditCard className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-sm text-slate-900">{entity?.payment_terms?.replace(/_/g, " ") || "—"}</span>
                </div>
              </div>
            </div>
          </DetailSection>

          {entity?.xero_contact_id && (
            <DetailSection label="Integrations">
              <DetailField label="Xero Contact ID" value={entity.xero_contact_id} mono />
            </DetailSection>
          )}

          <DetailSection label="Timestamps">
            <div className="grid grid-cols-2 gap-4">
              <DetailField
                label="Created"
                value={entity?.created_at ? format(new Date(entity.created_at), "MMM d, yyyy h:mm a") : undefined}
              />
              <DetailField
                label="Updated"
                value={entity?.updated_at ? format(new Date(entity.updated_at), "MMM d, yyyy h:mm a") : undefined}
              />
            </div>
          </DetailSection>
        </>
      )}
    </DetailPanel>
  );
}
