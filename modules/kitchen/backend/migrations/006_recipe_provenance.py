"""Migration 006 — Add forked_from_recipe_id to kitchen_recipes."""

id = "006_recipe_provenance"
description = "Track which recipe a fork was created from (provenance chain)"


async def up(db) -> None:
    await db.execute(
        "ALTER TABLE kitchen_recipes ADD COLUMN forked_from_recipe_id TEXT"
    )


async def down(db) -> None:
    # SQLite <3.35 has no DROP COLUMN — recreate table without the column.
    await db.execute("""
        CREATE TABLE kitchen_recipes_bak AS
        SELECT id, title, description, workflow_id, cuisine_tag,
               prep_time_mins, cook_time_mins, servings, notes,
               created_at, updated_at
        FROM kitchen_recipes
    """)
    await db.execute("DROP TABLE kitchen_recipes")
    await db.execute("ALTER TABLE kitchen_recipes_bak RENAME TO kitchen_recipes")
