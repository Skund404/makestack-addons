"""Kitchen module routes — recipe CRUD and nutrition endpoints (K2).

NOTE ON IMPORTS
--------------
The shell loader imports this file by absolute file path via importlib
(spec_from_file_location), so the kitchen module root is NOT on sys.path.
Internal kitchen imports (models, nutrition) are therefore loaded the same
way — via _kitchen_import() — rather than `from backend.models import ...`.
"""

from __future__ import annotations

import importlib.util
import json as _json
import os
import sys
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from makestack_sdk.userdb import get_module_userdb_factory, ModuleUserDB
from makestack_sdk.peers import PeerModules, get_peer_modules


# ---------------------------------------------------------------------------
# Internal module loader
# ---------------------------------------------------------------------------


def _kitchen_import(name: str):
    """Load a sibling Python file from the kitchen backend directory.

    Uses a stable sys.modules key so repeated calls return the cached module.
    This mirrors how the shell loader itself imports migration and route files.
    """
    key = f"_kitchen_backend_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load kitchen backend module: {name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_m = _kitchen_import("models")
_n = _kitchen_import("nutrition")
_s = _kitchen_import("shopping")

# Models
RecipeCreate = _m.RecipeCreate
RecipeUpdate = _m.RecipeUpdate
IngredientNutritionCreate = _m.IngredientNutritionCreate
MealPlanEntryCreate = _m.MealPlanEntryCreate
CookLogCreate = _m.CookLogCreate
BulkStockItem = _m.BulkStockItem
StockAliasCreate = _m.StockAliasCreate

# Nutrition calculator
calculate_recipe_nutrition = _n.calculate_recipe_nutrition

# Shopping list builder
build_shopping_list = _s.build_shopping_list


# ---------------------------------------------------------------------------
# Router + dependency
# ---------------------------------------------------------------------------

router = APIRouter()

# All kitchen_ tables plus cross-module read-only tables.
get_db = get_module_userdb_factory(
    module_name="kitchen",
    allowed_tables=[
        "kitchen_recipes",
        "kitchen_recipe_ingredients",
        "kitchen_recipe_nutrition",
        "kitchen_ingredient_nutrition",
        "kitchen_meal_plan",
        "kitchen_meal_plan_entries",
        "kitchen_cook_log",
        "kitchen_locations",
        "kitchen_stock_aliases",
        "kitchen_stock_metadata",
        "inventory_stock_items",  # read-only; declared in manifest read_tables
        "inventory",              # Shell-core table; needed for catalogue_path JOIN
    ],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _total_time(prep: int | None, cook: int | None) -> int | None:
    total = (prep or 0) + (cook or 0)
    return total if total > 0 else None


async def _fetch_recipe_full(db: ModuleUserDB, recipe_id: str) -> dict | None:
    """Fetch a recipe with its ingredients, nutrition, and cook summary."""
    row = await db.fetch_one(
        "SELECT * FROM kitchen_recipes WHERE id = ?", [recipe_id]
    )
    if not row:
        return None

    r = dict(row)

    ingredients = await db.fetch_all(
        "SELECT * FROM kitchen_recipe_ingredients WHERE recipe_id = ? ORDER BY rowid",
        [recipe_id],
    )

    nutrition_row = await db.fetch_one(
        "SELECT * FROM kitchen_recipe_nutrition WHERE recipe_id = ?", [recipe_id]
    )

    cook_row = await db.fetch_one(
        "SELECT COUNT(*) as total_cooks, MAX(cooked_at) as last_cooked_at, "
        "AVG(CAST(rating AS REAL)) as avg_rating "
        "FROM kitchen_cook_log WHERE recipe_id = ?",
        [recipe_id],
    )

    r["ingredients"] = [dict(i) for i in ingredients]
    r["nutrition"] = dict(nutrition_row) if nutrition_row else None
    r["cook_summary"] = {
        "total_cooks": (cook_row["total_cooks"] if cook_row else 0) or 0,
        "avg_rating": (
            round(cook_row["avg_rating"], 1)
            if cook_row and cook_row["avg_rating"] is not None
            else None
        ),
        "last_cooked_at": cook_row["last_cooked_at"] if cook_row else None,
    }
    r["total_time_mins"] = _total_time(r.get("prep_time_mins"), r.get("cook_time_mins"))

    return r


# ---------------------------------------------------------------------------
# GET /recipes
# IMPORTANT: static sub-paths (e.g. /recipes/can-make added in K4) must be
# declared BEFORE this parameterized route to avoid can-make being treated as
# a recipe_id. Add them immediately above this handler when implementing K4.
# ---------------------------------------------------------------------------


@router.get("/recipes")
async def list_recipes(
    cuisine_tag: str | None = Query(None),
    max_cook_time: int | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: ModuleUserDB = Depends(get_db),
):
    """List recipes with optional filters. Supports pagination."""
    conditions: list[str] = []
    params: list = []

    if cuisine_tag:
        conditions.append("r.cuisine_tag = ?")
        params.append(cuisine_tag)

    if max_cook_time is not None:
        conditions.append("(r.cook_time_mins IS NULL OR r.cook_time_mins <= ?)")
        params.append(max_cook_time)

    if search:
        like = f"%{search}%"
        conditions.append(
            "(r.title LIKE ? OR EXISTS("
            "SELECT 1 FROM kitchen_recipe_ingredients i "
            "WHERE i.recipe_id = r.id AND i.name LIKE ?"
            "))"
        )
        params.extend([like, like])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_row = await db.fetch_one(
        f"SELECT COUNT(*) as n FROM kitchen_recipes r {where}", params or None
    )
    total = (count_row["n"] if count_row else 0) or 0

    rows = await db.fetch_all(
        f"""
        SELECT
            r.id, r.title, r.servings, r.prep_time_mins, r.cook_time_mins, r.cuisine_tag,
            r.created_at, r.updated_at,
            (SELECT COUNT(*) FROM kitchen_cook_log WHERE recipe_id = r.id) AS cook_count,
            (SELECT MAX(cooked_at) FROM kitchen_cook_log WHERE recipe_id = r.id) AS last_cooked_at
        FROM kitchen_recipes r
        {where}
        ORDER BY r.updated_at DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    )

    items = []
    for row in rows:
        d = dict(row)
        d["total_time_mins"] = _total_time(d.get("prep_time_mins"), d.get("cook_time_mins"))
        items.append(d)

    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# GET /recipes/can-make
# MUST remain before GET /recipes/{recipe_id} — FastAPI matches in declaration
# order, so "can-make" would otherwise be treated as a recipe_id wildcard.
# ---------------------------------------------------------------------------

_STOCK_BY_PATH_SQL = """
    SELECT inv.catalogue_path, SUM(isi.quantity) AS total_qty
    FROM inventory_stock_items isi
    JOIN inventory inv ON isi.inventory_id = inv.id
    GROUP BY inv.catalogue_path
"""


@router.get("/recipes/can-make")
async def can_make_recipes(
    strict: bool = Query(False),
    db: ModuleUserDB = Depends(get_db),
):
    """Return recipes that can be made (strict=True) or nearly made (strict=False, ≤1 missing)."""
    max_missing = 0 if strict else 1

    rows = await db.fetch_all(
        f"""
        SELECT
            r.id, r.title, r.prep_time_mins, r.cook_time_mins, r.servings,
            COUNT(i.id) AS total_ingredients,
            SUM(CASE WHEN COALESCE(s.total_qty, 0) > 0 THEN 1 ELSE 0 END) AS in_stock_count
        FROM kitchen_recipes r
        JOIN kitchen_recipe_ingredients i ON i.recipe_id = r.id
        LEFT JOIN ({_STOCK_BY_PATH_SQL}) s ON s.catalogue_path = i.catalogue_path
        GROUP BY r.id
        """
    )

    results = []
    for row in rows:
        total = row["total_ingredients"] or 0
        in_stock = row["in_stock_count"] or 0
        missing = total - in_stock

        if missing > max_missing:
            continue

        ing_rows = await db.fetch_all(
            f"""
            SELECT i.id, i.name, i.catalogue_path, i.quantity, i.unit,
                   COALESCE(s.total_qty, 0) AS in_stock_qty
            FROM kitchen_recipe_ingredients i
            LEFT JOIN ({_STOCK_BY_PATH_SQL}) s ON s.catalogue_path = i.catalogue_path
            WHERE i.recipe_id = ?
            """,
            [row["id"]],
        )

        ingredients = []
        for ing in ing_rows:
            d = dict(ing)
            d["status"] = "ok" if float(ing["in_stock_qty"]) > 0 else "missing"
            ingredients.append(d)

        results.append(
            {
                "recipe_id": row["id"],
                "recipe_title": row["title"],
                "can_make": missing == 0,
                "missing_count": missing,
                "prep_time_mins": row["prep_time_mins"],
                "cook_time_mins": row["cook_time_mins"],
                "ingredients": ingredients,
            }
        )

    return {"recipes": results, "total": len(results)}


@router.get("/recipes/{recipe_id}/stock-check")
async def stock_check_recipe(
    recipe_id: str,
    serves: int | None = Query(None),
    db: ModuleUserDB = Depends(get_db),
):
    """Return per-ingredient stock status for a recipe, optionally scaled to a serving count."""
    recipe = await db.fetch_one(
        "SELECT * FROM kitchen_recipes WHERE id = ?", [recipe_id]
    )
    if not recipe:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Recipe not found",
                "recipe_id": recipe_id,
                "suggestion": "Use GET /recipes to list available recipes",
            },
        )

    recipe_servings = max(recipe["servings"] or 1, 1)
    target_serves = serves or recipe_servings
    scale = target_serves / recipe_servings

    ing_rows = await db.fetch_all(
        f"""
        SELECT i.id, i.name, i.catalogue_path, i.quantity, i.unit,
               COALESCE(s.total_qty, 0) AS in_stock_qty
        FROM kitchen_recipe_ingredients i
        LEFT JOIN ({_STOCK_BY_PATH_SQL}) s ON s.catalogue_path = i.catalogue_path
        WHERE i.recipe_id = ?
        """,
        [recipe_id],
    )

    ingredients = []
    for row in ing_rows:
        required_qty = float(row["quantity"]) * scale
        in_stock_qty = float(row["in_stock_qty"])
        if in_stock_qty == 0:
            status = "missing"
        elif in_stock_qty < required_qty:
            status = "low"
        else:
            status = "ok"
        ingredients.append(
            {
                "name": row["name"],
                "catalogue_path": row["catalogue_path"],
                "quantity": row["quantity"],
                "unit": row["unit"],
                "required_qty": round(required_qty, 3),
                "in_stock_qty": round(in_stock_qty, 3),
                "status": status,
            }
        )

    missing_count = sum(1 for i in ingredients if i["status"] == "missing")
    can_make = all(i["status"] == "ok" for i in ingredients) if ingredients else True
    return {
        "recipe_id": recipe_id,
        "recipe_title": recipe["title"],
        "can_make": can_make,
        "missing_count": missing_count,
        "ingredients": ingredients,
    }


@router.get("/recipes/{recipe_id}")
async def get_recipe(recipe_id: str, db: ModuleUserDB = Depends(get_db)):
    """Return full recipe with ingredients, nutrition, and cook summary."""
    result = await _fetch_recipe_full(db, recipe_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Recipe not found",
                "recipe_id": recipe_id,
                "suggestion": "Use GET /recipes to list available recipes",
            },
        )
    return result


@router.post("/recipes", status_code=201)
async def create_recipe(body: RecipeCreate, db: ModuleUserDB = Depends(get_db)):
    """Create a new recipe, including all ingredient rows."""
    recipe_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """
        INSERT INTO kitchen_recipes
            (id, title, description, workflow_id, cuisine_tag,
             prep_time_mins, cook_time_mins, servings, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            recipe_id, body.title, body.description, body.workflow_id, body.cuisine_tag,
            body.prep_time_mins, body.cook_time_mins, body.servings, body.notes, now, now,
        ],
    )

    for ing in body.ingredients:
        await db.execute(
            """
            INSERT INTO kitchen_recipe_ingredients
                (id, recipe_id, catalogue_path, name, quantity, unit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [str(uuid.uuid4()), recipe_id, ing.catalogue_path, ing.name,
             ing.quantity, ing.unit, ing.notes],
        )

    return await _fetch_recipe_full(db, recipe_id)


@router.put("/recipes/{recipe_id}")
async def update_recipe(
    recipe_id: str,
    body: RecipeUpdate,
    db: ModuleUserDB = Depends(get_db),
):
    """Update recipe metadata and/or ingredients (full ingredient replace when provided)."""
    existing = await db.fetch_one(
        "SELECT id FROM kitchen_recipes WHERE id = ?", [recipe_id]
    )
    if not existing:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Recipe not found",
                "recipe_id": recipe_id,
                "suggestion": "Use GET /recipes to list available recipes",
            },
        )

    updates = body.model_dump(exclude={"ingredients"}, exclude_none=True)
    if updates:
        now = datetime.now(timezone.utc).isoformat()
        updates["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE kitchen_recipes SET {set_clause} WHERE id = ?",
            list(updates.values()) + [recipe_id],
        )

    if body.ingredients is not None:
        # Full replace — delete existing rows then insert new set
        await db.execute(
            "DELETE FROM kitchen_recipe_ingredients WHERE recipe_id = ?", [recipe_id]
        )
        for ing in body.ingredients:
            await db.execute(
                """
                INSERT INTO kitchen_recipe_ingredients
                    (id, recipe_id, catalogue_path, name, quantity, unit, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [str(uuid.uuid4()), recipe_id, ing.catalogue_path, ing.name,
                 ing.quantity, ing.unit, ing.notes],
            )

    return await _fetch_recipe_full(db, recipe_id)


# ---------------------------------------------------------------------------
# Nutrition endpoints
# ---------------------------------------------------------------------------


@router.get("/recipes/{recipe_id}/nutrition")
async def get_recipe_nutrition(recipe_id: str, db: ModuleUserDB = Depends(get_db)):
    """Return stored nutrition data for a recipe, or null if not set."""
    recipe = await db.fetch_one(
        "SELECT id FROM kitchen_recipes WHERE id = ?", [recipe_id]
    )
    if not recipe:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Recipe not found",
                "recipe_id": recipe_id,
                "suggestion": "Use GET /recipes to list available recipes",
            },
        )
    row = await db.fetch_one(
        "SELECT * FROM kitchen_recipe_nutrition WHERE recipe_id = ?", [recipe_id]
    )
    return dict(row) if row else None


@router.post("/nutrition/ingredient", status_code=201)
async def set_ingredient_nutrition(
    body: IngredientNutritionCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Upsert per-100g nutrition data for a catalogue ingredient."""
    now = datetime.now(timezone.utc).isoformat()

    existing = await db.fetch_one(
        "SELECT id FROM kitchen_ingredient_nutrition WHERE catalogue_path = ?",
        [body.catalogue_path],
    )

    if existing:
        updates = body.model_dump(exclude={"catalogue_path"}, exclude_none=True)
        updates["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE kitchen_ingredient_nutrition SET {set_clause} WHERE catalogue_path = ?",
            list(updates.values()) + [body.catalogue_path],
        )
    else:
        await db.execute(
            """
            INSERT INTO kitchen_ingredient_nutrition
                (id, catalogue_path, calories_per_100g, protein_g, fat_g, carbs_g,
                 fiber_g, sugar_g, sodium_mg, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()), body.catalogue_path, body.calories_per_100g,
                body.protein_g, body.fat_g, body.carbs_g, body.fiber_g,
                body.sugar_g, body.sodium_mg, body.source, now,
            ],
        )

    row = await db.fetch_one(
        "SELECT * FROM kitchen_ingredient_nutrition WHERE catalogue_path = ?",
        [body.catalogue_path],
    )
    return dict(row)


@router.post("/recipes/{recipe_id}/nutrition/calculate")
async def calculate_nutrition(
    recipe_id: str,
    save: bool = Query(False, description="Persist the result to kitchen_recipe_nutrition"),
    db: ModuleUserDB = Depends(get_db),
):
    """Calculate per-serving nutrition totals from stored ingredient data.

    Ingredients with no nutrition data or unconvertible units are skipped and
    named in the warnings list. Never calls external APIs.
    """
    recipe = await db.fetch_one(
        "SELECT * FROM kitchen_recipes WHERE id = ?", [recipe_id]
    )
    if not recipe:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Recipe not found",
                "recipe_id": recipe_id,
                "suggestion": "Use GET /recipes to list available recipes",
            },
        )

    ingredients = await db.fetch_all(
        "SELECT * FROM kitchen_recipe_ingredients WHERE recipe_id = ?", [recipe_id]
    )

    # Fetch nutrition rows for all referenced catalogue paths in one query.
    nutrition_map: dict[str, dict] = {}
    if ingredients:
        paths = [i["catalogue_path"] for i in ingredients]
        placeholders = ",".join("?" * len(paths))
        nutr_rows = await db.fetch_all(
            f"SELECT * FROM kitchen_ingredient_nutrition WHERE catalogue_path IN ({placeholders})",
            paths,
        )
        nutrition_map = {r["catalogue_path"]: dict(r) for r in nutr_rows}

    per_serving, warnings = calculate_recipe_nutrition(
        [dict(i) for i in ingredients],
        nutrition_map,
        recipe["servings"],
    )

    if save:
        now = datetime.now(timezone.utc).isoformat()
        exists = await db.fetch_one(
            "SELECT id FROM kitchen_recipe_nutrition WHERE recipe_id = ?", [recipe_id]
        )
        if exists:
            await db.execute(
                """
                UPDATE kitchen_recipe_nutrition
                SET calories=?, protein_g=?, fat_g=?, carbs_g=?, fiber_g=?,
                    sugar_g=?, sodium_mg=?, per_servings=?, updated_at=?
                WHERE recipe_id=?
                """,
                [
                    per_serving["calories"], per_serving["protein_g"], per_serving["fat_g"],
                    per_serving["carbs_g"], per_serving["fiber_g"], per_serving["sugar_g"],
                    per_serving["sodium_mg"], recipe["servings"], now, recipe_id,
                ],
            )
        else:
            await db.execute(
                """
                INSERT INTO kitchen_recipe_nutrition
                    (id, recipe_id, calories, protein_g, fat_g, carbs_g,
                     fiber_g, sugar_g, sodium_mg, per_servings, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(uuid.uuid4()), recipe_id,
                    per_serving["calories"], per_serving["protein_g"], per_serving["fat_g"],
                    per_serving["carbs_g"], per_serving["fiber_g"], per_serving["sugar_g"],
                    per_serving["sodium_mg"], recipe["servings"], now,
                ],
            )

    return {**per_serving, "source": "calculated", "warnings": warnings}


# ---------------------------------------------------------------------------
# Meal Plan endpoints
# ---------------------------------------------------------------------------


async def _get_or_create_plan(db: ModuleUserDB, week: str) -> dict:
    """Return the meal plan for a week, creating it if it does not exist."""
    plan = await db.fetch_one(
        "SELECT * FROM kitchen_meal_plan WHERE week_start = ?", [week]
    )
    if plan:
        return dict(plan)
    plan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO kitchen_meal_plan (id, week_start, notes, created_at, updated_at) "
        "VALUES (?, ?, '', ?, ?)",
        [plan_id, week, now, now],
    )
    return {"id": plan_id, "week_start": week, "notes": "", "created_at": now, "updated_at": now}


async def _plan_with_entries(db: ModuleUserDB, plan: dict) -> dict:
    entries = await db.fetch_all(
        "SELECT * FROM kitchen_meal_plan_entries WHERE plan_id = ? "
        "ORDER BY day_of_week, meal_slot",
        [plan["id"]],
    )
    result = dict(plan)
    result["entries"] = [dict(e) for e in entries]
    return result


@router.get("/meal-plan/{week}")
async def get_meal_plan(week: str, db: ModuleUserDB = Depends(get_db)):
    """Return (or auto-create) the meal plan for the given Monday ISO date."""
    plan = await _get_or_create_plan(db, week)
    return await _plan_with_entries(db, plan)


@router.put("/meal-plan/{week}/entry")
async def upsert_meal_plan_entry(
    week: str,
    body: MealPlanEntryCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Upsert a single meal slot entry within the week's plan."""
    plan = await _get_or_create_plan(db, week)
    plan_id = plan["id"]

    existing = await db.fetch_one(
        "SELECT id FROM kitchen_meal_plan_entries "
        "WHERE plan_id = ? AND day_of_week = ? AND meal_slot = ?",
        [plan_id, body.day_of_week, body.meal_slot],
    )

    if existing:
        await db.execute(
            """
            UPDATE kitchen_meal_plan_entries
            SET recipe_id = ?, servings = ?, notes = ?,
                free_text = ?, serves_override = ?
            WHERE id = ?
            """,
            [
                body.recipe_id, body.servings, body.notes,
                body.free_text, body.serves_override, existing["id"],
            ],
        )
        entry_id = existing["id"]
    else:
        entry_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO kitchen_meal_plan_entries
                (id, plan_id, day_of_week, meal_slot, recipe_id,
                 servings, notes, free_text, serves_override)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entry_id, plan_id, body.day_of_week, body.meal_slot,
                body.recipe_id, body.servings, body.notes,
                body.free_text, body.serves_override,
            ],
        )

    row = await db.fetch_one(
        "SELECT * FROM kitchen_meal_plan_entries WHERE id = ?", [entry_id]
    )
    return dict(row)


@router.get("/meal-plan/{week}/shopping-list")
async def get_shopping_list(week: str, db: ModuleUserDB = Depends(get_db)):
    """Return aggregated shopping list for the week, minus on-hand stock."""
    plan = await db.fetch_one(
        "SELECT * FROM kitchen_meal_plan WHERE week_start = ?", [week]
    )
    if not plan:
        return {"week_start": week, "items": [], "total_items": 0}

    entries = await db.fetch_all(
        "SELECT * FROM kitchen_meal_plan_entries WHERE plan_id = ?", [plan["id"]]
    )
    items = await build_shopping_list([dict(e) for e in entries], db)
    return {"week_start": week, "items": items, "total_items": len(items)}


# ---------------------------------------------------------------------------
# Cook Log endpoints
# ---------------------------------------------------------------------------


@router.post("/cook-log", status_code=201)
async def create_cook_log(
    body: CookLogCreate,
    db: ModuleUserDB = Depends(get_db),
    peers: PeerModules = Depends(get_peer_modules),
):
    """Record a cooking session and attempt to deduct stock via inventory-stock peer."""
    recipe = await db.fetch_one(
        "SELECT * FROM kitchen_recipes WHERE id = ?", [body.recipe_id]
    )
    if not recipe:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Recipe not found",
                "recipe_id": body.recipe_id,
                "suggestion": "Use GET /recipes to list available recipes",
            },
        )

    ingredients = await db.fetch_all(
        "SELECT * FROM kitchen_recipe_ingredients WHERE recipe_id = ?",
        [body.recipe_id],
    )

    recipe_servings = max(recipe["servings"] or 1, 1)
    serves_made = max(body.serves_made or recipe_servings, 1)
    scale = serves_made / recipe_servings

    # Build intended pull list (scaled quantities).
    material_pulls: list[dict] = []
    for ing in ingredients:
        material_pulls.append(
            {
                "catalogue_path": ing["catalogue_path"],
                "name": ing["name"],
                "quantity": round(float(ing["quantity"]) * scale, 4),
                "unit": ing["unit"],
                "deducted": False,
            }
        )

    stock_deducted = 0
    warnings: list[str] = []

    if peers.is_installed("inventory-stock"):
        deducted_count = 0
        for pull in material_pulls:
            try:
                stock_row = await db.fetch_one(
                    """
                    SELECT isi.id, isi.quantity
                    FROM inventory_stock_items isi
                    JOIN inventory ii ON isi.inventory_id = ii.id
                    WHERE ii.catalogue_path = ?
                    LIMIT 1
                    """,
                    [pull["catalogue_path"]],
                )
                if stock_row:
                    new_qty = max(0.0, float(stock_row["quantity"]) - pull["quantity"])
                    await peers.call(
                        "inventory-stock",
                        "PUT",
                        f"/stock/{stock_row['id']}",
                        body={"quantity": new_qty},
                    )
                    pull["deducted"] = True
                    deducted_count += 1
                else:
                    warnings.append(f"{pull['name']}: no stock item found")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{pull['name']}: deduction failed — {exc}")
        if deducted_count > 0:
            stock_deducted = 1
    else:
        warnings.append("inventory-stock not installed; stock not deducted")

    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO kitchen_cook_log
            (id, recipe_id, cooked_at, serves_made, rating, notes,
             stock_deducted, material_pulls_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            log_id, body.recipe_id, body.cooked_at, serves_made,
            body.rating, body.notes, stock_deducted,
            _json.dumps(material_pulls),
        ],
    )

    row = await db.fetch_one(
        "SELECT * FROM kitchen_cook_log WHERE id = ?", [log_id]
    )
    result = dict(row)
    result["warnings"] = warnings
    return result


@router.get("/cook-log")
async def list_cook_log(
    recipe_id: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    min_rating: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: ModuleUserDB = Depends(get_db),
):
    """List cooking sessions with optional filters. Supports pagination."""
    conditions: list[str] = []
    params: list = []

    if recipe_id:
        conditions.append("recipe_id = ?")
        params.append(recipe_id)
    if from_date:
        conditions.append("cooked_at >= ?")
        params.append(from_date)
    if to_date:
        conditions.append("cooked_at <= ?")
        params.append(to_date)
    if min_rating is not None:
        conditions.append("rating >= ?")
        params.append(min_rating)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_row = await db.fetch_one(
        f"SELECT COUNT(*) as n FROM kitchen_cook_log {where}", params or None
    )
    total = (count_row["n"] if count_row else 0) or 0

    rows = await db.fetch_all(
        f"SELECT * FROM kitchen_cook_log {where} ORDER BY cooked_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )

    items = []
    for row in rows:
        d = dict(row)
        d["warnings"] = []  # warnings only surfaced at creation time
        items.append(d)

    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# GET /stock — list stock with optional location filter
# Joins inventory_stock_items + inventory + kitchen_stock_metadata.
# Must be declared before /stock/aliases/lookup and /stock/expiring to keep
# the static sub-paths (/aliases/..., /expiring) matched before the bare /stock.
# ---------------------------------------------------------------------------


@router.get("/stock")
async def list_stock(
    location: str | None = Query(None, description="Filter by location key (pantry/fridge/freezer/other)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: ModuleUserDB = Depends(get_db),
):
    """List stock items, optionally filtered by location.

    Joins inventory_stock_items with inventory (for catalogue_path) and
    kitchen_stock_metadata (for expiry_date / frozen_on_date).
    """
    where = "WHERE 1=1"
    params: list = []
    if location:
        where += " AND isi.location = ?"
        params.append(location)

    total_row = await db.fetch_one(
        f"SELECT COUNT(*) AS n FROM inventory_stock_items isi {where}",
        params,
    )
    total = total_row["n"] if total_row else 0

    rows = await db.fetch_all(
        f"""
        SELECT
            isi.id,
            inv.catalogue_path,
            isi.quantity,
            isi.unit,
            isi.location,
            isi.notes,
            m.expiry_date,
            m.frozen_on_date
        FROM inventory_stock_items isi
        JOIN inventory inv ON inv.id = isi.inventory_id
        LEFT JOIN kitchen_stock_metadata m ON m.stock_item_id = isi.id
        {where}
        ORDER BY inv.catalogue_path
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    )

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Stock alias endpoints
# NOTE: GET /stock/aliases/lookup must be declared before any GET /stock/{id}
# route that may be added in a later phase.
# ---------------------------------------------------------------------------


@router.get("/stock/aliases/lookup")
async def lookup_stock_alias(
    text: str = Query(..., description="Receipt text to look up"),
    db: ModuleUserDB = Depends(get_db),
):
    """Return the alias record for the given receipt text, or null if not found."""
    row = await db.fetch_one(
        "SELECT * FROM kitchen_stock_aliases WHERE receipt_text = ?", [text]
    )
    return dict(row) if row else None


@router.post("/stock/aliases", status_code=201)
async def create_stock_alias(
    body: StockAliasCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Upsert a receipt-text → catalogue_path alias."""
    now = datetime.now(timezone.utc).isoformat()

    existing = await db.fetch_one(
        "SELECT id FROM kitchen_stock_aliases WHERE receipt_text = ?",
        [body.receipt_text],
    )

    if existing:
        await db.execute(
            "UPDATE kitchen_stock_aliases SET catalogue_path = ? WHERE id = ?",
            [body.catalogue_path, existing["id"]],
        )
        alias_id = existing["id"]
    else:
        alias_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO kitchen_stock_aliases (id, receipt_text, catalogue_path, created_at) "
            "VALUES (?, ?, ?, ?)",
            [alias_id, body.receipt_text, body.catalogue_path, now],
        )

    row = await db.fetch_one(
        "SELECT * FROM kitchen_stock_aliases WHERE id = ?", [alias_id]
    )
    return dict(row)


# ---------------------------------------------------------------------------
# GET /stock/expiring — kitchen_stock_metadata expiry window
# NOTE: declared before GET /stock/bulk to keep static paths first.
# ---------------------------------------------------------------------------


@router.get("/stock/expiring")
async def list_expiring_stock(
    days: int = Query(7, ge=0, le=365, description="Items expiring within this many days"),
    db: ModuleUserDB = Depends(get_db),
):
    """Return stock items that have an expiry date within the given day window.

    Reads from kitchen_stock_metadata (expiry_date) joined with
    inventory_stock_items and inventory for catalogue_path context.
    Items with no expiry_date recorded are excluded.
    """
    from datetime import date, timedelta

    cutoff = (date.today() + timedelta(days=days)).isoformat()

    rows = await db.fetch_all(
        """
        SELECT
            m.stock_item_id,
            m.expiry_date,
            CAST(
                (julianday(m.expiry_date) - julianday('now'))
                AS INTEGER
            ) AS days_until_expiry,
            inv.id        AS inventory_id,
            inv.catalogue_path,
            isi.quantity,
            isi.unit,
            isi.location
        FROM kitchen_stock_metadata m
        JOIN inventory_stock_items isi ON isi.id = m.stock_item_id
        JOIN inventory inv ON inv.id = isi.inventory_id
        WHERE m.expiry_date IS NOT NULL
          AND m.expiry_date <= ?
        ORDER BY m.expiry_date
        """,
        [cutoff],
    )

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Bulk stock update
# ---------------------------------------------------------------------------


@router.post("/stock/bulk")
async def bulk_update_stock(
    body: list[BulkStockItem],
    db: ModuleUserDB = Depends(get_db),
    peers: PeerModules = Depends(get_peer_modules),
):
    """Batch update or create stock items.

    For each item: finds the matching inventory record by catalogue_path, then
    either updates the existing stock entry (action='set'|'add') or creates a
    new one via the inventory-stock peer.

    Partial failure is allowed — items that cannot be processed are added to
    the 'failed' list while valid items are still processed.
    """
    if not peers.is_installed("inventory-stock"):
        return {
            "updated": [],
            "created": [],
            "failed": [
                {
                    "catalogue_path": item.catalogue_path,
                    "error": "inventory-stock peer not installed",
                }
                for item in body
            ],
        }

    updated: list[dict] = []
    created: list[dict] = []
    failed: list[dict] = []

    for item in body:
        try:
            inv_row = await db.fetch_one(
                "SELECT id FROM inventory WHERE catalogue_path = ?",
                [item.catalogue_path],
            )
            if not inv_row:
                failed.append(
                    {
                        "catalogue_path": item.catalogue_path,
                        "error": "No inventory item found for this catalogue_path",
                    }
                )
                continue

            inv_id = inv_row["id"]

            stock_row = await db.fetch_one(
                "SELECT id, quantity, unit FROM inventory_stock_items WHERE inventory_id = ?",
                [inv_id],
            )

            if stock_row:
                # Update existing stock entry.
                if item.action == "add":
                    new_qty = float(stock_row["quantity"]) + item.quantity
                else:
                    new_qty = item.quantity

                result = await peers.call(
                    "inventory-stock",
                    "PUT",
                    f"/stock/{stock_row['id']}",
                    body={
                        "quantity": new_qty,
                        "unit": item.unit or stock_row["unit"] or "",
                        "location": item.location or "",
                    },
                )

                if item.expiry_date:
                    now = datetime.now(timezone.utc).isoformat()
                    meta = await db.fetch_one(
                        "SELECT id FROM kitchen_stock_metadata WHERE stock_item_id = ?",
                        [stock_row["id"]],
                    )
                    if meta:
                        await db.execute(
                            "UPDATE kitchen_stock_metadata SET expiry_date = ?, updated_at = ? "
                            "WHERE stock_item_id = ?",
                            [item.expiry_date, now, stock_row["id"]],
                        )
                    else:
                        await db.execute(
                            "INSERT INTO kitchen_stock_metadata "
                            "(id, stock_item_id, expiry_date, updated_at) VALUES (?, ?, ?, ?)",
                            [str(uuid.uuid4()), stock_row["id"], item.expiry_date, now],
                        )

                updated.append(
                    {
                        "catalogue_path": item.catalogue_path,
                        "stock_item_id": stock_row["id"],
                        "quantity": new_qty,
                    }
                )

            else:
                # No existing stock entry — create one.
                result = await peers.call(
                    "inventory-stock",
                    "POST",
                    "/stock",
                    body={
                        "inventory_id": inv_id,
                        "quantity": item.quantity,
                        "unit": item.unit,
                        "location": item.location or "",
                    },
                )

                new_stock_id = result.get("id") if isinstance(result, dict) else None

                if item.expiry_date and new_stock_id:
                    now = datetime.now(timezone.utc).isoformat()
                    await db.execute(
                        "INSERT INTO kitchen_stock_metadata "
                        "(id, stock_item_id, expiry_date, updated_at) VALUES (?, ?, ?, ?)",
                        [str(uuid.uuid4()), new_stock_id, item.expiry_date, now],
                    )

                created.append(
                    {
                        "catalogue_path": item.catalogue_path,
                        "stock_item_id": new_stock_id,
                        "quantity": item.quantity,
                    }
                )

        except Exception as exc:  # noqa: BLE001
            failed.append(
                {
                    "catalogue_path": item.catalogue_path,
                    "error": str(exc),
                }
            )

    return {"updated": updated, "created": created, "failed": failed}
