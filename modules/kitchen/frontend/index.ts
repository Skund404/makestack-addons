/**
 * Kitchen module frontend — registers panels, views, and app mode with the shell.
 *
 * registerKitchenModule() is called by the shell's registry.ts (auto-generated
 * at build time when the kitchen module is installed). It registers:
 *  - App mode: standalone layout with branded sidebar
 *  - Panels: resolved by the workshop home page via panel-registry
 *  - Views:  resolved by the shell's ModuleViewRenderer via view-registry
 *
 * Route patterns match manifest.json views[].route exactly.
 */
import { registerPanel } from '@/modules/panel-registry'
import { registerView } from '@/modules/view-registry'
import { registerAppMode } from '@/modules/app-registry'
import { KitchenStockOverview } from './panels/KitchenStockOverview'
import { KitchenCanMakeTonight } from './panels/KitchenCanMakeTonight'
import { KitchenExpiringSoon } from './panels/KitchenExpiringSoon'
import { KitchenMealPlanToday } from './panels/KitchenMealPlanToday'
import { KitchenRecentlyCooked } from './panels/KitchenRecentlyCooked'
import { KitchenHome } from './views/KitchenHome'
import { KitchenLarder } from './views/KitchenLarder'
import { KitchenRecipes } from './views/KitchenRecipes'
import { KitchenRecipeDetail } from './views/KitchenRecipeDetail'
import { KitchenMealPlan } from './views/KitchenMealPlan'
import { KitchenShoppingList } from './views/KitchenShoppingList'
import { KitchenCookLog } from './views/KitchenCookLog'
import { KitchenSidebar } from './components/KitchenSidebar'

export function registerKitchenModule(): void {
  // --- App mode (standalone layout) ---
  registerAppMode({
    module_name: 'kitchen',
    title: 'Kitchen',
    subtitle: 'Home module',
    sidebar_width: 186,
    home_route: '/kitchen',
    nav_items: [
      { id: 'kitchen-home',      label: 'Home',    icon: 'Home',         route: '/kitchen' },
      { id: 'kitchen-larder',    label: 'Larder',  icon: 'Archive',      route: '/kitchen/larder' },
      { id: 'kitchen-recipes',   label: 'Recipes', icon: 'BookOpen',     route: '/kitchen/recipes' },
      { id: 'kitchen-meal-plan', label: 'Plan',    icon: 'Calendar',     route: '/kitchen/meal-plan' },
      { id: 'kitchen-shopping',  label: 'Shop',    icon: 'ShoppingCart', route: '/kitchen/shopping' },
    ],
    theme: {
      sidebar_bg: '#15100b',
      sidebar_text: '#eddec8',
      sidebar_active_bg: '#271d12',
      accent: '#c8935a',
    },
    custom_sidebar: KitchenSidebar,
  })

  // --- Panels (workshop home) ---
  registerPanel('kitchen-stock-overview',   KitchenStockOverview)
  registerPanel('kitchen-can-make-tonight', KitchenCanMakeTonight)
  registerPanel('kitchen-expiring-soon',    KitchenExpiringSoon)
  registerPanel('kitchen-meal-plan-today',  KitchenMealPlanToday)
  registerPanel('kitchen-recently-cooked',  KitchenRecentlyCooked)

  // --- Views (routes) ---
  registerView('/kitchen',                  KitchenHome)
  registerView('/kitchen/larder',           KitchenLarder)
  registerView('/kitchen/recipes',          KitchenRecipes)
  registerView('/kitchen/recipes/:id',      KitchenRecipeDetail)
  registerView('/kitchen/meal-plan',        KitchenMealPlan)
  registerView('/kitchen/shopping',         KitchenShoppingList)
  registerView('/kitchen/cook-log',         KitchenCookLog)
}

// No keyword renderers in this module
export const keywords = {}
