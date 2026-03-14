"""Migration 004 — Add serves_made/material_pulls_json to cook_log; free_text/serves_override to meal_plan_entries."""

id = "004_add_cook_log_fields"
description = (
    "Rename cook_log.servings → serves_made, add material_pulls_json; "
    "add free_text and serves_override to meal_plan_entries"
)


async def up(db) -> None:
    await db.execute(
        "ALTER TABLE kitchen_cook_log RENAME COLUMN servings TO serves_made"
    )
    await db.execute(
        "ALTER TABLE kitchen_cook_log ADD COLUMN material_pulls_json TEXT"
    )
    await db.execute(
        "ALTER TABLE kitchen_meal_plan_entries ADD COLUMN free_text TEXT NOT NULL DEFAULT ''"
    )
    await db.execute(
        "ALTER TABLE kitchen_meal_plan_entries ADD COLUMN serves_override INTEGER"
    )


async def down(db) -> None:
    await db.execute(
        "ALTER TABLE kitchen_cook_log RENAME COLUMN serves_made TO servings"
    )
    await db.execute(
        "ALTER TABLE kitchen_cook_log DROP COLUMN material_pulls_json"
    )
    await db.execute(
        "ALTER TABLE kitchen_meal_plan_entries DROP COLUMN free_text"
    )
    await db.execute(
        "ALTER TABLE kitchen_meal_plan_entries DROP COLUMN serves_override"
    )
