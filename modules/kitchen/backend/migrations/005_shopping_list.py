"""Migration 005 — Create kitchen_shopping_list table."""

id = "005_shopping_list"
description = "Create persistent shopping list table for manual and recipe-derived items"


async def up(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_shopping_list (
            id               TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            catalogue_path   TEXT,
            quantity         REAL NOT NULL DEFAULT 1,
            unit             TEXT NOT NULL DEFAULT '',
            source           TEXT NOT NULL DEFAULT 'manual',
            source_recipe_id TEXT REFERENCES kitchen_recipes(id) ON DELETE SET NULL,
            checked          INTEGER NOT NULL DEFAULT 0,
            note             TEXT NOT NULL DEFAULT '',
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_kitchen_shopping_list_checked
        ON kitchen_shopping_list (checked)
    """)


async def down(db) -> None:
    await db.execute("DROP TABLE IF EXISTS kitchen_shopping_list")
