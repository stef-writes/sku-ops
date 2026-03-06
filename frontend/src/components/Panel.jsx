import { cn } from "@/lib/utils";

export function Panel({ children, className }) {
  return (
    <div className={cn("bg-surface rounded-xl border border-border/80 shadow-soft p-6", className)}>
      {children}
    </div>
  );
}

/** Section heading with optional right-aligned action.
 *  variant="default" (subtle label) | "report" (bold uppercase with accent left border)
 */
export function SectionHead({ title, action, variant = "default" }) {
  return (
    <div className="flex items-center justify-between mb-4">
      {variant === "report" ? (
        <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground border-l-2 border-accent pl-3">
          {title}
        </h3>
      ) : (
        <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
      )}
      {action}
    </div>
  );
}
