# Home Kitchen Module

A full-stack Makestack module for managing your home kitchen: pantry, fridge,
freezer, recipe library, meal planning, shopping lists, and cooking history.
Designed to work seamlessly with AI assistants via the Makestack MCP server.

---

## What It Does

- **Stock tracking** — know what's in your pantry, fridge, and freezer at all
  times, including expiry dates and frozen-on dates
- **Recipe library** — save and search recipes linked to catalogue ingredients,
  with full nutritional data stored per serving
- **Can-make queries** — instantly see which recipes you can cook tonight based
  on what's actually in stock
- **Meal planning** — plan breakfast, lunch, dinner, and snacks across a full
  week on a calendar grid
- **Shopping lists** — auto-generated from meal plans, with shortfalls
  calculated against current stock and unit-normalised aggregation
- **Receipt parsing** — paste in a grocery receipt and have AI parse, alias, and
  bulk-update your stock in one pass
- **Cook log** — record every cooking session with rating and notes; stock is
  automatically deducted

---

## Requirements

- makestack-shell >= 0.1.0
- **inventory-stock** module (required peer) — provides the stock table and
  write API; kitchen stock is a filtered view of inventory stock

Optional peers: `costing`, `suppliers`

---

## Installation

```bash
makestack module install kitchen
```

Or install via the Packages page in the UI. The shell will:
1. Run database migrations (kitchen\_\* tables)
2. Seed default locations (pantry, fridge, freezer)
3. Mount the backend router at `/modules/kitchen/`
4. Register kitchen panels on the workshop home
5. Add kitchen nav views to workshop sidebars

---

## Storage Model

Kitchen stock is a **filtered view of the inventory-stock module**. Stock items
live in `inventory_stock_items` (owned by inventory-stock); the kitchen module
reads them directly and writes through the peer API.

Kitchen-specific metadata (expiry dates, frozen-on dates) lives in
`kitchen_stock_metadata`, joined with stock items for display.

### Locations

| Key | Description |
|---|---|
| `pantry` | Dry goods, canned goods, spices |
| `fridge` | Refrigerators items |
| `freezer` | Frozen items |

---

## Key Features

### Receipt Parsing (AI flow)

Ask Claude: *"I just went shopping — here's my receipt: flour 2kg, milk 2L, eggs 12..."*

Claude will:
1. Look up aliases for each item
2. Search the catalogue for unrecognised items
3. Ask where each item goes (pantry/fridge/freezer)
4. Bulk-update stock in one call

### Can Make Tonight

Ask Claude: *"What can I cook for dinner?"*

Claude checks which recipes are fully covered by current stock, and which are
one ingredient away. Shows cook time and cuisine tag.

### Meal Planning

Ask Claude: *"Plan dinners for next week"*

Claude fills the weekly meal plan grid based on your preferences, then
generates a shopping list for anything you're missing.

### Nutrition Tracking

Nutrition is always stored data — never estimated. Set ingredient values
(per 100g) and the module calculates per-serving recipe totals. Warns about
missing data rather than guessing.

---

## API Reference

All endpoints are at `/modules/kitchen/`. See the manifest for the full list.

### Stock
| Method | Path | Description |
|---|---|---|
| `GET` | `/stock/expiring` | Items expiring within N days |
| `GET` | `/stock/aliases/lookup` | Resolve receipt text to catalogue path |
| `POST` | `/stock/aliases` | Save receipt text alias |
| `POST` | `/stock/bulk` | Batch update/create stock from receipt |

### Recipes
| Method | Path | Description |
|---|---|---|
| `GET` | `/recipes` | List with filters (cuisine, time, search) |
| `GET` | `/recipes/{id}` | Full recipe detail |
| `POST` | `/recipes` | Create recipe |
| `PUT` | `/recipes/{id}` | Update recipe |
| `GET` | `/recipes/can-make` | Makeable from current stock |
| `GET` | `/recipes/{id}/stock-check` | Per-ingredient availability |

### Nutrition
| Method | Path | Description |
|---|---|---|
| `GET` | `/recipes/{id}/nutrition` | Stored per-serving nutrition |
| `POST` | `/nutrition/ingredient` | Set ingredient per-100g data |
| `POST` | `/recipes/{id}/nutrition/calculate` | Recalculate from stored data |

### Meal Plan
| Method | Path | Description |
|---|---|---|
| `GET` | `/meal-plan/{week}` | Get/create week plan (Monday ISO date) |
| `PUT` | `/meal-plan/{week}/entry` | Set a meal slot |
| `GET` | `/meal-plan/{week}/shopping-list` | Shopping list for the week |

### Cook Log
| Method | Path | Description |
|---|---|---|
| `POST` | `/cook-log` | Record a cooking session |
| `GET` | `/cook-log` | List sessions with filters |

---

## MCP Tools

When the module is installed, the following MCP tools are available to AI
agents. See `SKILL.md` for the complete AI interaction guide.

`kitchen__list_expiring_stock`, `kitchen__lookup_stock_alias`,
`kitchen__save_stock_alias`, `kitchen__bulk_update_stock`,
`kitchen__list_recipes`, `kitchen__get_recipe`, `kitchen__create_recipe`,
`kitchen__update_recipe`, `kitchen__can_make`, `kitchen__check_recipe_stock`,
`kitchen__get_recipe_nutrition`, `kitchen__set_ingredient_nutrition`,
`kitchen__calculate_recipe_nutrition`, `kitchen__get_meal_plan`,
`kitchen__set_meal_plan_entry`, `kitchen__get_shopping_list`,
`kitchen__log_cook`, `kitchen__list_cook_log`

---

## Database Tables

All tables are prefixed `kitchen_` in the UserDB (`~/.makestack/userdb.sqlite`).

| Table | Description |
|---|---|
| `kitchen_recipes` | Recipe records with metadata |
| `kitchen_recipe_ingredients` | Ingredients per recipe with quantities |
| `kitchen_recipe_nutrition` | Stored per-serving nutrition totals |
| `kitchen_ingredient_nutrition` | Per-100g nutrition data per ingredient |
| `kitchen_meal_plan` | Weekly plans (one per Monday date) |
| `kitchen_meal_plan_entries` | Meal slots within a plan |
| `kitchen_cook_log` | Cooking session history |
| `kitchen_locations` | Configured storage locations |
| `kitchen_stock_aliases` | Receipt text → catalogue path mappings |
| `kitchen_stock_metadata` | Expiry and frozen-on dates per stock item |

---

## License

Proprietary — see module licence terms.
