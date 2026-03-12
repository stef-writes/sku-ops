import { cn } from "@/lib/utils";

export function ReportPanel({ children, className }) {
  return (
    <div
      className={cn(
        "bg-card/70 rounded-2xl border border-border/70 shadow-soft p-6 backdrop-blur-sm relative overflow-hidden",
        "before:absolute before:inset-x-0 before:top-0 before:h-[2px] before:bg-gradient-to-r before:from-accent/80 before:via-category-4/60 before:to-transparent",
        className,
      )}
    >
      <div className="relative">{children}</div>
    </div>
  );
}

export function ReportSectionHead({ title, action, className }) {
  return (
    <div className={cn("flex items-center justify-between gap-3 mb-4", className)}>
      <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground border-l-2 border-accent pl-3">
        {title}
      </h3>
      {action}
    </div>
  );
}
