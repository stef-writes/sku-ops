import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "./ui/sheet";
import { Button } from "./ui/button";
import { X, Loader2 } from "lucide-react";
import { StatusBadge } from "./StatusBadge";

/**
 * Reusable right-side panel for entity detail views.
 * Slides in from the right while keeping the page context visible.
 *
 * @param {{
 *   open: boolean,
 *   onOpenChange: (open: boolean) => void,
 *   title: string,
 *   subtitle?: string,
 *   status?: string,
 *   icon?: React.ComponentType,
 *   loading?: boolean,
 *   actions?: React.ReactNode,
 *   width?: "sm" | "md" | "lg" | "xl",
 *   children: React.ReactNode,
 * }} props
 */
export function DetailPanel({
  open, onOpenChange, title, subtitle, status, icon: Icon,
  loading, actions, width = "md", children,
}) {
  const widthClass = {
    sm: "sm:max-w-sm",
    md: "sm:max-w-lg",
    lg: "sm:max-w-2xl",
    xl: "sm:max-w-3xl",
  }[width] || "sm:max-w-lg";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className={`${widthClass} w-full p-0 flex flex-col`}>
        <div className="px-6 py-4 border-b border-border bg-card shrink-0">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3 min-w-0">
              {Icon && (
                <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
                  <Icon className="w-5 h-5 text-muted-foreground" />
                </div>
              )}
              <div className="min-w-0">
                <SheetTitle className="text-base font-semibold text-foreground truncate flex items-center gap-2">
                  {title}
                  {status && <StatusBadge status={status} />}
                </SheetTitle>
                {subtitle && (
                  <SheetDescription className="text-xs text-muted-foreground mt-0.5 truncate">
                    {subtitle}
                  </SheetDescription>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="px-6 py-5 space-y-6">
              {children}
            </div>
          )}
        </div>

        {actions && (
          <div className="px-6 py-4 border-t border-border bg-muted/80 shrink-0 flex items-center justify-end gap-2">
            {actions}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

/**
 * Section within a DetailPanel — groups related fields with a label.
 */
export function DetailSection({ label, children, className = "" }) {
  return (
    <div className={className}>
      {label && (
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground mb-3">{label}</p>
      )}
      {children}
    </div>
  );
}

/**
 * Key-value field display within a DetailSection.
 */
export function DetailField({ label, value, mono = false, className = "" }) {
  return (
    <div className={className}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-sm text-foreground mt-0.5 ${mono ? "font-mono tabular-nums" : ""}`}>
        {value || "—"}
      </p>
    </div>
  );
}
