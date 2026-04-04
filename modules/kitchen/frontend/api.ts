/**
 * Kitchen module API client — typed wrappers around the shell's apiGet/apiPost/apiPut.
 */
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface KitchenStockItem {
  id: string
  catalogue_path: string
  quantity: number
  unit: string
  location: string
  notes: string
  expiry_date: string | null
  frozen_on_date: string | null
}

export interface KitchenStockList {
  items: KitchenStockItem[]
  total: number
  limit: number
  offset: number
}

export interface ExpiringItem {
  stock_item_id: string
  expiry_date: string
  days_until_expiry: number
  inventory_id: string
  quantity: number
  unit: string
  location: string
  catalogue_path?: string
}

export interface RecipeListItem {
  id: string
  title: string
  servings: number
  prep_time_mins: number | null
  cook_time_mins: number | null
  total_time_mins: number | null
  cuisine_tag: string
  last_cooked_at: string | null
  cook_count: number
  created_at: string
  updated_at: string
}

export interface RecipeListResponse {
  items: RecipeListItem[]
  total: number
  limit: number
  offset: number
}

export interface RecipeIngredient {
  id: string
  recipe_id: string
  catalogue_path: string
  name: string
  quantity: number
  unit: string
  notes: string
}

export interface LinkedPrimitive {
  path: string
  name: string
}

export interface RecipeDetail extends RecipeListItem {
  description: string
  workflow_id: string | null
  forked_from_recipe_id: string | null
  forked_from_recipe_title: string | null
  notes: string
  ingredients: RecipeIngredient[]
  techniques: LinkedPrimitive[]
  tools: LinkedPrimitive[]
  nutrition: NutritionData | null
  cook_summary: { count: number; last_cooked_at: string | null; avg_rating: number | null } | null
}

export interface NutritionData {
  calories: number | null
  protein_g: number | null
  fat_g: number | null
  carbs_g: number | null
  fiber_g: number | null
  sugar_g: number | null
  sodium_mg: number | null
  source: string | null
  warnings: string[]
}

export interface StockCheckIngredient {
  catalogue_path: string
  name: string
  required_quantity: number
  unit: string
  on_hand_quantity: number
  status: 'ok' | 'low' | 'missing'
}

export interface CanMakeResult {
  recipe_id: string
  recipe_title: string
  can_make: boolean
  missing_count: number
  ingredients: StockCheckIngredient[]
}

export interface CanMakeResponse {
  recipes: CanMakeResult[]
  total: number
}

export interface MealPlanEntry {
  id: string
  day_of_week: number
  meal_slot: string
  recipe_id: string | null
  servings: number
  notes: string
  free_text: string
  serves_override: number | null
  recipe_title?: string
}

export interface MealPlan {
  id: string
  week_start: string
  notes: string
  entries: MealPlanEntry[]
  created_at: string
  updated_at: string
}

export interface CookLogEntry {
  id: string
  recipe_id: string
  cooked_at: string
  serves_made: number
  rating: number | null
  notes: string
  stock_deducted: boolean
  material_pulls_json: string | null
  warnings: string[]
  recipe_title?: string
}

export interface CookLogResponse {
  items: CookLogEntry[]
  total: number
  limit: number
  offset: number
}

export interface ShoppingListItem {
  catalogue_path: string
  name: string
  required_quantity: number
  unit: string
  on_hand_quantity: number
  shortfall: number
}

export interface ShoppingListResponse {
  week_start: string
  items: ShoppingListItem[]
  total_items: number
}

// Persistent shopping list (kitchen_shopping_list table)
export interface PersistentShoppingItem {
  id: string
  name: string
  catalogue_path: string | null
  quantity: number
  unit: string
  source: string
  source_recipe_id: string | null
  checked: boolean | number
  note: string
  created_at: string
  updated_at: string
}

export interface PersistentShoppingListData {
  items: PersistentShoppingItem[]
  total: number
  to_buy: number
}

// K9b: Recipe builder types
export interface RecipeIngredientInput {
  catalogue_path?: string | null
  name: string
  quantity: number
  unit: string
  notes?: string
}

export interface RecipeFullCreate {
  title: string
  description?: string
  cuisine_tag?: string
  prep_time_mins?: number | null
  cook_time_mins?: number | null
  servings?: number
  difficulty?: string
  notes?: string
  tags?: string[]
  steps?: string[]
  ingredients?: RecipeIngredientInput[]
  techniques?: string[]
  tools?: string[]
}

export interface CatalogueSearchResult {
  path: string
  name: string
  type: string
  description: string
  tags: string[]
}

export interface CatalogueSearchResponse {
  results: CatalogueSearchResult[]
  total: number
}

export interface StockItemUpdate {
  quantity?: number
  unit?: string
  location?: string
  expiry_date?: string | null
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

const BASE = '/modules/kitchen'

export const kitchenApi = {
  // Stock
  listStock: (params?: { location?: string; limit?: number; offset?: number }) =>
    apiGet<KitchenStockList>(`${BASE}/stock`, params as Record<string, string | number | undefined>),

  listExpiring: (days = 7) =>
    apiGet<ExpiringItem[]>(`${BASE}/stock/expiring`, { days }),

  // Recipes
  listRecipes: (params?: { cuisine_tag?: string; max_cook_time?: number; search?: string; limit?: number; offset?: number }) =>
    apiGet<RecipeListResponse>(`${BASE}/recipes`, params as Record<string, string | number | undefined>),

  getRecipe: (id: string) =>
    apiGet<RecipeDetail>(`${BASE}/recipes/${id}`),

  canMake: (strict = true, limit = 20) =>
    apiGet<CanMakeResponse>(`${BASE}/recipes/can-make`, { strict: strict ? '1' : '0', limit }),

  stockCheck: (recipeId: string) =>
    apiGet<CanMakeResult>(`${BASE}/recipes/${recipeId}/stock-check`),

  // Meal plan
  getMealPlan: (week: string) =>
    apiGet<MealPlan>(`${BASE}/meal-plan/${week}`),

  setMealPlanEntry: (week: string, entry: object) =>
    apiPut<MealPlanEntry>(`${BASE}/meal-plan/${week}/entry`, entry),

  getShoppingList: (week: string) =>
    apiGet<ShoppingListResponse>(`${BASE}/meal-plan/${week}/shopping-list`),

  // Cook log
  listCookLog: (params?: { recipe_id?: string; limit?: number; offset?: number }) =>
    apiGet<CookLogResponse>(`${BASE}/cook-log`, params as Record<string, string | number | undefined>),

  recordCookSession: (entry: object) =>
    apiPost<CookLogEntry>(`${BASE}/cook-log`, entry),

  // Persistent shopping list
  listShopping: (tab?: string) =>
    apiGet<PersistentShoppingListData>(`${BASE}/shopping`, tab ? { tab } : undefined),

  addShopping: (item: { name: string; catalogue_path?: string; quantity?: number; unit?: string; note?: string }) =>
    apiPost<PersistentShoppingItem>(`${BASE}/shopping`, item),

  updateShopping: (id: string, updates: { checked?: boolean; quantity?: number; note?: string }) =>
    apiPut<PersistentShoppingItem>(`${BASE}/shopping/${id}`, updates),

  deleteShopping: (id: string) =>
    apiDelete(`${BASE}/shopping/${id}`),

  addFromRecipe: (recipeId: string) =>
    apiPost<{ added: number; recipe_id: string; recipe_title: string }>(`${BASE}/shopping/from-recipe/${recipeId}`, {}),

  clearChecked: () =>
    apiPost<{ deleted: number }>(`${BASE}/shopping/clear-checked`, {}),

  getShoppingBadge: () =>
    apiGet<{ count: number }>(`${BASE}/shopping/badge`),

  // Stock — add
  addStockItem: (item: { catalogue_path?: string; name?: string; quantity: number; unit: string; location: string; expiry_date?: string; notes?: string }) =>
    apiPost<{ stock_item_id: string; catalogue_path: string; quantity: number; location: string }>(`${BASE}/stock/add`, item),

  // Forking
  forkRecipe: (id: string, name?: string) =>
    apiPost<RecipeDetail>(`${BASE}/recipes/${id}/fork`, name ? { name } : {}),

  forkCataloguePrimitive: (path: string, name?: string, description?: string) =>
    apiPost<{ id: string; type: string; name: string; slug: string; path: string; cloned_from: string; description: string; tags: string[] }>(
      `${BASE}/catalogue/primitives/${path}/fork`,
      { ...(name ? { name } : {}), ...(description ? { description } : {}) }
    ),

  // K9b: Orchestrated recipe CRUD
  createRecipeFull: (data: RecipeFullCreate) =>
    apiPost<RecipeDetail>(`${BASE}/recipes/full`, data),

  updateRecipeFull: (id: string, data: RecipeFullCreate) =>
    apiPut<RecipeDetail>(`${BASE}/recipes/${id}/full`, data),

  deleteRecipe: (id: string) =>
    apiDelete<{ deleted: boolean; id: string }>(`${BASE}/recipes/${id}`),

  // K9b: Catalogue search
  searchCatalogue: (q: string, type?: string) =>
    apiGet<CatalogueSearchResponse>(`${BASE}/catalogue/search`, { q, ...(type ? { type } : {}) }),

  // K9b: Stock item edit/delete
  updateStockItem: (id: string, updates: StockItemUpdate) =>
    apiPut<KitchenStockItem>(`${BASE}/stock/${id}`, updates),

  deleteStockItem: (id: string) =>
    apiDelete<{ deleted: boolean; id: string }>(`${BASE}/stock/${id}`),

  // K9b: Meal plan entry delete
  deleteMealPlanEntry: (week: string, entryId: string) =>
    apiDelete<{ deleted: boolean; id: string }>(`${BASE}/meal-plan/${week}/entry/${entryId}`),
}

// ---------------------------------------------------------------------------
// Date helpers
// ---------------------------------------------------------------------------

/** Returns the ISO date of the Monday of the current week. */
export function currentMondayISO(): string {
  const d = new Date()
  const day = d.getDay() // 0=Sun, 1=Mon...6=Sat
  const diff = d.getDate() - day + (day === 0 ? -6 : 1)
  const monday = new Date(d)
  monday.setDate(diff)
  return monday.toISOString().split('T')[0]
}

/** Returns the day-of-week index where 0=Monday...6=Sunday (matches backend). */
export function todayDow(): number {
  const day = new Date().getDay() // 0=Sun
  return day === 0 ? 6 : day - 1
}

/** Format a quantity + unit for display. */
export function fmtQty(quantity: number, unit: string): string {
  const qty = quantity % 1 === 0 ? quantity.toString() : quantity.toFixed(1)
  return unit ? `${qty} ${unit}` : qty
}

/** Display name from catalogue_path like "materials/flour" → "Flour". */
export function nameFromPath(path: string): string {
  // Catalogue paths are "type/slug/manifest.json" — the readable name is the slug (index -2).
  // Fall back to the last segment if the path has fewer than 2 parts.
  const parts = path.split('/')
  const slug = parts.length >= 2 ? parts[parts.length - 2] : (parts[parts.length - 1] || parts[0])
  return slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}
