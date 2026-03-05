import { cn } from "@/lib/utils";

export function Panel({ children, className }) {
  return (
    <div className={cn("bg-white rounded-xl border border-slate-200 shadow-sm p-6", className)}>
      {children}
    </div>
  );
}

/** Section heading with optional right-aligned action.
 *  variant="default" (subtle label) | "report" (bold uppercase with amber left border)
 */
export function SectionHead({ title, action, variant = "default" }) {
  return (
    <div className="flex items-center justify-between mb-4">
      {variant === "report" ? (
        <h3 className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400 border-l-2 border-amber-400 pl-3">
          {title}
        </h3>
      ) : (
        <h3 className="text-sm font-medium text-slate-600">{title}</h3>
      )}
      {action}
    </div>
  );
}
