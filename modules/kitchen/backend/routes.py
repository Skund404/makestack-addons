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
from makestack_sdk.catalogue_client import (
    CatalogueClient,
    get_catalogue_client,
    CoreUnavailableError,
)


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
ShoppingItemCreate = _m.ShoppingItemCreate
ShoppingItemUpdate = _m.ShoppingItemUpdate
StockItemCreate = _m.StockItemCreate
RecipeFullCreate = _m.RecipeFullCreate
RecipeIngredientInput = _m.RecipeIngredientInput
StockItemUpdate = _m.StockItemUpdate

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
        "kitchen_shopping_list",
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


# ---------------------------------------------------------------------------
# POST /recipes/full — orchestrated recipe creation with primitive composition
# MUST remain before GET /recipes/{recipe_id} — FastAPI matches in declaration
# order, so "full" would otherwise be treated as a recipe_id wildcard.
# ---------------------------------------------------------------------------


@router.post("/recipes/full", status_code=201)
async def create_recipe_full(
    body: RecipeFullCreate,
    db: ModuleUserDB = Depends(get_db),
    catalogue: CatalogueClient = Depends(get_catalogue_client),
    peers: PeerModules = Depends(get_peer_modules),
):
    """Create a complete recipe with primitive composition.

    1. For each ingredient without catalogue_path → create a Material primitive
    2. Create a Workflow primitive with relationships to techniques/tools/materials
    3. Pin the Workflow to inventory
    4. Create kitchen_recipes + kitchen_recipe_ingredients rows
    """
    from backend.app.models import PrimitiveCreate

    # Step 1: resolve ingredients — create Material primitives for new ones
    resolved_ingredients: list[dict] = []
    for ing in body.ingredients:
        cat_path = ing.catalogue_path
        if not cat_path:
            # Create new Material primitive
            try:
                prim = await catalogue.create_primitive(PrimitiveCreate(
                    type="material",
                    name=ing.name,
                    description=f"Kitchen ingredient: {ing.name}",
                    tags=["kitchen", "ingredient"],
                    domain="kitchen",
                ))
                cat_path = prim.path
            except CoreUnavailableError:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "Core unavailable — cannot create new ingredient primitives",
                        "suggestion": "Retry when Core is connected, or use existing catalogue_paths",
                    },
                )
        resolved_ingredients.append({
            "catalogue_path": cat_path,
            "name": ing.name,
            "quantity": ing.quantity,
            "unit": ing.unit,
            "notes": ing.notes,
        })

    # Step 2: build relationships list for Workflow
    relationships: list[dict] = []
    for ing_data in resolved_ingredients:
        relationships.append({
            "relationship_type": "uses_material",
            "target_path": ing_data["catalogue_path"],
        })
    for tech_path in body.techniques:
        relationships.append({
            "relationship_type": "uses_technique",
            "target_path": tech_path,
        })
    for tool_path in body.tools:
        relationships.append({
            "relationship_type": "uses_tool",
            "target_path": tool_path,
        })

    # Step 3: build steps for Workflow
    workflow_steps = [
        {"order": i + 1, "title": step_text}
        for i, step_text in enumerate(body.steps)
    ]

    # Step 4: create Workflow primitive
    workflow_id: str | None = None
    try:
        wf = await catalogue.create_primitive(PrimitiveCreate(
            type="workflow",
            name=body.title,
            description=body.description,
            tags=body.tags + (["kitchen", "recipe"] if "recipe" not in body.tags else ["kitchen"]),
            domain="kitchen",
            steps=workflow_steps if workflow_steps else None,
            relationships=relationships,
            properties={
                k: v for k, v in {
                    "cuisine_tag": body.cuisine_tag,
                    "prep_time_mins": body.prep_time_mins,
                    "cook_time_mins": body.cook_time_mins,
                    "servings": body.servings,
                    "difficulty": body.difficulty,
                }.items() if v
            } or None,
        ))
        workflow_id = wf.path
    except CoreUnavailableError:
        # Proceed without workflow primitive — kitchen row still useful
        pass

    # Step 5: create kitchen_recipes row
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
            recipe_id, body.title, body.description, workflow_id, body.cuisine_tag,
            body.prep_time_mins, body.cook_time_mins, body.servings, body.notes, now, now,
        ],
    )

    # Step 6: insert ingredient rows
    for ing_data in resolved_ingredients:
        await db.execute(
            """
            INSERT INTO kitchen_recipe_ingredients
                (id, recipe_id, catalogue_path, name, quantity, unit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()), recipe_id, ing_data["catalogue_path"],
                ing_data["name"], ing_data["quantity"], ing_data["unit"],
                ing_data["notes"],
            ],
        )

    return await _fetch_recipe_full(db, recipe_id)


# ---------------------------------------------------------------------------
# DELETE /recipes/{recipe_id}
# MUST remain before GET /recipes/{recipe_id} for the same route-ordering reason.
# ---------------------------------------------------------------------------


@router.delete("/recipes/{recipe_id}")
async def delete_recipe(
    recipe_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Delete a recipe and its ingredients/nutrition. Preserves the Workflow primitive."""
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

    # Cascade delete kitchen data (preserve Workflow primitive in catalogue)
    await db.execute(
        "DELETE FROM kitchen_recipe_ingredients WHERE recipe_id = ?", [recipe_id]
    )
    await db.execute(
        "DELETE FROM kitchen_recipe_nutrition WHERE recipe_id = ?", [recipe_id]
    )
    await db.execute(
        "DELETE FROM kitchen_recipes WHERE id = ?", [recipe_id]
    )

    return {"deleted": True, "id": recipe_id}


@router.post("/recipes/{recipe_id}/fork", status_code=201)
async def fork_recipe(
    recipe_id: str,
    db: ModuleUserDB = Depends(get_db),
    catalogue: CatalogueClient = Depends(get_catalogue_client),
):
    """Fork a recipe into an independent copy.

    Creates a fork of the catalogue Workflow primitive (via the Shell's fork endpoint)
    and duplicates all kitchen metadata (recipe row, ingredients, nutrition) to produce
    a fully independent variant. The fork's cloned_from field links back to the original
    workflow for provenance.

    Returns the new recipe record (same shape as GET /recipes/{id}).
    """
    # Load source recipe.
    src = await db.fetch_one(
        "SELECT * FROM kitchen_recipes WHERE id = ?", [recipe_id]
    )
    if not src:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Recipe not found",
                "recipe_id": recipe_id,
                "suggestion": "Use GET /recipes to list available recipes",
            },
        )

    # Fork the catalogue Workflow primitive (if one is linked).
    new_workflow_id = src["workflow_id"]
    if src.get("workflow_id"):
        try:
            forked = await catalogue.fork_primitive(
                src["workflow_id"],
                name=f"{src['title']} (fork)",
            )
            new_workflow_id = forked.path
        except Exception:
            # Continue without forking the primitive — kitchen data still forks.
            pass

    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())

    # Duplicate the kitchen_recipes row.
    await db.execute(
        """
        INSERT INTO kitchen_recipes
            (id, title, description, workflow_id, cuisine_tag,
             prep_time_mins, cook_time_mins, servings, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            new_id,
            f"{src['title']} (fork)",
            src["description"],
            new_workflow_id,
            src["cuisine_tag"],
            src["prep_time_mins"],
            src["cook_time_mins"],
            src["servings"],
            src["notes"],
            now,
            now,
        ],
    )

    # Duplicate ingredients.
    ingredients = await db.fetch_all(
        "SELECT * FROM kitchen_recipe_ingredients WHERE recipe_id = ?", [recipe_id]
    )
    for ing in ingredients:
        await db.execute(
            """
            INSERT INTO kitchen_recipe_ingredients
                (id, recipe_id, catalogue_path, name, quantity, unit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                new_id,
                ing["catalogue_path"],
                ing["name"],
                ing["quantity"],
                ing["unit"],
                ing["notes"],
            ],
        )

    # Duplicate nutrition data (per-serving).
    nutrition = await db.fetch_one(
        "SELECT * FROM kitchen_recipe_nutrition WHERE recipe_id = ?", [recipe_id]
    )
    if nutrition:
        await db.execute(
            """
            INSERT INTO kitchen_recipe_nutrition
                (id, recipe_id, calories, protein_g, carbs_g, fat_g, fibre_g,
                 sugar_g, sodium_mg, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                new_id,
                nutrition["calories"],
                nutrition["protein_g"],
                nutrition["carbs_g"],
                nutrition["fat_g"],
                nutrition["fibre_g"],
                nutrition["sugar_g"],
                nutrition["sodium_mg"],
                now,
            ],
        )

    return await _fetch_recipe_full(db, new_id)


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
        "SELECT e.*, r.title AS recipe_title "
        "FROM kitchen_meal_plan_entries e "
        "LEFT JOIN kitchen_recipes r ON e.recipe_id = r.id "
        "WHERE e.plan_id = ? ORDER BY e.day_of_week, e.meal_slot",
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
# Shopping list endpoints (persistent)
# IMPORTANT: static sub-paths MUST be declared BEFORE /shopping/{id}.
# ---------------------------------------------------------------------------


@router.get("/shopping")
async def list_shopping(
    tab: str | None = Query(None, description="'buy' to return unchecked only"),
    db: ModuleUserDB = Depends(get_db),
):
    """List persistent shopping list items."""
    where = "WHERE checked = 0" if tab == "buy" else ""
    items = await db.fetch_all(
        f"SELECT * FROM kitchen_shopping_list {where} ORDER BY created_at DESC"
    )
    total_row = await db.fetch_one(
        "SELECT COUNT(*) AS n FROM kitchen_shopping_list"
    )
    buy_row = await db.fetch_one(
        "SELECT COUNT(*) AS n FROM kitchen_shopping_list WHERE checked = 0"
    )
    return {
        "items": [dict(r) for r in items],
        "total": (total_row["n"] if total_row else 0) or 0,
        "to_buy": (buy_row["n"] if buy_row else 0) or 0,
    }


@router.post("/shopping", status_code=201)
async def add_shopping_item(
    body: ShoppingItemCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Add a manual item to the persistent shopping list."""
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO kitchen_shopping_list
            (id, name, catalogue_path, quantity, unit, source,
             source_recipe_id, checked, note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """,
        [
            item_id, body.name, body.catalogue_path, body.quantity,
            body.unit, body.source, body.source_recipe_id, body.note, now, now,
        ],
    )
    row = await db.fetch_one(
        "SELECT * FROM kitchen_shopping_list WHERE id = ?", [item_id]
    )
    return dict(row)


@router.post("/shopping/from-recipe/{recipe_id}")
async def add_recipe_to_shopping(
    recipe_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Stock-check recipe, add missing ingredients to shopping list.

    Deduplicates against existing unchecked items by (catalogue_path OR name).
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
        f"""
        SELECT i.name, i.catalogue_path, i.quantity, i.unit,
               COALESCE(s.total_qty, 0) AS in_stock_qty
        FROM kitchen_recipe_ingredients i
        LEFT JOIN ({_STOCK_BY_PATH_SQL}) s ON s.catalogue_path = i.catalogue_path
        WHERE i.recipe_id = ?
        """,
        [recipe_id],
    )

    # Fetch existing unchecked shopping items for dedup
    existing = await db.fetch_all(
        "SELECT name, catalogue_path FROM kitchen_shopping_list WHERE checked = 0"
    )
    existing_paths = {r["catalogue_path"] for r in existing if r["catalogue_path"]}
    existing_names = {r["name"].lower() for r in existing}

    added = 0
    now = datetime.now(timezone.utc).isoformat()
    for ing in ingredients:
        if float(ing["in_stock_qty"]) > 0:
            continue  # in stock — skip

        # Dedup check
        if ing["catalogue_path"] and ing["catalogue_path"] in existing_paths:
            continue
        if ing["name"].lower() in existing_names:
            continue

        await db.execute(
            """
            INSERT INTO kitchen_shopping_list
                (id, name, catalogue_path, quantity, unit, source,
                 source_recipe_id, checked, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'recipe', ?, 0, '', ?, ?)
            """,
            [
                str(uuid.uuid4()), ing["name"], ing["catalogue_path"],
                ing["quantity"], ing["unit"], recipe_id, now, now,
            ],
        )
        added += 1

    return {"added": added, "recipe_id": recipe_id, "recipe_title": recipe["title"]}


@router.post("/shopping/clear-checked")
async def clear_checked_shopping(db: ModuleUserDB = Depends(get_db)):
    """Delete all checked (completed) shopping list items."""
    count_row = await db.fetch_one(
        "SELECT COUNT(*) AS n FROM kitchen_shopping_list WHERE checked = 1"
    )
    count = (count_row["n"] if count_row else 0) or 0
    await db.execute("DELETE FROM kitchen_shopping_list WHERE checked = 1")
    return {"deleted": count}


@router.get("/shopping/badge")
async def get_shopping_badge(db: ModuleUserDB = Depends(get_db)):
    """Return count of unchecked shopping list items (for sidebar badge)."""
    row = await db.fetch_one(
        "SELECT COUNT(*) AS n FROM kitchen_shopping_list WHERE checked = 0"
    )
    return {"count": (row["n"] if row else 0) or 0}


@router.put("/shopping/{item_id}")
async def update_shopping_item(
    item_id: str,
    body: ShoppingItemUpdate,
    db: ModuleUserDB = Depends(get_db),
):
    """Update a shopping list item (toggle checked, update qty/note)."""
    existing = await db.fetch_one(
        "SELECT id FROM kitchen_shopping_list WHERE id = ?", [item_id]
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Shopping item not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        row = await db.fetch_one(
            "SELECT * FROM kitchen_shopping_list WHERE id = ?", [item_id]
        )
        return dict(row)

    # Convert checked bool to int for SQLite
    if "checked" in updates:
        updates["checked"] = 1 if updates["checked"] else 0

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    await db.execute(
        f"UPDATE kitchen_shopping_list SET {set_clause} WHERE id = ?",
        list(updates.values()) + [item_id],
    )
    row = await db.fetch_one(
        "SELECT * FROM kitchen_shopping_list WHERE id = ?", [item_id]
    )
    return dict(row)


@router.delete("/shopping/{item_id}")
async def delete_shopping_item(
    item_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Remove a single shopping list item."""
    existing = await db.fetch_one(
        "SELECT id FROM kitchen_shopping_list WHERE id = ?", [item_id]
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Shopping item not found")
    await db.execute("DELETE FROM kitchen_shopping_list WHERE id = ?", [item_id])
    return {"deleted": True, "id": item_id}


# ---------------------------------------------------------------------------
# POST /stock/add — create a single stock item via inventory-stock peer
# ---------------------------------------------------------------------------


@router.post("/stock/add", status_code=201)
async def add_stock_item(
    body: StockItemCreate,
    db: ModuleUserDB = Depends(get_db),
    peers: PeerModules = Depends(get_peer_modules),
):
    """Create a single stock item via inventory-stock peer.

    If catalogue_path is provided, looks up the inventory pin. If not found,
    the item cannot be created (inventory pin is a prerequisite).
    If catalogue_path is absent, creates via peer with name only.
    Optionally stores kitchen_stock_metadata if expiry_date is provided.
    """
    if not peers.is_installed("inventory-stock"):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "inventory-stock peer not installed",
                "suggestion": "Install the inventory-stock module first",
            },
        )

    inv_id = None
    if body.catalogue_path:
        inv_row = await db.fetch_one(
            "SELECT id FROM inventory WHERE catalogue_path = ?",
            [body.catalogue_path],
        )
        if not inv_row:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "No inventory pin found for this catalogue_path",
                    "catalogue_path": body.catalogue_path,
                    "suggestion": "Use add_to_inventory to pin this catalogue entry first",
                },
            )
        inv_id = inv_row["id"]

    peer_body: dict = {
        "quantity": body.quantity,
        "unit": body.unit,
        "location": body.location,
        "notes": body.notes,
    }
    if inv_id:
        peer_body["inventory_id"] = inv_id
    if body.name and not inv_id:
        peer_body["name"] = body.name

    result = await peers.call(
        "inventory-stock", "POST", "/stock", body=peer_body,
    )

    new_stock_id = result.get("id") if isinstance(result, dict) else None

    if body.expiry_date and new_stock_id:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO kitchen_stock_metadata "
            "(id, stock_item_id, expiry_date, updated_at) VALUES (?, ?, ?, ?)",
            [str(uuid.uuid4()), new_stock_id, body.expiry_date, now],
        )

    return {
        "stock_item_id": new_stock_id,
        "catalogue_path": body.catalogue_path,
        "quantity": body.quantity,
        "location": body.location,
    }


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


@router.put("/recipes/{recipe_id}/full")
async def update_recipe_full(
    recipe_id: str,
    body: RecipeFullCreate,
    db: ModuleUserDB = Depends(get_db),
    catalogue: CatalogueClient = Depends(get_catalogue_client),
):
    """Update recipe with full primitive composition.

    Creates new Material primitives for ingredients without catalogue_path.
    Updates the linked Workflow primitive if one exists.
    Replaces kitchen_recipe_ingredients.
    """
    from backend.app.models import PrimitiveCreate, PrimitiveUpdate

    existing = await db.fetch_one(
        "SELECT * FROM kitchen_recipes WHERE id = ?", [recipe_id]
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

    # Resolve ingredients
    resolved_ingredients: list[dict] = []
    for ing in body.ingredients:
        cat_path = ing.catalogue_path
        if not cat_path:
            try:
                prim = await catalogue.create_primitive(PrimitiveCreate(
                    type="material",
                    name=ing.name,
                    description=f"Kitchen ingredient: {ing.name}",
                    tags=["kitchen", "ingredient"],
                    domain="kitchen",
                ))
                cat_path = prim.path
            except CoreUnavailableError:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "Core unavailable — cannot create new ingredient primitives",
                        "suggestion": "Retry when Core is connected",
                    },
                )
        resolved_ingredients.append({
            "catalogue_path": cat_path,
            "name": ing.name,
            "quantity": ing.quantity,
            "unit": ing.unit,
            "notes": ing.notes,
        })

    # Update Workflow primitive if linked
    workflow_id = existing["workflow_id"]
    if workflow_id:
        try:
            wf_prim = await catalogue.get_primitive(workflow_id)
            relationships: list[dict] = []
            for ing_data in resolved_ingredients:
                relationships.append({
                    "relationship_type": "uses_material",
                    "target_path": ing_data["catalogue_path"],
                })
            for tech_path in body.techniques:
                relationships.append({
                    "relationship_type": "uses_technique",
                    "target_path": tech_path,
                })
            for tool_path in body.tools:
                relationships.append({
                    "relationship_type": "uses_tool",
                    "target_path": tool_path,
                })

            workflow_steps = [
                {"order": i + 1, "title": step_text}
                for i, step_text in enumerate(body.steps)
            ]

            await catalogue.update_primitive(
                workflow_id,
                PrimitiveUpdate(
                    id=wf_prim.id,
                    type=wf_prim.type,
                    name=body.title,
                    slug=wf_prim.slug,
                    description=body.description,
                    tags=body.tags + (["kitchen", "recipe"] if "recipe" not in body.tags else ["kitchen"]),
                    steps=workflow_steps if workflow_steps else None,
                    relationships=relationships,
                    properties={
                        k: v for k, v in {
                            "cuisine_tag": body.cuisine_tag,
                            "prep_time_mins": body.prep_time_mins,
                            "cook_time_mins": body.cook_time_mins,
                            "servings": body.servings,
                            "difficulty": body.difficulty,
                        }.items() if v
                    } or None,
                ),
            )
        except (CoreUnavailableError, Exception):
            pass  # Best-effort update of the Workflow primitive

    # Update kitchen_recipes row
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        UPDATE kitchen_recipes
        SET title=?, description=?, cuisine_tag=?, prep_time_mins=?,
            cook_time_mins=?, servings=?, notes=?, updated_at=?
        WHERE id=?
        """,
        [
            body.title, body.description, body.cuisine_tag, body.prep_time_mins,
            body.cook_time_mins, body.servings, body.notes, now, recipe_id,
        ],
    )

    # Replace ingredients
    await db.execute(
        "DELETE FROM kitchen_recipe_ingredients WHERE recipe_id = ?", [recipe_id]
    )
    for ing_data in resolved_ingredients:
        await db.execute(
            """
            INSERT INTO kitchen_recipe_ingredients
                (id, recipe_id, catalogue_path, name, quantity, unit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()), recipe_id, ing_data["catalogue_path"],
                ing_data["name"], ing_data["quantity"], ing_data["unit"],
                ing_data["notes"],
            ],
        )

    return await _fetch_recipe_full(db, recipe_id)


# ---------------------------------------------------------------------------
# K9a: GET /catalogue/search — proxy to CatalogueClient
# ---------------------------------------------------------------------------


@router.get("/catalogue/search")
async def search_catalogue(
    q: str = Query(..., description="Search query"),
    type: str | None = Query(None, description="Filter by primitive type (material/tool/technique/workflow)"),
    catalogue: CatalogueClient = Depends(get_catalogue_client),
):
    """Search the catalogue with optional type filter. Kitchen-friendly response."""
    try:
        results = await catalogue.search(q)
    except CoreUnavailableError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Core unavailable — catalogue search disabled",
                "suggestion": "Retry when Core is connected",
            },
        )

    if type:
        results = [r for r in results if r.type == type]

    return {
        "results": [
            {
                "path": r.path,
                "name": r.name,
                "type": r.type,
                "description": r.description,
                "tags": r.tags,
            }
            for r in results
        ],
        "total": len(results) if not type else len(results),
    }


# ---------------------------------------------------------------------------
# K9a: PUT /stock/{item_id} — update single stock item
# ---------------------------------------------------------------------------


@router.put("/stock/{item_id}")
async def update_stock_item(
    item_id: str,
    body: StockItemUpdate,
    db: ModuleUserDB = Depends(get_db),
    peers: PeerModules = Depends(get_peer_modules),
):
    """Update a stock item's quantity/unit/location via inventory-stock peer + expiry metadata."""
    if not peers.is_installed("inventory-stock"):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "inventory-stock peer not installed",
                "suggestion": "Install the inventory-stock module first",
            },
        )

    # Verify item exists
    stock_row = await db.fetch_one(
        "SELECT id, quantity, unit, location FROM inventory_stock_items WHERE id = ?",
        [item_id],
    )
    if not stock_row:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Stock item not found",
                "stock_item_id": item_id,
                "suggestion": "Use GET /stock to list available items",
            },
        )

    # Build peer update body (only changed fields)
    peer_body: dict = {}
    if body.quantity is not None:
        peer_body["quantity"] = body.quantity
    if body.unit is not None:
        peer_body["unit"] = body.unit
    if body.location is not None:
        peer_body["location"] = body.location

    if peer_body:
        await peers.call(
            "inventory-stock", "PUT", f"/stock/{item_id}", body=peer_body,
        )

    # Update expiry metadata
    if body.expiry_date is not None:
        now = datetime.now(timezone.utc).isoformat()
        meta = await db.fetch_one(
            "SELECT id FROM kitchen_stock_metadata WHERE stock_item_id = ?",
            [item_id],
        )
        if meta:
            await db.execute(
                "UPDATE kitchen_stock_metadata SET expiry_date = ?, updated_at = ? "
                "WHERE stock_item_id = ?",
                [body.expiry_date or None, now, item_id],
            )
        elif body.expiry_date:
            await db.execute(
                "INSERT INTO kitchen_stock_metadata "
                "(id, stock_item_id, expiry_date, updated_at) VALUES (?, ?, ?, ?)",
                [str(uuid.uuid4()), item_id, body.expiry_date, now],
            )

    # Return updated item
    row = await db.fetch_one(
        """
        SELECT isi.id, inv.catalogue_path, isi.quantity, isi.unit, isi.location,
               isi.notes, m.expiry_date, m.frozen_on_date
        FROM inventory_stock_items isi
        JOIN inventory inv ON inv.id = isi.inventory_id
        LEFT JOIN kitchen_stock_metadata m ON m.stock_item_id = isi.id
        WHERE isi.id = ?
        """,
        [item_id],
    )
    return dict(row) if row else {"id": item_id, "updated": True}


# ---------------------------------------------------------------------------
# K9a: DELETE /stock/{item_id} — remove stock item
# ---------------------------------------------------------------------------


@router.delete("/stock/{item_id}")
async def delete_stock_item(
    item_id: str,
    db: ModuleUserDB = Depends(get_db),
    peers: PeerModules = Depends(get_peer_modules),
):
    """Remove a stock item via inventory-stock peer + clean kitchen_stock_metadata."""
    if not peers.is_installed("inventory-stock"):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "inventory-stock peer not installed",
                "suggestion": "Install the inventory-stock module first",
            },
        )

    # Clean kitchen metadata first
    await db.execute(
        "DELETE FROM kitchen_stock_metadata WHERE stock_item_id = ?", [item_id]
    )

    # Delete via peer
    await peers.call("inventory-stock", "DELETE", f"/stock/{item_id}")

    return {"deleted": True, "id": item_id}


# ---------------------------------------------------------------------------
# K9a: DELETE /meal-plan/{week}/entry/{entry_id}
# ---------------------------------------------------------------------------


@router.delete("/meal-plan/{week}/entry/{entry_id}")
async def delete_meal_plan_entry(
    week: str,
    entry_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Delete a single meal plan entry."""
    existing = await db.fetch_one(
        "SELECT e.id FROM kitchen_meal_plan_entries e "
        "JOIN kitchen_meal_plan p ON e.plan_id = p.id "
        "WHERE e.id = ? AND p.week_start = ?",
        [entry_id, week],
    )
    if not existing:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Meal plan entry not found",
                "entry_id": entry_id,
                "week": week,
                "suggestion": "Use GET /meal-plan/{week} to see available entries",
            },
        )

    await db.execute(
        "DELETE FROM kitchen_meal_plan_entries WHERE id = ?", [entry_id]
    )
    return {"deleted": True, "id": entry_id}
