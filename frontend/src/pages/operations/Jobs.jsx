import { useState, useMemo } from "react";
import { Plus, Briefcase } from "lucide-react";
import { format } from "date-fns";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { DataTable } from "@/components/DataTable";
import { ViewToolbar } from "@/components/ViewToolbar";
import { StatusBadge } from "@/components/StatusBadge";
import { JobDetailPanel } from "@/components/JobDetailPanel";
import { useJobs, useCreateJob } from "@/hooks/useJobs";
import { useViewController } from "@/hooks/useViewController";
import { JOB_STATUSES } from "@/lib/constants";

const COLUMNS = [
  {
    key: "code",
    label: "Code",
    type: "text",
    render: (row) => (
      <span className="font-mono text-sm font-semibold text-foreground">{row.code}</span>
    ),
  },
  {
    key: "name",
    label: "Name",
    type: "text",
    render: (row) => (
      <span className="text-foreground">{row.name || "—"}</span>
    ),
  },
  {
    key: "status",
    label: "Status",
    type: "enum",
    filterValues: Object.values(JOB_STATUSES),
    render: (row) => <StatusBadge status={row.status} />,
  },
  {
    key: "service_address",
    label: "Address",
    type: "text",
    render: (row) => (
      <span className="text-sm text-muted-foreground truncate max-w-[200px] inline-block">
        {row.service_address || "—"}
      </span>
    ),
  },
  {
    key: "created_at",
    label: "Created",
    type: "date",
    render: (row) => (
      <span className="font-mono text-xs text-muted-foreground">
        {row.created_at ? format(new Date(row.created_at), "MMM d, yyyy") : "—"}
      </span>
    ),
  },
];

const Jobs = () => {
  const [detailJobId, setDetailJobId] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ code: "", name: "" });

  const { data: jobs = [], isLoading } = useJobs();
  const createJob = useCreateJob();

  const view = useViewController({ columns: COLUMNS });
  const processed = view.apply(jobs);

  const statusCounts = useMemo(() => {
    const counts = {};
    jobs.forEach((j) => {
      counts[j.status] = (counts[j.status] || 0) + 1;
    });
    return counts;
  }, [jobs]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!createForm.code.trim()) {
      toast.error("Job code is required");
      return;
    }
    try {
      const job = await createJob.mutateAsync({
        code: createForm.code.trim(),
        name: createForm.name.trim() || createForm.code.trim(),
      });
      toast.success(`Job ${createForm.code} created`);
      setCreateOpen(false);
      setCreateForm({ code: "", name: "" });
      setDetailJobId(job.id);
    } catch {
      toast.error("Failed to create job");
    }
  };

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="jobs-page">
      <PageHeader
        title="Jobs"
        subtitle={`${jobs.length} job${jobs.length !== 1 ? "s" : ""}`}
        action={
          <Button onClick={() => setCreateOpen(true)} className="gap-2" data-testid="create-job-btn">
            <Plus className="w-4 h-4" />
            New Job
          </Button>
        }
      />

      <div className="flex flex-wrap gap-2 mb-6">
        {Object.entries(statusCounts).map(([status, count]) => (
          <div
            key={status}
            className="px-3 py-1.5 rounded-lg border text-xs bg-muted border-border text-foreground"
          >
            <span className="font-semibold capitalize">{count} {status}</span>
          </div>
        ))}
      </div>

      <ViewToolbar
        controller={view}
        columns={COLUMNS}
        data={jobs}
        resultCount={processed.length}
        className="mb-3"
      />

      <DataTable
        data={processed}
        columns={view.visibleColumns}
        title="Jobs"
        emptyMessage="No jobs yet"
        emptyIcon={Briefcase}
        onRowClick={(row) => setDetailJobId(row.id)}
        disableSort
      />

      <JobDetailPanel
        jobId={detailJobId}
        open={!!detailJobId}
        onOpenChange={(open) => !open && setDetailJobId(null)}
      />

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Briefcase className="w-5 h-5 text-muted-foreground" />
              New Job
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 pt-2">
            <div>
              <Label className="text-xs text-muted-foreground">Job Code *</Label>
              <Input
                value={createForm.code}
                onChange={(e) => setCreateForm((f) => ({ ...f, code: e.target.value }))}
                placeholder="e.g. JOB-2026-001"
                className="mt-1 font-mono"
                autoFocus
              />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Name</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Optional descriptive name"
                className="mt-1"
              />
            </div>
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)} className="flex-1">Cancel</Button>
              <Button type="submit" disabled={createJob.isPending} className="flex-1">
                {createJob.isPending ? "Creating…" : "Create Job"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Jobs;
