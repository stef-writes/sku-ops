import { useState, useRef, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { CheckCircle, X, Search, Loader2, PackagePlus } from "lucide-react";

/**
 * Inline widget for matching an item to an existing inventory product.
 *
 * States:
 *  - matched: shows "Matched: SKU — Name (qty)" badge + clear button
 *  - unmatched: shows "New product" badge + search input
 *  - searching: shows dropdown of candidates
 *
 * @param {object|null} matched        The matched product (or null)
 * @param {array}       options        Search result candidates
 * @param {boolean}     searching      Whether a search is in progress
 * @param {function}    onSearch       (query: string) => void
 * @param {function}    onConfirm      (product: object) => void
 * @param {function}    onClear        () => void
 */
export function ProductMatchPicker({
  matched,
  options = [],
  searching = false,
  onSearch,
  onConfirm,
  onClear,
}) {
  const [query, setQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const wrapperRef = useRef(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleQueryChange = (val) => {
    setQuery(val);
    setShowDropdown(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (val.trim().length >= 2) {
      debounceRef.current = setTimeout(() => onSearch?.(val.trim()), 350);
    }
  };

  const handleSelect = (product) => {
    onConfirm?.(product);
    setQuery("");
    setShowDropdown(false);
  };

  const handleClear = () => {
    onClear?.();
    setQuery("");
  };

  if (matched) {
    return (
      <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-success/10 border border-success/30 text-xs">
        <CheckCircle className="w-3.5 h-3.5 text-success shrink-0" />
        <span className="font-mono text-success font-medium">{matched.sku}</span>
        <span className="text-muted-foreground truncate flex-1">{matched.name}</span>
        <span className="text-muted-foreground tabular-nums shrink-0">qty: {matched.quantity ?? 0}</span>
        <button
          type="button"
          onClick={handleClear}
          className="p-0.5 text-muted-foreground hover:text-destructive transition-colors"
          title="Remove match"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div ref={wrapperRef} className="relative">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-warning/10 border border-warning/30 text-[10px] font-medium text-accent shrink-0">
          <PackagePlus className="w-3 h-3" />
          New
        </span>
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            onFocus={() => { if (options.length > 0 || query.length >= 2) setShowDropdown(true); }}
            placeholder="Search existing product…"
            className="h-8 text-xs pl-7 pr-2"
          />
          {searching && (
            <Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground animate-spin" />
          )}
        </div>
      </div>

      {showDropdown && options.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-lg max-h-48 overflow-auto">
          {options.map((product) => (
            <button
              key={product.id}
              type="button"
              onClick={() => handleSelect(product)}
              className="w-full text-left px-3 py-2 hover:bg-muted flex items-center gap-2 text-xs border-b border-border/50 last:border-0 transition-colors"
            >
              <span className="font-mono font-medium text-foreground shrink-0">{product.sku}</span>
              <span className="text-muted-foreground truncate flex-1">{product.name}</span>
              <span className="text-muted-foreground tabular-nums shrink-0">qty: {product.quantity ?? 0}</span>
            </button>
          ))}
        </div>
      )}

      {showDropdown && query.length >= 2 && !searching && options.length === 0 && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-lg px-3 py-2 text-xs text-muted-foreground">
          No matches found
        </div>
      )}
    </div>
  );
}
