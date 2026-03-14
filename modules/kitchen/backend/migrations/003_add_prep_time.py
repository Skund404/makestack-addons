"""Migration 003 — Add prep_time_mins to kitchen_recipes, source to kitchen_ingredient_nutrition."""

id = "003_add_prep_time"
description = "Add prep_time_mins column to kitchen_recipes and source column to kitchen_ingredient_nutrition"


async def up(db) -> None:
    await db.execute(
        "ALTER TABLE kitchen_recipes ADD COLUMN prep_time_mins INTEGER"
    )
    await db.execute(
        "ALTER TABLE kitchen_ingredient_nutrition ADD COLUMN source TEXT"
    )


async def down(db) -> None:
    # DROP COLUMN requires SQLite >= 3.35.0
    await db.execute(
        "ALTER TABLE kitchen_recipes DROP COLUMN prep_time_mins"
    )
    await db.execute(
        "ALTER TABLE kitchen_ingredient_nutrition DROP COLUMN source"
    )
