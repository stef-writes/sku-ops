import { useEffect } from "react";
import { Camera, CameraOff, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCameraScanner } from "@/hooks/useCameraScanner";

/**
 * Camera viewfinder for barcode scanning.
 *
 * Self-contained UI — decodes barcodes and calls onScan(code).
 * Does not do product lookup; the parent wires onScan to the
 * barcode scanner hook's submit() function.
 *
 * @param {{ onScan: (code: string) => void, onClose: () => void, scanning?: boolean }} props
 */
export function CameraScanner({ onScan, onClose, scanning = false }) {
  const { elementId, start, stop, active, error } = useCameraScanner({ onScan });

  useEffect(() => {
    start();
    return () => { stop(); };
  }, [start, stop]);

  return (
    <div className="relative rounded-2xl overflow-hidden bg-black">
      <div id={elementId} className="w-full aspect-[4/3]" />

      {scanning && (
        <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
          <span className="text-white text-sm font-medium animate-pulse">Looking up…</span>
        </div>
      )}

      {error && (
        <div className="absolute inset-0 bg-card flex flex-col items-center justify-center gap-3 p-6 text-center">
          <CameraOff className="w-10 h-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground max-w-xs">{error}</p>
          <Button variant="outline" size="sm" onClick={start}>
            <Camera className="w-4 h-4 mr-2" />Try Again
          </Button>
        </div>
      )}

      {!error && !active && !scanning && (
        <div className="absolute inset-0 bg-card flex items-center justify-center">
          <span className="text-sm text-muted-foreground animate-pulse">Starting camera…</span>
        </div>
      )}

      <button
        onClick={() => { stop(); onClose(); }}
        className="absolute top-3 right-3 rounded-full bg-black/50 p-2 text-white hover:bg-black/70 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
