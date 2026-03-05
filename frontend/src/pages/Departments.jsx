import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Plus, Edit2, Trash2, Layers, Package } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EntityFormDialog } from "@/components/EntityFormDialog";
import { getErrorMessage } from "@/lib/api-client";
import { getDeptColor } from "@/lib/constants";
import {
  useDepartments,
  useSkuOverview,
  useCreateDepartment,
  useUpdateDepartment,
  useDeleteDepartment,
} from "@/hooks/useDepartments";

const deptSchema = z.object({
  name: z.string().min(1, "Name is required"),
  code: z.string().length(3, "Code must be exactly 3 characters"),
  description: z.string().optional().default(""),
});

const FIELDS = [
  { name: "name", label: "Department Name *", placeholder: "e.g., Lumber" },
  {
    name: "code",
    label: "Code (3 characters) *",
    placeholder: "e.g., LUM",
    maxLength: 3,
    className: "font-mono uppercase",
    disabled: (isEditing) => isEditing,
    note: "Code cannot be changed after creation",
    transform: (v) => v.toUpperCase().slice(0, 3),
  },
  { name: "description", label: "Description", placeholder: "Optional description" },
];

const DEFAULTS = { name: "", code: "", description: "" };

const Departments = () => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingDept, setEditingDept] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, dept: null });

  const { data: departments = [], isLoading } = useDepartments();
  const { data: skuOverview } = useSkuOverview();
  const createMutation = useCreateDepartment();
  const updateMutation = useUpdateDepartment();
  const deleteMutation = useDeleteDepartment();

  const openDialog = (dept = null) => {
    setEditingDept(dept);
    setDialogOpen(true);
  };

  const handleSubmit = async (data, isEditing) => {
    try {
      if (isEditing) {
        await updateMutation.mutateAsync({ id: editingDept.id, data });
        toast.success("Department updated!");
      } else {
        await createMutation.mutateAsync(data);
        toast.success("Department created!");
      }
      setDialogOpen(false);
    } catch (err) {
      toast.error(getErrorMessage(err));
    }
  };

  const handleDeleteConfirm = async () => {
    const { dept } = deleteConfirm;
    if (!dept) return;
    try {
      await deleteMutation.mutateAsync(dept.id);
      toast.success("Department deleted");
    } catch (error) {
      toast.error(getErrorMessage(error));
      throw error;
    }
  };

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="departments-page">
      <PageHeader
        title="Departments"
        subtitle={`${departments.length} departments`}
        action={
          <Button onClick={() => openDialog()} className="btn-primary h-12 px-6" data-testid="add-department-btn">
            <Plus className="w-5 h-5 mr-2" />
            Add Department
          </Button>
        }
      />

      <div className="card-workshop p-4 mb-6 bg-slate-50 border-slate-200">
        <p className="text-sm text-slate-600">
          <strong>Automated SKU System:</strong> Format{" "}
          <span className="font-mono bg-white px-2 py-1 rounded border border-slate-200">DEPT-XXXXX</span>{" "}
          — each product gets a unique SKU from its department code + sequence. SKUs are assigned automatically when you add products.
        </p>
      </div>

      {departments.length === 0 ? (
        <div className="card-workshop p-12 text-center">
          <Layers className="w-16 h-16 mx-auto mb-4 text-slate-300" />
          <p className="text-slate-500 font-medium">No departments yet</p>
          <p className="text-slate-400 text-sm mb-4">Departments are auto-seeded on first dashboard load</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6" data-testid="departments-grid">
          {departments.map((dept) => (
            <div key={dept.id} className="card-workshop p-6" data-testid={`department-card-${dept.code}`}>
              <div className="flex items-start justify-between mb-4">
                <div className={`w-14 h-14 ${getDeptColor(dept.code)} rounded-sm flex items-center justify-center`}>
                  <span className="font-mono font-bold text-lg">{dept.code}</span>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => openDialog(dept)} className="p-2 text-slate-600 hover:text-orange-500 hover:bg-orange-50 rounded-sm transition-colors" data-testid={`edit-dept-${dept.code}`}>
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button onClick={() => setDeleteConfirm({ open: true, dept })} className="p-2 text-slate-600 hover:text-red-500 hover:bg-red-50 rounded-sm transition-colors" data-testid={`delete-dept-${dept.code}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <h3 className="font-heading font-bold text-xl text-slate-900 uppercase tracking-wide mb-2">{dept.name}</h3>
              {dept.description && <p className="text-sm text-slate-500 mb-4 line-clamp-2">{dept.description}</p>}
              <div className="space-y-2 pt-4 border-t border-slate-200">
                <div className="flex items-center gap-2 text-sm text-slate-600">
                  <Package className="w-4 h-4" />
                  <span>{dept.product_count || 0} products</span>
                </div>
                {skuOverview?.departments?.find((d) => d.id === dept.id)?.next_sku && (
                  <p className="text-xs font-mono text-slate-500">
                    Next SKU: {skuOverview.departments.find((d) => d.id === dept.id).next_sku}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <EntityFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="Department"
        schema={deptSchema}
        fields={FIELDS}
        defaults={DEFAULTS}
        entity={editingDept}
        onSubmit={handleSubmit}
        saving={createMutation.isPending || updateMutation.isPending}
        testIdPrefix="dept"
      />

      <ConfirmDialog
        open={deleteConfirm.open}
        onOpenChange={(open) => setDeleteConfirm((p) => ({ ...p, open }))}
        title="Delete department"
        description={deleteConfirm.dept ? `Delete "${deleteConfirm.dept.name}"? This cannot be undone.` : ""}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleDeleteConfirm}
        variant="danger"
      />
    </div>
  );
};

export default Departments;
