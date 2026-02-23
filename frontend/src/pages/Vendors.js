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
import { Plus, Edit2, Trash2, Users, Mail, Phone, MapPin } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Vendors = () => {
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState(null);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    name: "",
    contact_name: "",
    email: "",
    phone: "",
    address: "",
  });

  useEffect(() => {
    fetchVendors();
  }, []);

  const fetchVendors = async () => {
    try {
      const response = await axios.get(`${API}/vendors`);
      setVendors(response.data);
    } catch (error) {
      console.error("Error fetching vendors:", error);
      toast.error("Failed to load vendors");
    } finally {
      setLoading(false);
    }
  };

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
      setForm({
        name: "",
        contact_name: "",
        email: "",
        phone: "",
        address: "",
      });
    }
    setDialogOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name) {
      toast.error("Vendor name is required");
      return;
    }

    setSaving(true);
    try {
      if (editingVendor) {
        await axios.put(`${API}/vendors/${editingVendor.id}`, form);
        toast.success("Vendor updated!");
      } else {
        await axios.post(`${API}/vendors`, form);
        toast.success("Vendor created!");
      }

      setDialogOpen(false);
      fetchVendors();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to save vendor");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (vendor) => {
    if (!window.confirm(`Delete vendor "${vendor.name}"?`)) return;

    try {
      await axios.delete(`${API}/vendors/${vendor.id}`);
      toast.success("Vendor deleted");
      fetchVendors();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to delete vendor");
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">
          Loading Vendors...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="vendors-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">
            Vendors
          </h1>
          <p className="text-slate-600 mt-1">{vendors.length} vendors</p>
        </div>
        <Button
          onClick={() => openDialog()}
          className="btn-primary h-12 px-6"
          data-testid="add-vendor-btn"
        >
          <Plus className="w-5 h-5 mr-2" />
          Add Vendor
        </Button>
      </div>

      {/* Vendors Grid */}
      {vendors.length === 0 ? (
        <div className="card-workshop p-12 text-center">
          <Users className="w-16 h-16 mx-auto mb-4 text-slate-300" />
          <p className="text-slate-500 font-medium">No vendors yet</p>
          <p className="text-slate-400 text-sm mb-4">Add vendors to track your suppliers</p>
          <Button onClick={() => openDialog()} className="btn-primary">
            <Plus className="w-5 h-5 mr-2" />
            Add First Vendor
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="vendors-grid">
          {vendors.map((vendor) => (
            <div
              key={vendor.id}
              className="card-workshop p-6"
              data-testid={`vendor-card-${vendor.id}`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-slate-100 rounded-sm flex items-center justify-center">
                  <Users className="w-6 h-6 text-slate-600" />
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => openDialog(vendor)}
                    className="p-2 text-slate-600 hover:text-orange-500 hover:bg-orange-50 rounded-sm transition-colors"
                    data-testid={`edit-vendor-${vendor.id}`}
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(vendor)}
                    className="p-2 text-slate-600 hover:text-red-500 hover:bg-red-50 rounded-sm transition-colors"
                    data-testid={`delete-vendor-${vendor.id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <h3 className="font-heading font-bold text-xl text-slate-900 uppercase tracking-wide mb-2">
                {vendor.name}
              </h3>

              {vendor.contact_name && (
                <p className="text-slate-600 mb-3">{vendor.contact_name}</p>
              )}

              <div className="space-y-2 text-sm text-slate-500">
                {vendor.email && (
                  <div className="flex items-center gap-2">
                    <Mail className="w-4 h-4" />
                    <span>{vendor.email}</span>
                  </div>
                )}
                {vendor.phone && (
                  <div className="flex items-center gap-2">
                    <Phone className="w-4 h-4" />
                    <span>{vendor.phone}</span>
                  </div>
                )}
                {vendor.address && (
                  <div className="flex items-center gap-2">
                    <MapPin className="w-4 h-4" />
                    <span className="truncate">{vendor.address}</span>
                  </div>
                )}
              </div>

              <div className="mt-4 pt-4 border-t border-slate-200">
                <span className="text-xs text-slate-400 uppercase tracking-wide">
                  {vendor.product_count || 0} products
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Vendor Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="vendor-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
              {editingVendor ? "Edit Vendor" : "Add New Vendor"}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 pt-4">
            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Company Name *
              </Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g., ABC Hardware Supply"
                className="input-workshop mt-2"
                data-testid="vendor-name-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Contact Name
              </Label>
              <Input
                value={form.contact_name}
                onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
                placeholder="e.g., John Smith"
                className="input-workshop mt-2"
                data-testid="vendor-contact-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Email
              </Label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="vendor@example.com"
                className="input-workshop mt-2"
                data-testid="vendor-email-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Phone
              </Label>
              <Input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="(555) 123-4567"
                className="input-workshop mt-2"
                data-testid="vendor-phone-input"
              />
            </div>

            <div>
              <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                Address
              </Label>
              <Input
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder="123 Main St, City, State"
                className="input-workshop mt-2"
                data-testid="vendor-address-input"
              />
            </div>

            <div className="flex gap-3 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
                className="flex-1 btn-secondary h-12"
                data-testid="vendor-cancel-btn"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={saving}
                className="flex-1 btn-primary h-12"
                data-testid="vendor-save-btn"
              >
                {saving ? "Saving..." : editingVendor ? "Update Vendor" : "Create Vendor"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Vendors;
