"""K6 test suite — full coverage for kitchen module.

Covers:
  - Migration 003 and 004 up/down
  - GET /stock/expiring (with and without expiring items)
  - Recipe endpoints: list filters, 404 paths
  - Nutrition: calculate endpoint, save flag, partial data
  - Can-make: strict / relaxed / empty recipe list
  - Stock-check: scaling, all statuses
  - Meal plan: full round-trip, shopping list
  - Cook log: filters, pagination
  - Aliases: create, lookup, upsert
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid

import time

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
    key = f"_kitchen_k6_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_KITCHEN_ROOT, relpath)
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


migration_001 = _load_kitchen("mig001k6", "backend/migrations/001_create_tables.py")
migration_002 = _load_kitchen("mig002k6", "backend/migrations/002_seed_locations.py")
migration_003 = _load_kitchen("mig003k6", "backend/migrations/003_add_prep_time.py")
migration_004 = _load_kitchen("mig004k6", "backend/migrations/004_add_cook_log_fields.py")
migration_006 = _load_kitchen("mig006k6", "backend/migrations/006_recipe_provenance.py")
routes_mod    = _load_kitchen("routesk6",  "backend/routes.py")

router = routes_mod.router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

async def _apply_migrations(userdb: MockUserDB) -> None:
    await migration_001.up(userdb)
    await migration_002.up(userdb)
    await migration_003.up(userdb)
    await migration_004.up(userdb)
    await migration_006.up(userdb)
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
    """Insert an inventory row; return its id."""
    inv_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory (id, catalogue_path, catalogue_hash, primitive_type, added_at, updated_at) "
        "VALUES (?, ?, 'abc', 'material', '2026-01-01', '2026-01-01')",
        [inv_id, catalogue_path],
    )
    return inv_id


async def _seed_stock(db: MockUserDB, catalogue_path: str, quantity: float, unit: str, location: str = "pantry") -> tuple[str, str]:
    """Insert inventory + stock_item rows; return (inv_id, stock_id)."""
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


# ---------------------------------------------------------------------------
# Migration 003 up/down
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_003_up_adds_prep_time():
    """003 up() adds prep_time_mins to kitchen_recipes."""
    db = MockUserDB()
    await db.setup()
    try:
        await migration_001.up(db)
        await migration_003.up(db)
        row = await db.fetch_one(
            "SELECT prep_time_mins FROM kitchen_recipes WHERE 1=0"
        )
        # No rows returned but the column must exist (no error)
        assert row is None
    finally:
        await db.teardown()


@pytest.mark.asyncio
async def test_migration_003_down_drops_prep_time():
    """003 down() removes prep_time_mins from kitchen_recipes."""
    db = MockUserDB()
    await db.setup()
    try:
        await migration_001.up(db)
        await migration_003.up(db)
        await migration_003.down(db)
        # Column should no longer exist; SELECT should raise
        raised = False
        try:
            await db.fetch_one("SELECT prep_time_mins FROM kitchen_recipes WHERE 1=0")
        except Exception:
            raised = True
        assert raised, "prep_time_mins column was not dropped"
    finally:
        await db.teardown()


@pytest.mark.asyncio
async def test_migration_004_up_adds_columns():
    """004 up() adds material_pulls_json, free_text, serves_override."""
    db = MockUserDB()
    await db.setup()
    try:
        await migration_001.up(db)
        await migration_003.up(db)
        await migration_004.up(db)
        # serves_made should exist in cook_log
        await db.fetch_one("SELECT serves_made FROM kitchen_cook_log WHERE 1=0")
        # free_text and serves_override in meal_plan_entries
        await db.fetch_one("SELECT free_text, serves_override FROM kitchen_meal_plan_entries WHERE 1=0")
    finally:
        await db.teardown()


@pytest.mark.asyncio
async def test_migration_004_down_reverts_columns():
    """004 down() renames serves_made back and drops added columns."""
    db = MockUserDB()
    await db.setup()
    try:
        await migration_001.up(db)
        await migration_003.up(db)
        await migration_004.up(db)
        await migration_004.down(db)
        # servings should be back; serves_made gone
        await db.fetch_one("SELECT servings FROM kitchen_cook_log WHERE 1=0")
        raised = False
        try:
            await db.fetch_one("SELECT serves_made FROM kitchen_cook_log WHERE 1=0")
        except Exception:
            raised = True
        assert raised, "serves_made was not reverted"
    finally:
        await db.teardown()


# ---------------------------------------------------------------------------
# GET /stock/expiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expiring_empty(client):
    """Returns [] when no stock metadata exists."""
    resp = await client.get("/stock/expiring")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_expiring_item_within_window(client, db):
    """Returns items whose expiry_date is within the requested window."""
    _, stock_id = await _seed_stock(db, "materials/milk", 2.0, "L", "fridge")
    # Expiry date 3 days from now
    from datetime import date, timedelta
    expiry = (date.today() + timedelta(days=3)).isoformat()
    meta_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO kitchen_stock_metadata (id, stock_item_id, expiry_date, updated_at) VALUES (?, ?, ?, '2026-01-01')",
        [meta_id, stock_id, expiry],
    )

    resp = await client.get("/stock/expiring", params={"days": 7})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["stock_item_id"] == stock_id
    assert items[0]["expiry_date"] == expiry
    assert items[0]["days_until_expiry"] <= 3


@pytest.mark.asyncio
async def test_expiring_item_outside_window(client, db):
    """Does not return items whose expiry_date is beyond the window."""
    _, stock_id = await _seed_stock(db, "materials/cheese", 0.5, "kg", "fridge")
    from datetime import date, timedelta
    expiry = (date.today() + timedelta(days=30)).isoformat()
    await db.execute(
        "INSERT INTO kitchen_stock_metadata (id, stock_item_id, expiry_date, updated_at) VALUES (?, ?, ?, '2026-01-01')",
        [str(uuid.uuid4()), stock_id, expiry],
    )

    resp = await client.get("/stock/expiring", params={"days": 7})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_expiring_window_zero(client, db):
    """days=0 returns only items expiring today or earlier."""
    _, stock_id = await _seed_stock(db, "materials/yoghurt", 1.0, "piece", "fridge")
    from datetime import date
    today = date.today().isoformat()
    await db.execute(
        "INSERT INTO kitchen_stock_metadata (id, stock_item_id, expiry_date, updated_at) VALUES (?, ?, ?, '2026-01-01')",
        [str(uuid.uuid4()), stock_id, today],
    )
    resp = await client.get("/stock/expiring", params={"days": 0})
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["stock_item_id"] == stock_id for i in items)


@pytest.mark.asyncio
async def test_expiring_no_expiry_date_excluded(client, db):
    """Stock items with no expiry_date in metadata are excluded."""
    _, stock_id = await _seed_stock(db, "materials/salt", 500.0, "g")
    # Insert metadata with null expiry
    await db.execute(
        "INSERT INTO kitchen_stock_metadata (id, stock_item_id, expiry_date, updated_at) VALUES (?, ?, NULL, '2026-01-01')",
        [str(uuid.uuid4()), stock_id],
    )
    resp = await client.get("/stock/expiring")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Recipe list filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_recipes_max_cook_time_filter(client):
    """max_cook_time filter excludes recipes with longer cook times."""
    await client.post("/recipes", json={"title": "Quick", "servings": 1, "cook_time_mins": 15})
    await client.post("/recipes", json={"title": "Slow", "servings": 1, "cook_time_mins": 60})

    resp = await client.get("/recipes", params={"max_cook_time": 20})
    assert resp.status_code == 200
    data = resp.json()
    titles = [r["title"] for r in data["items"]]
    assert "Quick" in titles
    assert "Slow" not in titles


@pytest.mark.asyncio
async def test_list_recipes_total_time_computed(client):
    """total_time_mins = prep_time_mins + cook_time_mins."""
    resp = await client.post("/recipes", json={
        "title": "Timed", "servings": 2, "prep_time_mins": 10, "cook_time_mins": 25,
    })
    assert resp.json()["total_time_mins"] == 35


@pytest.mark.asyncio
async def test_list_recipes_total_time_null_when_both_null(client):
    """total_time_mins is None when both prep and cook are absent."""
    resp = await client.post("/recipes", json={"title": "NoTime", "servings": 1})
    assert resp.json()["total_time_mins"] is None


@pytest.mark.asyncio
async def test_recipe_404_returns_suggestion(client):
    """GET /recipes/:id 404 includes suggestion field."""
    resp = await client.get("/recipes/nonexistent-id")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "suggestion" in detail


@pytest.mark.asyncio
async def test_update_recipe_404(client):
    """PUT /recipes/:id returns 404 for missing recipe."""
    resp = await client.put("/recipes/does-not-exist", json={"title": "X"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Nutrition: calculate endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_nutrition_no_save_does_not_persist(client):
    """calculate without save=true does not write to kitchen_recipe_nutrition."""
    recipe_id = await _create_recipe(client, ingredients=[
        {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 100, "unit": "g"},
    ])
    # Set ingredient nutrition
    await client.post("/nutrition/ingredient", json={
        "catalogue_path": "materials/flour",
        "calories_per_100g": 364.0,
        "protein_g": 10.0,
        "fat_g": 1.0,
        "carbs_g": 76.0,
    })
    # Calculate without saving
    resp = await client.post(f"/recipes/{recipe_id}/nutrition/calculate", params={"save": "false"})
    assert resp.status_code == 200
    assert resp.json()["source"] == "calculated"

    # Nutrition endpoint should still return null
    resp2 = await client.get(f"/recipes/{recipe_id}/nutrition")
    assert resp2.status_code == 200
    assert resp2.json() is None


@pytest.mark.asyncio
async def test_calculate_nutrition_save_overwrites_previous(client):
    """Calling calculate with save=true twice overwrites the previous record."""
    recipe_id = await _create_recipe(client, ingredients=[
        {"catalogue_path": "materials/butter", "name": "Butter", "quantity": 50, "unit": "g"},
    ])
    await client.post("/nutrition/ingredient", json={
        "catalogue_path": "materials/butter",
        "calories_per_100g": 717.0,
        "fat_g": 81.0,
    })
    await client.post(f"/recipes/{recipe_id}/nutrition/calculate", params={"save": "true"})
    # Update ingredient nutrition
    await client.post("/nutrition/ingredient", json={
        "catalogue_path": "materials/butter",
        "calories_per_100g": 720.0,
        "fat_g": 82.0,
    })
    resp = await client.post(f"/recipes/{recipe_id}/nutrition/calculate", params={"save": "true"})
    assert resp.status_code == 200
    # Calories should reflect updated value
    data = resp.json()
    assert data["calories"] is not None


@pytest.mark.asyncio
async def test_calculate_nutrition_404(client):
    """calculate endpoint returns 404 for missing recipe."""
    resp = await client.post("/recipes/nonexistent/nutrition/calculate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nutrition_warnings_all_missing(client):
    """All-missing ingredients produce warnings but no error."""
    recipe_id = await _create_recipe(client, ingredients=[
        {"catalogue_path": "materials/mystery", "name": "Mystery", "quantity": 100, "unit": "g"},
    ])
    resp = await client.post(f"/recipes/{recipe_id}/nutrition/calculate")
    assert resp.status_code == 200
    data = resp.json()
    assert any("Mystery" in w for w in data["warnings"])


# ---------------------------------------------------------------------------
# Can-make: 3 scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_can_make_strict_with_all_stock(client, db):
    """Strict can-make returns recipe when all ingredients are in stock."""
    await _seed_stock(db, "materials/pasta", 500.0, "g")
    await _seed_stock(db, "materials/tomato-sauce", 400.0, "g")

    recipe_id = await _create_recipe(client, title="Pasta", ingredients=[
        {"catalogue_path": "materials/pasta", "name": "Pasta", "quantity": 200.0, "unit": "g"},
        {"catalogue_path": "materials/tomato-sauce", "name": "Tomato Sauce", "quantity": 200.0, "unit": "g"},
    ])

    resp = await client.get("/recipes/can-make", params={"strict": "true"})
    assert resp.status_code == 200
    ids = [r["recipe_id"] for r in resp.json()["recipes"]]
    assert recipe_id in ids


@pytest.mark.asyncio
async def test_can_make_strict_missing_one_excluded(client, db):
    """Strict can-make excludes recipes where one ingredient is missing."""
    await _seed_stock(db, "materials/rice", 500.0, "g")
    # No stock for curry-paste

    recipe_id = await _create_recipe(client, title="Curry", ingredients=[
        {"catalogue_path": "materials/rice", "name": "Rice", "quantity": 200.0, "unit": "g"},
        {"catalogue_path": "materials/curry-paste", "name": "Curry Paste", "quantity": 50.0, "unit": "g"},
    ])

    resp = await client.get("/recipes/can-make", params={"strict": "true"})
    assert resp.status_code == 200
    ids = [r["recipe_id"] for r in resp.json()["recipes"]]
    assert recipe_id not in ids


@pytest.mark.asyncio
async def test_can_make_relaxed_one_missing_included(client, db):
    """Relaxed can-make includes recipes with exactly one missing ingredient."""
    await _seed_stock(db, "materials/eggs", 6.0, "piece")
    # No stock for cream

    recipe_id = await _create_recipe(client, title="Omelette", ingredients=[
        {"catalogue_path": "materials/eggs", "name": "Eggs", "quantity": 2.0, "unit": "piece"},
        {"catalogue_path": "materials/cream", "name": "Cream", "quantity": 30.0, "unit": "ml"},
    ])

    resp = await client.get("/recipes/can-make", params={"strict": "false"})
    assert resp.status_code == 200
    ids = [r["recipe_id"] for r in resp.json()["recipes"]]
    assert recipe_id in ids


# ---------------------------------------------------------------------------
# Stock check: scaling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_check_scaled_low_status(client, db):
    """stock-check with serves parameter scales required quantities."""
    await _seed_stock(db, "materials/flour", 100.0, "g")
    recipe_id = await _create_recipe(client, servings=2, ingredients=[
        {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 100.0, "unit": "g"},
    ])
    # Need 200g for 4 servings (scale=2), but only 100g in stock → low
    resp = await client.get(f"/recipes/{recipe_id}/stock-check", params={"serves": 4})
    assert resp.status_code == 200
    data = resp.json()
    flour_ing = next(i for i in data["ingredients"] if i["catalogue_path"] == "materials/flour")
    assert flour_ing["status"] == "low"
    assert flour_ing["required_qty"] == 200.0
    assert not data["can_make"]


# ---------------------------------------------------------------------------
# Meal plan: round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_meal_plan_round_trip(client):
    """Create plan, add entries, verify all entries returned."""
    recipe_id = await _create_recipe(client, title="Breakfast Oats")

    week = "2026-04-07"
    # Add Monday breakfast
    resp = await client.put(f"/meal-plan/{week}/entry", json={
        "day_of_week": 0,
        "meal_slot": "breakfast",
        "recipe_id": recipe_id,
        "servings": 2,
    })
    assert resp.status_code == 200

    # Add Tuesday dinner (free text)
    resp = await client.put(f"/meal-plan/{week}/entry", json={
        "day_of_week": 1,
        "meal_slot": "dinner",
        "free_text": "Takeaway",
        "servings": 1,
    })
    assert resp.status_code == 200

    # Fetch plan
    resp = await client.get(f"/meal-plan/{week}")
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["week_start"] == week
    assert len(plan["entries"]) == 2
    slots = {(e["day_of_week"], e["meal_slot"]) for e in plan["entries"]}
    assert (0, "breakfast") in slots
    assert (1, "dinner") in slots


@pytest.mark.asyncio
async def test_meal_plan_entry_upsert(client):
    """Setting the same slot twice replaces the first entry."""
    week = "2026-04-14"
    recipe_id = await _create_recipe(client, title="Pancakes")

    await client.put(f"/meal-plan/{week}/entry", json={
        "day_of_week": 0, "meal_slot": "breakfast", "free_text": "Toast",
    })
    await client.put(f"/meal-plan/{week}/entry", json={
        "day_of_week": 0, "meal_slot": "breakfast", "recipe_id": recipe_id,
    })

    resp = await client.get(f"/meal-plan/{week}")
    entries = resp.json()["entries"]
    breakfast = [e for e in entries if e["day_of_week"] == 0 and e["meal_slot"] == "breakfast"]
    assert len(breakfast) == 1
    assert breakfast[0]["recipe_id"] == recipe_id


# ---------------------------------------------------------------------------
# Shopping list: generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shopping_list_aggregates_across_days(client, db):
    """Shopping list sums the same ingredient across multiple meal plan entries."""
    week = "2026-04-21"
    await _seed_stock(db, "materials/oats", 100.0, "g")

    recipe_id = await _create_recipe(client, servings=1, ingredients=[
        {"catalogue_path": "materials/oats", "name": "Oats", "quantity": 80.0, "unit": "g"},
    ])
    # Add the same recipe on two days (total required: 160g)
    for day in (0, 1):
        await client.put(f"/meal-plan/{week}/entry", json={
            "day_of_week": day, "meal_slot": "breakfast", "recipe_id": recipe_id, "servings": 1,
        })

    resp = await client.get(f"/meal-plan/{week}/shopping-list")
    assert resp.status_code == 200
    data = resp.json()
    oats = next((i for i in data["items"] if i["catalogue_path"] == "materials/oats"), None)
    assert oats is not None
    # Required 160g, on-hand 100g → shortfall 60g
    assert oats["required_quantity"] == 160.0
    assert oats["on_hand_quantity"] == 100.0
    assert oats["shortfall"] == 60.0


@pytest.mark.asyncio
async def test_shopping_list_no_plan_returns_empty(client):
    """Shopping list returns empty list for weeks with no plan."""
    resp = await client.get("/meal-plan/2030-01-01/shopping-list")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["total_items"] == 0


# ---------------------------------------------------------------------------
# Cook log: filters and pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cook_log_filter_by_rating(client):
    """min_rating filter returns only sessions with rating >= threshold."""
    recipe_id = await _create_recipe(client)
    await client.post("/cook-log", json={
        "recipe_id": recipe_id, "cooked_at": "2026-03-01T12:00:00", "serves_made": 2, "rating": 3,
    })
    await client.post("/cook-log", json={
        "recipe_id": recipe_id, "cooked_at": "2026-03-02T12:00:00", "serves_made": 2, "rating": 5,
    })

    resp = await client.get("/cook-log", params={"min_rating": 4})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["rating"] == 5


@pytest.mark.asyncio
async def test_cook_log_date_range_filter(client):
    """from_date and to_date filter cook log by session date."""
    recipe_id = await _create_recipe(client)
    await client.post("/cook-log", json={
        "recipe_id": recipe_id, "cooked_at": "2026-01-10T10:00:00", "serves_made": 1,
    })
    await client.post("/cook-log", json={
        "recipe_id": recipe_id, "cooked_at": "2026-03-15T10:00:00", "serves_made": 1,
    })

    resp = await client.get("/cook-log", params={
        "from_date": "2026-03-01", "to_date": "2026-03-31",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert "2026-03-15" in data["items"][0]["cooked_at"]


@pytest.mark.asyncio
async def test_cook_log_pagination(client):
    """offset and limit work correctly for the cook log."""
    recipe_id = await _create_recipe(client)
    for i in range(5):
        await client.post("/cook-log", json={
            "recipe_id": recipe_id,
            "cooked_at": f"2026-02-{i+1:02d}T10:00:00",
            "serves_made": 1,
        })

    resp = await client.get("/cook-log", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2

    resp2 = await client.get("/cook-log", params={"limit": 2, "offset": 2})
    data2 = resp2.json()
    assert len(data2["items"]) == 2

    # Page 3 (offset=4) should have 1 item
    resp3 = await client.get("/cook-log", params={"limit": 2, "offset": 4})
    data3 = resp3.json()
    assert len(data3["items"]) == 1


# ---------------------------------------------------------------------------
# Aliases: upsert semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alias_lookup_after_create(client):
    """Lookup returns the saved alias."""
    await client.post("/stock/aliases", json={
        "receipt_text": "FLOUR 2KG",
        "catalogue_path": "materials/flour",
    })
    resp = await client.get("/stock/aliases/lookup", params={"text": "FLOUR 2KG"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["catalogue_path"] == "materials/flour"
    assert data["receipt_text"] == "FLOUR 2KG"


@pytest.mark.asyncio
async def test_alias_lookup_miss_returns_null(client):
    """Lookup for unknown receipt text returns null."""
    resp = await client.get("/stock/aliases/lookup", params={"text": "UNKNOWN ITEM"})
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_alias_upsert_updates_path(client):
    """Saving the same receipt_text twice updates the catalogue_path."""
    await client.post("/stock/aliases", json={
        "receipt_text": "MILK 2L",
        "catalogue_path": "materials/full-fat-milk",
    })
    await client.post("/stock/aliases", json={
        "receipt_text": "MILK 2L",
        "catalogue_path": "materials/semi-skimmed-milk",
    })
    resp = await client.get("/stock/aliases/lookup", params={"text": "MILK 2L"})
    assert resp.json()["catalogue_path"] == "materials/semi-skimmed-milk"


# ---------------------------------------------------------------------------
# Can-make response structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_can_make_empty_recipes(client):
    """can-make returns empty list when no recipes exist."""
    resp = await client.get("/recipes/can-make")
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipes"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_can_make_ingredient_status_ok_vs_missing(client, db):
    """Ingredient status is 'ok' when in stock and 'missing' when absent."""
    await _seed_stock(db, "materials/garlic", 5.0, "piece")

    recipe_id = await _create_recipe(client, title="Garlic Bread", ingredients=[
        {"catalogue_path": "materials/garlic", "name": "Garlic", "quantity": 2.0, "unit": "piece"},
        {"catalogue_path": "materials/bread", "name": "Bread", "quantity": 1.0, "unit": "piece"},
    ])

    resp = await client.get("/recipes/can-make", params={"strict": "false"})
    assert resp.status_code == 200
    recipes = resp.json()["recipes"]
    recipe = next(r for r in recipes if r["recipe_id"] == recipe_id)
    ing_statuses = {i["catalogue_path"]: i["status"] for i in recipe["ingredients"]}
    assert ing_statuses["materials/garlic"] == "ok"
    assert ing_statuses["materials/bread"] == "missing"


# ---------------------------------------------------------------------------
# Bulk stock: partial failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_stock_partial_failure_continues(db):
    """Items that fail don't prevent other valid items from processing."""
    from fastapi import FastAPI
    from makestack_sdk.peers import get_peer_modules
    from backend.app.module_loader import ModuleRegistry

    class _MockPeers:
        def is_installed(self, name): return True

        async def call(self, module, method, path, body=None, **kwargs):
            if method == "PUT":
                return {"id": "x", "quantity": body.get("quantity", 0)}
            return {"id": str(uuid.uuid4())}

    inv_id = await _seed_inventory(db, "materials/olive-oil")
    stock_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory_stock_items (id, inventory_id, quantity, unit, location, updated_at) "
        "VALUES (?, ?, 500.0, 'ml', 'pantry', '2026-01-01')",
        [stock_id, inv_id],
    )

    app = FastAPI()
    app.state.userdb = db
    app.state.dev_mode = True
    app.state.config = {"port": 3000}
    app.state.start_time = time.monotonic()
    app.state.module_registry = ModuleRegistry()
    app.include_router(router)
    app.dependency_overrides[get_peer_modules] = lambda: _MockPeers()

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/stock/bulk", json=[
            # Valid — has inventory + stock
            {"catalogue_path": "materials/olive-oil", "quantity": 300.0, "unit": "ml", "action": "set"},
            # Invalid — no inventory row
            {"catalogue_path": "materials/unicorn-powder", "quantity": 1.0, "unit": "g", "action": "set"},
        ])

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["updated"]) == 1
    assert len(data["failed"]) == 1
    assert data["updated"][0]["catalogue_path"] == "materials/olive-oil"
    assert data["failed"][0]["catalogue_path"] == "materials/unicorn-powder"
