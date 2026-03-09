import { useState, useCallback, useEffect } from "react";
import { toast } from "sonner";

const CART_KEY = "sku_ops_cart";

function loadPersistedCart() {
  try {
    const raw = localStorage.getItem(CART_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch { /* corrupted data — start fresh */ }
  return [];
}

/**
 * Shared cart state for material-picking flows (POS, RequestMaterials, ScanMode).
 *
 * Each item shape: { product_id, sku, name, quantity, max_quantity, unit, unit_price }
 * Cart is persisted to localStorage so a page refresh doesn't lose items.
 *
 * @param {object} [options]
 * @param {(product: object) => number} [options.getPrice] - derive unit_price from a product. Defaults to sell_price ?? price.
 * @param {boolean} [options.persist=false] - enable localStorage persistence
 */
export function useCart({ getPrice, persist = false } = {}) {
  const [items, setItems] = useState(() => (persist ? loadPersistedCart() : []));

  useEffect(() => {
    if (persist) localStorage.setItem(CART_KEY, JSON.stringify(items));
  }, [items, persist]);

  const resolvePrice = getPrice || ((p) => p.sell_price ?? p.price ?? 0);

  function addItem(product) {
    const sellQty = product.sell_quantity ?? product.quantity;
    const existing = items.find((i) => i.product_id === product.id);
    if (existing) {
      if (existing.quantity >= sellQty) {
        toast.error("Not enough stock");
        return;
      }
      setItems((prev) =>
        prev.map((i) =>
          i.product_id === product.id ? { ...i, quantity: i.quantity + 1 } : i
        )
      );
    } else {
      setItems((prev) => [
        ...prev,
        {
          product_id: product.id,
          sku: product.sku,
          name: product.name,
          quantity: 1,
          max_quantity: sellQty,
          unit: product.sell_uom || "each",
          unit_price: resolvePrice(product),
        },
      ]);
    }
  }

  function updateQuantity(productId, newQty) {
    setItems((prev) =>
      prev
        .map((item) => {
          if (item.product_id !== productId) return item;
          if (newQty <= 0) return null;
          if (newQty > item.max_quantity) {
            toast.error("Not enough stock");
            return item;
          }
          return { ...item, quantity: newQty };
        })
        .filter(Boolean)
    );
  }

  function removeItem(productId) {
    setItems((prev) => prev.filter((i) => i.product_id !== productId));
  }

  function clear() {
    setItems([]);
    if (persist) localStorage.removeItem(CART_KEY);
  }

  const syncStock = useCallback((products) => {
    if (!products?.length) return;
    const productMap = new Map(products.map((p) => [p.id, p]));
    setItems((prev) =>
      prev.map((item) => {
        const fresh = productMap.get(item.product_id);
        if (!fresh) return item;
        const newMax = fresh.sell_quantity ?? fresh.quantity;
        return { ...item, max_quantity: newMax };
      })
    );
  }, []);

  const total = items.reduce((sum, i) => sum + i.quantity * i.unit_price, 0);

  return { items, addItem, updateQuantity, removeItem, clear, syncStock, total };
}
