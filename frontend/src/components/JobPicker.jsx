import { useState, useRef, useEffect } from "react";
import { Input } from "./ui/input";
import { FileText, Plus, Check } from "lucide-react";
import { useJobSearch, useCreateJob } from "@/hooks/useJobs";
import { toast } from "sonner";

/**
 * Autocomplete combobox for selecting or creating jobs.
 * @param {{ value: string, onChange: (code: string) => void, placeholder?: string, required?: boolean }} props
 */
export function JobPicker({ value, onChange, placeholder = "e.g. JOB-2024-001", required = false }) {
  const [query, setQuery] = useState(value || "");
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const inputRef = useRef(null);
  const createJob = useCreateJob();

  const { data: results = [] } = useJobSearch(query);

  useEffect(() => {
    setQuery(value || "");
  }, [value]);

  useEffect(() => {
    const handler = (e) => {
      if (!wrapperRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const select = (code) => {
    setQuery(code);
    onChange(code);
    setOpen(false);
  };

  const handleInputChange = (e) => {
    const v = e.target.value;
    setQuery(v);
    onChange(v);
    if (v.trim()) setOpen(true);
  };

  const handleCreate = async () => {
    const code = query.trim();
    if (!code) return;
    try {
      await createJob.mutateAsync({ code, name: code });
      toast.success(`Job ${code} created`);
      select(code);
    } catch {
      select(code);
    }
  };

  const exactMatch = results.some((j) => j.code.toLowerCase() === query.trim().toLowerCase());

  return (
    <div ref={wrapperRef} className="relative">
      <FileText className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
      <Input
        ref={inputRef}
        value={query}
        onChange={handleInputChange}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className="pl-10"
        required={required}
        data-testid="job-picker-input"
      />
      {open && query.trim() && (
        <div className="absolute z-30 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden max-h-56 overflow-y-auto">
          {results.map((job) => (
            <button
              key={job.id}
              type="button"
              onClick={() => select(job.code)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50 text-left border-b border-slate-100 last:border-b-0"
            >
              {job.code.toLowerCase() === query.trim().toLowerCase() ? (
                <Check className="w-4 h-4 text-emerald-500 shrink-0" />
              ) : (
                <FileText className="w-4 h-4 text-slate-300 shrink-0" />
              )}
              <div className="min-w-0">
                <span className="font-mono text-sm font-medium text-slate-900">{job.code}</span>
                {job.name && job.name !== job.code && (
                  <span className="text-xs text-slate-400 ml-2">{job.name}</span>
                )}
              </div>
            </button>
          ))}
          {!exactMatch && query.trim() && (
            <button
              type="button"
              onClick={handleCreate}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-emerald-50 text-left text-emerald-700"
            >
              <Plus className="w-4 h-4 shrink-0" />
              <span className="text-sm">Create <strong>{query.trim()}</strong></span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
