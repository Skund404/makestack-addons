"""K8 test suite — shopping list, stock add, meal plan recipe title join.

Covers:
  - Migration 005 up/down
  - Shopping CRUD: list, add, update checked, delete, clear checked
  - Add from recipe: dedup, missing-only
  - Shopping badge count
  - Stock add endpoint
  - Recipe title join in meal plan entries
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from makestack_sdk.testing import MockUserDB, create_test_app

# ---------------------------------------------------------------------------
# Load kitchen modules
# ---------------------------------------------------------------------------

_KITCHEN_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _load_kitchen(name: str, relpath: str):
    key = f"_kitchen_k8_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_KITCHEN_ROOT, relpath)
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


migration_001 = _load_kitchen("mig001k8", "backend/migrations/001_create_tables.py")
migration_002 = _load_kitchen("mig002k8", "backend/migrations/002_seed_locations.py")
migration_003 = _load_kitchen("mig003k8", "backend/migrations/003_add_prep_time.py")
migration_004 = _load_kitchen("mig004k8", "backend/migrations/004_add_cook_log_fields.py")
migration_005 = _load_kitchen("mig005k8", "backend/migrations/005_shopping_list.py")
migration_006 = _load_kitchen("mig006k8", "backend/migrations/006_recipe_provenance.py")
routes_mod    = _load_kitchen("routesk8",  "backend/routes.py")

router = routes_mod.router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

async def _apply_migrations(userdb: MockUserDB) -> None:
    await migration_001.up(userdb)
    await migration_002.up(userdb)
    await migration_003.up(userdb)
    await migration_004.up(userdb)
    await migration_005.up(userdb)
    await migration_006.up(userdb)
    # Create shell tables that kitchen reads
    await userdb.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id              TEXT PRIMARY KEY,
            catalogue_path  TEXT NOT NULL,
            catalogue_hash  TEXT NOT NULL DEFAULT '',
            primitive_type  TEXT NOT NULL DEFAULT 'material',
            added_at        TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)
    await userdb.execute("""
        CREATE TABLE IF NOT EXISTS inventory_stock_items (
            id                TEXT PRIMARY KEY,
            inventory_id      TEXT NOT NULL,
            quantity          REAL NOT NULL DEFAULT 0,
            unit              TEXT NOT NULL DEFAULT '',
            location          TEXT NOT NULL DEFAULT '',
            reorder_threshold REAL NOT NULL DEFAULT 0,
            notes             TEXT NOT NULL DEFAULT '',
            updated_at        TEXT NOT NULL
        )
    """)


@pytest_asyncio.fixture
async def db():
    userdb = MockUserDB()
    await userdb.setup()
    await _apply_migrations(userdb)
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_inventory(db: MockUserDB, catalogue_path: str) -> str:
    inv_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory (id, catalogue_path, catalogue_hash, primitive_type, added_at, updated_at) "
        "VALUES (?, ?, 'abc', 'material', '2026-01-01', '2026-01-01')",
        [inv_id, catalogue_path],
    )
    return inv_id


async def _seed_stock(db: MockUserDB, catalogue_path: str, quantity: float, unit: str, location: str = "pantry") -> tuple[str, str]:
    inv_id = await _seed_inventory(db, catalogue_path)
    stock_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory_stock_items (id, inventory_id, quantity, unit, location, updated_at) "
        "VALUES (?, ?, ?, ?, ?, '2026-01-01')",
        [stock_id, inv_id, quantity, unit, location],
    )
    return inv_id, stock_id


async def _create_recipe(client, title: str = "Soup", servings: int = 2, ingredients=None) -> str:
    body = {
        "title": title,
        "servings": servings,
        "ingredients": ingredients or [],
    }
    resp = await client.post("/recipes", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ===========================================================================
# Migration 005
# ===========================================================================


@pytest.mark.asyncio
async def test_migration_005_up_creates_shopping_list():
    """005 up() creates kitchen_shopping_list table."""
    db = MockUserDB()
    await db.setup()
    try:
        await migration_001.up(db)
        await migration_005.up(db)
        row = await db.fetch_one(
            "SELECT COUNT(*) AS n FROM kitchen_shopping_list"
        )
        assert row["n"] == 0
    finally:
        await db.teardown()


@pytest.mark.asyncio
async def test_migration_005_down_drops_table():
    """005 down() drops kitchen_shopping_list."""
    db = MockUserDB()
    await db.setup()
    try:
        await migration_001.up(db)
        await migration_005.up(db)
        await migration_005.down(db)
        with pytest.raises(Exception):
            await db.fetch_one("SELECT COUNT(*) AS n FROM kitchen_shopping_list")
    finally:
        await db.teardown()


# ===========================================================================
# Shopping list — CRUD
# ===========================================================================


@pytest.mark.asyncio
async def test_shopping_list_empty(client):
    """GET /shopping returns empty list initially."""
    resp = await client.get("/shopping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["to_buy"] == 0


@pytest.mark.asyncio
async def test_add_shopping_item(client):
    """POST /shopping creates an item."""
    resp = await client.post("/shopping", json={
        "name": "Milk", "quantity": 2, "unit": "L",
    })
    assert resp.status_code == 201
    item = resp.json()
    assert item["name"] == "Milk"
    assert item["quantity"] == 2
    assert item["unit"] == "L"
    assert item["checked"] == 0
    assert item["source"] == "manual"


@pytest.mark.asyncio
async def test_shopping_list_returns_items(client):
    """Adding items and listing them."""
    await client.post("/shopping", json={"name": "Eggs"})
    await client.post("/shopping", json={"name": "Bread"})
    resp = await client.get("/shopping")
    data = resp.json()
    assert data["total"] == 2
    assert data["to_buy"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_shopping_tab_buy(client):
    """GET /shopping?tab=buy returns only unchecked items."""
    r1 = await client.post("/shopping", json={"name": "Eggs"})
    await client.post("/shopping", json={"name": "Bread"})
    # Check off eggs
    item_id = r1.json()["id"]
    await client.put(f"/shopping/{item_id}", json={"checked": True})

    resp = await client.get("/shopping", params={"tab": "buy"})
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Bread"


@pytest.mark.asyncio
async def test_update_shopping_item_checked(client):
    """PUT /shopping/{id} toggles checked state."""
    r = await client.post("/shopping", json={"name": "Milk"})
    item_id = r.json()["id"]

    resp = await client.put(f"/shopping/{item_id}", json={"checked": True})
    assert resp.status_code == 200
    assert resp.json()["checked"] == 1

    resp = await client.put(f"/shopping/{item_id}", json={"checked": False})
    assert resp.json()["checked"] == 0


@pytest.mark.asyncio
async def test_update_shopping_item_quantity(client):
    """PUT /shopping/{id} updates quantity."""
    r = await client.post("/shopping", json={"name": "Flour", "quantity": 1})
    item_id = r.json()["id"]

    resp = await client.put(f"/shopping/{item_id}", json={"quantity": 3})
    assert resp.json()["quantity"] == 3


@pytest.mark.asyncio
async def test_update_shopping_item_note(client):
    """PUT /shopping/{id} updates note."""
    r = await client.post("/shopping", json={"name": "Butter"})
    item_id = r.json()["id"]

    resp = await client.put(f"/shopping/{item_id}", json={"note": "unsalted"})
    assert resp.json()["note"] == "unsalted"


@pytest.mark.asyncio
async def test_update_shopping_item_404(client):
    """PUT /shopping/{id} returns 404 for missing item."""
    resp = await client.put("/shopping/nonexistent", json={"checked": True})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_shopping_item(client):
    """DELETE /shopping/{id} removes the item."""
    r = await client.post("/shopping", json={"name": "Sugar"})
    item_id = r.json()["id"]

    resp = await client.delete(f"/shopping/{item_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = await client.get("/shopping")
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_shopping_item_404(client):
    """DELETE /shopping/{id} returns 404 for missing item."""
    resp = await client.delete("/shopping/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_clear_checked_shopping(client):
    """POST /shopping/clear-checked removes only checked items."""
    r1 = await client.post("/shopping", json={"name": "Milk"})
    await client.post("/shopping", json={"name": "Bread"})
    await client.put(f"/shopping/{r1.json()['id']}", json={"checked": True})

    resp = await client.post("/shopping/clear-checked")
    assert resp.json()["deleted"] == 1

    resp = await client.get("/shopping")
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["name"] == "Bread"


@pytest.mark.asyncio
async def test_clear_checked_shopping_none(client):
    """POST /shopping/clear-checked with nothing checked returns 0."""
    await client.post("/shopping", json={"name": "Milk"})
    resp = await client.post("/shopping/clear-checked")
    assert resp.json()["deleted"] == 0


# ===========================================================================
# Shopping badge
# ===========================================================================


@pytest.mark.asyncio
async def test_shopping_badge_empty(client):
    """GET /shopping/badge returns 0 with no items."""
    resp = await client.get("/shopping/badge")
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_shopping_badge_counts_unchecked(client):
    """GET /shopping/badge counts unchecked items."""
    r1 = await client.post("/shopping", json={"name": "A"})
    await client.post("/shopping", json={"name": "B"})
    await client.post("/shopping", json={"name": "C"})
    await client.put(f"/shopping/{r1.json()['id']}", json={"checked": True})

    resp = await client.get("/shopping/badge")
    assert resp.json()["count"] == 2


# ===========================================================================
# Add from recipe
# ===========================================================================


@pytest.mark.asyncio
async def test_add_from_recipe_missing_only(client, db):
    """POST /shopping/from-recipe/{id} adds only missing ingredients."""
    # Stock: flour is in stock, eggs is not
    await _seed_stock(db, "materials/flour/manifest.json", 500, "g")
    await _seed_inventory(db, "materials/eggs/manifest.json")

    recipe_id = await _create_recipe(client, "Cake", 4, [
        {"catalogue_path": "materials/flour/manifest.json", "name": "Flour", "quantity": 200, "unit": "g"},
        {"catalogue_path": "materials/eggs/manifest.json", "name": "Eggs", "quantity": 3, "unit": "piece"},
    ])

    resp = await client.post(f"/shopping/from-recipe/{recipe_id}")
    assert resp.status_code == 200
    assert resp.json()["added"] == 1  # only eggs (missing)

    resp = await client.get("/shopping")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Eggs"
    assert items[0]["source"] == "recipe"


@pytest.mark.asyncio
async def test_add_from_recipe_dedup(client, db):
    """POST /shopping/from-recipe/{id} deduplicates against existing items."""
    await _seed_inventory(db, "materials/eggs/manifest.json")

    recipe_id = await _create_recipe(client, "Omelette", 2, [
        {"catalogue_path": "materials/eggs/manifest.json", "name": "Eggs", "quantity": 4, "unit": "piece"},
    ])

    # First add
    resp = await client.post(f"/shopping/from-recipe/{recipe_id}")
    assert resp.json()["added"] == 1

    # Second add — should dedup
    resp = await client.post(f"/shopping/from-recipe/{recipe_id}")
    assert resp.json()["added"] == 0

    resp = await client.get("/shopping")
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_add_from_recipe_404(client):
    """POST /shopping/from-recipe/{id} returns 404 for missing recipe."""
    resp = await client.post("/shopping/from-recipe/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_from_recipe_all_in_stock(client, db):
    """POST /shopping/from-recipe/{id} adds nothing when all in stock."""
    await _seed_stock(db, "materials/flour/manifest.json", 500, "g")

    recipe_id = await _create_recipe(client, "Simple", 1, [
        {"catalogue_path": "materials/flour/manifest.json", "name": "Flour", "quantity": 100, "unit": "g"},
    ])

    resp = await client.post(f"/shopping/from-recipe/{recipe_id}")
    assert resp.json()["added"] == 0


# ===========================================================================
# Stock add endpoint
# ===========================================================================


@pytest.mark.asyncio
async def test_stock_add_no_peer(client, db):
    """POST /stock/add without inventory-stock peer returns 503."""
    # The test app doesn't have peers installed by default
    resp = await client.post("/stock/add", json={
        "catalogue_path": "materials/flour/manifest.json",
        "quantity": 500, "unit": "g", "location": "pantry",
    })
    assert resp.status_code == 503


# ===========================================================================
# Meal plan — recipe title join
# ===========================================================================


@pytest.mark.asyncio
async def test_meal_plan_entry_has_recipe_title(client, db):
    """Meal plan entries include recipe_title from the join."""
    recipe_id = await _create_recipe(client, "Pasta Carbonara", 2)

    week = "2026-03-16"
    resp = await client.put(f"/meal-plan/{week}/entry", json={
        "day_of_week": 0, "meal_slot": "dinner",
        "recipe_id": recipe_id, "servings": 2,
    })
    assert resp.status_code == 200

    resp = await client.get(f"/meal-plan/{week}")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["recipe_title"] == "Pasta Carbonara"


@pytest.mark.asyncio
async def test_meal_plan_entry_free_text_no_recipe_title(client):
    """Free text entries have recipe_title = None."""
    week = "2026-03-16"
    resp = await client.put(f"/meal-plan/{week}/entry", json={
        "day_of_week": 1, "meal_slot": "lunch",
        "free_text": "Leftovers", "servings": 1,
    })
    assert resp.status_code == 200

    resp = await client.get(f"/meal-plan/{week}")
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["recipe_title"] is None
    assert entries[0]["free_text"] == "Leftovers"


# ===========================================================================
# Shopping list — item with catalogue_path
# ===========================================================================


@pytest.mark.asyncio
async def test_add_shopping_item_with_catalogue_path(client):
    """POST /shopping with catalogue_path stores it."""
    resp = await client.post("/shopping", json={
        "name": "Flour",
        "catalogue_path": "materials/flour/manifest.json",
        "quantity": 500, "unit": "g",
    })
    assert resp.status_code == 201
    item = resp.json()
    assert item["catalogue_path"] == "materials/flour/manifest.json"


@pytest.mark.asyncio
async def test_add_shopping_item_without_catalogue_path(client):
    """POST /shopping without catalogue_path stores null."""
    resp = await client.post("/shopping", json={"name": "Mystery item"})
    assert resp.status_code == 201
    assert resp.json()["catalogue_path"] is None
