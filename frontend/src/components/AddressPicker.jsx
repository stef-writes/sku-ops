import { useState, useRef, useEffect } from "react";
import { Input } from "./ui/input";
import { MapPin, Plus, Check } from "lucide-react";
import { useAddressSearch, useCreateAddress } from "@/hooks/useAddresses";
import { toast } from "sonner";

/**
 * Autocomplete combobox for selecting or creating addresses.
 * @param {{ value: string, onChange: (text: string) => void, placeholder?: string, required?: boolean }} props
 */
export function AddressPicker({ value, onChange, placeholder = "Where are these going?", required = false }) {
  const [query, setQuery] = useState(value || "");
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const createAddress = useCreateAddress();

  const { data: results = [] } = useAddressSearch(query);

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

  const select = (text) => {
    setQuery(text);
    onChange(text);
    setOpen(false);
  };

  const handleInputChange = (e) => {
    const v = e.target.value;
    setQuery(v);
    onChange(v);
    if (v.trim()) setOpen(true);
  };

  const handleCreate = async () => {
    const text = query.trim();
    if (!text) return;
    try {
      await createAddress.mutateAsync({ line1: text, label: text.slice(0, 80) });
      toast.success("Address saved");
      select(text);
    } catch {
      select(text);
    }
  };

  const exactMatch = results.some((a) => (a.line1 || "").toLowerCase() === query.trim().toLowerCase());

  return (
    <div ref={wrapperRef} className="relative">
      <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
      <Input
        value={query}
        onChange={handleInputChange}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className="pl-10"
        required={required}
        data-testid="address-picker-input"
      />
      {open && query.trim() && (
        <div className="absolute z-30 left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-lg overflow-hidden max-h-56 overflow-y-auto">
          {results.map((addr) => (
            <button
              key={addr.id}
              type="button"
              onClick={() => select(addr.line1)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-muted text-left border-b border-border/50 last:border-b-0"
            >
              {(addr.line1 || "").toLowerCase() === query.trim().toLowerCase() ? (
                <Check className="w-4 h-4 text-success shrink-0" />
              ) : (
                <MapPin className="w-4 h-4 text-muted-foreground/60 shrink-0" />
              )}
              <div className="min-w-0">
                <span className="text-sm font-medium text-foreground">{addr.label || addr.line1}</span>
                {addr.city && (
                  <span className="text-xs text-muted-foreground ml-2">{addr.city}{addr.state ? `, ${addr.state}` : ""}</span>
                )}
              </div>
            </button>
          ))}
          {!exactMatch && query.trim() && (
            <button
              type="button"
              onClick={handleCreate}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-success/10 text-left text-success"
            >
              <Plus className="w-4 h-4 shrink-0" />
              <span className="text-sm">Save <strong>{query.trim().slice(0, 40)}{query.trim().length > 40 ? "..." : ""}</strong></span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
