"""Kitchen module — nutrition calculation helpers.

Pure functions; no Pydantic or kitchen-specific imports.
Returns plain Python dicts so this module can be loaded independently.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Unit → grams conversion table
# Volume units use water density (1 g/ml) as an approximation.
# Units not in this table cannot be converted; those ingredients are skipped
# and their names are added to the warnings list.
# ---------------------------------------------------------------------------

_UNIT_TO_GRAMS: dict[str, float] = {
    # mass
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
    # volume (approximate — water density)
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "millilitre": 1.0,
    "millilitres": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "litre": 1000.0,
    "litres": 1000.0,
    "cup": 240.0,
    "cups": 240.0,
    "tbsp": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "tsp": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
    "fl oz": 29.5735,
    "fluid ounce": 29.5735,
    "fluid ounces": 29.5735,
}

# DB column name for the per-100g value, keyed by the output field name.
_FIELD_TO_DB: dict[str, str] = {
    "calories": "calories_per_100g",
    "protein_g": "protein_g",
    "fat_g": "fat_g",
    "carbs_g": "carbs_g",
    "fiber_g": "fiber_g",
    "sugar_g": "sugar_g",
    "sodium_mg": "sodium_mg",
}

_NUTRITION_FIELDS: list[str] = list(_FIELD_TO_DB.keys())


def unit_to_grams(unit: str) -> float | None:
    """Return the grams-per-unit factor for a given unit string, or None if unknown."""
    return _UNIT_TO_GRAMS.get(unit.strip().lower())


def calculate_recipe_nutrition(
    ingredients: list[dict],
    nutrition_map: dict[str, dict],
    serves: int,
) -> tuple[dict[str, float], list[str]]:
    """Calculate per-serving nutrition totals for a recipe.

    Args:
        ingredients: rows from kitchen_recipe_ingredients
                     (must have: catalogue_path, name, quantity, unit)
        nutrition_map: catalogue_path → row from kitchen_ingredient_nutrition
        serves: number of servings (recipe.servings)

    Returns:
        (per_serving, warnings) where:
          - per_serving  is a dict with keys from _NUTRITION_FIELDS,
                         values rounded to 2 decimal places
          - warnings     is a list of human-readable strings for ingredients
                         that were skipped (no nutrition data or unconvertible unit)
    """
    totals: dict[str, float] = {f: 0.0 for f in _NUTRITION_FIELDS}
    warnings: list[str] = []

    for ing in ingredients:
        name = ing.get("name") or ing.get("catalogue_path") or "unknown"
        path = ing.get("catalogue_path")

        nutr = nutrition_map.get(path) if path else None
        if not nutr:
            warnings.append(f"{name}: no nutrition data")
            continue

        unit = ing.get("unit", "")
        quantity = float(ing.get("quantity") or 0.0)
        grams_per_unit = unit_to_grams(unit)

        if grams_per_unit is None:
            warnings.append(f"{name}: cannot convert unit '{unit}' to grams")
            continue

        quantity_g = quantity * grams_per_unit

        for field in _NUTRITION_FIELDS:
            db_col = _FIELD_TO_DB[field]
            per_100g = nutr.get(db_col)
            if per_100g is not None:
                totals[field] += (quantity_g / 100.0) * float(per_100g)

    serves = max(serves, 1)
    per_serving = {f: round(totals[f] / serves, 2) for f in _NUTRITION_FIELDS}

    return per_serving, warnings
