/**
 * KitchenRecipes — two-pane recipe browser.
 *
 * Left: scrollable recipe list with status dots (green=ready, amber=1 missing, red=>1).
 * Right: selected recipe detail with stock-check per ingredient.
 */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Clock, Users, Plus, Pencil, Trash2, ShoppingCart } from 'lucide-react'
import { kitchenApi, fmtQty } from '../api'
import type { CanMakeResult } from '../api'

function statusColor(recipe: { can_make: boolean; missing_count: number }): string {
  if (recipe.can_make) return '#22c55e'        // green
  if (recipe.missing_count === 1) return '#f59e0b' // amber
  return '#ef4444'                               // red
}

export function KitchenRecipes() {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Fetch all recipes with can-make status (relaxed — includes up to 1 missing)
  const { data: canMakeData, isLoading } = useQuery({
    queryKey: ['kitchen-recipes-canmake'],
    queryFn: () => kitchenApi.canMake(false, 200),
    staleTime: 60_000,
  })

  // Also fetch full recipe list for recipes that may have no ingredients (won't appear in can-make)
  const { data: allRecipes } = useQuery({
    queryKey: ['kitchen-recipes-all'],
    queryFn: () => kitchenApi.listRecipes({ limit: 200 }),
    staleTime: 60_000,
  })

  // Merge: can-make data keyed by recipe_id, fallback to recipe list
  const canMakeMap = new Map<string, CanMakeResult>()
  for (const r of canMakeData?.recipes ?? []) {
    canMakeMap.set(r.recipe_id, r)
  }

  // Build unified list: all recipes, enriched with can-make data
  const recipes = (allRecipes?.items ?? []).map((r) => {
    const cm = canMakeMap.get(r.id)
    return {
      id: r.id,
      title: r.title,
      cuisine_tag: r.cuisine_tag,
      total_time_mins: r.total_time_mins,
      servings: r.servings,
      can_make: cm?.can_make ?? false,
      missing_count: cm?.missing_count ?? 0,
    }
  })

  const selected = selectedId ?? null

  return (
    <div className="flex h-full">
      {/* Left pane — recipe list */}
      <div className="w-56 shrink-0 border-r border-border flex flex-col bg-surface">
        <div className="px-3 py-2.5 border-b border-border">
          <div className="flex items-center justify-between">
            <h2
              className="text-lg"
              style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
            >
              Recipes
            </h2>
            <button
              onClick={() => { window.location.href = '/kitchen/recipes/new' }}
              className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
              data-testid="new-recipe-btn"
            >
              <Plus size={10} /> New
            </button>
          </div>
          <p className="text-[10px] text-text-faint">{recipes.length} recipes</p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-8 text-text-muted gap-2">
              <Loader2 size={12} className="animate-spin" />
              <span className="text-xs">Loading...</span>
            </div>
          ) : recipes.length === 0 ? (
            <p className="text-xs text-text-faint italic p-3">No recipes yet</p>
          ) : (
            recipes.map((r) => {
              const isSelected = r.id === selected
              return (
                <button
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  className="w-full text-left px-3 py-2.5 border-b border-border/50 transition-colors cursor-pointer"
                  style={{
                    backgroundColor: isSelected ? 'var(--bg-secondary, #1a1a1a)' : 'transparent',
                    borderLeft: isSelected ? '2px solid var(--accent, #c8935a)' : '2px solid transparent',
                  }}
                >
                  <div className="flex items-center gap-2">
                    {/* Status dot */}
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: statusColor(r) }}
                    />
                    <span className="text-xs text-text font-medium truncate flex-1">{r.title}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 ml-4 text-[10px] text-text-faint">
                    {r.total_time_mins != null && <span>{r.total_time_mins}min</span>}
                    {r.cuisine_tag && <span>{r.cuisine_tag}</span>}
                  </div>
                </button>
              )
            })
          )}
        </div>
      </div>

      {/* Right pane — recipe detail */}
      <div className="flex-1 overflow-y-auto bg-secondary">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-text-faint text-sm">
            Select a recipe
          </div>
        ) : (
          <RecipeDetailPane recipeId={selected} onDeleted={() => setSelectedId(null)} />
        )}
      </div>
    </div>
  )
}

function RecipeDetailPane({ recipeId, onDeleted }: { recipeId: string; onDeleted: () => void }) {
  const queryClient = useQueryClient()
  const [deleting, setDeleting] = useState(false)
  const [addingShopping, setAddingShopping] = useState(false)

  const { data: recipe, isLoading } = useQuery({
    queryKey: ['kitchen-recipe', recipeId],
    queryFn: () => kitchenApi.getRecipe(recipeId),
    staleTime: 60_000,
  })

  const { data: stockCheck } = useQuery({
    queryKey: ['kitchen-stock-check', recipeId],
    queryFn: () => kitchenApi.stockCheck(recipeId),
    staleTime: 60_000,
    enabled: !!recipe,
  })

  const handleDelete = async () => {
    if (!confirm('Delete this recipe? The catalogue entry will be preserved.')) return
    setDeleting(true)
    try {
      await kitchenApi.deleteRecipe(recipeId)
      await queryClient.invalidateQueries({ queryKey: ['kitchen-recipes'] })
      onDeleted()
    } catch {
      // silently fail
    } finally {
      setDeleting(false)
    }
  }

  const handleAddToShopping = async () => {
    setAddingShopping(true)
    try {
      await kitchenApi.addFromRecipe(recipeId)
      await queryClient.invalidateQueries({ queryKey: ['kitchen-shopping'] })
    } catch {
      // silently fail
    } finally {
      setAddingShopping(false)
    }
  }

  if (isLoading || !recipe) {
    return (
      <div className="flex items-center justify-center py-12 text-text-muted gap-2">
        <Loader2 size={14} className="animate-spin" />
        <span className="text-xs">Loading...</span>
      </div>
    )
  }

  return (
    <div className="p-5 max-w-xl">
      {/* Title + action buttons */}
      <div className="flex items-start gap-3 mb-2">
        <h1
          className="text-[25px] flex-1 leading-tight"
          style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
        >
          {recipe.title}
        </h1>
        <div className="flex items-center gap-1 shrink-0 mt-1">
          <button
            onClick={() => { window.location.href = `/kitchen/recipes/${recipeId}/edit` }}
            className="p-1.5 rounded text-text-faint hover:text-accent hover:bg-accent/10 transition-colors"
            title="Edit recipe"
            data-testid="recipe-edit-btn"
          >
            <Pencil size={13} />
          </button>
          <button
            onClick={handleAddToShopping}
            disabled={addingShopping}
            className="p-1.5 rounded text-text-faint hover:text-accent hover:bg-accent/10 transition-colors disabled:opacity-50"
            title="Add missing ingredients to shopping list"
          >
            <ShoppingCart size={13} />
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="p-1.5 rounded text-text-faint hover:text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-50"
            title="Delete recipe"
            data-testid="recipe-delete-btn"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Meta badges */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {recipe.total_time_mins != null && (
          <MetaBadge>
            <Clock size={10} /> {recipe.total_time_mins}min
          </MetaBadge>
        )}
        <MetaBadge>
          <Users size={10} /> {recipe.servings}
        </MetaBadge>
        {recipe.cuisine_tag && <MetaBadge>{recipe.cuisine_tag}</MetaBadge>}
        {stockCheck && (
          <span
            className="text-[10px] font-medium px-2 py-0.5 rounded-full"
            style={{
              color: stockCheck.can_make ? '#22c55e' : '#ef4444',
              backgroundColor: stockCheck.can_make ? '#22c55e15' : '#ef444415',
            }}
          >
            {stockCheck.can_make ? 'Can make' : `Missing ${stockCheck.missing_count}`}
          </span>
        )}
      </div>

      {recipe.description && (
        <p className="text-sm text-text-muted mb-4">{recipe.description}</p>
      )}

      {/* Ingredients */}
      {recipe.ingredients.length > 0 && (
        <div className="mb-4">
          <h3 className="text-[10px] font-medium uppercase tracking-wider text-text-faint mb-2">Ingredients</h3>
          <div className="space-y-1.5">
            {recipe.ingredients.map((ing) => {
              const stockIng = stockCheck?.ingredients.find((i) => i.catalogue_path === ing.catalogue_path)
              const isMissing = stockIng && stockIng.status !== 'ok'
              return (
                <div key={ing.id} className="flex items-center gap-2 text-sm">
                  <span className="flex-1 text-text">{ing.name}</span>
                  <span className="text-text-muted font-mono text-xs">{fmtQty(ing.quantity, ing.unit)}</span>
                  {isMissing && (
                    <span className="text-[9px] font-medium px-1.5 py-px rounded-full" style={{ color: '#ef4444', backgroundColor: '#ef444415' }}>
                      {stockIng.status === 'low' ? 'Low' : 'Missing'}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Notes */}
      {recipe.notes && (
        <div>
          <h3 className="text-[10px] font-medium uppercase tracking-wider text-text-faint mb-1">Notes</h3>
          <p className="text-sm text-text-muted whitespace-pre-line">{recipe.notes}</p>
        </div>
      )}
    </div>
  )
}

function MetaBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-1 text-[10px] text-text-muted px-2 py-0.5 rounded-full bg-surface border border-border">
      {children}
    </span>
  )
}
