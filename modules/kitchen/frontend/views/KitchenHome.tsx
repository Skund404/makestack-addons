/**
 * KitchenHome — dashboard view matching the mockup's "Good evening" screen.
 *
 * Shows today's meal plan cards and quick-look widgets (expiring, can-make, shopping summary).
 */
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/lib/api'
import { Loader2 } from 'lucide-react'

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function getTodayWeekKey(): string {
  const now = new Date()
  const day = now.getDay()
  const diff = day === 0 ? -6 : 1 - day
  const monday = new Date(now)
  monday.setDate(now.getDate() + diff)
  return monday.toISOString().slice(0, 10)
}

const MEAL_SLOTS = ['breakfast', 'lunch', 'dinner', 'snack'] as const

interface MealPlanEntry {
  slot: string
  day: string
  recipe_id: string | null
  recipe_name: string | null
  custom_text: string | null
}

interface MealPlanResponse {
  id: string
  week: string
  entries: MealPlanEntry[]
}

interface ExpiringItem {
  id: string
  name: string
  expiry_date: string
  location: string
}

interface CanMakeRecipe {
  id: string
  name: string
  cuisine_tag: string | null
}

export function KitchenHome() {
  const weekKey = getTodayWeekKey()
  const todayIso = new Date().toISOString().slice(0, 10)
  const dayName = new Date().toLocaleDateString('en-US', { weekday: 'long' }).toLowerCase()

  const { data: mealPlan, isLoading: mpLoading } = useQuery({
    queryKey: ['kitchen-meal-plan', weekKey],
    queryFn: () => apiGet<MealPlanResponse>(`/modules/kitchen/meal-plan/${weekKey}`),
    staleTime: 60_000,
  })

  const { data: expiring } = useQuery({
    queryKey: ['kitchen-expiring-home'],
    queryFn: () => apiGet<{ items: ExpiringItem[] }>('/modules/kitchen/stock/expiring', { days: 7 }),
    staleTime: 60_000,
  })

  const { data: canMake } = useQuery({
    queryKey: ['kitchen-can-make-home'],
    queryFn: () => apiGet<{ items: CanMakeRecipe[] }>('/modules/kitchen/recipes/can-make'),
    staleTime: 60_000,
  })

  const todayEntries = (mealPlan?.entries ?? []).filter((e) => e.day === dayName)

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
            const entry = todayEntries.find((e) => e.slot === slot)
            return (
              <div key={slot} className="rounded-lg border border-border bg-surface p-3">
                <p className="text-[9px] uppercase tracking-wider text-text-faint mb-1">{slot}</p>
                <p className="text-xs font-medium text-text">
                  {entry?.recipe_name ?? entry?.custom_text ?? <span className="italic text-text-faint">Not planned</span>}
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
          {(expiring?.items ?? []).length === 0 ? (
            <p className="text-xs text-text-faint italic">Nothing expiring soon</p>
          ) : (
            (expiring?.items ?? []).slice(0, 4).map((item) => (
              <div key={item.id} className="flex items-center justify-between py-1 border-b border-border/50 last:border-0">
                <span className="text-xs text-text truncate">{item.name}</span>
                <span className="text-[10px] text-text-faint shrink-0">{item.expiry_date}</span>
              </div>
            ))
          )}
        </QuickCard>

        {/* Can make tonight */}
        <QuickCard title="Can Make Tonight" linkLabel="View all" linkRoute="/kitchen/recipes">
          {(canMake?.items ?? []).length === 0 ? (
            <p className="text-xs text-text-faint italic">No recipes ready</p>
          ) : (
            (canMake?.items ?? []).slice(0, 4).map((r) => (
              <div key={r.id} className="flex items-center justify-between py-1 border-b border-border/50 last:border-0">
                <span className="text-xs text-text truncate">{r.name}</span>
                {r.cuisine_tag && <span className="text-[10px] text-text-faint shrink-0">{r.cuisine_tag}</span>}
              </div>
            ))
          )}
        </QuickCard>

        {/* Shopping list summary */}
        <QuickCard title="Shopping List" linkLabel="View all" linkRoute="/kitchen/shopping">
          <p className="text-xs text-text-faint italic">View your shopping list</p>
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
