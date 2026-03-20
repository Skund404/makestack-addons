# SKILL.md — Home Kitchen Module

> This file is the AI intelligence guide for the Home Kitchen module.
> Read it in full before performing any kitchen-related task.
> It defines every flow, every tool call, and every constraint.

---

## 1. Module Purpose

The Home Kitchen module manages what food is in the house, what can be cooked
with it, and what needs to be bought. It tracks stock across three physical
locations (pantry, fridge, freezer), maintains a recipe library tied to the
catalogue, generates weekly meal plans, calculates shopping lists from those
plans, and logs cooking sessions. All stock writes go through the inventory-
stock peer — the kitchen module never writes directly to stock tables.

---

## 2. Storage Model

Stock is stored in **inventory_stock_items** (owned by inventory-stock) and
filtered by the `location` field. The kitchen module adds a metadata layer in
**kitchen_stock_metadata** for expiry dates and frozen-on dates.

| Location key | Meaning |
|---|---|
| `pantry` | Ambient storage (dry goods, canned goods, spices) |
| `fridge` | Refrigerated items |
| `freezer` | Frozen items |
| (empty) | Unknown/unassigned location |

When reading stock for a specific location, use `kitchen__list_stock` which
proxies to inventory-stock with the location filter already applied.

---

## 3. Receipt Parsing Flow

Use this flow when the user provides a receipt, grocery list, or spoken list of
items they just bought.

1. **Parse each line item** from the receipt text into: raw_text, quantity,
   unit, and candidate ingredient name. Do not invent catalogue paths yet.

2. **Alias lookup** — for each item, call `kitchen__lookup_alias` with the
   raw receipt text. If an alias is found, use its `catalogue_path` directly.
   Skip steps 3–4 for aliased items.

3. **Catalogue search** — for unaliased items, call `search_catalogue` with the
   ingredient name as query. Filter results to `type=material`.

4. **Path resolution** — pick the best matching `catalogue_path` from the
   search results. If no match exists, call `create_primitive` (type=material)
   to create the ingredient in the catalogue first. Never guess a path.

5. **Inventory pin** — for each resolved path, call `add_to_inventory` with the
   `catalogue_path` and `primitive_type="material"` if the item is not already
   in the user's inventory. This is a hard prerequisite: `kitchen__bulk_update_stock`
   looks up items by `catalogue_path` in the `inventory` table and will silently
   fail with "No inventory item found" if the pin is missing. Check the current
   inventory first with `list_inventory` to avoid duplicate pins.

6. **Save alias** — call `kitchen__save_alias` to map the original receipt text
   to the resolved catalogue_path. This prevents repeated lookups on future
   receipts.

7. **Location assignment** — ask the user where each item goes (pantry, fridge,
   freezer) if not obvious from context. Frozen items → freezer. Dairy, fresh
   produce → fridge. Everything else → pantry by default.

8. **Bulk update** — collect all resolved items and call
   `kitchen__bulk_update_stock` in a single call. Include `expiry_date` when
   visible on the packaging. Use `action: "add"` when adding to existing stock,
   `action: "set"` only when the receipt represents the total new quantity.

9. **Confirm results** — report back: N updated, M created, K failed. For
   failed items, explain what went wrong. A "No inventory item found" failure
   means step 5 was missed — call `add_to_inventory` for that item and retry.

---

## 4. Recipe Capture Flow

Use this flow when the user wants to save a new recipe.

1. **Check for existing recipe** — call `kitchen__list_recipes` with a search
   term. If a similar recipe already exists, confirm with the user before
   creating a duplicate.

2. **Resolve ingredients** — for each ingredient in the recipe, determine the
   catalogue_path using `search_catalogue`. Create missing catalogue materials
   via `create_primitive` if not found. Never use a guessed path.

3. **Create recipe** — call `kitchen__create_recipe` with all metadata:
   `title`, `description`, `cuisine_tag`, `prep_time_mins`, `cook_time_mins`,
   `servings`, `notes`, and the full `ingredients` list (each with
   `catalogue_path`, `name`, `quantity`, `unit`).

4. **Confirm creation** — report the recipe ID and summary. Offer to set
   nutrition data.

5. **Nutrition (optional)** — if the user provides nutritional values per
   ingredient (per 100g), call `kitchen__set_ingredient_nutrition` for each.
   Then call `kitchen__calculate_recipe_nutrition` with `save=true` to compute
   and store per-serving totals.

6. **Verify** — call `kitchen__get_recipe` to confirm all data was saved
   correctly. Show the recipe card to the user.

7. **Stock check** — optionally call `kitchen__check_recipe_stock` to show
   whether the recipe is makeable from current stock.

---

## 5. 'What Can I Make Tonight?' Flow

Use this flow when the user asks what they can cook with current stock.

1. **Strict check first** — call `kitchen__can_make` with `strict=true` to get
   recipes fully covered by current stock.

2. **Relaxed check if few results** — if strict returns fewer than 3 recipes,
   call `kitchen__can_make` with `strict=false` to include recipes missing at
   most one ingredient.

3. **Filter by preference** — if the user mentions a cuisine type or time
   constraint, pass these as filters to `kitchen__list_recipes` and intersect
   with can-make results.

4. **Show options** — present the makeable recipes by name, total cook time, and
   cuisine tag. For relaxed matches, state which single ingredient is missing.

5. **Stock detail on request** — if the user picks a recipe, call
   `kitchen__check_recipe_stock` to show per-ingredient status (ok / low /
   missing) so they can decide whether to proceed.

6. **Log cooking** — when the user confirms they are cooking, call
   `kitchen__log_cook` with `recipe_id`, `cooked_at` (current ISO timestamp),
   `serves_made`, and optional `rating`/`notes`. Stock is automatically deducted
   via the inventory-stock peer.

---

## 6. Meal Planning Flow

Use this flow when the user wants to plan meals for the week.

1. **Get or create the plan** — call `kitchen__get_meal_plan` with the Monday
   ISO date of the target week (format: `YYYY-MM-DD`). The endpoint creates an
   empty plan if none exists.

2. **Fill slots** — for each meal slot the user specifies (day_of_week 0–6,
   meal_slot: breakfast/lunch/dinner/snack), call `kitchen__set_meal_plan_entry`
   with the `recipe_id` or `free_text` and `servings`.

3. **Confirm** — after all slots are filled, call `kitchen__get_meal_plan` again
   to retrieve the full plan and show it to the user as a weekly grid.

4. **Shopping check** — optionally call `kitchen__get_shopping_list` to show
   what needs to be bought for the week's plan.

5. **Iterate** — if the user wants to change a slot, call
   `kitchen__set_meal_plan_entry` again for that specific day/slot. The endpoint
   upserts — calling it twice for the same slot replaces the first entry.

---

## 7. Shopping List Flow

Use this flow when the user asks what to buy for the week.

1. **Get the shopping list** — call `kitchen__get_shopping_list` with the
   Monday ISO date of the target week.

2. **Read the result** — `items` contains one entry per ingredient per unit,
   with `required_quantity`, `on_hand_quantity`, and `shortfall`. Items with
   `shortfall = 0` are already covered by stock. Only show items where
   `shortfall > 0` unless the user asks to see all.

3. **Group for presentation** — group shortfall items by physical location
   where they will be stored (pantry, fridge, freezer) if that information is
   available from prior receipts or aliases.

4. **After shopping** — use the receipt parsing flow (Section 3) to record what
   was purchased and update stock.

---

## 8. Nutrition Queries

Nutrition data is always read from stored records. Never estimate or fabricate
nutritional values.

- **Recipe nutrition** — call `kitchen__get_recipe_nutrition`. Returns null if
  no data has been set.

- **Set ingredient data** — call `kitchen__set_ingredient_nutrition` with
  per-100g values sourced from user input or a reliable external source. Always
  include `source` (e.g. `"usda"`, `"label"`, `"manual"`).

- **Recalculate recipe** — call `kitchen__calculate_recipe_nutrition` with
  `save=true` after setting new ingredient data. This derives per-serving totals
  from the stored ingredient records.

- **Missing data** — if `warnings` is non-empty in the nutrition response, name
  the missing ingredients to the user and offer to set their data.

- **Never estimate** — if ingredient nutrition data is absent, say so. Do not
  fill in values from memory or general knowledge.

---

## 9. Unit Handling

The kitchen module normalises mass and volume quantities to base units for
stock comparison and shopping list aggregation:

| Category | Base unit | Conversions |
|---|---|---|
| Mass | `g` | 1 kg = 1000 g, 1 lb = 453.592 g, 1 oz = 28.3495 g |
| Volume | `ml` | 1 L = 1000 ml, 1 cup = 240 ml, 1 tbsp = 15 ml, 1 tsp = 5 ml |
| Count | `piece` | eggs, items (no conversion) |

When recording recipe ingredients or stock quantities, use these base units
where possible. Use `g` for dry goods, `ml` for liquids, `piece` for discrete
items (eggs, apples). Using base units ensures correct shopping list arithmetic
when the same ingredient appears in multiple recipes with different unit
notations.

---

## 10. What Claude Must Never Do

| Prohibited | Reason | Correct alternative |
|---|---|---|
| Guess stock quantities | Stock data must come from `kitchen__list_stock` | Always call the tool |
| Assume a recipe exists | Recipe IDs are UUIDs — never fabricate them | Call `kitchen__list_recipes` first |
| Create catalogue primitives without user confirmation | Catalogue is authoritative; accidental entries are hard to remove | Always confirm before `create_primitive` |
| Write directly to inventory_stock_items | Kitchen module has read-only access to stock tables | Use `kitchen__bulk_update_stock` for writes |
| Estimate nutrition data | Nutrition is stored from explicit data only | Use stored values or acknowledge absence |
| Hallucinate catalogue paths | Paths are structured filesystem paths; wrong paths corrupt inventory links | Use `search_catalogue` to resolve |
| Assume the same unit across recipes | 200g flour ≠ 200ml flour; unit normalisation handles this | Let the shopping list aggregation handle unit conversion |

---

## MCP Tool Reference

### Stock
| Tool | Endpoint | Description |
|---|---|---|
| `kitchen__list_stock` | GET /stock | List stock (with location filter) |
| `kitchen__bulk_update_stock` | POST /stock/bulk | Batch create/update from receipt (primary write path) |
| `kitchen__get_expiring_soon` | GET /stock/expiring | Items expiring within N days |
| `kitchen__lookup_alias` | GET /stock/aliases/lookup | Resolve receipt text → catalogue_path |
| `kitchen__save_alias` | POST /stock/aliases | Save receipt text alias |

### Recipes
| Tool | Endpoint | Description |
|---|---|---|
| `kitchen__list_recipes` | GET /recipes | List with filters (cuisine, time, search) |
| `kitchen__get_recipe` | GET /recipes/{id} | Full recipe with ingredients + nutrition |
| `kitchen__create_recipe` | POST /recipes | Create new recipe |
| `kitchen__update_recipe` | PUT /recipes/{id} | Update recipe or ingredients |
| `kitchen__can_make` | GET /recipes/can-make | Recipes makeable from current stock |
| `kitchen__check_recipe_stock` | GET /recipes/{id}/stock-check | Per-ingredient availability |

### Nutrition
| Tool | Endpoint | Description |
|---|---|---|
| `kitchen__get_recipe_nutrition` | GET /recipes/{id}/nutrition | Stored per-serving nutrition |
| `kitchen__set_ingredient_nutrition` | POST /nutrition/ingredient | Upsert per-100g ingredient data |
| `kitchen__calculate_recipe_nutrition` | POST /recipes/{id}/nutrition/calculate | Recalculate from stored data |

### Meal Plan
| Tool | Endpoint | Description |
|---|---|---|
| `kitchen__get_meal_plan` | GET /meal-plan/{week} | Get or create week's plan |
| `kitchen__set_meal_plan_entry` | PUT /meal-plan/{week}/entry | Set a meal slot |
| `kitchen__get_shopping_list` | GET /meal-plan/{week}/shopping-list | Required ingredients minus stock |

### Cook Log
| Tool | Endpoint | Description |
|---|---|---|
| `kitchen__log_cook` | POST /cook-log | Record session, deduct stock |
| `kitchen__list_cook_log` | GET /cook-log | History with filters |

### Core tools used in kitchen flows
| Tool | Used for |
|---|---|
| `search_catalogue` | Resolve ingredient names to catalogue_path |
| `create_primitive` | Create new ingredient entries (type=material) |
