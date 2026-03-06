import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Consistent page header with optional breadcrumbs and primary action.
 */
export function PageHeader({ title, subtitle, breadcrumbs, action, className }) {
  return (
    <div className={cn("mb-8", className)}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
          {breadcrumbs.map((item, i) => (
            <span key={i} className="flex items-center gap-2">
              {item.href ? (
                <Link
                  to={item.href}
                  className="hover:text-foreground transition-colors"
                >
                  {item.label}
                </Link>
              ) : (
                <span className="text-foreground font-medium">{item.label}</span>
              )}
              {i < breadcrumbs.length - 1 && (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-[1.75rem] font-semibold text-foreground tracking-tight">
            {title}
          </h1>
          {subtitle && (
            <p className="text-muted-foreground mt-1 text-sm">{subtitle}</p>
          )}
        </div>
        {action && <div className="flex-shrink-0">{action}</div>}
      </div>
    </div>
  );
}
