import { useState, useCallback } from "react";
import { toast } from "sonner";

/**
 * Shared cart state for material-picking flows (POS, RequestMaterials).
 *
 * Each item shape: { product_id, sku, name, quantity, max_quantity, unit, unit_price }
 *
 * @param {object} [options]
 * @param {(product: object) => number} [options.getPrice] - derive unit_price from a product. Defaults to sell_price ?? price.
 */
export function useCart({ getPrice } = {}) {
  const [items, setItems] = useState([]);

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
