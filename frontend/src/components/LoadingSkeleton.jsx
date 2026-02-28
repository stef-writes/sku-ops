import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * Page-level loading skeleton.
 */
export function PageSkeleton({ className }) {
  return (
    <div className={cn("space-y-6 p-8", className)}>
      <div className="space-y-2">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-5 w-48" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-28 rounded-lg" />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Skeleton className="h-64 rounded-lg" />
        <Skeleton className="h-64 rounded-lg" />
      </div>
    </div>
  );
}

/**
 * Table row skeleton for list loading.
 */
export function TableRowSkeleton({ columns = 5 }) {
  return (
    <>
      {[1, 2, 3, 4, 5].map((row) => (
        <tr key={row} className="border-b">
          {Array.from({ length: columns }).map((_, col) => (
            <td key={col} className="px-4 py-3">
              <Skeleton className="h-5 w-full" />
            </td>
          ))}
          <td className="px-4 py-3">
            <div className="flex gap-2">
              <Skeleton className="h-8 w-8" />
              <Skeleton className="h-8 w-8" />
            </div>
          </td>
        </tr>
      ))}
    </>
  );
}
