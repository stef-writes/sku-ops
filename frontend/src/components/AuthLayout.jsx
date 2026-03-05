import { Wrench } from "lucide-react";

export function AuthLayout({ children, testId }) {
  return (
    <div
      className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900"
      data-testid={testId}
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-amber-500/5 via-transparent to-transparent" />
      <div className="w-full max-w-md relative">
        <div className="text-center mb-10">
          <div className="w-14 h-14 bg-gradient-to-br from-amber-400 to-orange-500 rounded-xl mx-auto flex items-center justify-center mb-5 shadow-soft">
            <Wrench className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-semibold text-white tracking-tight">
            Supply Yard
          </h1>
          <p className="text-slate-400 mt-2 text-sm">
            Material management for contractors & warehouses
          </p>
        </div>
        <div className="bg-white rounded-2xl p-8 shadow-soft-lg border border-slate-200/50">
          {children}
        </div>
      </div>
    </div>
  );
}
