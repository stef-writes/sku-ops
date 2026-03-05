import { useState, useRef, useEffect } from "react";
import { Input } from "./ui/input";
import { Building2, Plus, Check } from "lucide-react";
import { useBillingEntitySearch, useCreateBillingEntity } from "@/hooks/useBillingEntities";
import { toast } from "sonner";

/**
 * Autocomplete combobox for selecting or creating billing entities.
 * @param {{ value: string, onChange: (name: string) => void, placeholder?: string }} props
 */
export function BillingEntityPicker({ value, onChange, placeholder = "Billing entity name" }) {
  const [query, setQuery] = useState(value || "");
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const createEntity = useCreateBillingEntity();

  const { data: results = [] } = useBillingEntitySearch(query);

  useEffect(() => {
    setQuery(value || "");
  }, [value]);

  useEffect(() => {
    const handler = (e) => {
      if (!wrapperRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const select = (name) => {
    setQuery(name);
    onChange(name);
    setOpen(false);
  };

  const handleInputChange = (e) => {
    const v = e.target.value;
    setQuery(v);
    onChange(v);
    if (v.trim()) setOpen(true);
  };

  const handleCreate = async () => {
    const name = query.trim();
    if (!name) return;
    try {
      await createEntity.mutateAsync({ name });
      toast.success(`Billing entity "${name}" created`);
      select(name);
    } catch {
      select(name);
    }
  };

  const exactMatch = results.some((e) => e.name.toLowerCase() === query.trim().toLowerCase());

  return (
    <div ref={wrapperRef} className="relative">
      <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
      <Input
        value={query}
        onChange={handleInputChange}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className="pl-10"
        data-testid="billing-entity-picker-input"
      />
      {open && query.trim() && (
        <div className="absolute z-30 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden max-h-56 overflow-y-auto">
          {results.map((entity) => (
            <button
              key={entity.id}
              type="button"
              onClick={() => select(entity.name)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50 text-left border-b border-slate-100 last:border-b-0"
            >
              {entity.name.toLowerCase() === query.trim().toLowerCase() ? (
                <Check className="w-4 h-4 text-emerald-500 shrink-0" />
              ) : (
                <Building2 className="w-4 h-4 text-slate-300 shrink-0" />
              )}
              <div className="min-w-0">
                <span className="text-sm font-medium text-slate-900">{entity.name}</span>
                {entity.contact_name && (
                  <span className="text-xs text-slate-400 ml-2">{entity.contact_name}</span>
                )}
              </div>
            </button>
          ))}
          {!exactMatch && query.trim() && (
            <button
              type="button"
              onClick={handleCreate}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-emerald-50 text-left text-emerald-700"
            >
              <Plus className="w-4 h-4 shrink-0" />
              <span className="text-sm">Create <strong>{query.trim()}</strong></span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
