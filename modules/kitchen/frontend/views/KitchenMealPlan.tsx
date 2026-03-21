/**
 * KitchenMealPlan — weekly calendar grid with click-to-edit and shopping sidebar.
 */
import { useState, useRef, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react'
import { kitchenApi, currentMondayISO, fmtQty } from '../api'
import type { MealPlanEntry, RecipeListItem } from '../api'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MEAL_SLOTS = ['breakfast', 'lunch', 'dinner', 'snack']

function addDays(isoDate: string, days: number): string {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

interface EditState {
  dow: number
  slot: string
  mode: 'recipe' | 'freetext'
  recipeId: string
  freeText: string
  servings: number
}

export function KitchenMealPlan() {
  const [week, setWeek] = useState(currentMondayISO)
  const [editing, setEditing] = useState<EditState | null>(null)
  const [saving, setSaving] = useState(false)
  const queryClient = useQueryClient()
  const popoverRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-meal-plan', week],
    queryFn: () => kitchenApi.getMealPlan(week),
    staleTime: 60_000,
  })

  // Fetch recipe list for the dropdown
  const { data: recipesData } = useQuery({
    queryKey: ['kitchen-recipes-for-plan'],
    queryFn: () => kitchenApi.listRecipes({ limit: 200 }),
    staleTime: 120_000,
  })

  // Shopping list for sidebar
  const { data: shoppingData } = useQuery({
    queryKey: ['kitchen-shopping-list', week],
    queryFn: () => kitchenApi.getShoppingList(week),
    staleTime: 60_000,
  })

  const entries = data?.entries ?? []
  const recipes = recipesData?.items ?? []
  const shoppingItems = shoppingData?.items ?? []
  const needed = shoppingItems.filter((i) => i.shortfall > 0)
  const covered = shoppingItems.filter((i) => i.shortfall === 0)

  // Build grid lookup: dow → slot → entry
  const grid: Record<number, Record<string, MealPlanEntry>> = {}
  for (const entry of entries) {
    if (!grid[entry.day_of_week]) grid[entry.day_of_week] = {}
    grid[entry.day_of_week][entry.meal_slot] = entry
  }

  const handleCellClick = (dow: number, slot: string) => {
    const entry = grid[dow]?.[slot]
    setEditing({
      dow,
      slot,
      mode: entry?.recipe_id ? 'recipe' : 'freetext',
      recipeId: entry?.recipe_id ?? '',
      freeText: entry?.free_text ?? '',
      servings: entry?.servings ?? 1,
    })
  }

  const handleSave = async () => {
    if (!editing) return
    setSaving(true)
    try {
      await kitchenApi.setMealPlanEntry(week, {
        day_of_week: editing.dow,
        meal_slot: editing.slot,
        recipe_id: editing.mode === 'recipe' ? editing.recipeId || null : null,
        free_text: editing.mode === 'freetext' ? editing.freeText : '',
        servings: editing.servings,
      })
      await queryClient.invalidateQueries({ queryKey: ['kitchen-meal-plan', week] })
      await queryClient.invalidateQueries({ queryKey: ['kitchen-shopping-list', week] })
      setEditing(null)
    } finally {
      setSaving(false)
    }
  }

  // Close popover on click outside
  useEffect(() => {
    if (!editing) return
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setEditing(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [editing])

  return (
    <div className="flex h-full">
      {/* Left pane — calendar grid */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 pt-3 pb-2 shrink-0">
          <h2
            className="text-lg flex-1"
            style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
          >
            Meal Plan
          </h2>
          <div className="flex items-center gap-1">
            <button className="p-1 rounded hover:bg-surface text-text-muted" onClick={() => setWeek(addDays(week, -7))}>
              <ChevronLeft size={14} />
            </button>
            <span className="text-xs text-text-muted w-24 text-center">{week}</span>
            <button className="p-1 rounded hover:bg-surface text-text-muted" onClick={() => setWeek(addDays(week, 7))}>
              <ChevronRight size={14} />
            </button>
            <button
              className="text-[10px] text-text-faint hover:text-text ml-1 px-2 py-1 rounded hover:bg-surface"
              onClick={() => setWeek(currentMondayISO())}
            >
              Today
            </button>
          </div>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-auto px-4 pb-4">
          {isLoading && (
            <div className="flex items-center justify-center py-16 text-text-muted gap-2">
              <Loader2 size={16} className="animate-spin" /> Loading...
            </div>
          )}
          {isError && (
            <div className="flex items-center justify-center py-16 text-danger/70 gap-2">
              <AlertCircle size={16} /> Failed to load meal plan.
            </div>
          )}
          {!isLoading && !isError && (
            <div className="relative">
              <div
                className="grid gap-px bg-border/30"
                style={{ gridTemplateColumns: '80px repeat(7, 1fr)', gridTemplateRows: 'auto' }}
              >
                {/* Header row */}
                <div />
                {DAYS.map((day, i) => (
                  <div key={day} className="text-center py-2 text-text-muted">
                    <div className="text-[11px] font-medium">{day}</div>
                    <div className="text-[10px] text-text-faint">{addDays(week, i).slice(5)}</div>
                  </div>
                ))}

                {/* Meal rows */}
                {MEAL_SLOTS.map((slot) => (
                  <>
                    <div key={`label-${slot}`} className="py-2.5 pr-2 text-[11px] text-text-muted font-medium flex items-start">
                      {slot.charAt(0).toUpperCase() + slot.slice(1)}
                    </div>
                    {DAYS.map((_, dow) => {
                      const entry = grid[dow]?.[slot]
                      const cellText = entry?.recipe_title || entry?.free_text || null
                      const isEditing = editing?.dow === dow && editing?.slot === slot
                      return (
                        <div
                          key={`${slot}-${dow}`}
                          className="relative py-2 px-1.5 min-h-[36px] cursor-pointer rounded hover:bg-surface/50 transition-colors"
                          onClick={() => handleCellClick(dow, slot)}
                        >
                          {cellText ? (
                            <span className="text-xs text-text leading-tight">{cellText}</span>
                          ) : (
                            <span className="text-xs text-text-faint">—</span>
                          )}

                          {/* Edit popover */}
                          {isEditing && editing && (
                            <div
                              ref={popoverRef}
                              className="absolute z-50 top-full left-0 mt-1 w-56 bg-surface border border-border rounded-lg shadow-xl p-3 space-y-2"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {/* Mode toggle */}
                              <div className="flex gap-1 text-[10px]">
                                <button
                                  className="flex-1 py-1 rounded text-center"
                                  style={{
                                    backgroundColor: editing.mode === 'recipe' ? 'var(--accent, #c8935a)' : 'transparent',
                                    color: editing.mode === 'recipe' ? '#15100b' : 'var(--text-faint)',
                                  }}
                                  onClick={() => setEditing({ ...editing, mode: 'recipe' })}
                                >
                                  Recipe
                                </button>
                                <button
                                  className="flex-1 py-1 rounded text-center"
                                  style={{
                                    backgroundColor: editing.mode === 'freetext' ? 'var(--accent, #c8935a)' : 'transparent',
                                    color: editing.mode === 'freetext' ? '#15100b' : 'var(--text-faint)',
                                  }}
                                  onClick={() => setEditing({ ...editing, mode: 'freetext' })}
                                >
                                  Free text
                                </button>
                              </div>

                              {editing.mode === 'recipe' ? (
                                <select
                                  value={editing.recipeId}
                                  onChange={(e) => setEditing({ ...editing, recipeId: e.target.value })}
                                  className="w-full px-2 py-1.5 text-xs rounded border border-border bg-bg text-text"
                                >
                                  <option value="">— Select recipe —</option>
                                  {recipes.map((r) => (
                                    <option key={r.id} value={r.id}>{r.title}</option>
                                  ))}
                                </select>
                              ) : (
                                <input
                                  type="text"
                                  value={editing.freeText}
                                  onChange={(e) => setEditing({ ...editing, freeText: e.target.value })}
                                  placeholder="e.g. Leftovers"
                                  className="w-full px-2 py-1.5 text-xs rounded border border-border bg-bg text-text"
                                  autoFocus
                                />
                              )}

                              <div>
                                <label className="text-[10px] text-text-faint">Servings</label>
                                <input
                                  type="number"
                                  value={editing.servings}
                                  onChange={(e) => setEditing({ ...editing, servings: parseInt(e.target.value) || 1 })}
                                  min="1"
                                  className="w-full px-2 py-1 text-xs rounded border border-border bg-bg text-text"
                                />
                              </div>

                              <div className="flex gap-2">
                                <button
                                  onClick={handleSave}
                                  disabled={saving}
                                  className="flex-1 py-1.5 text-xs font-medium rounded transition-colors disabled:opacity-50"
                                  style={{ backgroundColor: '#c8935a', color: '#15100b' }}
                                >
                                  {saving ? 'Saving...' : 'Save'}
                                </button>
                                {(grid[editing.dow]?.[editing.slot]) && (
                                  <button
                                    onClick={async () => {
                                      const entry = grid[editing.dow]?.[editing.slot]
                                      if (!entry) return
                                      setSaving(true)
                                      try {
                                        await kitchenApi.deleteMealPlanEntry(week, entry.id)
                                        await queryClient.invalidateQueries({ queryKey: ['kitchen-meal-plan', week] })
                                        await queryClient.invalidateQueries({ queryKey: ['kitchen-shopping-list', week] })
                                        setEditing(null)
                                      } finally {
                                        setSaving(false)
                                      }
                                    }}
                                    disabled={saving}
                                    className="px-3 py-1.5 text-xs font-medium rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                                  >
                                    Clear
                                  </button>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right pane — shopping sidebar */}
      <div className="w-56 shrink-0 border-l border-border flex flex-col bg-surface">
        <div className="px-3 py-2.5 border-b border-border">
          <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint">Shopping List</p>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-2">
          {shoppingItems.length === 0 ? (
            <p className="text-xs text-text-faint italic">No items for this week</p>
          ) : (
            <>
              {needed.length > 0 && (
                <div className="mb-3">
                  <p className="text-[10px] font-medium text-text-faint mb-1">Need to buy ({needed.length})</p>
                  {needed.map((item) => (
                    <div key={`${item.catalogue_path}-${item.unit}`} className="flex items-center gap-1 py-0.5">
                      <span className="text-xs text-text truncate flex-1">{item.name}</span>
                      <span className="text-[10px] text-text-faint shrink-0 font-mono">{fmtQty(item.shortfall, item.unit)}</span>
                    </div>
                  ))}
                </div>
              )}
              {covered.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium text-text-faint mb-1">In stock ({covered.length})</p>
                  {covered.map((item) => (
                    <div key={`${item.catalogue_path}-${item.unit}`} className="flex items-center gap-1 py-0.5">
                      <span className="text-xs text-text-muted truncate flex-1 line-through">{item.name}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
