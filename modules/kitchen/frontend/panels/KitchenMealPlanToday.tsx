/**
 * Today's Meal Plan panel — half-width.
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, Calendar } from 'lucide-react'
import { kitchenApi, currentMondayISO, todayDow } from '../api'
import type { PanelProps } from '@/modules/panel-registry'

const MEAL_SLOTS = ['breakfast', 'lunch', 'dinner', 'snack']

const SLOT_ICONS: Record<string, string> = {
  breakfast: '🌅',
  lunch: '☀️',
  dinner: '🌙',
  snack: '🍎',
}

export function KitchenMealPlanToday(_props: PanelProps) {
  const week = currentMondayISO()
  const dow = todayDow()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-meal-plan', week],
    queryFn: () => kitchenApi.getMealPlan(week),
    staleTime: 120_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6 text-text-muted gap-2">
        <Loader2 size={14} className="animate-spin" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center py-6 gap-1 text-danger/60 text-xs">
        <AlertCircle size={12} /> Failed to load
      </div>
    )
  }

  const entries = (data?.entries ?? []).filter((e) => e.day_of_week === dow)

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-6 gap-2 text-text-faint">
        <Calendar size={20} className="opacity-30" />
        <span className="text-xs">No meals planned for today</span>
      </div>
    )
  }

  const entryBySlot = Object.fromEntries(entries.map((e) => [e.meal_slot, e]))

  return (
    <ul className="space-y-2">
      {MEAL_SLOTS.filter((slot) => slot in entryBySlot).map((slot) => {
        const entry = entryBySlot[slot]
        const label = entry.recipe_title || entry.free_text || '—'
        return (
          <li key={slot} className="flex items-start gap-2 text-xs">
            <span className="text-base shrink-0 leading-none">{SLOT_ICONS[slot]}</span>
            <div className="flex-1 min-w-0">
              <div className="text-text-muted capitalize">{slot}</div>
              <div className="text-text truncate">{label}</div>
            </div>
            {entry.servings > 1 && (
              <span className="text-text-faint shrink-0">×{entry.serves_override ?? entry.servings}</span>
            )}
          </li>
        )
      })}
    </ul>
  )
}
