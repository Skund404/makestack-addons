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
- kitchen_* UserDB tables (recipes, ingredients, nutrition, meal plans, cook log, locations, aliases, stock metadata)
- Kitchen-specific API endpoints mounted at /modules/kitchen/
- Kitchen views and panels (registered via Phase 8 manifest)
- SKILL.md — the AI intelligence layer


### What this module does NOT own
- inventory_stock_items table — owned by inventory-stock. Read-only cross-module access declared in manifest.
- Catalogue primitives — the kitchen backend NEVER calls Core's create/update/delete APIs.
  Primitive creation (for new ingredients) happens via the SKILL.md AI flow using core MCP tools.
- Shell routes, settings, or system endpoints
- Any other module's tables


### Stock access pattern
- For READS: the kitchen module declares inventory_stock_items as a read-only allowed table.
  This enables the can-make SQL join. The SDK allows this when declared in the manifest.
- For WRITES: all stock writes go through peers.call('inventory-stock', 'create_stock'|'update_stock').
  The kitchen module NEVER writes directly to inventory_stock_items.
- kitchen__list_stock, kitchen__update_stock, kitchen__add_stock_item are convenience wrappers
  that proxy to inventory-stock endpoints with location filter applied.
- kitchen__bulk_update_stock is the only genuinely new stock endpoint (batch operation).


### Kitchen-specific stock metadata
- kitchen_stock_metadata table extends inventory stock items with expiry_date and frozen_on_date.
- Joined with inventory_stock_items for display. Never replaces inventory-stock's own data.
- The kitchen module owns this table and its migration.


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


## API Endpoints


All mounted at /modules/kitchen/. Auto-generate MCP tools with naming: kitchen__{endpoint_name}


### Stock (convenience wrappers around inventory-stock peer)
- GET /stock — list kitchen stock (proxies to inventory-stock with location filter)
- GET /stock/:id — get item detail (proxies + joins kitchen_stock_metadata)
- PUT /stock/:id — update item (proxies to inventory-stock, updates kitchen_stock_metadata)
- POST /stock — add stock item (proxies to inventory-stock with location pre-filled)
- POST /stock/bulk — batch update (genuine kitchen endpoint for receipt parsing)
- GET /stock/expiring — expiring items from kitchen_stock_metadata
- GET /stock/aliases/lookup — look up receipt text alias
- POST /stock/aliases — save receipt text alias


### Recipes
- GET /recipes — list recipes with filters (cuisine_tag, max_cook_time, search)
- GET /recipes/:id — full recipe with ingredients, nutrition, cook log summary
- POST /recipes — create recipe
- PUT /recipes/:id — update recipe
- GET /recipes/can-make — recipes makeable from current stock
- GET /recipes/:id/stock-check — stock availability for a specific recipe


### Nutrition
- GET /recipes/:id/nutrition — nutrition breakdown per serving
- POST /nutrition/ingredient — set/update ingredient nutrition data
- POST /recipes/:id/nutrition/calculate — recalculate from ingredient data


### Meal Plan
- GET /meal-plan/:week — get or create plan for a week (Monday ISO date)
- PUT /meal-plan/:week/entry — set a meal slot entry
- GET /meal-plan/:week/shopping-list — required ingredients minus current stock


### Cook Log
- POST /cook-log — record cooking session (auto-deducts stock via peer)
- GET /cook-log — list sessions with filters (recipe_id, date range, rating)


## Manifest


### Views (Phase 8, registered in manifest.json views[])
- kitchen-pantry, kitchen-fridge, kitchen-freezer — location-filtered stock views
- kitchen-recipes — recipe library
- kitchen-recipe-detail — full recipe view
- kitchen-meal-plan — weekly calendar grid
- kitchen-shopping-list — generated shopping list
- kitchen-cook-log — cooking history


### Panels (Phase 8, registered in manifest.json panels[])
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


## Session Rules


Before writing any code:
1. Confirm inventory-stock is present in modules/ and its tests pass
2. Read the Shell CLAUDE.md fully for SDK patterns
3. Read modules/inventory-stock/backend/routes.py for the reference pattern
4. Check module_manifest.py for current manifest schema


## Build Order


K1 migrations + models + stock metadata table →
K2 recipe CRUD + ingredients + nutrition →
K3 meal plan + shopping list + cook log →
K4 can-make query + bulk stock + alias table →
K5 frontend (GATED on Phase 8B) →
K6 SKILL.md + manifest + full test suite


## Current State


K6 complete: SKILL.md, README.md, manifest finalised, GET /stock/expiring added, 113 passing tests.


## Session Log


2026-03-14 — K1: Created module scaffold, manifest, migrations (001 tables + 002 seed locations),
  Pydantic models, empty router/nutrition/shopping stubs, frontend index stub, tests.

2026-03-14 — K2: Recipe CRUD (GET/POST/PUT /recipes), ingredient management, nutrition endpoints
  (GET/:id/nutrition, POST /nutrition/ingredient, POST /:id/nutrition/calculate), migration 003
  (prep_time_mins + source columns), nutrition.py pure calculation logic, routes.py. 34 tests.

2026-03-14 — K3: Meal plan (GET/PUT /meal-plan/:week, PUT /meal-plan/:week/entry),
  shopping list (GET /meal-plan/:week/shopping-list with inventory JOIN), cook log
  (POST/GET /cook-log with peer stock deduction), migration 004 (serves_made rename +
  material_pulls_json + meal plan entry fields), shopping.py. 57 tests total.
  Key: Shell core inventory table is `inventory` (not `inventory_items`).
  Cook log deduction uses `peers.call("inventory-stock", "PUT", /stock/:id)`.

2026-03-14 — K4: can-make (GET /recipes/can-make, declared BEFORE /:id wildcard),
  stock-check (GET /recipes/:id/stock-check), bulk stock (POST /stock/bulk with peer
  create/update), alias endpoints (GET /stock/aliases/lookup, POST /stock/aliases),
  shopping list unit normalisation (g canonical unit for mass/volume, tuple key aggregation).
  78 tests total.
  Key: stock-check can_make=False for both 'missing' AND 'low' status.
  Key: _STOCK_BY_PATH_SQL subquery shared between can-make and stock-check.

2026-03-14 — K5: Frontend panels + views. Phase 8B wiring implemented in shell:
  vite.config.ts @kitchen-frontend alias, registry.ts (registerAllModulePanels),
  main.tsx calls registerAllModulePanels(), router.tsx kitchen routes added.
  Kitchen frontend: api.ts (typed wrappers), 5 panels (stock-overview/can-make/
  expiring/meal-plan-today/recently-cooked), 8 views (pantry/fridge/freezer/
  recipes/recipe-detail/meal-plan/shopping-list/cook-log), index.ts registration.
  Key: @kitchen-frontend alias → ../../makestack-addons/modules/kitchen/frontend/
  Key: registry.ts is "auto-generated at build time" pattern — kitchen wired manually.
  Key: Kitchen components import @/lib/api, @/components/ui/* via shell's @/ alias.
  TypeScript: 0 errors.

2026-03-14 — K6: SKILL.md (10 sections: purpose, storage model, receipt parsing,
  recipe capture, can-make, meal planning, shopping list, nutrition, unit handling,
  prohibited actions, full MCP tool reference table).
  README.md (install guide, feature overview, API reference, table list).
  manifest.json: removed unimplemented stock proxy endpoints (GET/PUT/POST /stock/:id,
  POST /stock); GET /stock/expiring moved to top of api_endpoints.
  routes.py: added GET /stock/expiring (reads kitchen_stock_metadata + JOIN).
  test_k6.py: 35 new tests covering migrations 003/004 up/down, expiring stock endpoint
  (5 scenarios), recipe filters, nutrition calculate, can-make (3 scenarios),
  stock-check scaling, meal plan round-trip, shopping list aggregation, cook log
  filters/pagination, alias upsert.
  Total: 113 kitchen tests passing, 474 shell tests passing.


