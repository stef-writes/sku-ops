import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Plus, Edit2, Trash2, Users, Mail, Phone, MapPin, FileUp } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EntityFormDialog } from "@/components/EntityFormDialog";
import { getErrorMessage } from "@/lib/api-client";
import { useVendors, useCreateVendor, useUpdateVendor, useDeleteVendor } from "@/hooks/useVendors";

const vendorSchema = z.object({
  name: z.string().min(1, "Vendor name is required"),
  contact_name: z.string().optional().default(""),
  email: z.string().email("Invalid email").or(z.literal("")).optional().default(""),
  phone: z.string().optional().default(""),
  address: z.string().optional().default(""),
});

const FIELDS = [
  { name: "name", label: "Company Name *", placeholder: "e.g., ABC Hardware Supply" },
  { name: "contact_name", label: "Contact Name", placeholder: "e.g., John Smith" },
  { name: "email", label: "Email", type: "email", placeholder: "vendor@example.com" },
  { name: "phone", label: "Phone", placeholder: "(555) 123-4567" },
  { name: "address", label: "Address", placeholder: "123 Main St, City, State" },
];

const DEFAULTS = { name: "", contact_name: "", email: "", phone: "", address: "" };

const Vendors = () => {
  const navigate = useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, vendor: null });

  const { data: vendors = [], isLoading } = useVendors();
  const createMutation = useCreateVendor();
  const updateMutation = useUpdateVendor();
  const deleteMutation = useDeleteVendor();

  const openDialog = (vendor = null) => {
    setEditingVendor(vendor);
    setDialogOpen(true);
  };

  const handleSubmit = async (data, isEditing) => {
    try {
      if (isEditing) {
        await updateMutation.mutateAsync({ id: editingVendor.id, data });
        toast.success("Vendor updated!");
      } else {
        await createMutation.mutateAsync(data);
        toast.success("Vendor created!");
      }
      setDialogOpen(false);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
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
                <div className="w-12 h-12 bg-muted rounded-sm flex items-center justify-center">
                  <Users className="w-6 h-6 text-muted-foreground" />
                </div>
                <div className="flex gap-1">
                  <button onClick={() => openDialog(vendor)} className="p-2 text-muted-foreground hover:text-accent hover:bg-warning/10 rounded-sm transition-colors" data-testid={`edit-vendor-${vendor.id}`}>
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button onClick={() => setDeleteConfirm({ open: true, vendor })} className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-sm transition-colors" data-testid={`delete-vendor-${vendor.id}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <h3 className="font-heading font-bold text-xl text-foreground uppercase tracking-wide mb-2">{vendor.name}</h3>
              {vendor.contact_name && <p className="text-muted-foreground mb-3">{vendor.contact_name}</p>}
              <div className="space-y-2 text-sm text-muted-foreground">
                {vendor.email && <div className="flex items-center gap-2"><Mail className="w-4 h-4" /><span>{vendor.email}</span></div>}
                {vendor.phone && <div className="flex items-center gap-2"><Phone className="w-4 h-4" /><span>{vendor.phone}</span></div>}
                {vendor.address && <div className="flex items-center gap-2"><MapPin className="w-4 h-4" /><span className="truncate">{vendor.address}</span></div>}
              </div>
              <div className="mt-4 pt-4 border-t border-border">
                <span className="text-xs text-muted-foreground uppercase tracking-wide">{vendor.product_count || 0} products</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <EntityFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="Vendor"
        schema={vendorSchema}
        fields={FIELDS}
        defaults={DEFAULTS}
        entity={editingVendor}
        onSubmit={handleSubmit}
        saving={createMutation.isPending || updateMutation.isPending}
        testIdPrefix="vendor"
      />

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
