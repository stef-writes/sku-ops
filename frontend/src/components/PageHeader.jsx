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
        <nav className="flex items-center gap-2 text-sm text-slate-500 mb-2">
          {breadcrumbs.map((item, i) => (
            <span key={i} className="flex items-center gap-2">
              {item.href ? (
                <Link
                  to={item.href}
                  className="hover:text-slate-700 transition-colors"
                >
                  {item.label}
                </Link>
              ) : (
                <span className="text-slate-600 font-medium">{item.label}</span>
              )}
              {i < breadcrumbs.length - 1 && (
                <ChevronRight className="w-4 h-4 text-slate-400" />
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
            {title}
          </h1>
          {subtitle && (
            <p className="text-slate-500 mt-1 text-sm">{subtitle}</p>
          )}
        </div>
        {action && <div className="flex-shrink-0">{action}</div>}
      </div>
    </div>
  );
}
