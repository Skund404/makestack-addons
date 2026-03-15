/**
 * Kitchen module frontend — registers all panels and views with the shell.
 *
 * registerKitchenModule() is called by the shell's registry.ts (auto-generated
 * at build time when the kitchen module is installed). It registers:
 *  - Panels: resolved by the workshop home page via panel-registry
 *  - Views:  resolved by the shell's ModuleViewRenderer via view-registry
 *
 * Route patterns match manifest.json views[].route exactly.
 */
import { registerPanel } from '@/modules/panel-registry'
import { registerView } from '@/modules/view-registry'
import { KitchenStockOverview } from './panels/KitchenStockOverview'
import { KitchenCanMakeTonight } from './panels/KitchenCanMakeTonight'
import { KitchenExpiringSoon } from './panels/KitchenExpiringSoon'
import { KitchenMealPlanToday } from './panels/KitchenMealPlanToday'
import { KitchenRecentlyCooked } from './panels/KitchenRecentlyCooked'
import { KitchenPantry, KitchenFridge, KitchenFreezer } from './views/KitchenStockView'
import { KitchenRecipes } from './views/KitchenRecipes'
import { KitchenRecipeDetail } from './views/KitchenRecipeDetail'
import { KitchenMealPlan } from './views/KitchenMealPlan'
import { KitchenShoppingList } from './views/KitchenShoppingList'
import { KitchenCookLog } from './views/KitchenCookLog'

export function registerKitchenModule(): void {
  // --- Panels (workshop home) ---
  registerPanel('kitchen-stock-overview',   KitchenStockOverview)
  registerPanel('kitchen-can-make-tonight', KitchenCanMakeTonight)
  registerPanel('kitchen-expiring-soon',    KitchenExpiringSoon)
  registerPanel('kitchen-meal-plan-today',  KitchenMealPlanToday)
  registerPanel('kitchen-recently-cooked',  KitchenRecentlyCooked)

  // --- Views (routes match manifest.json views[].route) ---
  registerView('/kitchen/pantry',           KitchenPantry)
  registerView('/kitchen/fridge',           KitchenFridge)
  registerView('/kitchen/freezer',          KitchenFreezer)
  registerView('/kitchen/recipes',          KitchenRecipes)
  registerView('/kitchen/recipes/:id',      KitchenRecipeDetail)
  registerView('/kitchen/meal-plan',        KitchenMealPlan)
  registerView('/kitchen/shopping',         KitchenShoppingList)
  registerView('/kitchen/cook-log',         KitchenCookLog)
}

// No keyword renderers in this module
export const keywords = {}
