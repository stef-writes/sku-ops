import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export function ActionTile({ to, icon: Icon, title, description, className }) {
  return (
    <Link
      to={to}
      className={cn(
        "group rounded-xl border border-border/80 bg-surface p-4 shadow-soft hover:border-accent/40 hover:shadow-md transition-all",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-muted flex items-center justify-center ring-1 ring-border/60 shrink-0 transition-colors group-hover:bg-accent/10 group-hover:text-accent">
          <Icon className="w-5 h-5 text-foreground group-hover:text-accent transition-colors" />
        </div>
        <div className="min-w-0">
          <p className="font-semibold text-foreground">{title}</p>
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        </div>
      </div>
    </Link>
  );
}
