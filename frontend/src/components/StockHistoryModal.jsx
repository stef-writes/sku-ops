import { useState, useEffect } from "react";
import axios from "axios";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { format } from "date-fns";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

const TX_TYPE_LABELS = {
  withdrawal: "Withdrawal",
  import: "Import",
  adjustment: "Adjustment",
  receiving: "Receiving",
  return: "Return",
  transfer: "Transfer",
};

export function StockHistoryModal({ product, open, onOpenChange }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !product?.id) return;
    setLoading(true);
    axios
      .get(`${API}/products/${product.id}/stock-history`)
      .then((res) => setHistory(res.data.history || []))
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, [open, product?.id]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="font-heading font-bold text-xl uppercase tracking-wider">
            Stock History — {product?.sku || ""}
          </DialogTitle>
          {product?.name && (
            <p className="text-sm text-slate-500">{product.name}</p>
          )}
        </DialogHeader>
        <div className="flex-1 overflow-auto mt-4">
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : history.length === 0 ? (
            <p className="text-slate-500 text-center py-8">No transactions yet</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="font-semibold">Date</TableHead>
                  <TableHead className="font-semibold">Type</TableHead>
                  <TableHead className="font-semibold text-right">Delta</TableHead>
                  <TableHead className="font-semibold text-right">Before</TableHead>
                  <TableHead className="font-semibold text-right">After</TableHead>
                  <TableHead className="font-semibold">User</TableHead>
                  <TableHead className="font-semibold">Reference</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((tx) => (
                  <TableRow key={tx.id}>
                    <TableCell className="text-sm">
                      {tx.created_at
                        ? format(new Date(tx.created_at), "MMM d, yyyy HH:mm")
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {TX_TYPE_LABELS[tx.transaction_type] || tx.transaction_type}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {tx.quantity_delta > 0 ? "+" : ""}
                      {tx.quantity_delta}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {tx.quantity_before}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {tx.quantity_after}
                    </TableCell>
                    <TableCell className="text-sm">{tx.user_name || "—"}</TableCell>
                    <TableCell className="text-sm font-mono text-slate-500">
                      {tx.reference_id?.slice(0, 8) || tx.reason || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
