"""Tests for kitchen module migrations.

Verifies that:
  - 001_create_tables up() creates all kitchen_ tables
  - 002_seed_locations up() inserts the four default locations
  - 002_seed_locations down() removes the seed rows
  - 001_create_tables down() drops all kitchen_ tables cleanly
"""

from __future__ import annotations

import importlib.util
import os

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB

# ---------------------------------------------------------------------------
# Load migration modules by path (filenames start with digits — can't import
# them directly with the normal import machinery).
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "backend", "migrations"
)


def _load_migration(filename: str):
    path = os.path.join(_MIGRATIONS_DIR, filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


migration_001 = _load_migration("001_create_tables.py")
migration_002 = _load_migration("002_seed_locations.py")

# All kitchen_ table names created by 001
_KITCHEN_TABLES = [
    "kitchen_locations",
    "kitchen_recipes",
    "kitchen_recipe_ingredients",
    "kitchen_recipe_nutrition",
    "kitchen_ingredient_nutrition",
    "kitchen_meal_plan",
    "kitchen_meal_plan_entries",
    "kitchen_cook_log",
    "kitchen_stock_aliases",
    "kitchen_stock_metadata",
]

_SEED_LOCATION_KEYS = ["pantry", "fridge", "freezer", "other"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    """In-memory UserDB with Shell migrations applied (no kitchen tables yet)."""
    userdb = MockUserDB()
    await userdb.setup()
    yield userdb
    await userdb.teardown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _table_exists(db: MockUserDB, table: str) -> bool:
    row = await db.fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table]
    )
    return row is not None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_001_up_creates_all_tables(db):
    """up() creates every kitchen_ table."""
    await migration_001.up(db)

    for table in _KITCHEN_TABLES:
        assert await _table_exists(db, table), f"Table '{table}' was not created"


@pytest.mark.asyncio
async def test_001_up_is_idempotent(db):
    """Running up() twice does not raise (CREATE TABLE IF NOT EXISTS)."""
    await migration_001.up(db)
    await migration_001.up(db)  # should not raise


@pytest.mark.asyncio
async def test_002_up_seeds_locations(db):
    """up() on 002 inserts four default location rows."""
    await migration_001.up(db)
    await migration_002.up(db)

    rows = await db.fetch_all(
        "SELECT location_key FROM kitchen_locations ORDER BY sort_order"
    )
    keys = [r["location_key"] for r in rows]
    assert keys == _SEED_LOCATION_KEYS


@pytest.mark.asyncio
async def test_002_up_location_fields(db):
    """Seed rows contain correct name, icon, and sort_order values."""
    await migration_001.up(db)
    await migration_002.up(db)

    expected = {
        "pantry":  ("Pantry",  "Archive",     0),
        "fridge":  ("Fridge",  "Thermometer", 1),
        "freezer": ("Freezer", "Snowflake",   2),
        "other":   ("Other",   "Box",         3),
    }

    rows = await db.fetch_all("SELECT * FROM kitchen_locations")
    assert len(rows) == 4
    for row in rows:
        name, icon, order = expected[row["location_key"]]
        assert row["name"] == name
        assert row["icon"] == icon
        assert row["sort_order"] == order
        assert row["id"]  # UUID — just check non-empty


@pytest.mark.asyncio
async def test_002_down_removes_seed_rows(db):
    """down() on 002 deletes only the four seed rows."""
    await migration_001.up(db)
    await migration_002.up(db)
    await migration_002.down(db)

    rows = await db.fetch_all("SELECT * FROM kitchen_locations")
    assert rows == []


@pytest.mark.asyncio
async def test_001_down_drops_all_tables(db):
    """down() drops every kitchen_ table."""
    await migration_001.up(db)
    await migration_002.up(db)
    await migration_002.down(db)
    await migration_001.down(db)

    for table in _KITCHEN_TABLES:
        assert not await _table_exists(db, table), f"Table '{table}' was not dropped"


@pytest.mark.asyncio
async def test_001_down_is_idempotent(db):
    """down() can be called on a fresh DB without raising."""
    await migration_001.down(db)  # nothing to drop — should not raise
