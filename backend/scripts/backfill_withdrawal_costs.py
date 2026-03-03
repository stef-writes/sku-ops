"""
One-time migration: backfill item cost and cost_total on existing withdrawals
that were stored with cost=0.0.

Uses current product catalog cost as a proxy for historical cost.
Run from the backend directory:
    uv run python scripts/backfill_withdrawal_costs.py
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite

DB_PATH = "./data/sku_ops.db"


async def main():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Build product cost map: {product_id: cost}
        cur = await conn.execute("SELECT id, cost FROM products")
        rows = await cur.fetchall()
        cost_map = {r["id"]: (r["cost"] or 0.0) for r in rows}
        print(f"Loaded {len(cost_map)} products")

        # Fetch all withdrawals
        cur = await conn.execute("SELECT id, items, cost_total FROM withdrawals")
        withdrawals = await cur.fetchall()
        print(f"Processing {len(withdrawals)} withdrawals…")

        updated = 0
        for w in withdrawals:
            items = json.loads(w["items"])
            changed = False
            for item in items:
                if (item.get("cost", 0.0) == 0.0) and item.get("product_id") in cost_map:
                    item["cost"] = cost_map[item["product_id"]]
                    changed = True

            if changed:
                new_cost_total = sum(i.get("cost", 0.0) * i.get("quantity", 0) for i in items)
                await conn.execute(
                    "UPDATE withdrawals SET items = ?, cost_total = ? WHERE id = ?",
                    (json.dumps(items), new_cost_total, w["id"]),
                )
                updated += 1

        await conn.commit()
        print(f"Updated {updated} withdrawals with backfilled costs.")


if __name__ == "__main__":
    asyncio.run(main())
