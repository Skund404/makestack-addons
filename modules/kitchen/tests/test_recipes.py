"""Tests for kitchen recipe and nutrition endpoints (K2)."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB, create_test_app

# ---------------------------------------------------------------------------
# Load kitchen modules by file path (same mechanism the shell loader uses).
# The kitchen module root is NOT on sys.path to avoid shadowing the shell's
# backend namespace package.
# ---------------------------------------------------------------------------

_KITCHEN_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND_DIR = os.path.join(_KITCHEN_ROOT, "backend")


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
routes_mod = _load_kitchen("routes", "backend/routes.py")
nutrition_mod = _load_kitchen("nutrition", "backend/nutrition.py")

router = routes_mod.router
calculate_recipe_nutrition = nutrition_mod.calculate_recipe_nutrition


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
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BOLOGNESE_BODY = {
    "title": "Spaghetti Bolognese",
    "servings": 4,
    "prep_time_mins": 15,
    "cook_time_mins": 45,
    "cuisine_tag": "italian",
    "ingredients": [
        {"catalogue_path": "materials/spaghetti", "name": "Spaghetti",
         "quantity": 400, "unit": "g"},
        {"catalogue_path": "materials/beef-mince", "name": "Beef Mince",
         "quantity": 500, "unit": "g"},
    ],
}


# ---------------------------------------------------------------------------
# Recipe CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_recipe_returns_201(client):
    resp = await client.post("/recipes", json=_BOLOGNESE_BODY)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_recipe_metadata(client):
    body = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()
    assert body["title"] == "Spaghetti Bolognese"
    assert body["servings"] == 4
    assert body["prep_time_mins"] == 15
    assert body["cook_time_mins"] == 45
    assert body["total_time_mins"] == 60
    assert body["cuisine_tag"] == "italian"
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_recipe_writes_ingredients(client, db):
    body = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()
    recipe_id = body["id"]

    rows = await db.fetch_all(
        "SELECT * FROM kitchen_recipe_ingredients WHERE recipe_id = ?", [recipe_id]
    )
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert names == {"Spaghetti", "Beef Mince"}


@pytest.mark.asyncio
async def test_create_recipe_response_includes_ingredients(client):
    body = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()
    assert len(body["ingredients"]) == 2
    paths = {i["catalogue_path"] for i in body["ingredients"]}
    assert paths == {"materials/spaghetti", "materials/beef-mince"}


@pytest.mark.asyncio
async def test_create_recipe_cook_summary_zero(client):
    body = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()
    assert body["cook_summary"]["total_cooks"] == 0
    assert body["cook_summary"]["avg_rating"] is None
    assert body["cook_summary"]["last_cooked_at"] is None


@pytest.mark.asyncio
async def test_get_recipe_includes_ingredients(client):
    create_body = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()
    recipe_id = create_body["id"]

    resp = await client.get(f"/recipes/{recipe_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == recipe_id
    assert len(body["ingredients"]) == 2


@pytest.mark.asyncio
async def test_get_recipe_404(client):
    resp = await client.get("/recipes/does-not-exist")
    assert resp.status_code == 404
    assert "suggestion" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_recipes_pagination(client):
    for i in range(3):
        await client.post("/recipes", json={**_BOLOGNESE_BODY, "title": f"Recipe {i}"})

    resp = await client.get("/recipes?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_list_recipes_filter_cuisine(client):
    await client.post("/recipes", json={**_BOLOGNESE_BODY, "cuisine_tag": "italian"})
    await client.post("/recipes", json={**_BOLOGNESE_BODY, "title": "Pad Thai", "cuisine_tag": "thai"})

    resp = await client.get("/recipes?cuisine_tag=italian")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["cuisine_tag"] == "italian"


@pytest.mark.asyncio
async def test_list_recipes_search_by_title(client):
    await client.post("/recipes", json={**_BOLOGNESE_BODY, "title": "Pasta Carbonara"})
    await client.post("/recipes", json={**_BOLOGNESE_BODY, "title": "Beef Stew"})

    resp = await client.get("/recipes?search=carbonara")
    body = resp.json()
    assert body["total"] == 1
    assert "Carbonara" in body["items"][0]["title"]


@pytest.mark.asyncio
async def test_list_recipes_search_by_ingredient(client):
    chicken_recipe = {
        **_BOLOGNESE_BODY,
        "title": "Chicken Curry",
        "ingredients": [
            {"catalogue_path": "materials/chicken", "name": "Chicken Breast",
             "quantity": 500, "unit": "g"},
        ],
    }
    await client.post("/recipes", json=chicken_recipe)
    await client.post("/recipes", json=_BOLOGNESE_BODY)

    resp = await client.get("/recipes?search=Chicken+Breast")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Chicken Curry"


@pytest.mark.asyncio
async def test_update_recipe_metadata(client):
    recipe_id = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()["id"]

    resp = await client.put(f"/recipes/{recipe_id}", json={"cook_time_mins": 60})
    assert resp.status_code == 200
    assert resp.json()["cook_time_mins"] == 60
    assert resp.json()["total_time_mins"] == 75  # 15 prep + 60 cook


@pytest.mark.asyncio
async def test_update_recipe_replaces_ingredients(client):
    recipe_id = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()["id"]

    new_ingredients = [
        {"catalogue_path": "materials/pasta", "name": "Pasta", "quantity": 200, "unit": "g"},
    ]
    resp = await client.put(f"/recipes/{recipe_id}", json={"ingredients": new_ingredients})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["ingredients"]) == 1
    assert body["ingredients"][0]["name"] == "Pasta"


@pytest.mark.asyncio
async def test_update_recipe_none_ingredients_preserves_existing(client):
    recipe_id = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()["id"]

    # Omitting ingredients key entirely (None) should not touch existing rows
    resp = await client.put(f"/recipes/{recipe_id}", json={"title": "New Title"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "New Title"
    assert len(body["ingredients"]) == 2  # original ingredients unchanged


@pytest.mark.asyncio
async def test_update_recipe_404(client):
    resp = await client.put("/recipes/no-such-recipe", json={"title": "x"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Nutrition calculation — pure function tests (no HTTP needed)
# ---------------------------------------------------------------------------

_FLOUR_NUTR = {
    "calories_per_100g": 364.0, "protein_g": 10.0, "fat_g": 1.2,
    "carbs_g": 76.0, "fiber_g": 2.7, "sugar_g": 0.3, "sodium_mg": 2.0,
}
_BUTTER_NUTR = {
    "calories_per_100g": 717.0, "protein_g": 0.9, "fat_g": 81.0,
    "carbs_g": 0.1, "fiber_g": 0.0, "sugar_g": 0.1, "sodium_mg": 576.0,
}


def test_nutrition_calculation_arithmetic():
    """Per-serving totals match hand-calculated expected values."""
    ingredients = [
        {"catalogue_path": "materials/flour",  "name": "Flour",  "quantity": 200.0, "unit": "g"},
        {"catalogue_path": "materials/butter", "name": "Butter", "quantity": 100.0, "unit": "g"},
    ]
    nutrition_map = {
        "materials/flour":  _FLOUR_NUTR,
        "materials/butter": _BUTTER_NUTR,
    }
    per_serving, warnings = calculate_recipe_nutrition(ingredients, nutrition_map, serves=4)

    # Total calories = (200/100)*364 + (100/100)*717 = 728 + 717 = 1445
    # Per serving = 1445 / 4 = 361.25
    assert per_serving["calories"] == pytest.approx(361.25, rel=1e-3)
    # Total protein_g = (200/100)*10 + (100/100)*0.9 = 20 + 0.9 = 20.9
    # Per serving = 20.9 / 4 = 5.225 → rounded to 5.22 or 5.23 depending on rounding
    assert per_serving["protein_g"] == pytest.approx(5.225, rel=1e-3)
    assert warnings == []


def test_nutrition_calculation_serves_1():
    ingredients = [
        {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 100.0, "unit": "g"},
    ]
    nutrition_map = {"materials/flour": _FLOUR_NUTR}
    per_serving, warnings = calculate_recipe_nutrition(ingredients, nutrition_map, serves=1)

    assert per_serving["calories"] == pytest.approx(364.0, rel=1e-3)
    assert warnings == []


def test_nutrition_calculation_unit_conversion():
    """1 kg flour = 1000 g — result should match 1000g hand calculation."""
    ingredients = [
        {"catalogue_path": "materials/flour", "name": "Flour", "quantity": 1.0, "unit": "kg"},
    ]
    nutrition_map = {"materials/flour": _FLOUR_NUTR}
    per_serving, warnings = calculate_recipe_nutrition(ingredients, nutrition_map, serves=1)

    # 1kg = 1000g → (1000/100)*364 = 3640 calories
    assert per_serving["calories"] == pytest.approx(3640.0, rel=1e-3)
    assert warnings == []


def test_nutrition_calculation_missing_ingredient():
    """Ingredients with no nutrition data are skipped and named in warnings."""
    ingredients = [
        {"catalogue_path": "materials/flour",       "name": "Flour",       "quantity": 200.0, "unit": "g"},
        {"catalogue_path": "materials/secret-spice","name": "Secret Spice","quantity": 5.0,   "unit": "g"},
    ]
    nutrition_map = {"materials/flour": _FLOUR_NUTR}  # secret-spice absent

    per_serving, warnings = calculate_recipe_nutrition(ingredients, nutrition_map, serves=1)

    assert any("Secret Spice" in w for w in warnings)
    # Flour contribution still calculated
    assert per_serving["calories"] == pytest.approx((200.0 / 100.0) * 364.0, rel=1e-3)


def test_nutrition_calculation_unconvertible_unit():
    """Ingredients with unconvertible units (e.g. 'pinch') are skipped with a warning."""
    ingredients = [
        {"catalogue_path": "materials/flour", "name": "Flour",  "quantity": 100.0, "unit": "g"},
        {"catalogue_path": "materials/salt",  "name": "Salt",   "quantity": 1.0,   "unit": "pinch"},
    ]
    salt_nutr = {"calories_per_100g": 0.0, "protein_g": 0.0, "fat_g": 0.0,
                 "carbs_g": 0.0, "fiber_g": 0.0, "sugar_g": 0.0, "sodium_mg": 38758.0}
    nutrition_map = {"materials/flour": _FLOUR_NUTR, "materials/salt": salt_nutr}

    per_serving, warnings = calculate_recipe_nutrition(ingredients, nutrition_map, serves=1)

    assert any("Salt" in w and "pinch" in w for w in warnings)
    assert per_serving["calories"] == pytest.approx(364.0, rel=1e-3)  # only flour


def test_nutrition_calculation_all_missing_returns_zeros():
    """All ingredients missing data → all zeros, no crash."""
    ingredients = [
        {"catalogue_path": "materials/mystery", "name": "Mystery", "quantity": 100.0, "unit": "g"},
    ]
    per_serving, warnings = calculate_recipe_nutrition(ingredients, {}, serves=2)

    assert len(warnings) == 1
    assert per_serving["calories"] == 0.0


# ---------------------------------------------------------------------------
# Nutrition endpoints (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_ingredient_nutrition_creates_row(client, db):
    resp = await client.post("/nutrition/ingredient", json={
        "catalogue_path": "materials/flour",
        "calories_per_100g": 364.0,
        "protein_g": 10.0,
    })
    assert resp.status_code == 201
    row = await db.fetch_one(
        "SELECT * FROM kitchen_ingredient_nutrition WHERE catalogue_path = ?",
        ["materials/flour"],
    )
    assert row is not None
    assert row["calories_per_100g"] == 364.0


@pytest.mark.asyncio
async def test_set_ingredient_nutrition_upserts(client):
    await client.post("/nutrition/ingredient", json={
        "catalogue_path": "materials/flour",
        "calories_per_100g": 364.0,
    })
    resp = await client.post("/nutrition/ingredient", json={
        "catalogue_path": "materials/flour",
        "calories_per_100g": 370.0,
        "protein_g": 12.0,
    })
    assert resp.status_code == 201
    assert resp.json()["calories_per_100g"] == 370.0
    assert resp.json()["protein_g"] == 12.0


@pytest.mark.asyncio
async def test_get_recipe_nutrition_null_when_not_set(client):
    recipe_id = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()["id"]
    resp = await client.get(f"/recipes/{recipe_id}/nutrition")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_calculate_nutrition_endpoint(client):
    # Set up ingredient nutrition
    for path, nutr in [
        ("materials/spaghetti", {"calories_per_100g": 157.0, "protein_g": 5.8,
                                  "fat_g": 0.9, "carbs_g": 30.9, "fiber_g": 1.8,
                                  "sugar_g": 0.6, "sodium_mg": 1.0}),
        ("materials/beef-mince", {"calories_per_100g": 215.0, "protein_g": 26.1,
                                   "fat_g": 12.0, "carbs_g": 0.0, "fiber_g": 0.0,
                                   "sugar_g": 0.0, "sodium_mg": 75.0}),
    ]:
        await client.post("/nutrition/ingredient", json={"catalogue_path": path, **nutr})

    recipe_id = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()["id"]
    resp = await client.post(f"/recipes/{recipe_id}/nutrition/calculate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "calculated"
    assert body["warnings"] == []
    assert body["calories"] > 0


@pytest.mark.asyncio
async def test_calculate_nutrition_with_save(client, db):
    for path, nutr in [
        ("materials/spaghetti", {"calories_per_100g": 157.0, "protein_g": 5.8,
                                  "fat_g": 0.9, "carbs_g": 30.9, "fiber_g": 1.8,
                                  "sugar_g": 0.6, "sodium_mg": 1.0}),
        ("materials/beef-mince", {"calories_per_100g": 215.0, "protein_g": 26.1,
                                   "fat_g": 12.0, "carbs_g": 0.0, "fiber_g": 0.0,
                                   "sugar_g": 0.0, "sodium_mg": 75.0}),
    ]:
        await client.post("/nutrition/ingredient", json={"catalogue_path": path, **nutr})

    recipe_id = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()["id"]
    await client.post(f"/recipes/{recipe_id}/nutrition/calculate?save=true")

    row = await db.fetch_one(
        "SELECT * FROM kitchen_recipe_nutrition WHERE recipe_id = ?", [recipe_id]
    )
    assert row is not None
    assert row["calories"] is not None
    assert row["per_servings"] == 4


@pytest.mark.asyncio
async def test_calculate_nutrition_missing_data_returns_warnings(client):
    # No nutrition data seeded for bolognese ingredients
    recipe_id = (await client.post("/recipes", json=_BOLOGNESE_BODY)).json()["id"]
    resp = await client.post(f"/recipes/{recipe_id}/nutrition/calculate")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["warnings"]) == 2  # both ingredients have no data
