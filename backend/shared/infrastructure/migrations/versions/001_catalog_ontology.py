"""Migration 001 — Catalog ontology: products → products + skus + vendor_items.

Transforms the flat `products` table (which held SKU-level data) into three
tables that match the new domain model:

  products     — lightweight product family (name, description, category)
  skus         — inventory-level item (sku, price, cost, quantity, barcode, …)
  vendor_items — vendor-specific pricing, sourced from old vendor_id/vendor_name

Also renames departments.product_count → sku_count and drops
vendors.product_count (no longer tracked on vendor).

Detection: if products.sku column exists, we're on the old schema and need
to migrate. If products.category_id exists, we're already on the new schema.
"""

import logging
import uuid

logger = logging.getLogger(__name__)


async def _column_exists(conn, table: str, column: str, dialect: str) -> bool:
    if dialect == "sqlite":
        cursor = await conn.execute(f"PRAGMA table_info({table})")
        rows = await cursor.fetchall()
        return any(row[1] == column for row in rows)
    cursor = await conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        (table, column),
    )
    return (await cursor.fetchone()) is not None


async def up(conn, dialect: str) -> None:
    # Detect schema state
    has_old_sku_col = await _column_exists(conn, "products", "sku", dialect)
    has_new_category_col = await _column_exists(conn, "products", "category_id", dialect)

    if has_new_category_col and not has_old_sku_col:
        logger.info("Migration 001: products table already has new schema — skipping")
        return

    if not has_old_sku_col:
        logger.info("Migration 001: products table has neither old nor new columns — skipping")
        return

    logger.info("Migration 001: transforming old products table → products + skus + vendor_items")

    # ── Step 1: Rename old products table ─────────────────────────────────
    await conn.execute("ALTER TABLE products RENAME TO _products_legacy")
    await conn.commit()

    # ── Step 2: Drop old indexes that reference the renamed table ─────────
    old_indexes = [
        "idx_products_sku",
        "idx_products_department",
        "idx_products_vendor",
        "idx_products_vendor_original_sku",
        "idx_products_barcode",
        "idx_products_vendor_barcode",
        "idx_products_org",
        "idx_products_group",
    ]
    for idx in old_indexes:
        await conn.execute(f"DROP INDEX IF EXISTS {idx}")
    await conn.commit()

    # ── Step 3: Create new tables ─────────────────────────────────────────
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category_id TEXT NOT NULL REFERENCES departments(id),
            category_name TEXT NOT NULL DEFAULT '',
            sku_count INTEGER NOT NULL DEFAULT 0,
            organization_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            id TEXT PRIMARY KEY,
            sku TEXT NOT NULL,
            product_id TEXT NOT NULL REFERENCES products(id),
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            price REAL NOT NULL,
            cost REAL NOT NULL DEFAULT 0,
            quantity REAL NOT NULL DEFAULT 0,
            min_stock INTEGER NOT NULL DEFAULT 5,
            category_id TEXT NOT NULL REFERENCES departments(id),
            category_name TEXT NOT NULL DEFAULT '',
            barcode TEXT,
            vendor_barcode TEXT,
            base_unit TEXT NOT NULL DEFAULT 'each',
            sell_uom TEXT NOT NULL DEFAULT 'each',
            pack_qty INTEGER NOT NULL DEFAULT 1,
            purchase_uom TEXT NOT NULL DEFAULT 'each',
            purchase_pack_qty INTEGER NOT NULL DEFAULT 1,
            organization_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS vendor_items (
            id TEXT PRIMARY KEY,
            vendor_id TEXT NOT NULL REFERENCES vendors(id),
            sku_id TEXT NOT NULL REFERENCES skus(id),
            vendor_sku TEXT,
            vendor_name TEXT NOT NULL DEFAULT '',
            purchase_uom TEXT NOT NULL DEFAULT 'each',
            purchase_pack_qty INTEGER NOT NULL DEFAULT 1,
            cost REAL NOT NULL DEFAULT 0,
            lead_time_days INTEGER,
            moq REAL,
            is_preferred INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            organization_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            UNIQUE(vendor_id, sku_id)
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sku_counters (
            department_code TEXT PRIMARY KEY,
            counter INTEGER NOT NULL DEFAULT 0
        )
    """)
    await conn.commit()

    # ── Step 4: Migrate data ──────────────────────────────────────────────
    # Each old product becomes both a new product (family) and a SKU.
    # The old product.id is reused as the new product.id so that FKs in
    # other tables (stock_transactions.product_id, etc.) keep working.
    # The SKU gets a new UUID.

    # 4a: Insert product families (one per old product)
    await conn.execute("""
        INSERT INTO products (id, name, description, category_id, category_name,
                              sku_count, organization_id, created_at, updated_at, deleted_at)
        SELECT id, name, COALESCE(description, ''), department_id,
               COALESCE(department_name, ''), 1, organization_id,
               created_at, updated_at, deleted_at
        FROM _products_legacy
    """)
    await conn.commit()

    # 4b: Insert SKUs — need to generate new UUIDs for each row
    # Fetch legacy rows and insert one by one (UUID generation)
    cursor = await conn.execute("""
        SELECT id, sku, name, COALESCE(description, ''), price, cost, quantity,
               min_stock, department_id, COALESCE(department_name, ''),
               barcode, vendor_barcode, COALESCE(base_unit, 'each'),
               COALESCE(sell_uom, 'each'), COALESCE(pack_qty, 1),
               organization_id, created_at, updated_at, deleted_at
        FROM _products_legacy
    """)
    rows = await cursor.fetchall()

    # Map old product.id → new sku.id for vendor_items step
    product_to_sku: dict[str, str] = {}

    for row in rows:
        (
            old_id,
            sku,
            name,
            desc,
            price,
            cost,
            qty,
            min_stock,
            dept_id,
            dept_name,
            barcode,
            vbarcode,
            base_unit,
            sell_uom,
            pack_qty,
            org_id,
            created,
            updated,
            deleted,
        ) = row
        sku_id = str(uuid.uuid4())
        product_to_sku[old_id] = sku_id
        await conn.execute(
            "INSERT INTO skus (id, sku, product_id, name, description, price, cost, "
            "quantity, min_stock, category_id, category_name, barcode, vendor_barcode, "
            "base_unit, sell_uom, pack_qty, purchase_uom, purchase_pack_qty, "
            "organization_id, created_at, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'each', 1, ?, ?, ?, ?)",
            (
                sku_id,
                sku,
                old_id,
                name,
                desc,
                price,
                cost,
                qty,
                min_stock,
                dept_id,
                dept_name,
                barcode,
                vbarcode,
                base_unit,
                sell_uom,
                pack_qty,
                org_id,
                created,
                updated,
                deleted,
            ),
        )
    await conn.commit()

    # 4c: Create vendor_items from old products that had a vendor_id
    cursor = await conn.execute("""
        SELECT id, vendor_id, COALESCE(vendor_name, ''), COALESCE(original_sku, ''),
               cost, organization_id, created_at, updated_at
        FROM _products_legacy
        WHERE vendor_id IS NOT NULL AND vendor_id != ''
    """)
    vendor_rows = await cursor.fetchall()

    for row in vendor_rows:
        old_id, vendor_id, vendor_name, orig_sku, cost, org_id, created, updated = row
        sku_id = product_to_sku.get(old_id)
        if not sku_id:
            continue
        await conn.execute(
            "INSERT INTO vendor_items (id, vendor_id, sku_id, vendor_sku, vendor_name, "
            "cost, is_preferred, organization_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                vendor_id,
                sku_id,
                orig_sku,
                vendor_name,
                cost,
                org_id,
                created,
                updated,
            ),
        )
    await conn.commit()

    # ── Step 5: Rename departments.product_count → sku_count ──────────────
    has_product_count = await _column_exists(conn, "departments", "product_count", dialect)
    if has_product_count:
        await conn.execute("ALTER TABLE departments RENAME COLUMN product_count TO sku_count")
        await conn.commit()

    # ── Step 6: Drop vendors.product_count if it exists ───────────────────
    has_vendor_pc = await _column_exists(conn, "vendors", "product_count", dialect)
    if has_vendor_pc:
        if dialect == "sqlite":
            # SQLite ≥ 3.35 supports DROP COLUMN
            await conn.execute("ALTER TABLE vendors DROP COLUMN product_count")
        else:
            await conn.execute("ALTER TABLE vendors DROP COLUMN product_count")
        await conn.commit()

    # ── Step 7: Drop legacy table ─────────────────────────────────────────
    await conn.execute("DROP TABLE IF EXISTS _products_legacy")
    await conn.commit()

    logger.info(
        "Migration 001 complete — migrated %d products → skus, %d vendor_items",
        len(rows),
        len(vendor_rows),
    )
