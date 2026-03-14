/**
 * Kitchen Meal Plan view — weekly calendar grid.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, Calendar, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { kitchenApi, currentMondayISO } from '../api'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MEAL_SLOTS = ['breakfast', 'lunch', 'dinner', 'snack']

const SLOT_ICONS: Record<string, string> = {
  breakfast: '🌅',
  lunch: '☀️',
  dinner: '🌙',
  snack: '🍎',
}

function addDays(isoDate: string, days: number): string {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

export function KitchenMealPlan() {
  const [week, setWeek] = useState(currentMondayISO)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-meal-plan', week],
    queryFn: () => kitchenApi.getMealPlan(week),
    staleTime: 60_000,
  })

  const entries = data?.entries ?? []

  // Build a lookup: day_of_week → meal_slot → entry
  const grid: Record<number, Record<string, (typeof entries)[0]>> = {}
  for (const entry of entries) {
    if (!grid[entry.day_of_week]) grid[entry.day_of_week] = {}
    grid[entry.day_of_week][entry.meal_slot] = entry
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        <Calendar size={16} className="text-text-muted" />
        <h1 className="text-base font-semibold text-text flex-1">Meal Plan</h1>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setWeek(addDays(week, -7))}>
            <ChevronLeft size={14} />
          </Button>
          <span className="text-xs text-text-muted w-24 text-center">{week}</span>
          <Button variant="ghost" size="sm" onClick={() => setWeek(addDays(week, 7))}>
            <ChevronRight size={14} />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setWeek(currentMondayISO())}>
            Today
          </Button>
        </div>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-auto px-4 pb-4">
        {isLoading && (
          <div className="flex items-center justify-center py-16 text-text-muted gap-2">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        )}
        {isError && (
          <div className="flex items-center justify-center py-16 text-danger/70 gap-2">
            <AlertCircle size={16} /> Failed to load meal plan.
          </div>
        )}
        {!isLoading && !isError && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr>
                  <th className="text-left py-2 pr-3 text-text-muted font-medium w-24">Meal</th>
                  {DAYS.map((day, i) => (
                    <th key={day} className="text-center py-2 px-2 text-text-muted font-medium">
                      <div>{day}</div>
                      <div className="text-text-faint font-normal">{addDays(week, i).slice(5)}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MEAL_SLOTS.map((slot) => (
                  <tr key={slot} className="border-t border-border/50">
                    <td className="py-2 pr-3 text-text-muted">
                      <span className="mr-1">{SLOT_ICONS[slot]}</span>
                      {slot.charAt(0).toUpperCase() + slot.slice(1)}
                    </td>
                    {DAYS.map((_, dow) => {
                      const entry = grid[dow]?.[slot]
                      return (
                        <td key={dow} className="py-2 px-2 text-center align-top">
                          {entry ? (
                            <div className="text-text leading-tight">
                              {entry.recipe_title || entry.free_text || <span className="text-text-faint">—</span>}
                            </div>
                          ) : (
                            <span className="text-text-faint">—</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
