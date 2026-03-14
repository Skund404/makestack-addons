"""Tests for kitchen K3: meal plan, shopping list, and cook log endpoints."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB, MockPeerModules, create_test_app

# ---------------------------------------------------------------------------
# Load kitchen modules by file path
# ---------------------------------------------------------------------------

_KITCHEN_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _load_kitchen(name: str, relpath: str):
    key = f"_kitchen_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_KITCHEN_ROOT, relpath)
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


migration_001 = _load_kitchen("mig001", "backend/migrations/001_create_tables.py")
migration_002 = _load_kitchen("mig002", "backend/migrations/002_seed_locations.py")
migration_003 = _load_kitchen("mig003", "backend/migrations/003_add_prep_time.py")
migration_004 = _load_kitchen("mig004", "backend/migrations/004_add_cook_log_fields.py")
routes_mod = _load_kitchen("routes", "backend/routes.py")

router = routes_mod.router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    userdb = MockUserDB()
    await userdb.setup()
    await migration_001.up(userdb)
    await migration_002.up(userdb)
    await migration_003.up(userdb)
    await migration_004.up(userdb)
    # inventory_stock_items is owned by inventory-stock; create it manually here
    # so that shopping-list and cook-log deduction tests can insert stock rows.
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
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEEK = "2026-03-16"  # a Monday


async def _make_recipe(client, title="Pasta", servings=2, ingredients=None):
    body = {
        "title": title,
        "servings": servings,
        "ingredients": ingredients or [],
    }
    r = await client.post("/recipes", json=body)
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# Meal Plan — GET (auto-create)
# ---------------------------------------------------------------------------


async def test_get_meal_plan_creates_if_missing(client):
    r = await client.get(f"/meal-plan/{WEEK}")
    assert r.status_code == 200
    data = r.json()
    assert data["week_start"] == WEEK
    assert data["entries"] == []
    assert "id" in data


async def test_get_meal_plan_is_idempotent(client):
    r1 = await client.get(f"/meal-plan/{WEEK}")
    r2 = await client.get(f"/meal-plan/{WEEK}")
    assert r1.json()["id"] == r2.json()["id"]


# ---------------------------------------------------------------------------
# Meal Plan — PUT /entry (upsert)
# ---------------------------------------------------------------------------


async def test_add_entry_to_meal_plan(client):
    recipe = await _make_recipe(client)
    r = await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={
            "day_of_week": 0,
            "meal_slot": "dinner",
            "recipe_id": recipe["id"],
            "servings": 2,
        },
    )
    assert r.status_code == 200
    entry = r.json()
    assert entry["day_of_week"] == 0
    assert entry["meal_slot"] == "dinner"
    assert entry["recipe_id"] == recipe["id"]


async def test_entry_upsert_replaces_existing(client):
    recipe1 = await _make_recipe(client, "Pasta")
    recipe2 = await _make_recipe(client, "Salad")

    await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={"day_of_week": 1, "meal_slot": "lunch", "recipe_id": recipe1["id"]},
    )
    r = await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={"day_of_week": 1, "meal_slot": "lunch", "recipe_id": recipe2["id"]},
    )
    assert r.status_code == 200
    assert r.json()["recipe_id"] == recipe2["id"]


async def test_multiple_entries_appear_in_plan(client):
    recipe = await _make_recipe(client)
    for day in range(3):
        await client.put(
            f"/meal-plan/{WEEK}/entry",
            json={"day_of_week": day, "meal_slot": "dinner", "recipe_id": recipe["id"]},
        )

    r = await client.get(f"/meal-plan/{WEEK}")
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 3


async def test_entry_serves_override(client):
    recipe = await _make_recipe(client, servings=4)
    r = await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={
            "day_of_week": 2,
            "meal_slot": "dinner",
            "recipe_id": recipe["id"],
            "serves_override": 6,
        },
    )
    assert r.status_code == 200
    assert r.json()["serves_override"] == 6


async def test_entry_free_text_no_recipe(client):
    r = await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={
            "day_of_week": 3,
            "meal_slot": "breakfast",
            "free_text": "Oats from the pantry",
        },
    )
    assert r.status_code == 200
    entry = r.json()
    assert entry["recipe_id"] is None
    assert entry["free_text"] == "Oats from the pantry"


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------


async def test_shopping_list_empty_plan(client):
    r = await client.get(f"/meal-plan/{WEEK}/shopping-list")
    assert r.status_code == 200
    data = r.json()
    assert data["week_start"] == WEEK
    assert data["items"] == []
    assert data["total_items"] == 0


async def test_shopping_list_no_stock(client, db):
    recipe = await _make_recipe(
        client,
        "Pasta",
        servings=2,
        ingredients=[
            {"catalogue_path": "materials/pasta", "name": "Pasta", "quantity": 200, "unit": "g"},
            {"catalogue_path": "materials/sauce", "name": "Sauce", "quantity": 100, "unit": "ml"},
        ],
    )
    await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={"day_of_week": 0, "meal_slot": "dinner", "recipe_id": recipe["id"], "servings": 2},
    )

    r = await client.get(f"/meal-plan/{WEEK}/shopping-list")
    assert r.status_code == 200
    data = r.json()
    assert data["total_items"] == 2

    by_path = {i["catalogue_path"]: i for i in data["items"]}
    assert by_path["materials/pasta"]["required_quantity"] == 200.0
    assert by_path["materials/pasta"]["on_hand_quantity"] == 0.0
    assert by_path["materials/pasta"]["shortfall"] == 200.0


async def test_shopping_list_partial_stock(client, db):
    """On-hand stock reduces shortfall; fully-covered items have shortfall=0."""
    recipe = await _make_recipe(
        client,
        "Risotto",
        servings=2,
        ingredients=[
            {"catalogue_path": "materials/rice", "name": "Rice", "quantity": 300, "unit": "g"},
        ],
    )
    await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={"day_of_week": 0, "meal_slot": "dinner", "recipe_id": recipe["id"], "servings": 2},
    )

    # Seed inventory + stock (200g rice on hand)
    inv_id = str(uuid.uuid4())
    stock_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory (id, catalogue_path, catalogue_hash, primitive_type, added_at, updated_at) "
        "VALUES (?, ?, 'abc', 'material', '2026-01-01', '2026-01-01')",
        [inv_id, "materials/rice"],
    )
    await db.execute(
        "INSERT INTO inventory_stock_items (id, inventory_id, quantity, unit, updated_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01')",
        [stock_id, inv_id, 200.0, "g"],
    )

    r = await client.get(f"/meal-plan/{WEEK}/shopping-list")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["on_hand_quantity"] == 200.0
    assert items[0]["required_quantity"] == 300.0
    assert items[0]["shortfall"] == 100.0


async def test_shopping_list_fully_covered(client, db):
    """When stock >= required, shortfall is 0."""
    recipe = await _make_recipe(
        client,
        "Toast",
        servings=1,
        ingredients=[
            {"catalogue_path": "materials/bread", "name": "Bread", "quantity": 50, "unit": "g"},
        ],
    )
    await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={"day_of_week": 0, "meal_slot": "breakfast", "recipe_id": recipe["id"]},
    )

    inv_id = str(uuid.uuid4())
    stock_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory (id, catalogue_path, catalogue_hash, primitive_type, added_at, updated_at) "
        "VALUES (?, ?, 'abc', 'material', '2026-01-01', '2026-01-01')",
        [inv_id, "materials/bread"],
    )
    await db.execute(
        "INSERT INTO inventory_stock_items (id, inventory_id, quantity, unit, updated_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01')",
        [stock_id, inv_id, 500.0, "g"],
    )

    r = await client.get(f"/meal-plan/{WEEK}/shopping-list")
    items = r.json()["items"]
    assert items[0]["shortfall"] == 0.0


async def test_shopping_list_serves_override_scales_requirement(client, db):
    """serves_override=4 on a 2-serving recipe should double the requirement."""
    recipe = await _make_recipe(
        client,
        "Soup",
        servings=2,
        ingredients=[
            {"catalogue_path": "materials/stock", "name": "Stock", "quantity": 500, "unit": "ml"},
        ],
    )
    await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={
            "day_of_week": 0,
            "meal_slot": "lunch",
            "recipe_id": recipe["id"],
            "serves_override": 4,
        },
    )

    r = await client.get(f"/meal-plan/{WEEK}/shopping-list")
    items = r.json()["items"]
    assert items[0]["required_quantity"] == 1000.0


# ---------------------------------------------------------------------------
# Cook Log — POST
# ---------------------------------------------------------------------------


async def test_create_cook_log_no_peer(client, db):
    """Log is created with stock_deducted=0 when inventory-stock is not installed."""
    recipe = await _make_recipe(client, "Omelette", servings=1)
    r = await client.post(
        "/cook-log",
        json={
            "recipe_id": recipe["id"],
            "cooked_at": "2026-03-14T18:00:00Z",
            "serves_made": 1,
            "rating": 4,
            "notes": "Fluffy",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["recipe_id"] == recipe["id"]
    assert data["serves_made"] == 1
    assert data["rating"] == 4
    assert data["stock_deducted"] == 0
    assert "inventory-stock not installed" in " ".join(data["warnings"])


async def test_create_cook_log_stores_material_pulls(client, db):
    recipe = await _make_recipe(
        client,
        "Steak",
        servings=2,
        ingredients=[
            {"catalogue_path": "materials/beef", "name": "Beef", "quantity": 300, "unit": "g"},
        ],
    )
    r = await client.post(
        "/cook-log",
        json={
            "recipe_id": recipe["id"],
            "cooked_at": "2026-03-14T19:00:00Z",
            "serves_made": 2,
        },
    )
    assert r.status_code == 201
    data = r.json()
    pulls = json.loads(data["material_pulls_json"])
    assert len(pulls) == 1
    assert pulls[0]["catalogue_path"] == "materials/beef"
    assert pulls[0]["quantity"] == 300.0


async def test_cook_log_scales_pulls_by_serves_made(client, db):
    """serves_made=4 on a 2-serving recipe should double pull quantities."""
    recipe = await _make_recipe(
        client,
        "BigBatch",
        servings=2,
        ingredients=[
            {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 200, "unit": "g"},
        ],
    )
    r = await client.post(
        "/cook-log",
        json={
            "recipe_id": recipe["id"],
            "cooked_at": "2026-03-14T20:00:00Z",
            "serves_made": 4,
        },
    )
    assert r.status_code == 201
    pulls = json.loads(r.json()["material_pulls_json"])
    assert pulls[0]["quantity"] == 400.0


async def test_cook_log_404_for_missing_recipe(client):
    r = await client.post(
        "/cook-log",
        json={
            "recipe_id": str(uuid.uuid4()),
            "cooked_at": "2026-03-14T18:00:00Z",
        },
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Cook Log — GET (list + filters)
# ---------------------------------------------------------------------------


async def test_list_cook_log_empty(client):
    r = await client.get("/cook-log")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_list_cook_log_returns_entries(client, db):
    recipe = await _make_recipe(client)
    for i in range(3):
        await client.post(
            "/cook-log",
            json={"recipe_id": recipe["id"], "cooked_at": f"2026-03-{10 + i:02d}T18:00:00Z"},
        )

    r = await client.get("/cook-log")
    assert r.json()["total"] == 3


async def test_list_cook_log_filter_by_recipe(client, db):
    r1 = await _make_recipe(client, "Pasta")
    r2 = await _make_recipe(client, "Pizza")
    await client.post("/cook-log", json={"recipe_id": r1["id"], "cooked_at": "2026-03-10T18:00:00Z"})
    await client.post("/cook-log", json={"recipe_id": r2["id"], "cooked_at": "2026-03-11T18:00:00Z"})

    r = await client.get(f"/cook-log?recipe_id={r1['id']}")
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["recipe_id"] == r1["id"]


async def test_list_cook_log_filter_by_date_range(client, db):
    recipe = await _make_recipe(client)
    for date in ["2026-03-01", "2026-03-15", "2026-03-31"]:
        await client.post(
            "/cook-log",
            json={"recipe_id": recipe["id"], "cooked_at": f"{date}T12:00:00Z"},
        )

    r = await client.get("/cook-log?from_date=2026-03-10T00:00:00Z&to_date=2026-03-20T00:00:00Z")
    assert r.json()["total"] == 1


async def test_list_cook_log_filter_by_min_rating(client, db):
    recipe = await _make_recipe(client)
    await client.post(
        "/cook-log",
        json={"recipe_id": recipe["id"], "cooked_at": "2026-03-10T12:00:00Z", "rating": 3},
    )
    await client.post(
        "/cook-log",
        json={"recipe_id": recipe["id"], "cooked_at": "2026-03-11T12:00:00Z", "rating": 5},
    )

    r = await client.get("/cook-log?min_rating=4")
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["rating"] == 5


async def test_cook_log_pagination(client, db):
    recipe = await _make_recipe(client)
    for i in range(5):
        await client.post(
            "/cook-log",
            json={"recipe_id": recipe["id"], "cooked_at": f"2026-03-{i + 1:02d}T12:00:00Z"},
        )

    r = await client.get("/cook-log?limit=2&offset=0")
    data = r.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2

    r2 = await client.get("/cook-log?limit=2&offset=2")
    assert len(r2.json()["items"]) == 2


# ---------------------------------------------------------------------------
# Cook Log — stock deduction with mock peer
# ---------------------------------------------------------------------------


async def test_cook_log_deducts_stock_via_peer(db):
    """When inventory-stock is available, stock is reduced and deducted=True."""
    from makestack_sdk.peers import get_peer_modules
    from fastapi import FastAPI
    from httpx import ASGITransport
    import httpx
    import time
    from backend.app.module_loader import ModuleRegistry

    # Track peer PUT calls
    peer_calls: list[dict] = []

    class _MockPeers:
        def is_installed(self, name):
            return name == "inventory-stock"

        async def call(self, module_name, method, path, body=None, **kwargs):
            peer_calls.append({"module": module_name, "method": method, "path": path, "body": body})
            return {"id": "stock-1", "quantity": body["quantity"]}

    app = FastAPI()
    app.state.userdb = db
    app.state.dev_mode = True
    app.state.config = {"port": 3000}
    app.state.start_time = time.monotonic()
    app.state.module_registry = ModuleRegistry()
    app.include_router(router)
    app.dependency_overrides[get_peer_modules] = lambda: _MockPeers()

    # Seed inventory + stock (12 eggs on hand)
    inv_id = str(uuid.uuid4())
    stock_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory (id, catalogue_path, catalogue_hash, primitive_type, added_at, updated_at) "
        "VALUES (?, ?, 'abc', 'material', '2026-01-01', '2026-01-01')",
        [inv_id, "materials/eggs"],
    )
    await db.execute(
        "INSERT INTO inventory_stock_items (id, inventory_id, quantity, unit, updated_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01')",
        [stock_id, inv_id, 12.0, "unit"],
    )

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.post(
            "/recipes",
            json={
                "title": "Scrambled Eggs",
                "servings": 2,
                "ingredients": [
                    {
                        "catalogue_path": "materials/eggs",
                        "name": "Eggs",
                        "quantity": 4,
                        "unit": "unit",
                    }
                ],
            },
        )
        assert r.status_code == 201
        recipe_id = r.json()["id"]

        r = await c.post(
            "/cook-log",
            json={
                "recipe_id": recipe_id,
                "cooked_at": "2026-03-14T19:00:00Z",
                "serves_made": 2,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["stock_deducted"] == 1
        assert data["warnings"] == []

    # Verify peer was called with reduced quantity (12 - 4 = 8)
    assert len(peer_calls) == 1
    assert peer_calls[0]["method"] == "PUT"
    assert peer_calls[0]["path"] == f"/stock/{stock_id}"
    assert peer_calls[0]["body"]["quantity"] == 12.0 - 4.0
