"""Migration 001 — Create suppliers_vendors and suppliers_catalog_links tables."""

id = "001_create_supplier_tables"
description = "Create vendor and catalogue link tables for the suppliers module"


async def up(db):
    """Create suppliers tables."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS suppliers_vendors (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            url         TEXT NOT NULL DEFAULT '',
            contact     TEXT NOT NULL DEFAULT '',
            notes       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS suppliers_catalog_links (
            id              TEXT PRIMARY KEY,
            vendor_id       TEXT NOT NULL REFERENCES suppliers_vendors(id),
            catalogue_path  TEXT NOT NULL,
            product_url     TEXT NOT NULL DEFAULT '',
            notes           TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_suppliers_links_vendor_id
        ON suppliers_catalog_links (vendor_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_suppliers_links_catalogue_path
        ON suppliers_catalog_links (catalogue_path)
    """)


async def down(db):
    """Drop supplier tables."""
    await db.execute("DROP TABLE IF EXISTS suppliers_catalog_links")
    await db.execute("DROP TABLE IF EXISTS suppliers_vendors")
