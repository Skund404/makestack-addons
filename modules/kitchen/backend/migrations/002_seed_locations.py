"""Migration 002 — Seed default kitchen locations."""

import uuid

id = "002_seed_locations"
description = "Insert the four default kitchen locations: pantry, fridge, freezer, other"

_LOCATIONS = [
    ("pantry",  "Pantry",  "Archive",     0),
    ("fridge",  "Fridge",  "Thermometer", 1),
    ("freezer", "Freezer", "Snowflake",   2),
    ("other",   "Other",   "Box",         3),
]


async def up(db) -> None:
    """Insert the four default kitchen locations (idempotent — skips existing rows)."""
    for location_key, name, icon, sort_order in _LOCATIONS:
        await db.execute(
            """
            INSERT OR IGNORE INTO kitchen_locations (id, name, location_key, icon, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            [str(uuid.uuid4()), name, location_key, icon, sort_order],
        )


async def down(db) -> None:
    """Remove the four default kitchen locations by location_key."""
    for location_key, _, _, _ in _LOCATIONS:
        await db.execute(
            "DELETE FROM kitchen_locations WHERE location_key = ?",
            [location_key],
        )
