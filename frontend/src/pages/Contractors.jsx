import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Plus, Edit2, Trash2, HardHat, Mail, Phone,
  Building2, DollarSign, ToggleLeft, ToggleRight,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ROLES } from "@/lib/constants";
import { getErrorMessage } from "@/lib/api-client";
import {
  useContractors,
  useCreateContractor,
  useUpdateContractor,
  useDeleteContractor,
} from "@/hooks/useContractors";

const INITIAL_FORM = { name: "", email: "", password: "", company: "", billing_entity: "", phone: "" };

const Contractors = () => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingContractor, setEditingContractor] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, contractor: null });

  const { data: contractors = [], isLoading } = useContractors();
  const createMutation = useCreateContractor();
  const updateMutation = useUpdateContractor();
  const deleteMutation = useDeleteContractor();
  const saving = createMutation.isPending || updateMutation.isPending;

  const openDialog = (contractor = null) => {
    if (contractor) {
      setEditingContractor(contractor);
      setForm({
        name: contractor.name,
        email: contractor.email,
        password: "",
        company: contractor.company || "",
        billing_entity: contractor.billing_entity || "",
        phone: contractor.phone || "",
      });
    } else {
      setEditingContractor(null);
      setForm(INITIAL_FORM);
    }
    setDialogOpen(true);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.name || !form.email) {
      toast.error("Name and email are required");
      return;
    }
    if (!editingContractor && !form.password) {
      toast.error("Password is required for new contractors");
      return;
    }

    if (editingContractor) {
      updateMutation.mutate(
        { id: editingContractor.id, data: { name: form.name, company: form.company, billing_entity: form.billing_entity, phone: form.phone } },
        {
          onSuccess: () => { toast.success("Contractor updated!"); setDialogOpen(false); },
          onError: (err) => toast.error(getErrorMessage(err)),
        }
      );
    } else {
      createMutation.mutate(
        { ...form, role: ROLES.CONTRACTOR },
        {
          onSuccess: () => { toast.success("Contractor created!"); setDialogOpen(false); },
          onError: (err) => toast.error(getErrorMessage(err)),
        }
      );
    }
  };

  const handleDeleteConfirm = async () => {
    const { contractor } = deleteConfirm;
    if (!contractor) return;
    try {
      await deleteMutation.mutateAsync(contractor.id);
      toast.success("Contractor deleted");
    } catch (error) {
      toast.error(getErrorMessage(error));
      throw error;
    }
  };

  const toggleActive = (contractor) => {
    updateMutation.mutate(
      { id: contractor.id, data: { is_active: !contractor.is_active } },
      {
        onSuccess: () => toast.success(contractor.is_active ? "Contractor disabled" : "Contractor enabled"),
        onError: () => toast.error("Failed to update contractor status"),
      }
    );
  };

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="contractors-page">
      <PageHeader
        title="Contractors"
        subtitle={`${contractors.length} registered contractors`}
        action={
          <Button onClick={() => openDialog()} className="btn-primary h-12 px-6" data-testid="add-contractor-btn">
            <Plus className="w-5 h-5 mr-2" />
            Add Contractor
          </Button>
        }
      />

      {contractors.length === 0 ? (
        <div className="card-workshop p-12 text-center">
          <HardHat className="w-16 h-16 mx-auto mb-4 text-slate-300" />
          <p className="text-slate-500 font-medium">No contractors yet</p>
          <p className="text-slate-400 text-sm mb-4">Add contractors to allow material withdrawals</p>
          <Button onClick={() => openDialog()} className="btn-primary">
            <Plus className="w-5 h-5 mr-2" />
            Add First Contractor
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="contractors-grid">
          {contractors.map((contractor) => (
            <div key={contractor.id} className={`card-workshop p-6 ${!contractor.is_active ? "opacity-60" : ""}`} data-testid={`contractor-card-${contractor.id}`}>
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-sm flex items-center justify-center ${contractor.is_active ? "bg-green-100" : "bg-slate-100"}`}>
                    <HardHat className={`w-6 h-6 ${contractor.is_active ? "text-green-600" : "text-slate-400"}`} />
                  </div>
                  {!contractor.is_active && <span className="badge-error text-xs">Disabled</span>}
                </div>
                <div className="flex gap-1">
                  <button onClick={() => toggleActive(contractor)} className="p-2 text-slate-600 hover:text-blue-500 hover:bg-blue-50 rounded-sm transition-colors" title={contractor.is_active ? "Disable" : "Enable"} data-testid={`toggle-contractor-${contractor.id}`}>
                    {contractor.is_active ? <ToggleRight className="w-5 h-5" /> : <ToggleLeft className="w-5 h-5" />}
                  </button>
                  <button onClick={() => openDialog(contractor)} className="p-2 text-slate-600 hover:text-orange-500 hover:bg-orange-50 rounded-sm transition-colors" data-testid={`edit-contractor-${contractor.id}`}>
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button onClick={() => setDeleteConfirm({ open: true, contractor })} className="p-2 text-slate-600 hover:text-red-500 hover:bg-red-50 rounded-sm transition-colors" data-testid={`delete-contractor-${contractor.id}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <h3 className="font-heading font-bold text-xl text-slate-900 uppercase tracking-wide mb-2">{contractor.name}</h3>
              <div className="space-y-2 text-sm text-slate-500">
                <div className="flex items-center gap-2"><Mail className="w-4 h-4" /><span>{contractor.email}</span></div>
                {contractor.phone && <div className="flex items-center gap-2"><Phone className="w-4 h-4" /><span>{contractor.phone}</span></div>}
                {contractor.company && <div className="flex items-center gap-2"><Building2 className="w-4 h-4" /><span>{contractor.company}</span></div>}
                {contractor.billing_entity && <div className="flex items-center gap-2"><DollarSign className="w-4 h-4" /><span className="text-xs">Bills to: {contractor.billing_entity}</span></div>}
              </div>
              <div className="mt-4 pt-4 border-t border-slate-200">
                <span className="text-xs text-slate-400">Created {new Date(contractor.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="contractor-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
              {editingContractor ? "Edit Contractor" : "Add New Contractor"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 pt-4">
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Full Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="John Smith" className="input-workshop mt-2" data-testid="contractor-name-input" />
            </div>
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Email *</Label>
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="john@company.com" className="input-workshop mt-2" disabled={!!editingContractor} data-testid="contractor-email-input" />
            </div>
            {!editingContractor && (
              <div>
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Password *</Label>
                <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="••••••••" className="input-workshop mt-2" data-testid="contractor-password-input" />
              </div>
            )}
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Company</Label>
              <Input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} placeholder="On Point / Stone & Timber / Independent" className="input-workshop mt-2" data-testid="contractor-company-input" />
            </div>
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Billing Entity</Label>
              <Input value={form.billing_entity} onChange={(e) => setForm({ ...form, billing_entity: e.target.value })} placeholder="Entity to invoice for materials" className="input-workshop mt-2" data-testid="contractor-billing-input" />
            </div>
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Phone</Label>
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="(555) 123-4567" className="input-workshop mt-2" data-testid="contractor-phone-input" />
            </div>
            <div className="flex gap-3 pt-4">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)} className="flex-1 btn-secondary h-12" data-testid="contractor-cancel-btn">Cancel</Button>
              <Button type="submit" disabled={saving} className="flex-1 btn-primary h-12" data-testid="contractor-save-btn">
                {saving ? "Saving..." : editingContractor ? "Update" : "Create"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteConfirm.open}
        onOpenChange={(open) => setDeleteConfirm((p) => ({ ...p, open }))}
        title="Delete contractor"
        description={deleteConfirm.contractor ? `Delete "${deleteConfirm.contractor.name}"? This cannot be undone.` : ""}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleDeleteConfirm}
        variant="danger"
      />
    </div>
  );
};

export default Contractors;
