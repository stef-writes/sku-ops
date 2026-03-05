import { Minus, Plus } from "lucide-react";

export function QuantityControl({ value, onChange, min = 0.01, max, step = 1, unit }) {
  const handleInput = (e) => {
    const val = parseFloat(e.target.value);
    if (!val || val < min) return;
    if (max != null && val > max) return;
    onChange(val);
  };

  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={() => value - step >= min && onChange(value - step)}
        className="w-8 h-8 border border-slate-200 rounded-lg flex items-center justify-center hover:bg-slate-50 transition-colors"
        type="button"
      >
        <Minus className="w-3.5 h-3.5" />
      </button>
      <input
        type="number"
        step="any"
        min={min}
        max={max}
        value={value}
        onChange={handleInput}
        className="w-16 text-center font-mono font-bold text-slate-900 border border-slate-200 rounded-lg h-8 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
      />
      <button
        onClick={() => (max == null || value + step <= max) && onChange(value + step)}
        className="w-8 h-8 border border-slate-200 rounded-lg flex items-center justify-center hover:bg-slate-50 transition-colors"
        type="button"
      >
        <Plus className="w-3.5 h-3.5" />
      </button>
      {unit && <span className="text-xs text-slate-400 ml-1">/{unit}</span>}
    </div>
  );
}
