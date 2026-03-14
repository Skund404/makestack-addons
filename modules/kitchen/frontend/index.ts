/**
 * Kitchen module frontend — panel and keyword renderer exports.
 *
 * registerKitchenPanels() is called by the shell's registry.ts (auto-generated
 * at build time when the kitchen module is installed).
 *
 * View components are imported directly in router.tsx.
 */
import { registerPanel } from '@/modules/panel-registry'
import { KitchenStockOverview } from './panels/KitchenStockOverview'
import { KitchenCanMakeTonight } from './panels/KitchenCanMakeTonight'
import { KitchenExpiringSoon } from './panels/KitchenExpiringSoon'
import { KitchenMealPlanToday } from './panels/KitchenMealPlanToday'
import { KitchenRecentlyCooked } from './panels/KitchenRecentlyCooked'

export function registerKitchenPanels(): void {
  registerPanel('kitchen-stock-overview',   KitchenStockOverview)
  registerPanel('kitchen-can-make-tonight', KitchenCanMakeTonight)
  registerPanel('kitchen-expiring-soon',    KitchenExpiringSoon)
  registerPanel('kitchen-meal-plan-today',  KitchenMealPlanToday)
  registerPanel('kitchen-recently-cooked',  KitchenRecentlyCooked)
}

// Re-export view components for use in router.tsx
export { KitchenPantry, KitchenFridge, KitchenFreezer } from './views/KitchenStockView'
export { KitchenRecipes } from './views/KitchenRecipes'
export { KitchenRecipeDetail } from './views/KitchenRecipeDetail'
export { KitchenMealPlan } from './views/KitchenMealPlan'
export { KitchenShoppingList } from './views/KitchenShoppingList'
export { KitchenCookLog } from './views/KitchenCookLog'

// No keyword renderers in K5
export const keywords = {}
