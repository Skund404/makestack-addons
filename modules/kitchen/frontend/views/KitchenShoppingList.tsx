/**
 * KitchenShoppingList — persistent shopping list with add panel.
 *
 * Left: item list with checkboxes, tabs (To buy / All), clear checked.
 * Right: add panel (from recipe or manual item).
 */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, X, Check } from 'lucide-react'
import { kitchenApi, fmtQty } from '../api'
import type { PersistentShoppingItem, RecipeListItem } from '../api'

export function KitchenShoppingList() {
  const [tab, setTab] = useState<'buy' | 'all'>('buy')
  const [addMode, setAddMode] = useState<'recipe' | 'item'>('item')
  const queryClient = useQueryClient()

  // Form state (manual item)
  const [formName, setFormName] = useState('')
  const [formQty, setFormQty] = useState('1')
  const [formUnit, setFormUnit] = useState('')
  const [formNote, setFormNote] = useState('')
  const [formSaving, setFormSaving] = useState(false)

  // Recipe picker state
  const [selectedRecipeId, setSelectedRecipeId] = useState('')
  const [addingRecipe, setAddingRecipe] = useState(false)
  const [recipeResult, setRecipeResult] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['kitchen-shopping', tab],
    queryFn: () => kitchenApi.listShopping(tab === 'buy' ? 'buy' : undefined),
    staleTime: 30_000,
  })

  const { data: allData } = useQuery({
    queryKey: ['kitchen-shopping-summary'],
    queryFn: () => kitchenApi.listShopping(),
    staleTime: 30_000,
  })

  const { data: recipesData } = useQuery({
    queryKey: ['kitchen-recipes-for-shop'],
    queryFn: () => kitchenApi.listRecipes({ limit: 200 }),
    staleTime: 120_000,
  })

  const items = data?.items ?? []
  const total = allData?.total ?? 0
  const toBuy = allData?.to_buy ?? 0
  const recipes = recipesData?.items ?? []

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['kitchen-shopping'] })
    await queryClient.invalidateQueries({ queryKey: ['kitchen-shopping-summary'] })
    await queryClient.invalidateQueries({ queryKey: ['kitchen-shopping-badge'] })
  }

  const handleToggle = async (item: PersistentShoppingItem) => {
    const isChecked = item.checked === true || item.checked === 1
    await kitchenApi.updateShopping(item.id, { checked: !isChecked })
    await invalidate()
  }

  const handleDelete = async (id: string) => {
    await kitchenApi.deleteShopping(id)
    await invalidate()
  }

  const handleClearChecked = async () => {
    await kitchenApi.clearChecked()
    await invalidate()
  }

  const handleAddItem = async () => {
    if (!formName.trim()) return
    setFormSaving(true)
    try {
      await kitchenApi.addShopping({
        name: formName.trim(),
        quantity: parseFloat(formQty) || 1,
        unit: formUnit,
        note: formNote,
      })
      setFormName('')
      setFormQty('1')
      setFormUnit('')
      setFormNote('')
      await invalidate()
    } finally {
      setFormSaving(false)
    }
  }

  const handleAddFromRecipe = async () => {
    if (!selectedRecipeId) return
    setAddingRecipe(true)
    setRecipeResult(null)
    try {
      const result = await kitchenApi.addFromRecipe(selectedRecipeId)
      setRecipeResult(`Added ${result.added} items from "${result.recipe_title}"`)
      await invalidate()
    } catch {
      setRecipeResult('Failed to add items')
    } finally {
      setAddingRecipe(false)
    }
  }

  // Group items by source for display
  const grouped = new Map<string, PersistentShoppingItem[]>()
  for (const item of items) {
    const key = item.source === 'recipe' ? 'From recipes' : 'Manual'
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key)!.push(item)
  }

  return (
    <div className="flex h-full">
      {/* Left pane — shopping list */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 pt-3 pb-2 shrink-0 border-b border-border">
          <h2
            className="text-lg flex-1"
            style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
          >
            Shop
          </h2>
          <span className="text-[11px] text-text-faint">
            {toBuy} to buy · {total} total
          </span>
          {total > toBuy && (
            <button
              onClick={handleClearChecked}
              className="text-[10px] text-text-faint hover:text-text underline underline-offset-2"
            >
              Clear checked
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-0 px-4 pt-2 shrink-0">
          {(['buy', 'all'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="px-3 py-1.5 text-[11px] font-medium transition-colors rounded-t"
              style={{
                color: tab === t ? 'var(--text)' : 'var(--text-faint)',
                borderBottom: tab === t ? '2px solid var(--accent, #c8935a)' : '2px solid transparent',
              }}
            >
              {t === 'buy' ? 'To buy' : 'All items'}
            </button>
          ))}
        </div>

        {/* Items */}
        <div className="flex-1 overflow-y-auto px-4 py-2">
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-text-muted gap-2">
              <Loader2 size={14} className="animate-spin" />
              <span className="text-xs">Loading...</span>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-text-faint">
              <p className="text-sm">{tab === 'buy' ? 'Nothing to buy' : 'Your list is empty'}</p>
            </div>
          ) : (
            Array.from(grouped.entries()).map(([group, groupItems]) => (
              <div key={group} className="mb-3">
                <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint mb-1">{group}</p>
                {groupItems.map((item) => {
                  const isChecked = item.checked === true || item.checked === 1
                  return (
                    <div
                      key={item.id}
                      className="flex items-center gap-2 py-1.5 border-b border-border/30"
                      style={{ opacity: isChecked ? 0.5 : 1 }}
                    >
                      {/* Checkbox */}
                      <button
                        onClick={() => handleToggle(item)}
                        className="w-4 h-4 rounded border border-border flex items-center justify-center shrink-0 transition-colors"
                        style={{
                          backgroundColor: isChecked ? 'var(--accent, #c8935a)' : 'transparent',
                          borderColor: isChecked ? 'var(--accent, #c8935a)' : undefined,
                        }}
                      >
                        {isChecked && <Check size={10} className="text-white" />}
                      </button>

                      <span className={`flex-1 text-xs ${isChecked ? 'line-through text-text-muted' : 'text-text'} truncate`}>
                        {item.name}
                      </span>
                      {item.quantity > 0 && item.unit && (
                        <span className="text-[10px] text-text-faint font-mono shrink-0">
                          {fmtQty(item.quantity, item.unit)}
                        </span>
                      )}
                      <button
                        onClick={() => handleDelete(item.id)}
                        className="text-text-faint hover:text-text shrink-0"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  )
                })}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right pane — add panel */}
      <div className="w-64 shrink-0 border-l border-border flex flex-col bg-surface">
        <div className="px-3 py-2.5 border-b border-border">
          <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint">Add to List</p>
        </div>

        {/* Mode toggle */}
        <div className="flex gap-1 mx-3 mt-2 text-[10px]">
          <button
            className="flex-1 py-1 rounded text-center"
            style={{
              backgroundColor: addMode === 'item' ? 'var(--accent, #c8935a)' : 'transparent',
              color: addMode === 'item' ? '#15100b' : 'var(--text-faint)',
            }}
            onClick={() => setAddMode('item')}
          >
            Item
          </button>
          <button
            className="flex-1 py-1 rounded text-center"
            style={{
              backgroundColor: addMode === 'recipe' ? 'var(--accent, #c8935a)' : 'transparent',
              color: addMode === 'recipe' ? '#15100b' : 'var(--text-faint)',
            }}
            onClick={() => setAddMode('recipe')}
          >
            From recipe
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {addMode === 'item' ? (
            <>
              <div>
                <label className="block text-[10px] font-medium text-text-faint mb-1">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Milk"
                  className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
                />
              </div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="block text-[10px] font-medium text-text-faint mb-1">Qty</label>
                  <input
                    type="number"
                    value={formQty}
                    onChange={(e) => setFormQty(e.target.value)}
                    min="0"
                    step="any"
                    className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-[10px] font-medium text-text-faint mb-1">Unit</label>
                  <input
                    type="text"
                    value={formUnit}
                    onChange={(e) => setFormUnit(e.target.value)}
                    placeholder="g, L"
                    className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
                  />
                </div>
              </div>
              <div>
                <label className="block text-[10px] font-medium text-text-faint mb-1">Note</label>
                <input
                  type="text"
                  value={formNote}
                  onChange={(e) => setFormNote(e.target.value)}
                  placeholder="Optional"
                  className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
                />
              </div>
              <button
                onClick={handleAddItem}
                disabled={!formName.trim() || formSaving}
                className="w-full py-1.5 text-xs font-medium rounded transition-colors disabled:opacity-50"
                style={{ backgroundColor: '#c8935a', color: '#15100b' }}
              >
                {formSaving ? 'Adding...' : 'Add item'}
              </button>
            </>
          ) : (
            <>
              <div>
                <label className="block text-[10px] font-medium text-text-faint mb-1">Recipe</label>
                <select
                  value={selectedRecipeId}
                  onChange={(e) => { setSelectedRecipeId(e.target.value); setRecipeResult(null) }}
                  className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
                >
                  <option value="">— Select recipe —</option>
                  {recipes.map((r) => (
                    <option key={r.id} value={r.id}>{r.title}</option>
                  ))}
                </select>
              </div>
              <p className="text-[10px] text-text-faint">
                Adds missing ingredients to your shopping list (deduplicates).
              </p>
              <button
                onClick={handleAddFromRecipe}
                disabled={!selectedRecipeId || addingRecipe}
                className="w-full py-1.5 text-xs font-medium rounded transition-colors disabled:opacity-50"
                style={{ backgroundColor: '#c8935a', color: '#15100b' }}
              >
                {addingRecipe ? 'Adding...' : 'Add missing ingredients'}
              </button>
              {recipeResult && (
                <p className="text-[10px] text-text-muted">{recipeResult}</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
