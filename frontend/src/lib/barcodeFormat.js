/**
 * Pick the best barcode format for a given value.
 * - 12 digits → UPC-A (North American retail standard)
 * - 13 digits → EAN-13 (international)
 * - Otherwise → CODE128 (supports alphanumeric, e.g. internal SKU)
 */
export function getBarcodeFormat(value) {
  const s = String(value || "").trim();
  if (/^\d{12}$/.test(s)) return "UPC";
  if (/^\d{13}$/.test(s)) return "EAN13";
  return "CODE128";
}
