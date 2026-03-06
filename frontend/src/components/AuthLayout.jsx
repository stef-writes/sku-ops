import { Wrench } from "lucide-react";

export function AuthLayout({ children, testId }) {
  return (
    <div
      className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-sidebar via-sidebar to-sidebar"
      data-testid={testId}
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-accent/10 via-transparent to-transparent" />
      <div className="w-full max-w-md relative">
        <div className="text-center mb-10">
          <div className="w-14 h-14 bg-gradient-to-br from-accent-gradient-from to-accent-gradient-to rounded-xl mx-auto flex items-center justify-center mb-5 shadow-soft">
            <Wrench className="w-7 h-7 text-accent-foreground" />
          </div>
          <h1 className="text-2xl font-semibold text-sidebar-foreground tracking-tight">
            Supply Yard
          </h1>
          <p className="text-sidebar-muted mt-2 text-sm">
            Material management for contractors & warehouses
          </p>
        </div>
        <div className="bg-surface rounded-2xl p-8 shadow-soft-lg border border-border/70 backdrop-blur-sm">
          {children}
        </div>
      </div>
    </div>
  );
}
