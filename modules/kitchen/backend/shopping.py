"""Kitchen module — shopping list helpers.

Builds an aggregated shopping list from a week's meal plan entries by:
  1. Scaling each recipe's ingredient quantities by the effective serving count.
  2. Normalising mass/volume quantities to grams so that ingredients measured
     in different units (e.g. "200g flour" and "1 cup flour") aggregate into a
     single line item.
  3. Summing requirements across all entries by (catalogue_path, canonical_unit).
  4. Joining with inventory_stock_items (via inventory) to find on-hand stock,
     also normalised to grams for a fair comparison.
  5. Returning items with required, on_hand, and shortfall quantities.
"""

from __future__ import annotations

import sys


def _get_unit_to_grams():
    """Return the unit_to_grams function from the already-loaded nutrition module.

    Routes.py loads the nutrition module via _kitchen_import() before loading
    this module, so the sys.modules key is always populated at call time.
    Falls back to a no-op lambda if somehow the module is not present.
    """
    mod = sys.modules.get("_kitchen_backend_nutrition")
    return mod.unit_to_grams if mod is not None else (lambda _u: None)


def _canonical(quantity: float, unit: str, unit_to_grams) -> tuple[float, str]:
    """Return (canonical_quantity, canonical_unit) by normalising to grams where possible."""
    factor = unit_to_grams(unit)
    if factor is not None:
        return quantity * factor, "g"
    return quantity, unit


async def build_shopping_list(entries: list[dict], db) -> list[dict]:
    """Compute the shopping list for a set of meal plan entries.

    Args:
        entries: rows from kitchen_meal_plan_entries
        db: ModuleUserDB instance (must have read access to inventory tables)

    Returns:
        List of dicts with keys: catalogue_path, name, required_quantity,
        unit, on_hand_quantity, shortfall.
    """
    unit_to_grams = _get_unit_to_grams()

    # Aggregate required quantities per (catalogue_path, canonical_unit).
    # Using a tuple key means "200g flour" and "1 cup flour" both map to
    # ("materials/flour", "g") and are summed together.
    required: dict[tuple[str, str], dict] = {}

    for entry in entries:
        recipe_id = entry.get("recipe_id")
        if not recipe_id:
            continue

        recipe = await db.fetch_one(
            "SELECT id, servings FROM kitchen_recipes WHERE id = ?", [recipe_id]
        )
        if not recipe:
            continue

        ingredients = await db.fetch_all(
            "SELECT catalogue_path, name, quantity, unit "
            "FROM kitchen_recipe_ingredients WHERE recipe_id = ?",
            [recipe_id],
        )

        recipe_servings = max(recipe["servings"] or 1, 1)
        serves_override = entry.get("serves_override")
        entry_servings = max(entry.get("servings") or 1, 1)
        target_servings = serves_override if serves_override else entry_servings
        scale = target_servings / recipe_servings

        for ing in ingredients:
            path = ing["catalogue_path"]
            scaled_qty = float(ing["quantity"]) * scale
            canon_qty, canon_unit = _canonical(scaled_qty, ing["unit"], unit_to_grams)

            key = (path, canon_unit)
            if key not in required:
                required[key] = {"name": ing["name"], "quantity": 0.0, "unit": canon_unit}
            required[key]["quantity"] += canon_qty

    if not required:
        return []

    # Fetch on-hand stock for all relevant catalogue_paths, normalised to the
    # same canonical unit so the comparison is unit-aware.
    paths = list({k[0] for k in required})
    placeholders = ",".join("?" * len(paths))
    stock_rows = await db.fetch_all(
        f"""
        SELECT ii.catalogue_path, isi.quantity, isi.unit
        FROM inventory_stock_items isi
        JOIN inventory ii ON isi.inventory_id = ii.id
        WHERE ii.catalogue_path IN ({placeholders})
        """,
        paths,
    )

    stock_map: dict[tuple[str, str], float] = {}
    for r in stock_rows:
        canon_qty, canon_unit = _canonical(
            float(r["quantity"] or 0.0), r["unit"], unit_to_grams
        )
        key = (r["catalogue_path"], canon_unit)
        stock_map[key] = stock_map.get(key, 0.0) + canon_qty

    items = []
    for (path, unit), info in required.items():
        on_hand = stock_map.get((path, unit), 0.0)
        shortfall = max(0.0, info["quantity"] - on_hand)
        items.append(
            {
                "catalogue_path": path,
                "name": info["name"],
                "required_quantity": round(info["quantity"], 3),
                "unit": unit,
                "on_hand_quantity": round(on_hand, 3),
                "shortfall": round(shortfall, 3),
            }
        )

    return items
