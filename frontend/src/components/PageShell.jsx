import { PageHeader } from "./PageHeader";
import { PageSkeleton } from "./LoadingSkeleton";

export function PageShell({ title, subtitle, breadcrumbs, action, loading, children, className }) {
  if (loading) return <PageSkeleton />;

  return (
    <div className={className || "p-8"}>
      <PageHeader title={title} subtitle={subtitle} breadcrumbs={breadcrumbs} action={action} />
      {children}
    </div>
  );
}
