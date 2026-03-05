import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

/**
 * Shared create/edit dialog for CRUD entities.
 *
 * @param {{
 *   open: boolean,
 *   onOpenChange: (open: boolean) => void,
 *   title: string,
 *   schema: import("zod").ZodObject,
 *   fields: Array<{
 *     name: string,
 *     label: string,
 *     type?: "text" | "email" | "password" | "number" | "textarea" | "select",
 *     placeholder?: string,
 *     options?: Array<{ value: string, label: string }>,
 *     disabled?: boolean | ((isEditing: boolean) => boolean),
 *     className?: string,
 *     note?: string,
 *     transform?: (value: string) => string,
 *   }>,
 *   entity?: object | null,
 *   entityToForm?: (entity: object) => object,
 *   defaults?: object,
 *   onSubmit: (data: object, isEditing: boolean) => Promise<void>,
 *   saving?: boolean,
 *   testIdPrefix?: string,
 * }} props
 */
export function EntityFormDialog({
  open, onOpenChange, title, schema, fields,
  entity = null, entityToForm, defaults = {},
  onSubmit, saving = false, testIdPrefix = "entity",
}) {
  const isEditing = !!entity;

  const form = useForm({
    resolver: schema ? zodResolver(schema) : undefined,
    defaultValues: defaults,
  });

  useEffect(() => {
    if (open) {
      if (entity && entityToForm) {
        form.reset(entityToForm(entity));
      } else if (entity) {
        const vals = {};
        fields.forEach((f) => { vals[f.name] = entity[f.name] ?? defaults[f.name] ?? ""; });
        form.reset(vals);
      } else {
        form.reset(defaults);
      }
    }
  }, [open, entity]);

  const handleSubmit = form.handleSubmit(async (data) => {
    await onSubmit(data, isEditing);
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid={`${testIdPrefix}-dialog`}>
        <DialogHeader>
          <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
            {isEditing ? `Edit ${title}` : `Add New ${title}`}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-4">
          {fields.map((field) => {
            const error = form.formState.errors[field.name];
            const isDisabled = typeof field.disabled === "function"
              ? field.disabled(isEditing)
              : field.disabled;

            return (
              <div key={field.name}>
                <Label className="text-slate-700 font-semibold uppercase text-sm tracking-wide">
                  {field.label}
                </Label>
                {field.type === "textarea" ? (
                  <Textarea
                    {...form.register(field.name)}
                    placeholder={field.placeholder}
                    disabled={isDisabled}
                    className={`input-workshop mt-2 ${field.className || ""}`}
                    data-testid={`${testIdPrefix}-${field.name}-input`}
                  />
                ) : field.type === "select" ? (
                  <Select
                    value={form.watch(field.name) || ""}
                    onValueChange={(v) => form.setValue(field.name, v)}
                    disabled={isDisabled}
                  >
                    <SelectTrigger className="mt-2" data-testid={`${testIdPrefix}-${field.name}-input`}>
                      <SelectValue placeholder={field.placeholder} />
                    </SelectTrigger>
                    <SelectContent>
                      {(field.options || []).map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    type={field.type || "text"}
                    {...form.register(field.name, {
                      onChange: field.transform
                        ? (e) => { e.target.value = field.transform(e.target.value); }
                        : undefined,
                    })}
                    placeholder={field.placeholder}
                    disabled={isDisabled}
                    maxLength={field.maxLength}
                    className={`input-workshop mt-2 ${field.className || ""}`}
                    data-testid={`${testIdPrefix}-${field.name}-input`}
                  />
                )}
                {field.note && isEditing && (
                  <p className="text-xs text-slate-400 mt-1">{field.note}</p>
                )}
                {error && (
                  <p className="text-xs text-red-500 mt-1">{error.message}</p>
                )}
              </div>
            );
          })}
          <div className="flex gap-3 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="flex-1 btn-secondary h-12"
              data-testid={`${testIdPrefix}-cancel-btn`}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={saving}
              className="flex-1 btn-primary h-12"
              data-testid={`${testIdPrefix}-save-btn`}
            >
              {saving ? "Saving..." : isEditing ? "Update" : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
