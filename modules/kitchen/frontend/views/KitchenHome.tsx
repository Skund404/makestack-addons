/**
 * KitchenHome — dashboard view matching the mockup's "Good evening" screen.
 *
 * Shows today's meal plan cards and quick-look widgets (expiring, can-make, shopping summary).
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { kitchenApi, currentMondayISO, todayDow, nameFromPath } from '../api'
import type { MealPlan, ExpiringItem, CanMakeResponse, PersistentShoppingListData } from '../api'

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

const MEAL_SLOTS = ['breakfast', 'lunch', 'dinner', 'snack'] as const

function expiryBadgeColor(daysUntil: number): string {
  if (daysUntil <= 1) return '#ef4444' // red
  if (daysUntil <= 3) return '#f97316' // orange
  return 'var(--text-faint)'
}

export function KitchenHome() {
  const weekKey = currentMondayISO()
  const dow = todayDow()

  const { data: mealPlan, isLoading: mpLoading } = useQuery({
    queryKey: ['kitchen-meal-plan', weekKey],
    queryFn: () => kitchenApi.getMealPlan(weekKey),
    staleTime: 60_000,
  })

  const { data: expiring } = useQuery({
    queryKey: ['kitchen-expiring-home'],
    queryFn: () => kitchenApi.listExpiring(7),
    staleTime: 60_000,
  })

  const { data: canMake } = useQuery({
    queryKey: ['kitchen-can-make-home'],
    queryFn: () => kitchenApi.canMake(false),
    staleTime: 60_000,
  })

  const { data: shoppingData } = useQuery({
    queryKey: ['kitchen-shopping-home'],
    queryFn: () => kitchenApi.listShopping('buy'),
    staleTime: 60_000,
  })

  const todayEntries = (mealPlan?.entries ?? []).filter((e) => e.day_of_week === dow)

  const expiringItems = expiring ?? []
  const canMakeRecipes = canMake?.recipes ?? []
  const shoppingItems = shoppingData?.items ?? []

  return (
    <div className="p-5 max-w-3xl">
      {/* Greeting */}
      <h1
        className="text-2xl mb-1"
        style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", color: 'var(--text-primary)' }}
      >
        {getGreeting()}
      </h1>
      <p className="text-xs text-text-faint mb-6">
        {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}
      </p>

      {/* Today's plan */}
      <SectionLabel>Today's Plan</SectionLabel>
      {mpLoading ? (
        <div className="flex items-center gap-2 py-4 text-text-muted">
          <Loader2 size={12} className="animate-spin" /> <span className="text-xs">Loading...</span>
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-3 mb-6">
          {MEAL_SLOTS.map((slot) => {
            const entry = todayEntries.find((e) => e.meal_slot === slot)
            return (
              <div key={slot} className="rounded-lg border border-border bg-surface p-3">
                <p className="text-[9px] uppercase tracking-wider text-text-faint mb-1">{slot}</p>
                <p className="text-xs font-medium text-text">
                  {entry?.recipe_title ?? entry?.free_text ?? <span className="italic text-text-faint">Not planned</span>}
                </p>
              </div>
            )
          })}
        </div>
      )}

      {/* Quick look */}
      <SectionLabel>Quick Look</SectionLabel>
      <div className="grid grid-cols-3 gap-3">
        {/* Expiring soon */}
        <QuickCard title="Expiring Soon" linkLabel="View all" linkRoute="/kitchen/larder">
          {expiringItems.length === 0 ? (
            <p className="text-xs text-text-faint italic">Nothing expiring soon</p>
          ) : (
            expiringItems.slice(0, 4).map((item) => (
              <div key={item.stock_item_id} className="flex items-center justify-between py-1 border-b border-border/50 last:border-0">
                <span className="text-xs text-text truncate">{nameFromPath(item.catalogue_path ?? '')}</span>
                <span
                  className="text-[10px] shrink-0 font-medium px-1.5 py-px rounded-full"
                  style={{ color: expiryBadgeColor(item.days_until_expiry), backgroundColor: `${expiryBadgeColor(item.days_until_expiry)}15` }}
                >
                  {item.days_until_expiry <= 0 ? 'expired' : `${item.days_until_expiry}d`}
                </span>
              </div>
            ))
          )}
        </QuickCard>

        {/* Can make tonight */}
        <QuickCard title="Can Make Tonight" linkLabel="View all" linkRoute="/kitchen/recipes">
          {canMakeRecipes.length === 0 ? (
            <p className="text-xs text-text-faint italic">No recipes ready</p>
          ) : (
            canMakeRecipes.slice(0, 4).map((r) => (
              <div key={r.recipe_id} className="flex items-center justify-between py-1 border-b border-border/50 last:border-0">
                <span className="text-xs text-text truncate">{r.recipe_title}</span>
                <span
                  className="text-[10px] font-medium px-1.5 py-px rounded-full"
                  style={{
                    color: r.can_make ? '#22c55e' : '#f59e0b',
                    backgroundColor: r.can_make ? '#22c55e15' : '#f59e0b15',
                  }}
                >
                  {r.can_make ? 'ready' : `−${r.missing_count}`}
                </span>
              </div>
            ))
          )}
        </QuickCard>

        {/* Shopping list summary */}
        <QuickCard title="Shopping List" linkLabel="View all" linkRoute="/kitchen/shopping">
          {shoppingItems.length === 0 ? (
            <p className="text-xs text-text-faint italic">Shopping list is empty</p>
          ) : (
            <>
              {shoppingItems.slice(0, 3).map((item) => (
                <div key={item.id} className="flex items-center justify-between py-1 border-b border-border/50 last:border-0">
                  <span className="text-xs text-text truncate">{item.name}</span>
                  {item.quantity > 0 && item.unit && (
                    <span className="text-[10px] text-text-faint shrink-0">{item.quantity} {item.unit}</span>
                  )}
                </div>
              ))}
              {shoppingItems.length > 3 && (
                <p className="text-[10px] text-text-faint mt-1">+{shoppingItems.length - 3} more</p>
              )}
            </>
          )}
        </QuickCard>
      </div>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint mb-2 mt-4 first:mt-0">
      {children}
    </p>
  )
}

function QuickCard({
  title,
  linkLabel,
  linkRoute,
  children,
}: {
  title: string
  linkLabel: string
  linkRoute: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint">{title}</p>
        <a href={linkRoute} className="text-[10px] text-text-faint underline underline-offset-2 hover:text-text">
          {linkLabel}
        </a>
      </div>
      {children}
    </div>
  )
}
