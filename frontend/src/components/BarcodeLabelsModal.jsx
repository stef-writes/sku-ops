import { useRef } from "react";
import { useReactToPrint } from "react-to-print";
import Barcode from "react-barcode";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Printer } from "lucide-react";

/** Printable barcode labels - 2" x 1" style, 3 per row */
export function BarcodeLabelsModal({ products, open, onOpenChange }) {
  const printRef = useRef(null);

  const handlePrint = useReactToPrint({
    contentRef: printRef,
    documentTitle: "SKU Labels",
    pageStyle: `
      @page { size: 4in 6in; margin: 0.25in; }
      @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
    `,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Print Barcode Labels</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-500">
          {products?.length || 0} labels · Standard 2×1" layout · Use browser Print
        </p>

        <div className="flex-1 overflow-auto border rounded-lg bg-white p-4">
          <div
            ref={printRef}
            className="grid grid-cols-3 gap-2 print:gap-1"
            style={{ minHeight: 200 }}
          >
            {products?.filter((p) => (p.barcode || p.sku)?.toString().trim()).map((p) => {
              const code = (p.barcode || p.sku).toString().trim();
              return (
              <div
                key={p.id}
                className="border border-slate-200 rounded p-2 flex flex-col items-center justify-center"
                style={{ minWidth: 120, minHeight: 80 }}
              >
                <Barcode
                  value={code}
                  format="CODE128"
                  width={1.2}
                  height={28}
                  margin={0}
                  fontSize={10}
                  displayValue={true}
                />
                <div className="text-[10px] font-mono mt-1 text-center truncate w-full">
                  {p.sku}
                </div>
                <div className="text-[9px] text-slate-500 text-center truncate w-full max-w-[100px]">
                  {p.name?.slice(0, 20)}
                  {p.name?.length > 20 ? "…" : ""}
                </div>
              </div>
            );
            })}
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <Button onClick={handlePrint} className="flex-1">
            <Printer className="w-4 h-4 mr-2" />
            Print
          </Button>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
