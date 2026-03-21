# CLAUDE.md — Makestack Kitchen Module

> Read this entire file before doing any work on this module.

---

## Module Identity

- Name: kitchen
- Display name: Home Kitchen
- Repo: makestack-addons
- Type: module (full-stack: backend + frontend)
- Required peer: inventory-stock
- Optional peers: costing, suppliers
- Shell compatibility: >=0.1.0


## Architecture

The kitchen module is a domain layer on top of the makestack-shell.
It does NOT fork or duplicate any shell or peer module functionality.

### What this module owns
- kitchen_* UserDB tables (recipes, ingredients, nutrition, meal plans, cook log, locations, aliases, stock metadata, shopping list)
- Kitchen-specific API endpoints mounted at /modules/kitchen/
- Kitchen views and panels (standalone app mode)
- SKILL.md — the AI intelligence layer

### What this module does NOT own
- inventory_stock_items table — owned by inventory-stock. Read-only cross-module access declared in manifest.
- Catalogue primitives — the kitchen backend NEVER calls Core's create/update/delete APIs.
  Primitive creation (for new ingredients) happens via the SKILL.md AI flow using core MCP tools.
- Shell routes, settings, or system endpoints
- Any other module's tables

### Primitive Data Flow

Kitchen data connects to Core primitives through a 4-layer chain:

```
Core Primitive (material/workflow)
  → Shell `inventory` table (hash-pointer, keyed by catalogue_path)
    → `inventory_stock_items` (quantity/unit/location per item)
      → Kitchen tables (recipes, metadata, shopping)
```

**`catalogue_path` is the universal key.** It links:
- Recipe ingredients (`kitchen_recipe_ingredients.catalogue_path`)
- Stock items (`inventory.catalogue_path` → `inventory_stock_items`)
- Shopping list items (`kitchen_shopping_list.catalogue_path`, nullable)
- Stock metadata (`kitchen_stock_metadata.stock_item_id` → stock → inventory)

**Inventory pin is prerequisite for stock writes.** Before stock can be created for
a catalogue entry, that entry must be pinned to the user's inventory via
`add_to_inventory`. The `POST /stock/bulk` and `POST /stock/add` endpoints look up
items by `catalogue_path` in the `inventory` table — if the pin is missing, the
operation fails with "No inventory item found".

**`_STOCK_BY_PATH_SQL`** is a shared subquery (in routes.py) that joins
`inventory_stock_items` → `inventory` and groups by `catalogue_path` to get
`total_qty` per path. Used by can-make, stock-check, and add-from-recipe.

### Stock Access Pattern
- For READS: the kitchen module declares `inventory_stock_items` as a read-only
  allowed table. This enables the can-make SQL join. Also reads `inventory` for
  `catalogue_path` resolution.
- For WRITES: all stock writes go through `peers.call('inventory-stock', ...)`.
  The kitchen module NEVER writes directly to `inventory_stock_items`.
- `kitchen__list_stock` joins inventory + stock + kitchen_stock_metadata.
- `kitchen__bulk_update_stock` is the batch receipt-parsing write path.
- `kitchen__add_stock_item` creates a single item via peer + optional metadata.

### Kitchen-specific stock metadata
- `kitchen_stock_metadata` extends inventory stock items with `expiry_date` and `frozen_on_date`.
- Joined with `inventory_stock_items` for display. Never replaces inventory-stock's own data.
- The kitchen module owns this table and its migration.

### MCP-Native Design

All endpoints auto-generate MCP tools via the manifest `api_endpoints[].name` field.
Tool naming follows the pattern: `kitchen__{name}` (e.g., `kitchen__list_stock`,
`kitchen__add_shopping_item`).

SKILL.md defines AI flows that compose kitchen tools + shell tools
(`search_catalogue`, `create_primitive`, `add_to_inventory`). The frontend is for
humans; MCP is for AI — same backend, different clients.


## Primitive Mapping

- Materials = Ingredients (catalogue entries in makestack-core)
- Tools = Kitchen equipment (catalogue entries)
- Techniques = Cooking techniques (catalogue entries)
- Workflows = Recipes (catalogue entry + kitchen_recipes composition layer)
- Projects = Meal plans (kitchen_meal_plan in UserDB)
- Events = Cooking sessions (kitchen_cook_log in UserDB)


## UserDB Tables (all prefixed kitchen_)

- kitchen_recipes — recipe records linking workflow primitives to kitchen metadata
- kitchen_recipe_ingredients — ingredient entries per recipe with quantities
- kitchen_recipe_nutrition — nutritional data per recipe (per serving)
- kitchen_ingredient_nutrition — nutritional data per ingredient (per 100g)
- kitchen_meal_plan — weekly meal plans
- kitchen_meal_plan_entries — individual entries within a meal plan
- kitchen_cook_log — cooking session log
- kitchen_locations — location configuration (pantry/fridge/freezer/other)
- kitchen_stock_aliases — receipt text to catalogue path mappings
- kitchen_stock_metadata — expiry_date, frozen_on_date per stock item
- kitchen_shopping_list — persistent shopping list (manual + recipe-derived items)


## API Endpoints

All mounted at /modules/kitchen/. Auto-generate MCP tools with naming: kitchen__{name}

### Stock
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| GET | /stock | list_stock | List stock items with optional location filter |
| GET | /stock/expiring | list_expiring_stock | Items expiring within N days |
| GET | /stock/aliases/lookup | lookup_stock_alias | Resolve receipt text to catalogue_path |
| POST | /stock/aliases | save_stock_alias | Save receipt text alias |
| POST | /stock/bulk | bulk_update_stock | Batch update from receipt parsing |
| POST | /stock/add | add_stock_item | Create single item via inventory-stock peer |
| PUT | /stock/{id} | update_stock_item | Update stock item qty/unit/location/expiry |
| DELETE | /stock/{id} | delete_stock_item | Remove stock item + clean metadata |

### Recipes
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| GET | /recipes | list_recipes | List with filters (cuisine_tag, max_cook_time, search) |
| GET | /recipes/{id} | get_recipe | Full recipe with ingredients, nutrition, cook summary |
| POST | /recipes | create_recipe | Create new recipe |
| PUT | /recipes/{id} | update_recipe | Update recipe metadata and/or ingredients |
| POST | /recipes/full | create_recipe_full | Create recipe with full primitive composition |
| PUT | /recipes/{id}/full | update_recipe_full | Update recipe with full primitive composition |
| DELETE | /recipes/{id} | delete_recipe | Delete recipe (preserves Workflow primitive) |
| GET | /recipes/can-make | list_can_make | Recipes makeable from current stock |
| GET | /recipes/{id}/stock-check | recipe_stock_check | Per-ingredient stock status |

### Nutrition
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| GET | /recipes/{id}/nutrition | get_recipe_nutrition | Stored per-serving nutrition |
| POST | /nutrition/ingredient | set_ingredient_nutrition | Upsert per-100g ingredient data |
| POST | /recipes/{id}/nutrition/calculate | calculate_recipe_nutrition | Recalculate from stored data |

### Meal Plan
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| GET | /meal-plan/{week} | get_meal_plan | Get or create plan (Monday ISO date) |
| PUT | /meal-plan/{week}/entry | set_meal_plan_entry | Upsert a meal slot entry |
| GET | /meal-plan/{week}/shopping-list | get_shopping_list | Aggregated ingredients minus stock |
| DELETE | /meal-plan/{week}/entry/{id} | delete_meal_plan_entry | Delete single meal plan entry |

### Cook Log
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| POST | /cook-log | record_cook_session | Record session, auto-deduct stock |
| GET | /cook-log | list_cook_log | History with filters |

### Catalogue
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| GET | /catalogue/search | search_catalogue | Search catalogue with optional type filter |

### Shopping List (persistent)
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| GET | /shopping | list_shopping | List items (tab=buy for unchecked only) |
| POST | /shopping | add_shopping_item | Add manual item |
| POST | /shopping/from-recipe/{id} | add_recipe_to_shopping | Add missing recipe ingredients |
| POST | /shopping/clear-checked | clear_checked_shopping | Delete checked items |
| GET | /shopping/badge | get_shopping_badge | Unchecked item count (for badge) |
| PUT | /shopping/{id} | update_shopping_item | Toggle checked, update qty/note |
| DELETE | /shopping/{id} | delete_shopping_item | Remove single item |


## App Mode (standalone layout)

The kitchen module uses standalone app mode — it renders with its own branded
sidebar instead of appearing as views in the shell sidebar.

- Title: "Kitchen", subtitle: "Home module"
- Theme: warm brown (#15100b bg, #eddec8 text, Cormorant Garamond serif)
- Custom sidebar: `KitchenSidebar` component with shopping list badge
- Home route: `/kitchen`
- Nav items: Home, Larder, Recipes, Plan, Shop

## Views

| Route | Component | Description |
|-------|-----------|-------------|
| /kitchen | KitchenHome | Dashboard: greeting, today's plan, quick-look widgets |
| /kitchen/larder | KitchenLarder | Three-column stock view (Pantry/Fridge/Freezer) + add item form |
| /kitchen/recipes | KitchenRecipes | Two-pane: recipe list with status dots + detail pane |
| /kitchen/recipes/new | KitchenRecipeNew | Recipe builder (create mode) |
| /kitchen/recipes/:id | KitchenRecipeDetail | Standalone recipe detail (deep-link) |
| /kitchen/recipes/:id/edit | KitchenRecipeEdit | Recipe builder (edit mode, pre-populated) |
| /kitchen/meal-plan | KitchenMealPlan | Weekly grid with click-to-edit + shopping sidebar |
| /kitchen/shopping | KitchenShoppingList | Persistent list with checkboxes + add panel |
| /kitchen/cook-log | KitchenCookLog | Cooking history (accessible by URL, not in sidebar) |

## Panels (workshop home dashboard)

- kitchen-stock-overview (full) — three-column stock summary
- kitchen-can-make-tonight (half) — makeable recipes
- kitchen-expiring-soon (half) — items expiring within 7 days
- kitchen-meal-plan-today (half) — today's meal plan
- kitchen-recently-cooked (third) — last 5 cook log entries


## Code Standards

- All endpoints async, typed (Pydantic 2.x), follow existing inventory-stock pattern
- All migrations have both up() and down() — Phase 10 hard requirement
- Use makestack_sdk imports: get_module_userdb_factory, get_peer_modules, get_logger
- Error responses include suggestion field for AI consumption
- Peer availability checked at request time, not import time
- Nutritional data is stored, never computed on-demand from external APIs
- If ingredient nutrition is absent, return null — never estimate in backend
- Frontend uses `nameFromPath(catalogue_path)` to display human-readable names from catalogue paths
- Shopping list has two systems: meal-plan-derived (auto-calculated) and persistent (manual + recipe-derived)


### Orchestrated Recipe Creation (K9a)

The kitchen backend now creates catalogue primitives directly via `CatalogueClient`:
- `POST /recipes/full` — one API call creates Material primitives (for new ingredients),
  a Workflow primitive (with relationships to materials/techniques/tools), pins to
  inventory, and creates kitchen_recipes + kitchen_recipe_ingredients rows.
- `PUT /recipes/{id}/full` — same orchestration for updates.
- `GET /catalogue/search` — proxy to Core search with optional type filter.

This is a departure from the original "kitchen never calls Core" rule — the kitchen
backend now imports `get_catalogue_client` from `makestack_sdk` and creates primitives
directly. This is intentional for the recipe builder UX.


## Current State

K9 in progress: orchestrated recipe CRUD (7 new endpoints), recipe builder UI,
stock edit/delete, cook log record form, meal plan clear entry.
Backend: 138 passing tests. 35 MCP tools. TypeScript: 0 errors.
Frontend: RecipeBuilder, IngredientSearch, StockItemDialog, RecordCookPanel.
New views: /kitchen/recipes/new, /kitchen/recipes/:id/edit.
