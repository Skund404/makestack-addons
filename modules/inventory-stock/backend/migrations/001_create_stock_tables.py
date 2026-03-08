"""Migration 001 — Create inventory_stock_items table."""

id = "001_create_stock_tables"
description = "Create stock tracking table for the inventory-stock module"


async def up(db):
    """Create the inventory_stock_items table."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS inventory_stock_items (
            id                 TEXT PRIMARY KEY,
            inventory_id       TEXT NOT NULL,
            quantity           REAL NOT NULL DEFAULT 0,
            unit               TEXT NOT NULL DEFAULT '',
            location           TEXT NOT NULL DEFAULT '',
            reorder_threshold  REAL NOT NULL DEFAULT 0,
            notes              TEXT NOT NULL DEFAULT '',
            updated_at         TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_stock_inventory_id
        ON inventory_stock_items (inventory_id)
    """)


async def down(db):
    """Drop stock tables."""
    await db.execute("DROP TABLE IF EXISTS inventory_stock_items")
