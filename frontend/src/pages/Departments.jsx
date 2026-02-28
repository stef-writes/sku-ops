import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Plus, Edit2, Trash2, Layers, Package } from "lucide-react";

import { API } from "@/lib/api";

const Departments = () => {
  const [departments, setDepartments] = useState([]);
  const [skuOverview, setSkuOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingDept, setEditingDept] = useState(null);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    name: "",
    code: "",
    description: "",
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [deptRes, overviewRes] = await Promise.all([
        axios.get(`${API}/departments`),
        axios.get(`${API}/sku/overview`).catch(() => ({ data: null })),
      ]);
      setDepartments(deptRes.data);
      setSkuOverview(overviewRes.data);
    } catch (error) {
      console.error("Error fetching departments:", error);
      toast.error("Failed to load departments");
    } finally {
      setLoading(false);
    }
  };

  const fetchDepartments = fetchData;

  const openDialog = (dept = null) => {
    if (dept) {
      setEditingDept(dept);
      setForm({
        name: dept.name,
        code: dept.code,
        description: dept.description || "",
      });
    } else {
      setEditingDept(null);
      setForm({
        name: "",
        code: "",
        description: "",
      });
    }
    setDialogOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.code) {
      toast.error("Name and code are required");
      return;
    }
    if (form.code.length !== 3) {
      toast.error("Code must be exactly 3 characters");
      return;
    }

    setSaving(true);
    try {
      if (editingDept) {
        await axios.put(`${API}/departments/${editingDept.id}`, form);
        toast.success("Department updated!");
      } else {
        await axios.post(`${API}/departments`, form);
        toast.success("Department created!");
      }

      setDialogOpen(false);
      fetchDepartments();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save department");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (dept) => {
    if (!window.confirm(`Delete department "${dept.name}"?`)) return;

    try {
      await axios.delete(`${API}/departments/${dept.id}`);
      toast.success("Department deleted");
      fetchDepartments();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete department");
    }
  };

  // Department icons/colors based on code
  const getDeptColor = (code) => {
    const colors = {
      LUM: "bg-amber-100 text-amber-700",
      PLU: "bg-blue-100 text-blue-700",
      ELE: "bg-yellow-100 text-yellow-700",
      PNT: "bg-purple-100 text-purple-700",
      TOL: "bg-red-100 text-red-700",
      HDW: "bg-slate-100 text-slate-700",
      GDN: "bg-green-100 text-green-700",
      APP: "bg-cyan-100 text-cyan-700",
    };
    return colors[code] || "bg-orange-100 text-orange-700";
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">
          Loading Departments...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="departments-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">
            Departments
          </h1>
          <p className="text-slate-600 mt-1">{departments.length} departments</p>
        </div>
        <Button
          onClick={() => openDialog()}
          className="btn-primary h-12 px-6"
          data-testid="add-department-btn"
        >
          <Plus className="w-5 h-5 mr-2" />
          Add Department
        </Button>
      </div>

      {/* SKU System Banner */}
      <div className="card-workshop p-4 mb-6 bg-slate-50 border-slate-200">
        <p className="text-sm text-slate-600">
          <strong>Automated SKU System:</strong> Format <span className="font-mono bg-white px-2 py-1 rounded border border-slate-200">DEPT-XXXXX</span> — each product gets a unique SKU from its department code + sequence.
          SKUs are assigned automatically when you add products.
        </p>
      </div>

      {/* Departments Grid */}
      {departments.length === 0 ? (
        <div className="card-workshop p-12 text-center">
          <Layers className="w-16 h-16 mx-auto mb-4 text-slate-300" />
          <p className="text-slate-500 font-medium">No departments yet</p>
          <p className="text-slate-400 text-sm mb-4">
            Departments are auto-seeded on first dashboard load
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6" data-testid="departments-grid">
          {departments.map((dept) => (
            <div
              key={dept.id}
              className="card-workshop p-6"
              data-testid={`department-card-${dept.code}`}
            >
              <div className="flex items-start justify-between mb-4">
                <div
                  className={`w-14 h-14 ${getDeptColor(dept.code)} rounded-sm flex items-center justify-center`}
                >
                  <span className="font-mono font-bold text-lg">{dept.code}</span>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => openDialog(dept)}
                    className="p-2 text-slate-600 hover:text-orange-500 hover:bg-orange-50 rounded-sm transition-colors"
                    data-testid={`edit-dept-${dept.code}`}
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(dept)}
                    className="p-2 text-slate-600 hover:text-red-500 hover:bg-red-50 rounded-sm transition-colors"
                    data-testid={`delete-dept-${dept.code}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <h3 className="font-heading font-bold text-xl text-slate-900 uppercase tracking-wide mb-2">
                {dept.name}
              </h3>

              {dept.description && (
                <p className="text-sm text-slate-500 mb-4 line-clamp-2">
                  {dept.description}
                </p>
              )}

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

      {/* Department Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="department-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
              {editingDept ? "Edit Department" : "Add New Department"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 pt-4">
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Department Name *
              </Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g., Lumber"
                className="input-workshop mt-2"
                data-testid="dept-name-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Code (3 characters) *
              </Label>
              <Input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase().slice(0, 3) })}
                placeholder="e.g., LUM"
                maxLength={3}
                className="input-workshop mt-2 font-mono uppercase"
                disabled={!!editingDept}
                data-testid="dept-code-input"
              />
              {editingDept && (
                <p className="text-xs text-slate-400 mt-1">Code cannot be changed after creation</p>
              )}
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Description
              </Label>
              <Input
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Optional description"
                className="input-workshop mt-2"
                data-testid="dept-description-input"
              />
            </div>

            <div className="flex gap-3 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
                className="flex-1 btn-secondary h-12"
                data-testid="dept-cancel-btn"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={saving}
                className="flex-1 btn-primary h-12"
                data-testid="dept-save-btn"
              >
                {saving ? "Saving..." : editingDept ? "Update" : "Create"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Departments;
