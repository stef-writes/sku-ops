import { cn } from "@/lib/utils";

const ACCENTS = {
  amber:   { bar: "bg-amber-400",   icon: "bg-amber-50 text-amber-600" },
  emerald: { bar: "bg-emerald-400", icon: "bg-emerald-50 text-emerald-600" },
  blue:    { bar: "bg-blue-400",    icon: "bg-blue-50 text-blue-600" },
  orange:  { bar: "bg-orange-400",  icon: "bg-orange-50 text-orange-600" },
  violet:  { bar: "bg-violet-400",  icon: "bg-violet-50 text-violet-600" },
  rose:    { bar: "bg-rose-400",    icon: "bg-rose-50 text-rose-600" },
  slate:   { bar: "bg-slate-200",   icon: "bg-slate-50 text-slate-500" },
};

/**
 * Unified stat/metric card used across Dashboard, Financials, Reports, MyHistory.
 *
 * @param {string}  label   – Uppercase tiny label
 * @param {string}  value   – Big number / formatted value
 * @param {string}  [note]  – Small subtext below the value
 * @param {string}  [accent="slate"] – Color theme key
 * @param {React.ComponentType} [icon] – Optional Lucide icon
 * @param {string}  [className]
 */
export function StatCard({ label, value, note, icon: Icon, accent = "slate", className }) {
  const cfg = ACCENTS[accent] || ACCENTS.slate;
  return (
    <div className={cn("bg-white rounded-xl border border-slate-200 p-5 relative overflow-hidden shadow-sm", className)}>
      <div className={cn("absolute top-0 left-0 right-0 h-[2px]", cfg.bar)} />
      <div className="flex items-start justify-between mb-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p>
        {Icon && (
          <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", cfg.icon)}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>
      <p className="text-2xl font-bold text-slate-900 tabular-nums leading-none">{value}</p>
      {note && <p className="text-xs text-slate-400 mt-2">{note}</p>}
    </div>
  );
}
