import { useState, useMemo } from "react";
import { Building2, Plus, Mail, CreditCard, User } from "lucide-react";
import { format } from "date-fns";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { EntityFormDialog } from "@/components/EntityFormDialog";
import { BillingEntityDetailPanel } from "./_BillingEntityDetailPanel";
import { useBillingEntities, useCreateBillingEntity } from "@/hooks/useBillingEntities";
import { getErrorMessage } from "@/lib/api-client";

const createSchema = z.object({
  name: z.string().min(1, "Name is required"),
  contact_name: z.string().optional().default(""),
  contact_email: z.string().email("Invalid email").or(z.literal("")).optional().default(""),
});

const FIELDS = [
  { name: "name", label: "Name *", placeholder: "e.g. Acme Construction LLC" },
  { name: "contact_name", label: "Contact Name", placeholder: "Optional" },
  { name: "contact_email", label: "Contact Email", type: "email", placeholder: "Optional" },
];

const DEFAULTS = { name: "", contact_name: "", contact_email: "" };

const BillingEntities = () => {
  const [detailId, setDetailId] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);

  const { data: entities = [], isLoading } = useBillingEntities();
  const createEntity = useCreateBillingEntity();

  const activeCount = useMemo(
    () => entities.filter((e) => e.is_active !== false).length,
    [entities]
  );

  const handleCreate = async (data) => {
    try {
      const entity = await createEntity.mutateAsync(data);
      toast.success(`Billing entity "${data.name}" created`);
      setCreateOpen(false);
      setDetailId(entity.id);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="billing-entities-page">
      <PageHeader
        title="Billing Entities"
        subtitle={`${entities.length} entit${entities.length !== 1 ? "ies" : "y"} · ${activeCount} active`}
        action={
          <Button onClick={() => setCreateOpen(true)} className="gap-2">
            <Plus className="w-4 h-4" />
            New Entity
          </Button>
        }
      />

      {entities.length === 0 ? (
        <div className="card-workshop p-12 text-center">
          <Building2 className="w-16 h-16 mx-auto mb-4 text-slate-300" />
          <p className="text-slate-500 font-medium">No billing entities yet</p>
          <p className="text-slate-400 text-sm mb-4">
            Billing entities represent the companies or entities you bill for materials
          </p>
          <Button onClick={() => setCreateOpen(true)} className="gap-2">
            <Plus className="w-4 h-4" />
            Create First Entity
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {entities.map((entity) => (
            <button
              key={entity.id}
              type="button"
              onClick={() => setDetailId(entity.id)}
              className={`text-left bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition-all ${entity.is_active === false ? "opacity-60" : ""}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                  <Building2 className="w-5 h-5 text-blue-500" />
                </div>
                <StatusBadge status={entity.is_active === false ? "inactive" : "active"} />
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">{entity.name}</h3>
              <div className="space-y-1.5 text-sm text-slate-500">
                {entity.contact_name && (
                  <div className="flex items-center gap-2">
                    <User className="w-3.5 h-3.5 text-slate-400" />
                    <span>{entity.contact_name}</span>
                  </div>
                )}
                {entity.contact_email && (
                  <div className="flex items-center gap-2">
                    <Mail className="w-3.5 h-3.5 text-slate-400" />
                    <span className="truncate">{entity.contact_email}</span>
                  </div>
                )}
                {entity.payment_terms && (
                  <div className="flex items-center gap-2">
                    <CreditCard className="w-3.5 h-3.5 text-slate-400" />
                    <span className="capitalize">{entity.payment_terms.replace(/_/g, " ")}</span>
                  </div>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-3 pt-3 border-t border-slate-100">
                Created {entity.created_at ? format(new Date(entity.created_at), "MMM d, yyyy") : "—"}
              </p>
            </button>
          ))}
        </div>
      )}

      <BillingEntityDetailPanel
        entityId={detailId}
        open={!!detailId}
        onOpenChange={(open) => !open && setDetailId(null)}
      />

      <EntityFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="Billing Entity"
        schema={createSchema}
        fields={FIELDS}
        defaults={DEFAULTS}
        onSubmit={handleCreate}
        saving={createEntity.isPending}
        testIdPrefix="billing-entity"
      />
    </div>
  );
};

export default BillingEntities;
