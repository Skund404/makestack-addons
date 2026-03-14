"""Migration 004 — Add serves_made/material_pulls_json to cook_log; free_text/serves_override to meal_plan_entries."""

id = "004_add_cook_log_fields"
description = (
    "Rename cook_log.servings → serves_made, add material_pulls_json; "
    "add free_text and serves_override to meal_plan_entries"
)


async def _add_column(db, sql: str) -> None:
    """Execute ALTER TABLE ADD COLUMN, ignoring 'duplicate column' if already present."""
    try:
        await db.execute(sql)
    except Exception as exc:
        if "duplicate column" not in str(exc).lower():
            raise


async def _rename_column(db, sql: str) -> None:
    """Execute ALTER TABLE RENAME COLUMN, ignoring 'no such column' if already renamed."""
    try:
        await db.execute(sql)
    except Exception as exc:
        msg = str(exc).lower()
        if "no such column" not in msg and "no column named" not in msg:
            raise


async def up(db) -> None:
    await _rename_column(db, "ALTER TABLE kitchen_cook_log RENAME COLUMN servings TO serves_made")
    await _add_column(db, "ALTER TABLE kitchen_cook_log ADD COLUMN material_pulls_json TEXT")
    await _add_column(db, "ALTER TABLE kitchen_meal_plan_entries ADD COLUMN free_text TEXT NOT NULL DEFAULT ''")
    await _add_column(db, "ALTER TABLE kitchen_meal_plan_entries ADD COLUMN serves_override INTEGER")


async def down(db) -> None:
    await _rename_column(db, "ALTER TABLE kitchen_cook_log RENAME COLUMN serves_made TO servings")
    await db.execute("ALTER TABLE kitchen_cook_log DROP COLUMN material_pulls_json")
    await db.execute("ALTER TABLE kitchen_meal_plan_entries DROP COLUMN free_text")
    await db.execute("ALTER TABLE kitchen_meal_plan_entries DROP COLUMN serves_override")
