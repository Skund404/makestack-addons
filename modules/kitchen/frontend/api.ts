/**
 * Kitchen module API client — typed wrappers around the shell's apiGet/apiPost/apiPut.
 */
import { apiGet, apiPost, apiPut } from '@/lib/api'

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

export interface RecipeDetail extends RecipeListItem {
  description: string
  workflow_id: string | null
  notes: string
  ingredients: RecipeIngredient[]
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
  const parts = path.split('/')
  const slug = parts[parts.length - 1] || parts[0]
  return slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}
