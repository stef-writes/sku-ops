import { useState } from "react";
import { Briefcase, Save } from "lucide-react";
import { toast } from "sonner";
import { format } from "date-fns";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { DetailPanel, DetailSection, DetailField } from "./DetailPanel";
import { useJob, useUpdateJob } from "@/hooks/useJobs";
import { JOB_STATUSES } from "@/lib/constants";

export function JobDetailPanel({ jobId, open, onOpenChange }) {
  const { data: job, isLoading } = useJob(jobId);
  const updateJob = useUpdateJob();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});

  const startEditing = () => {
    setForm({
      name: job?.name || "",
      status: job?.status || "active",
      notes: job?.notes || "",
    });
    setEditing(true);
  };

  const handleSave = async () => {
    try {
      await updateJob.mutateAsync({ id: job?.id || jobId, data: form });
      toast.success("Job updated");
      setEditing(false);
    } catch {
      toast.error("Failed to update job");
    }
  };

  const statusOptions = Object.entries(JOB_STATUSES).map(([, v]) => v);

  return (
    <DetailPanel
      open={open}
      onOpenChange={onOpenChange}
      title={job?.code || "Job"}
      subtitle={job?.name && job.name !== job.code ? job.name : undefined}
      status={job?.status}
      icon={Briefcase}
      loading={isLoading}
      width="md"
      actions={
        editing ? (
          <>
            <Button variant="outline" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
            <Button size="sm" onClick={handleSave} disabled={updateJob.isPending} className="gap-1.5">
              <Save className="w-3.5 h-3.5" />
              {updateJob.isPending ? "Saving…" : "Save"}
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" onClick={startEditing}>Edit</Button>
        )
      }
    >
      {editing ? (
        <>
          <DetailSection label="Details">
            <div className="space-y-3">
              <div>
                <label className="text-xs text-muted-foreground">Name</label>
                <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="mt-1" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Status</label>
                <Select value={form.status} onValueChange={(v) => setForm((f) => ({ ...f, status: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {statusOptions.map((s) => (
                      <SelectItem key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Notes</label>
                <Textarea value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} className="mt-1 min-h-[80px]" />
              </div>
            </div>
          </DetailSection>
        </>
      ) : (
        <>
          <DetailSection label="Details">
            <div className="grid grid-cols-2 gap-4">
              <DetailField label="Code" value={job?.code} mono />
              <DetailField label="Name" value={job?.name} />
              <DetailField label="Status" value={job?.status} />
              <DetailField
                label="Billing Entity"
                value={job?.billing_entity_id ? job.billing_entity_id.slice(0, 8) + "…" : undefined}
                mono
              />
            </div>
          </DetailSection>

          {job?.service_address && (
            <DetailSection label="Service Address">
              <p className="text-sm text-foreground">{job.service_address}</p>
            </DetailSection>
          )}

          {job?.notes && (
            <DetailSection label="Notes">
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{job.notes}</p>
            </DetailSection>
          )}

          <DetailSection label="Timestamps">
            <div className="grid grid-cols-2 gap-4">
              <DetailField
                label="Created"
                value={job?.created_at ? format(new Date(job.created_at), "MMM d, yyyy h:mm a") : undefined}
              />
              <DetailField
                label="Updated"
                value={job?.updated_at ? format(new Date(job.updated_at), "MMM d, yyyy h:mm a") : undefined}
              />
            </div>
          </DetailSection>
        </>
      )}
    </DetailPanel>
  );
}
