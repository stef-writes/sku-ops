import { useState } from "react";
import { useNavigate } from "react-router-dom";
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
import { Plus, Edit2, Trash2, Users, Mail, Phone, MapPin, FileUp } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { getErrorMessage } from "@/lib/api-client";
import { useVendors, useCreateVendor, useUpdateVendor, useDeleteVendor } from "@/hooks/useVendors";

const INITIAL_FORM = { name: "", contact_name: "", email: "", phone: "", address: "" };

const Vendors = () => {
  const navigate = useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, vendor: null });

  const { data: vendors = [], isLoading } = useVendors();
  const createMutation = useCreateVendor();
  const updateMutation = useUpdateVendor();
  const deleteMutation = useDeleteVendor();
  const saving = createMutation.isPending || updateMutation.isPending;

  const openDialog = (vendor = null) => {
    if (vendor) {
      setEditingVendor(vendor);
      setForm({
        name: vendor.name,
        contact_name: vendor.contact_name || "",
        email: vendor.email || "",
        phone: vendor.phone || "",
        address: vendor.address || "",
      });
    } else {
      setEditingVendor(null);
      setForm(INITIAL_FORM);
    }
    setDialogOpen(true);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.name) {
      toast.error("Vendor name is required");
      return;
    }
    const mutation = editingVendor ? updateMutation : createMutation;
    const arg = editingVendor ? { id: editingVendor.id, data: form } : form;

    mutation.mutate(arg, {
      onSuccess: () => {
        toast.success(editingVendor ? "Vendor updated!" : "Vendor created!");
        setDialogOpen(false);
      },
      onError: (err) => toast.error(getErrorMessage(err)),
    });
  };

  const handleDeleteConfirm = async () => {
    const { vendor } = deleteConfirm;
    if (!vendor) return;
    try {
      await deleteMutation.mutateAsync(vendor.id);
      toast.success("Vendor deleted");
    } catch (error) {
      toast.error(getErrorMessage(error));
      throw error;
    }
  };

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="vendors-page">
      <PageHeader
        title="Vendors"
        subtitle={`${vendors.length} vendors`}
        action={
          <div className="flex gap-2">
            <Button onClick={() => navigate("/import")} variant="outline" className="h-12 px-6" data-testid="import-document-btn">
              <FileUp className="w-5 h-5 mr-2" />
              Import Document
            </Button>
            <Button onClick={() => openDialog()} className="btn-primary h-12 px-6" data-testid="add-vendor-btn">
              <Plus className="w-5 h-5 mr-2" />
              Add Vendor
            </Button>
          </div>
        }
      />

      {vendors.length === 0 ? (
        <div className="card-workshop p-12">
          <EmptyState
            icon={Users}
            title="No vendors yet"
            description="Add vendors to track your suppliers"
            action={
              <Button onClick={() => openDialog()} className="btn-primary">
                <Plus className="w-5 h-5 mr-2" />
                Add First Vendor
              </Button>
            }
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="vendors-grid">
          {vendors.map((vendor) => (
            <div key={vendor.id} className="card-workshop p-6" data-testid={`vendor-card-${vendor.id}`}>
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-slate-100 rounded-sm flex items-center justify-center">
                  <Users className="w-6 h-6 text-slate-600" />
                </div>
                <div className="flex gap-1">
                  <button onClick={() => openDialog(vendor)} className="p-2 text-slate-600 hover:text-orange-500 hover:bg-orange-50 rounded-sm transition-colors" data-testid={`edit-vendor-${vendor.id}`}>
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button onClick={() => setDeleteConfirm({ open: true, vendor })} className="p-2 text-slate-600 hover:text-red-500 hover:bg-red-50 rounded-sm transition-colors" data-testid={`delete-vendor-${vendor.id}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <h3 className="font-heading font-bold text-xl text-slate-900 uppercase tracking-wide mb-2">{vendor.name}</h3>
              {vendor.contact_name && <p className="text-slate-600 mb-3">{vendor.contact_name}</p>}
              <div className="space-y-2 text-sm text-slate-500">
                {vendor.email && <div className="flex items-center gap-2"><Mail className="w-4 h-4" /><span>{vendor.email}</span></div>}
                {vendor.phone && <div className="flex items-center gap-2"><Phone className="w-4 h-4" /><span>{vendor.phone}</span></div>}
                {vendor.address && <div className="flex items-center gap-2"><MapPin className="w-4 h-4" /><span className="truncate">{vendor.address}</span></div>}
              </div>
              <div className="mt-4 pt-4 border-t border-slate-200">
                <span className="text-xs text-slate-400 uppercase tracking-wide">{vendor.product_count || 0} products</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="vendor-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
              {editingVendor ? "Edit Vendor" : "Add New Vendor"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 pt-4">
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Company Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g., ABC Hardware Supply" className="input-workshop mt-2" data-testid="vendor-name-input" />
            </div>
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Contact Name</Label>
              <Input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} placeholder="e.g., John Smith" className="input-workshop mt-2" data-testid="vendor-contact-input" />
            </div>
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Email</Label>
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="vendor@example.com" className="input-workshop mt-2" data-testid="vendor-email-input" />
            </div>
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Phone</Label>
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="(555) 123-4567" className="input-workshop mt-2" data-testid="vendor-phone-input" />
            </div>
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">Address</Label>
              <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="123 Main St, City, State" className="input-workshop mt-2" data-testid="vendor-address-input" />
            </div>
            <div className="flex gap-3 pt-4">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)} className="flex-1 btn-secondary h-12" data-testid="vendor-cancel-btn">Cancel</Button>
              <Button type="submit" disabled={saving} className="flex-1 btn-primary h-12" data-testid="vendor-save-btn">
                {saving ? "Saving..." : editingVendor ? "Update Vendor" : "Create Vendor"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteConfirm.open}
        onOpenChange={(open) => setDeleteConfirm((p) => ({ ...p, open }))}
        title="Delete vendor"
        description={deleteConfirm.vendor ? `Delete "${deleteConfirm.vendor.name}"? This cannot be undone.` : ""}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleDeleteConfirm}
        variant="danger"
      />
    </div>
  );
};

export default Vendors;
