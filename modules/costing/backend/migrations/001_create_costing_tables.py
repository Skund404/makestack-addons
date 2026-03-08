"""Migration 001 — Create costing_prices table."""

id = "001_create_costing_tables"
description = "Create purchase price tracking table for the costing module"


async def up(db):
    """Create the costing_prices table."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS costing_prices (
            id              TEXT PRIMARY KEY,
            catalogue_path  TEXT NOT NULL,
            amount          REAL NOT NULL,
            currency        TEXT NOT NULL DEFAULT 'GBP',
            unit            TEXT NOT NULL DEFAULT '',
            supplier_name   TEXT NOT NULL DEFAULT '',
            purchased_at    TEXT NOT NULL DEFAULT '',
            notes           TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_costing_prices_catalogue_path
        ON costing_prices (catalogue_path)
    """)


async def down(db):
    """Drop costing tables."""
    await db.execute("DROP TABLE IF EXISTS costing_prices")
