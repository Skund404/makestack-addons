"""Tests for kitchen K4: can-make, stock-check, bulk stock, aliases, unit normalisation."""

from __future__ import annotations

import importlib.util
import os
import sys
import time
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
migration_006 = _load_kitchen("mig006k4", "backend/migrations/006_recipe_provenance.py")
routes_mod = _load_kitchen("routes", "backend/routes.py")

router = routes_mod.router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WEEK = "2026-03-16"


@pytest_asyncio.fixture
async def db():
    userdb = MockUserDB()
    await userdb.setup()
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
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_recipe(client, title="Pasta", servings=2, ingredients=None):
    r = await client.post(
        "/recipes",
        json={"title": title, "servings": servings, "ingredients": ingredients or []},
    )
    assert r.status_code == 201
    return r.json()


async def _seed_stock(db, catalogue_path: str, quantity: float, unit: str = "g") -> tuple[str, str]:
    """Insert an inventory item + stock item. Returns (inv_id, stock_id)."""
    inv_id = str(uuid.uuid4())
    stock_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory (id, catalogue_path, catalogue_hash, primitive_type, added_at, updated_at) "
        "VALUES (?, ?, 'abc', 'material', '2026-01-01', '2026-01-01')",
        [inv_id, catalogue_path],
    )
    await db.execute(
        "INSERT INTO inventory_stock_items (id, inventory_id, quantity, unit, updated_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01')",
        [stock_id, inv_id, quantity, unit],
    )
    return inv_id, stock_id


# ---------------------------------------------------------------------------
# Route ordering: can-make must not be caught by /:id wildcard
# ---------------------------------------------------------------------------


async def test_can_make_route_not_treated_as_recipe_id(client):
    """GET /recipes/can-make returns a list response, not a 404 recipe-not-found error."""
    r = await client.get("/recipes/can-make")
    assert r.status_code == 200
    data = r.json()
    assert "recipes" in data
    assert isinstance(data["recipes"], list)
    assert "total" in data


# ---------------------------------------------------------------------------
# Can-make — strict mode
# ---------------------------------------------------------------------------


async def test_can_make_strict_all_in_stock(client, db):
    """All ingredients in stock → recipe appears in strict mode."""
    recipe = await _make_recipe(
        client, "Omelette", servings=1,
        ingredients=[
            {"catalogue_path": "materials/eggs", "name": "Eggs", "quantity": 3, "unit": "unit"},
            {"catalogue_path": "materials/butter", "name": "Butter", "quantity": 10, "unit": "g"},
        ],
    )
    await _seed_stock(db, "materials/eggs", 6, "unit")
    await _seed_stock(db, "materials/butter", 100, "g")

    r = await client.get("/recipes/can-make?strict=true")
    assert r.status_code == 200
    ids = [rec["recipe_id"] for rec in r.json()["recipes"]]
    assert recipe["id"] in ids


async def test_can_make_strict_one_missing(client, db):
    """One ingredient missing → recipe absent in strict mode."""
    recipe = await _make_recipe(
        client, "Omelette", servings=1,
        ingredients=[
            {"catalogue_path": "materials/eggs", "name": "Eggs", "quantity": 3, "unit": "unit"},
            {"catalogue_path": "materials/butter", "name": "Butter", "quantity": 10, "unit": "g"},
        ],
    )
    # Only stock eggs — butter missing
    await _seed_stock(db, "materials/eggs", 6, "unit")

    r = await client.get("/recipes/can-make?strict=true")
    ids = [rec["recipe_id"] for rec in r.json()["recipes"]]
    assert recipe["id"] not in ids


# ---------------------------------------------------------------------------
# Can-make — relaxed mode
# ---------------------------------------------------------------------------


async def test_can_make_relaxed_one_missing(client, db):
    """One ingredient missing → recipe appears in relaxed mode with missing_count=1."""
    recipe = await _make_recipe(
        client, "Omelette", servings=1,
        ingredients=[
            {"catalogue_path": "materials/eggs", "name": "Eggs", "quantity": 3, "unit": "unit"},
            {"catalogue_path": "materials/butter", "name": "Butter", "quantity": 10, "unit": "g"},
        ],
    )
    await _seed_stock(db, "materials/eggs", 6, "unit")

    r = await client.get("/recipes/can-make")  # strict=False by default
    assert r.status_code == 200
    recipes = r.json()["recipes"]
    match = next((rec for rec in recipes if rec["recipe_id"] == recipe["id"]), None)
    assert match is not None
    assert match["missing_count"] == 1
    assert match["can_make"] is False


async def test_can_make_relaxed_all_missing(client, db):
    """All ingredients missing → recipe absent even in relaxed mode."""
    recipe = await _make_recipe(
        client, "Stew", servings=4,
        ingredients=[
            {"catalogue_path": "materials/beef", "name": "Beef", "quantity": 500, "unit": "g"},
            {"catalogue_path": "materials/carrot", "name": "Carrot", "quantity": 200, "unit": "g"},
        ],
    )
    # No stock for either

    r = await client.get("/recipes/can-make")
    ids = [rec["recipe_id"] for rec in r.json()["recipes"]]
    assert recipe["id"] not in ids


async def test_can_make_strict_all_missing(client, db):
    """All missing → absent in strict mode too."""
    recipe = await _make_recipe(
        client, "Stew", servings=4,
        ingredients=[
            {"catalogue_path": "materials/beef", "name": "Beef", "quantity": 500, "unit": "g"},
        ],
    )
    r = await client.get("/recipes/can-make?strict=true")
    ids = [rec["recipe_id"] for rec in r.json()["recipes"]]
    assert recipe["id"] not in ids


async def test_can_make_ingredient_status_in_response(client, db):
    """Response includes ingredient list with ok/missing status per ingredient."""
    recipe = await _make_recipe(
        client, "Soup", servings=2,
        ingredients=[
            {"catalogue_path": "materials/veg", "name": "Veg", "quantity": 200, "unit": "g"},
            {"catalogue_path": "materials/salt", "name": "Salt", "quantity": 5, "unit": "g"},
        ],
    )
    await _seed_stock(db, "materials/veg", 300, "g")
    # salt missing

    r = await client.get("/recipes/can-make")
    recipes = r.json()["recipes"]
    match = next((rec for rec in recipes if rec["recipe_id"] == recipe["id"]), None)
    assert match is not None

    by_path = {i["catalogue_path"]: i for i in match["ingredients"]}
    assert by_path["materials/veg"]["status"] == "ok"
    assert by_path["materials/salt"]["status"] == "missing"


# ---------------------------------------------------------------------------
# Stock-check endpoint
# ---------------------------------------------------------------------------


async def test_stock_check_all_ok(client, db):
    recipe = await _make_recipe(
        client, "Cake", servings=1,
        ingredients=[
            {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 200, "unit": "g"},
        ],
    )
    await _seed_stock(db, "materials/flour", 500, "g")

    r = await client.get(f"/recipes/{recipe['id']}/stock-check")
    assert r.status_code == 200
    data = r.json()
    assert data["can_make"] is True
    assert data["missing_count"] == 0
    assert data["ingredients"][0]["status"] == "ok"


async def test_stock_check_low(client, db):
    """in_stock > 0 but < required → status 'low'."""
    recipe = await _make_recipe(
        client, "Cake", servings=1,
        ingredients=[
            {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 200, "unit": "g"},
        ],
    )
    await _seed_stock(db, "materials/flour", 50, "g")  # less than 200

    r = await client.get(f"/recipes/{recipe['id']}/stock-check")
    data = r.json()
    assert data["ingredients"][0]["status"] == "low"
    assert data["can_make"] is False


async def test_stock_check_missing(client, db):
    recipe = await _make_recipe(
        client, "Cake", servings=1,
        ingredients=[
            {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 200, "unit": "g"},
        ],
    )

    r = await client.get(f"/recipes/{recipe['id']}/stock-check")
    data = r.json()
    assert data["ingredients"][0]["status"] == "missing"
    assert data["missing_count"] == 1


async def test_stock_check_serves_scaling(client, db):
    """serves=4 on a 2-serving recipe doubles required_qty."""
    recipe = await _make_recipe(
        client, "Cake", servings=2,
        ingredients=[
            {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 200, "unit": "g"},
        ],
    )
    await _seed_stock(db, "materials/flour", 300, "g")

    r = await client.get(f"/recipes/{recipe['id']}/stock-check?serves=4")
    data = r.json()
    ing = data["ingredients"][0]
    assert ing["required_qty"] == 400.0
    assert ing["in_stock_qty"] == 300.0
    assert ing["status"] == "low"


async def test_stock_check_404(client):
    r = await client.get(f"/recipes/{uuid.uuid4()}/stock-check")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Alias endpoints
# ---------------------------------------------------------------------------


async def test_alias_lookup_miss(client):
    r = await client.get("/stock/aliases/lookup?text=UNKNOWN+ITEM")
    assert r.status_code == 200
    assert r.json() is None


async def test_alias_create_and_lookup(client):
    r = await client.post(
        "/stock/aliases",
        json={"receipt_text": "HHNZ ORG EGG", "catalogue_path": "materials/eggs"},
    )
    assert r.status_code == 201
    alias = r.json()
    assert alias["receipt_text"] == "HHNZ ORG EGG"
    assert alias["catalogue_path"] == "materials/eggs"

    r = await client.get("/stock/aliases/lookup?text=HHNZ+ORG+EGG")
    assert r.status_code == 200
    assert r.json()["catalogue_path"] == "materials/eggs"


async def test_alias_upsert(client):
    """Creating an alias for the same receipt_text updates the catalogue_path."""
    await client.post(
        "/stock/aliases",
        json={"receipt_text": "ORGANIC EGGS", "catalogue_path": "materials/eggs-standard"},
    )
    r = await client.post(
        "/stock/aliases",
        json={"receipt_text": "ORGANIC EGGS", "catalogue_path": "materials/eggs-organic"},
    )
    assert r.status_code == 201
    assert r.json()["catalogue_path"] == "materials/eggs-organic"

    lookup = await client.get("/stock/aliases/lookup?text=ORGANIC+EGGS")
    assert lookup.json()["catalogue_path"] == "materials/eggs-organic"


# ---------------------------------------------------------------------------
# Bulk stock update
# ---------------------------------------------------------------------------


async def test_bulk_stock_peer_unavailable(client):
    """With no peer installed, all items go to failed list."""
    r = await client.post(
        "/stock/bulk",
        json=[{"catalogue_path": "materials/flour", "quantity": 500, "unit": "g"}],
    )
    assert r.status_code == 200
    data = r.json()
    assert data["updated"] == []
    assert data["created"] == []
    assert len(data["failed"]) == 1
    assert "inventory-stock" in data["failed"][0]["error"]


async def test_bulk_stock_no_inventory_fails(db):
    """Item with no matching inventory entry → goes to failed list (even with peer)."""
    from makestack_sdk.peers import get_peer_modules
    from fastapi import FastAPI
    from backend.app.module_loader import ModuleRegistry

    class _MockPeers:
        def is_installed(self, name):
            return name == "inventory-stock"

        async def call(self, *args, **kwargs):
            return {"id": str(uuid.uuid4()), "quantity": 0}

    app = FastAPI()
    app.state.userdb = db
    app.state.dev_mode = True
    app.state.config = {"port": 3000}
    app.state.start_time = time.monotonic()
    app.state.module_registry = ModuleRegistry()
    app.include_router(router)
    app.dependency_overrides[get_peer_modules] = lambda: _MockPeers()

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/stock/bulk",
            json=[{"catalogue_path": "materials/noexist", "quantity": 1, "unit": "kg"}],
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["failed"]) == 1
        assert "No inventory item" in data["failed"][0]["error"]


async def test_bulk_stock_partial_failure(db):
    """Valid item → updated; item with no inventory → failed.  Partial results returned."""
    from makestack_sdk.peers import get_peer_modules
    from fastapi import FastAPI
    from backend.app.module_loader import ModuleRegistry

    peer_calls: list[dict] = []

    class _MockPeers:
        def is_installed(self, name):
            return name == "inventory-stock"

        async def call(self, module, method, path, body=None, **kwargs):
            peer_calls.append({"method": method, "path": path, "body": body})
            stock_id = path.split("/")[-1] if method == "PUT" else str(uuid.uuid4())
            return {"id": stock_id, "quantity": body.get("quantity", 0) if body else 0}

    app = FastAPI()
    app.state.userdb = db
    app.state.dev_mode = True
    app.state.config = {"port": 3000}
    app.state.start_time = time.monotonic()
    app.state.module_registry = ModuleRegistry()
    app.include_router(router)
    app.dependency_overrides[get_peer_modules] = lambda: _MockPeers()

    # Seed inventory + stock for item 1
    inv_id, stock_id = await _seed_stock(db, "materials/rice", 500, "g")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/stock/bulk",
            json=[
                {"catalogue_path": "materials/rice", "quantity": 750, "unit": "g", "action": "set"},
                {"catalogue_path": "materials/noexist", "quantity": 1, "unit": "kg"},
            ],
        )
        assert r.status_code == 200
        data = r.json()

    assert len(data["updated"]) == 1
    assert data["updated"][0]["catalogue_path"] == "materials/rice"
    assert data["updated"][0]["quantity"] == 750

    assert data["created"] == []

    assert len(data["failed"]) == 1
    assert data["failed"][0]["catalogue_path"] == "materials/noexist"

    # Verify peer PUT was called with new quantity
    put_calls = [c for c in peer_calls if c["method"] == "PUT"]
    assert len(put_calls) == 1
    assert put_calls[0]["body"]["quantity"] == 750


async def test_bulk_stock_add_action(db):
    """action='add' increments the existing quantity."""
    from makestack_sdk.peers import get_peer_modules
    from fastapi import FastAPI
    from backend.app.module_loader import ModuleRegistry

    received_qty: list[float] = []

    class _MockPeers:
        def is_installed(self, name):
            return name == "inventory-stock"

        async def call(self, module, method, path, body=None, **kwargs):
            if body and "quantity" in body:
                received_qty.append(body["quantity"])
            return {"id": path.split("/")[-1], "quantity": body.get("quantity", 0) if body else 0}

    app = FastAPI()
    app.state.userdb = db
    app.state.dev_mode = True
    app.state.config = {"port": 3000}
    app.state.start_time = time.monotonic()
    app.state.module_registry = ModuleRegistry()
    app.include_router(router)
    app.dependency_overrides[get_peer_modules] = lambda: _MockPeers()

    # Existing stock: 200g
    await _seed_stock(db, "materials/pasta", 200, "g")

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/stock/bulk",
            json=[{"catalogue_path": "materials/pasta", "quantity": 150, "unit": "g", "action": "add"}],
        )
        assert r.status_code == 200
        data = r.json()

    assert len(data["updated"]) == 1
    assert received_qty[0] == 350  # 200 + 150


async def test_bulk_stock_creates_when_no_existing_stock(db):
    """Inventory exists but no stock entry → creates new stock via POST peer."""
    from makestack_sdk.peers import get_peer_modules
    from fastapi import FastAPI
    from backend.app.module_loader import ModuleRegistry

    peer_calls: list[dict] = []

    class _MockPeers:
        def is_installed(self, name):
            return name == "inventory-stock"

        async def call(self, module, method, path, body=None, **kwargs):
            new_id = str(uuid.uuid4())
            peer_calls.append({"method": method, "path": path, "body": body})
            return {"id": new_id, "quantity": body.get("quantity", 0) if body else 0}

    app = FastAPI()
    app.state.userdb = db
    app.state.dev_mode = True
    app.state.config = {"port": 3000}
    app.state.start_time = time.monotonic()
    app.state.module_registry = ModuleRegistry()
    app.include_router(router)
    app.dependency_overrides[get_peer_modules] = lambda: _MockPeers()

    # Inventory item exists but NO stock item
    inv_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO inventory (id, catalogue_path, catalogue_hash, primitive_type, added_at, updated_at) "
        "VALUES (?, ?, 'abc', 'material', '2026-01-01', '2026-01-01')",
        [inv_id, "materials/oats"],
    )

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/stock/bulk",
            json=[{"catalogue_path": "materials/oats", "quantity": 500, "unit": "g"}],
        )
        assert r.status_code == 200
        data = r.json()

    assert len(data["created"]) == 1
    assert data["created"][0]["catalogue_path"] == "materials/oats"
    assert data["updated"] == []

    post_calls = [c for c in peer_calls if c["method"] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0]["body"]["inventory_id"] == inv_id


# ---------------------------------------------------------------------------
# Unit normalisation in shopping list
# ---------------------------------------------------------------------------


async def test_shopping_list_unit_normalisation(client, db):
    """Same ingredient in g and cups aggregates to a single grams line item."""
    recipe_a = await _make_recipe(
        client, "Bread", servings=1,
        ingredients=[
            {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 200, "unit": "g"},
        ],
    )
    recipe_b = await _make_recipe(
        client, "Pancakes", servings=1,
        ingredients=[
            {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 1, "unit": "cup"},
        ],
    )

    # Add both recipes to different meal slots on the same week
    await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={"day_of_week": 0, "meal_slot": "dinner", "recipe_id": recipe_a["id"], "servings": 1},
    )
    await client.put(
        f"/meal-plan/{WEEK}/entry",
        json={"day_of_week": 0, "meal_slot": "lunch", "recipe_id": recipe_b["id"], "servings": 1},
    )

    r = await client.get(f"/meal-plan/{WEEK}/shopping-list")
    assert r.status_code == 200
    items = r.json()["items"]

    flour_items = [i for i in items if i["catalogue_path"] == "materials/flour"]
    assert len(flour_items) == 1, "Expected single aggregated flour line item, not two"
    assert flour_items[0]["unit"] == "g"
    # 200g + 1 cup (240g water density) = 440g
    assert flour_items[0]["required_quantity"] == 440.0
