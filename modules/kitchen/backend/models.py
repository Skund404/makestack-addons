"""Kitchen module Pydantic models — request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Ingredients (sub-model used inside RecipeCreate / RecipeUpdate)
# ---------------------------------------------------------------------------


class IngredientItem(BaseModel):
    """Ingredient entry for use inside RecipeCreate/RecipeUpdate (no recipe_id)."""

    catalogue_path: str
    name: str
    quantity: float
    unit: str
    notes: str = ""


# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------


class RecipeCreate(BaseModel):
    title: str
    description: str = ""
    workflow_id: str | None = None
    cuisine_tag: str = ""
    prep_time_mins: int | None = None
    cook_time_mins: int | None = None
    servings: int = 1
    notes: str = ""
    ingredients: list[IngredientItem] = []


class RecipeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    workflow_id: str | None = None
    cuisine_tag: str | None = None
    prep_time_mins: int | None = None
    cook_time_mins: int | None = None
    servings: int | None = None
    notes: str | None = None
    # None = don't touch ingredients; [] = clear all; [...] = full replace
    ingredients: list[IngredientItem] | None = None


class RecipeListItem(BaseModel):
    id: str
    title: str
    servings: int
    prep_time_mins: int | None
    cook_time_mins: int | None
    total_time_mins: int | None
    cuisine_tag: str
    last_cooked_at: str | None
    cook_count: int
    created_at: str
    updated_at: str


class RecipeResponse(BaseModel):
    id: str
    title: str
    description: str
    workflow_id: str | None
    cuisine_tag: str
    prep_time_mins: int | None
    cook_time_mins: int | None
    total_time_mins: int | None
    servings: int
    notes: str
    ingredients: list[dict] = []
    nutrition: dict | None = None
    cook_summary: dict | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Ingredients (standalone response)
# ---------------------------------------------------------------------------


class IngredientCreate(BaseModel):
    recipe_id: str
    catalogue_path: str
    name: str
    quantity: float
    unit: str
    notes: str = ""


class IngredientResponse(BaseModel):
    id: str
    recipe_id: str
    catalogue_path: str
    name: str
    quantity: float
    unit: str
    notes: str


# ---------------------------------------------------------------------------
# Nutrition
# ---------------------------------------------------------------------------


class NutritionData(BaseModel):
    calories: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    source: str | None = None       # 'calculated' | 'manual' | etc.
    warnings: list[str] = []        # ingredient names missing nutrition data


class IngredientNutritionCreate(BaseModel):
    catalogue_path: str
    calories_per_100g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    source: str | None = None


# ---------------------------------------------------------------------------
# Meal Plan
# ---------------------------------------------------------------------------


class MealPlanEntryCreate(BaseModel):
    day_of_week: int  # 0=Monday … 6=Sunday
    meal_slot: str    # breakfast | lunch | dinner | snack
    recipe_id: str | None = None
    servings: int = 1
    notes: str = ""
    free_text: str = ""
    serves_override: int | None = None


class MealPlanResponse(BaseModel):
    id: str
    week_start: str
    notes: str
    entries: list[dict] = []
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Cook Log
# ---------------------------------------------------------------------------


class CookLogCreate(BaseModel):
    recipe_id: str
    cooked_at: str
    serves_made: int = 1
    rating: int | None = None
    notes: str = ""


class CookLogResponse(BaseModel):
    id: str
    recipe_id: str
    cooked_at: str
    serves_made: int
    rating: int | None
    notes: str
    stock_deducted: bool
    material_pulls_json: str | None = None
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Stock aliases
# ---------------------------------------------------------------------------


class StockAliasCreate(BaseModel):
    receipt_text: str
    catalogue_path: str


class StockAliasResponse(BaseModel):
    id: str
    receipt_text: str
    catalogue_path: str
    created_at: str


# ---------------------------------------------------------------------------
# Stock metadata
# ---------------------------------------------------------------------------


class StockMetadataUpdate(BaseModel):
    expiry_date: str | None = None
    frozen_on_date: str | None = None


class ExpiringItemResponse(BaseModel):
    stock_item_id: str
    expiry_date: str
    days_until_expiry: int
    inventory_id: str
    quantity: float
    unit: str
    location: str


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------


class BulkStockItem(BaseModel):
    catalogue_path: str
    quantity: float
    unit: str = ""
    location: str = ""
    action: str = "set"    # "set" | "add"
    expiry_date: str | None = None


class ShoppingListItem(BaseModel):
    catalogue_path: str
    name: str
    required_quantity: float
    unit: str
    on_hand_quantity: float
    shortfall: float


class ShoppingListResponse(BaseModel):
    week_start: str
    items: list[ShoppingListItem]
    total_items: int


# ---------------------------------------------------------------------------
# Can-make / stock check
# ---------------------------------------------------------------------------


class StockCheckResult(BaseModel):
    recipe_id: str
    recipe_title: str
    can_make: bool
    ingredients: list[dict]


class CanMakeResult(BaseModel):
    recipes: list[StockCheckResult]
    total: int
