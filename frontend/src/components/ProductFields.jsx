import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Info } from "lucide-react";
import { UOM_OPTIONS } from "@/lib/constants";
import { GroupCombobox } from "@/components/GroupCombobox";

function FieldTip({ children }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className="w-3.5 h-3.5 text-muted-foreground cursor-help inline-block ml-1 align-middle" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[220px] text-center">
        {children}
      </TooltipContent>
    </Tooltip>
  );
}

const isHidden = (set, name) => set?.has(name);
const isReadOnly = (set, name) => set?.has(name);

/**
 * Shared product field grid, extracted from ProductFormDialog.
 *
 * @param {object}   fields          Current field values (name, description, price, cost, quantity, min_stock, department_id, vendor_id, barcode, base_unit, sell_uom, pack_qty)
 * @param {function} onChange        (fieldName, value) => void
 * @param {array}    departments     Department list
 * @param {array}    vendors         Vendor list
 * @param {Set}      hiddenFields    Field names to hide entirely
 * @param {Set}      readOnlyFields  Field names to render read-only
 * @param {boolean}  compact         Tighter layout for inline use (receive review, receipt import)
 * @param {ReactNode} uomAction      Optional button to render next to UOM fields (e.g. "Suggest unit")
 */
export function ProductFields({
  fields,
  onChange,
  departments = [],
  vendors = [],
  hiddenFields,
  readOnlyFields,
  compact = false,
  uomAction,
}) {
  const h =
    hiddenFields instanceof Set ? hiddenFields : new Set(hiddenFields || []);
  const ro =
    readOnlyFields instanceof Set
      ? readOnlyFields
      : new Set(readOnlyFields || []);

  const inputCls = compact ? "input-field h-9 text-sm" : "input-workshop mt-2";
  const labelCls = compact
    ? "text-muted-foreground font-medium text-xs"
    : "text-muted-foreground font-medium text-sm";
  const gap = compact ? "gap-2" : "gap-4";

  const field = (name) => fields[name] ?? "";
  const set = (name, value) => onChange(name, value);

  return (
    <div className={`grid grid-cols-2 ${gap}`}>
      {!isHidden(h, "name") && (
        <div className="col-span-2">
          <Label className={labelCls}>Product name {!compact && "*"}</Label>
          <Input
            value={field("name")}
            onChange={(e) => set("name", e.target.value)}
            placeholder="e.g., 2x4 Pine Board"
            className={inputCls}
            readOnly={isReadOnly(ro, "name")}
            data-testid="pf-name"
          />
        </div>
      )}

      {!isHidden(h, "description") && (
        <div className="col-span-2">
          <Label className={labelCls}>Description</Label>
          <Input
            value={field("description")}
            onChange={(e) => set("description", e.target.value)}
            placeholder="Optional description"
            className={inputCls}
            readOnly={isReadOnly(ro, "description")}
            data-testid="pf-description"
          />
        </div>
      )}

      {!isHidden(h, "department_id") && (
        <div>
          <Label className={labelCls}>Department {!compact && "*"}</Label>
          <Select
            value={field("department_id")}
            onValueChange={(v) => set("department_id", v)}
            disabled={isReadOnly(ro, "department_id")}
          >
            <SelectTrigger className={inputCls} data-testid="pf-department">
              <SelectValue placeholder="Select department" />
            </SelectTrigger>
            <SelectContent>
              {departments.map((dept) => (
                <SelectItem key={dept.id} value={dept.id}>
                  <span className="font-mono font-medium">{dept.code}</span>
                  <span className="text-muted-foreground mx-1.5">—</span>
                  {dept.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {!isHidden(h, "vendor_id") && (
        <div>
          <Label className={labelCls}>Vendor</Label>
          <Select
            value={field("vendor_id") || "none"}
            onValueChange={(v) => set("vendor_id", v === "none" ? "" : v)}
            disabled={isReadOnly(ro, "vendor_id")}
          >
            <SelectTrigger className={inputCls} data-testid="pf-vendor">
              <SelectValue placeholder="Select vendor" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">None</SelectItem>
              {vendors.map((v) => (
                <SelectItem key={v.id} value={v.id}>
                  {v.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {!isHidden(h, "price") && (
        <div>
          <Label className={labelCls}>Price {!compact && "*"}</Label>
          <Input
            type="number"
            step="0.01"
            value={field("price")}
            onChange={(e) => set("price", e.target.value)}
            placeholder="0.00"
            className={inputCls}
            readOnly={isReadOnly(ro, "price")}
            data-testid="pf-price"
          />
        </div>
      )}

      {!isHidden(h, "cost") && (
        <div>
          <Label className={labelCls}>Cost</Label>
          <Input
            type="number"
            step="0.01"
            value={field("cost")}
            onChange={(e) => set("cost", e.target.value)}
            placeholder="0.00"
            className={inputCls}
            readOnly={isReadOnly(ro, "cost")}
            data-testid="pf-cost"
          />
        </div>
      )}

      {!isHidden(h, "quantity") && (
        <div>
          <Label className={labelCls}>Quantity</Label>
          <Input
            type="number"
            step="any"
            value={field("quantity")}
            onChange={(e) => set("quantity", e.target.value)}
            placeholder="0"
            className={inputCls}
            readOnly={isReadOnly(ro, "quantity")}
            data-testid="pf-quantity"
          />
        </div>
      )}

      {!isHidden(h, "min_stock") && (
        <div>
          <Label className={labelCls}>
            Min stock{!compact && " level"}
            {!compact && (
              <FieldTip>
                Alert threshold — item shows as Low Stock when quantity falls to
                or below this number.
              </FieldTip>
            )}
          </Label>
          <Input
            type="number"
            value={field("min_stock")}
            onChange={(e) => set("min_stock", e.target.value)}
            placeholder="5"
            className={inputCls}
            readOnly={isReadOnly(ro, "min_stock")}
            data-testid="pf-min-stock"
          />
        </div>
      )}

      {!isHidden(h, "base_unit") && (
        <div
          className={
            compact
              ? "col-span-2 flex items-end gap-2 flex-wrap"
              : "col-span-3 flex items-end gap-2 flex-wrap"
          }
        >
          <div className="flex-1 min-w-[100px]">
            <Label className={labelCls}>
              Base Unit
              {!compact && (
                <FieldTip>
                  The physical unit this product is stored and counted in (e.g.
                  each, roll, gallon).
                </FieldTip>
              )}
            </Label>
            <Select
              value={field("base_unit") || "each"}
              onValueChange={(v) => set("base_unit", v)}
              disabled={isReadOnly(ro, "base_unit")}
            >
              <SelectTrigger className={inputCls}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {UOM_OPTIONS.map((u) => (
                  <SelectItem key={u} value={u}>
                    {u}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {!isHidden(h, "sell_uom") && (
            <div className="flex-1 min-w-[100px]">
              <Label className={labelCls}>
                Sell Unit
                {!compact && (
                  <FieldTip>
                    The unit shown to customers and used when issuing materials.
                  </FieldTip>
                )}
              </Label>
              <Select
                value={field("sell_uom") || "each"}
                onValueChange={(v) => set("sell_uom", v)}
                disabled={isReadOnly(ro, "sell_uom")}
              >
                <SelectTrigger className={inputCls}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {UOM_OPTIONS.map((u) => (
                    <SelectItem key={u} value={u}>
                      {u}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {!isHidden(h, "pack_qty") && (
            <div className="min-w-[80px]">
              <Label className={labelCls}>
                Pack Qty
                {!compact && (
                  <FieldTip>
                    How many Base Units are in one Sell Unit. E.g. a box of 12
                    screws = 12.
                  </FieldTip>
                )}
              </Label>
              <Input
                type="number"
                min="1"
                value={field("pack_qty")}
                onChange={(e) => set("pack_qty", e.target.value)}
                className={inputCls}
                readOnly={isReadOnly(ro, "pack_qty")}
              />
            </div>
          )}

          {uomAction}
        </div>
      )}

      {!isHidden(h, "product_group") && (
        <div className="col-span-2" data-testid="pf-product-group">
          <Label className={labelCls}>
            Product Group
            {!compact && (
              <FieldTip>
                Group related variants together (e.g. &quot;1/2 PEX
                Tubing&quot;) so you can view combined stock across sizes and
                vendors.
              </FieldTip>
            )}
          </Label>
          <GroupCombobox
            value={field("product_group")}
            onChange={(v) => set("product_group", v)}
            compact={compact}
            disabled={isReadOnly(ro, "product_group")}
          />
        </div>
      )}

      {!isHidden(h, "barcode") && (
        <div className="col-span-2">
          <Label className={labelCls}>Barcode</Label>
          <Input
            value={field("barcode")}
            onChange={(e) => set("barcode", e.target.value)}
            placeholder={
              compact
                ? "UPC / barcode"
                : "UPC (12 digits) or leave blank to use SKU"
            }
            className={inputCls}
            readOnly={isReadOnly(ro, "barcode")}
            data-testid="pf-barcode"
          />
          {!compact && (
            <p className="text-xs text-muted-foreground mt-1">
              UPC for vendor products; leave blank to use internal SKU (Code128)
            </p>
          )}
        </div>
      )}
    </div>
  );
}
