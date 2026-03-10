import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ClipboardCheck, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/StatusBadge";
import { useCycleCounts, useOpenCycleCount } from "@/hooks/useCycleCounts";
import { useDepartments } from "@/hooks/useDepartments";
import { getErrorMessage } from "@/lib/api-client";

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function OpenCountDialog({ open, onOpenChange }) {
  const [scope, setScope] = useState("__all__");
  const { data: departments = [] } = useDepartments();
  const openMutation = useOpenCycleCount();
  const navigate = useNavigate();

  const handleSubmit = (e) => {
    e.preventDefault();
    openMutation.mutate(
      { scope: scope === "__all__" ? null : scope },
      {
        onSuccess: (count) => {
          toast.success("Cycle count opened");
          onOpenChange(false);
          setScope("__all__");
          navigate(`/cycle-counts/${count.id}`);
        },
        onError: (err) => toast.error(getErrorMessage(err)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>New Cycle Count</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div>
            <Label className="mb-2 block">Scope</Label>
            <Select value={scope} onValueChange={setScope}>
              <SelectTrigger className="input-workshop">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">
                  Full warehouse (all departments)
                </SelectItem>
                {departments.map((d) => (
                  <SelectItem key={d.id} value={d.name}>
                    {d.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground mt-1.5">
              Current on-hand quantities will be snapshotted at open time.
            </p>
          </div>
          <div className="flex gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="flex-1"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={openMutation.isPending}
              className="flex-1"
            >
              {openMutation.isPending ? "Opening…" : "Open Count"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const COLUMNS = [
  {
    key: "created_at",
    label: "Opened",
    render: (row) => formatDate(row.created_at),
  },
  {
    key: "scope",
    label: "Scope",
    render: (row) =>
      row.scope || (
        <span className="text-muted-foreground">Full warehouse</span>
      ),
  },
  {
    key: "status",
    label: "Status",
    render: (row) => <StatusBadge status={row.status} />,
  },
  {
    key: "created_by_name",
    label: "Opened by",
    render: (row) => row.created_by_name || "—",
  },
  {
    key: "committed_at",
    label: "Committed",
    render: (row) => (row.committed_at ? formatDate(row.committed_at) : "—"),
  },
];

export default function CycleCountsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data: counts = [] } = useCycleCounts();
  const navigate = useNavigate();

  return (
    <div className="flex-1 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            Cycle Counts
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Physical inventory counts — snapshot, count, reconcile.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)} className="gap-2">
          <Plus className="w-4 h-4" />
          New Count
        </Button>
      </div>

      <DataTable
        data={counts}
        columns={COLUMNS}
        emptyMessage="No cycle counts yet"
        emptyIcon={ClipboardCheck}
        onRowClick={(row) => navigate(`/cycle-counts/${row.id}`)}
        pageSize={20}
      />

      <OpenCountDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
