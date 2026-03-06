import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar as CalendarIcon } from "lucide-react";
import { format } from "date-fns";
import { DATE_PRESETS } from "@/lib/constants";

function toDateStr(d) {
  return d ? format(d, "yyyy-MM-dd") : "";
}

export function DateRangeFilter({ value, onChange }) {
  const label = value.from
    ? value.to
      ? `${format(value.from, "MMM d")} – ${format(value.to, "MMM d")}`
      : format(value.from, "MMM d, yyyy")
    : "Custom range";

  const activePreset = useMemo(() => {
    for (const preset of DATE_PRESETS) {
      const pv = preset.getValue();
      if (toDateStr(pv.from) === toDateStr(value.from) && toDateStr(pv.to) === toDateStr(value.to)) {
        return preset.label;
      }
    }
    return null;
  }, [value]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex gap-1 bg-muted rounded-lg p-1">
        {DATE_PRESETS.map((preset) => {
          const isActive = activePreset === preset.label;
          return (
            <button
              key={preset.label}
              onClick={() => onChange(preset.getValue())}
              className={`text-xs px-3 py-1.5 rounded-md transition-all font-medium ${
                isActive
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-card/60 hover:text-foreground"
              }`}
              type="button"
            >
              {preset.label}
            </button>
          );
        })}
      </div>
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" className="h-9 px-3 text-sm gap-2">
            <CalendarIcon className="w-4 h-4" />
            {label}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="end">
          <Calendar
            mode="range"
            selected={value}
            onSelect={(r) => onChange(r || { from: null, to: null })}
            numberOfMonths={2}
          />
        </PopoverContent>
      </Popover>
      {(value.from || value.to) && (
        <button
          onClick={() => onChange({ from: null, to: null })}
          className="text-xs text-muted-foreground hover:text-foreground"
          type="button"
        >
          Clear
        </button>
      )}
    </div>
  );
}
