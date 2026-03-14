"""Migration 001 — Create all kitchen_ UserDB tables."""

id = "001_create_tables"
description = "Create all kitchen module tables: recipes, ingredients, nutrition, meal plan, cook log, locations, aliases, stock metadata"


async def up(db) -> None:
    """Create all kitchen_ tables."""

    # Locations — must exist before stock metadata and other FK references
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_locations (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            location_key TEXT NOT NULL UNIQUE,
            icon         TEXT NOT NULL DEFAULT '',
            sort_order   INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Recipes — link catalogue workflows to kitchen metadata
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_recipes (
            id             TEXT PRIMARY KEY,
            title          TEXT NOT NULL,
            description    TEXT NOT NULL DEFAULT '',
            workflow_id    TEXT,
            cuisine_tag    TEXT NOT NULL DEFAULT '',
            cook_time_mins INTEGER,
            servings       INTEGER NOT NULL DEFAULT 1,
            notes          TEXT NOT NULL DEFAULT '',
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_kitchen_recipes_cuisine
        ON kitchen_recipes (cuisine_tag)
    """)

    # Recipe ingredients — per-recipe ingredient entries with quantities
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_recipe_ingredients (
            id            TEXT PRIMARY KEY,
            recipe_id     TEXT NOT NULL REFERENCES kitchen_recipes(id) ON DELETE CASCADE,
            catalogue_path TEXT NOT NULL,
            name          TEXT NOT NULL,
            quantity      REAL NOT NULL,
            unit          TEXT NOT NULL DEFAULT '',
            notes         TEXT NOT NULL DEFAULT ''
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_kitchen_recipe_ingredients_recipe
        ON kitchen_recipe_ingredients (recipe_id)
    """)

    # Recipe nutrition — per-serving totals for a recipe
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_recipe_nutrition (
            id          TEXT PRIMARY KEY,
            recipe_id   TEXT NOT NULL UNIQUE REFERENCES kitchen_recipes(id) ON DELETE CASCADE,
            calories    REAL,
            protein_g   REAL,
            fat_g       REAL,
            carbs_g     REAL,
            fiber_g     REAL,
            sugar_g     REAL,
            sodium_mg   REAL,
            per_servings INTEGER NOT NULL DEFAULT 1,
            updated_at  TEXT NOT NULL
        )
    """)

    # Ingredient nutrition — per-100g values for catalogue materials
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_ingredient_nutrition (
            id                 TEXT PRIMARY KEY,
            catalogue_path     TEXT NOT NULL UNIQUE,
            calories_per_100g  REAL,
            protein_g          REAL,
            fat_g              REAL,
            carbs_g            REAL,
            fiber_g            REAL,
            sugar_g            REAL,
            sodium_mg          REAL,
            updated_at         TEXT NOT NULL
        )
    """)

    # Meal plan — one record per week (keyed by Monday ISO date)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_meal_plan (
            id         TEXT PRIMARY KEY,
            week_start TEXT NOT NULL UNIQUE,
            notes      TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Meal plan entries — individual slots within a weekly plan
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_meal_plan_entries (
            id           TEXT PRIMARY KEY,
            plan_id      TEXT NOT NULL REFERENCES kitchen_meal_plan(id) ON DELETE CASCADE,
            day_of_week  INTEGER NOT NULL,
            meal_slot    TEXT NOT NULL,
            recipe_id    TEXT REFERENCES kitchen_recipes(id) ON DELETE SET NULL,
            servings     INTEGER NOT NULL DEFAULT 1,
            notes        TEXT NOT NULL DEFAULT '',
            UNIQUE(plan_id, day_of_week, meal_slot)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_kitchen_meal_plan_entries_plan
        ON kitchen_meal_plan_entries (plan_id)
    """)

    # Cook log — cooking session records
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_cook_log (
            id             TEXT PRIMARY KEY,
            recipe_id      TEXT NOT NULL REFERENCES kitchen_recipes(id),
            cooked_at      TEXT NOT NULL,
            servings       INTEGER NOT NULL DEFAULT 1,
            rating         INTEGER,
            notes          TEXT NOT NULL DEFAULT '',
            stock_deducted INTEGER NOT NULL DEFAULT 0
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_kitchen_cook_log_recipe
        ON kitchen_cook_log (recipe_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_kitchen_cook_log_cooked_at
        ON kitchen_cook_log (cooked_at)
    """)

    # Stock aliases — receipt text → catalogue path mappings
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_stock_aliases (
            id             TEXT PRIMARY KEY,
            receipt_text   TEXT NOT NULL UNIQUE,
            catalogue_path TEXT NOT NULL,
            created_at     TEXT NOT NULL
        )
    """)

    # Stock metadata — extends inventory_stock_items with kitchen-specific fields
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kitchen_stock_metadata (
            id             TEXT PRIMARY KEY,
            stock_item_id  TEXT NOT NULL UNIQUE,
            expiry_date    TEXT,
            frozen_on_date TEXT,
            updated_at     TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_kitchen_stock_metadata_expiry
        ON kitchen_stock_metadata (expiry_date)
    """)


async def down(db) -> None:
    """Drop all kitchen_ tables in reverse dependency order."""
    await db.execute("DROP TABLE IF EXISTS kitchen_stock_metadata")
    await db.execute("DROP TABLE IF EXISTS kitchen_stock_aliases")
    await db.execute("DROP TABLE IF EXISTS kitchen_cook_log")
    await db.execute("DROP TABLE IF EXISTS kitchen_meal_plan_entries")
    await db.execute("DROP TABLE IF EXISTS kitchen_meal_plan")
    await db.execute("DROP TABLE IF EXISTS kitchen_ingredient_nutrition")
    await db.execute("DROP TABLE IF EXISTS kitchen_recipe_nutrition")
    await db.execute("DROP TABLE IF EXISTS kitchen_recipe_ingredients")
    await db.execute("DROP TABLE IF EXISTS kitchen_recipes")
    await db.execute("DROP TABLE IF EXISTS kitchen_locations")
