/**
 * Kitchen Cook Log view — cooking history with ratings.
 */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, AlertCircle, UtensilsCrossed, Star, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { kitchenApi } from '../api'
import type { RecipeListItem } from '../api'

const PAGE_SIZE = 20

function StarRating({ rating }: { rating: number | null }) {
  if (rating == null) return null
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={10}
          className={i <= rating ? 'text-warning' : 'text-border'}
          fill={i <= rating ? 'currentColor' : 'none'}
        />
      ))}
    </div>
  )
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

function RecordCookPanel({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const queryClient = useQueryClient()
  const [recipeId, setRecipeId] = useState('')
  const [cookedAt, setCookedAt] = useState(new Date().toISOString().split('T')[0])
  const [servesMade, setServesMade] = useState('1')
  const [rating, setRating] = useState<number | null>(null)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  const { data: recipesData } = useQuery({
    queryKey: ['kitchen-recipes-all'],
    queryFn: () => kitchenApi.listRecipes({ limit: 200 }),
    staleTime: 60_000,
  })

  const recipes = recipesData?.items ?? []

  const handleSave = async () => {
    if (!recipeId) return
    setSaving(true)
    try {
      await kitchenApi.recordCookSession({
        recipe_id: recipeId,
        cooked_at: cookedAt,
        serves_made: parseInt(servesMade, 10) || 1,
        rating,
        notes,
      })
      await queryClient.invalidateQueries({ queryKey: ['kitchen-cook-log'] })
      onSaved()
    } catch {
      // silently fail
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border border-border rounded bg-surface p-4 mb-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-text">Record Cook Session</p>
        <button onClick={onClose} className="text-text-faint hover:text-text">
          <X size={14} />
        </button>
      </div>

      <div>
        <label className="block text-[10px] font-medium text-text-faint mb-1">Recipe</label>
        <select
          value={recipeId}
          onChange={(e) => setRecipeId(e.target.value)}
          className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
          data-testid="cook-recipe-select"
        >
          <option value="">Select recipe...</option>
          {recipes.map((r: RecipeListItem) => (
            <option key={r.id} value={r.id}>{r.title}</option>
          ))}
        </select>
      </div>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="block text-[10px] font-medium text-text-faint mb-1">Date</label>
          <input
            type="date"
            value={cookedAt}
            onChange={(e) => setCookedAt(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
          />
        </div>
        <div className="w-20">
          <label className="block text-[10px] font-medium text-text-faint mb-1">Servings</label>
          <input
            type="number"
            value={servesMade}
            onChange={(e) => setServesMade(e.target.value)}
            min="1"
            className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
          />
        </div>
      </div>

      <div>
        <label className="block text-[10px] font-medium text-text-faint mb-1">Rating</label>
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((i) => (
            <button
              key={i}
              onClick={() => setRating(rating === i ? null : i)}
              className="p-0.5"
            >
              <Star
                size={16}
                className={i <= (rating ?? 0) ? 'text-warning' : 'text-border'}
                fill={i <= (rating ?? 0) ? 'currentColor' : 'none'}
              />
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-[10px] font-medium text-text-faint mb-1">Notes</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="How did it go?"
          className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50 resize-none"
        />
      </div>

      <button
        onClick={handleSave}
        disabled={!recipeId || saving}
        className="w-full px-3 py-2 text-xs font-medium rounded transition-colors disabled:opacity-50"
        style={{ backgroundColor: '#c8935a', color: '#15100b' }}
        data-testid="cook-save-btn"
      >
        {saving ? 'Recording...' : 'Record session'}
      </button>
    </div>
  )
}

export function KitchenCookLog() {
  const [offset, setOffset] = useState(0)
  const [showRecord, setShowRecord] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-cook-log', offset],
    queryFn: () => kitchenApi.listCookLog({ limit: PAGE_SIZE, offset }),
    staleTime: 60_000,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 pt-4 pb-2">
        <UtensilsCrossed size={16} className="text-text-muted" />
        <h1 className="text-base font-semibold text-text flex-1">Cook Log</h1>
        <span className="text-xs text-text-faint mr-2">{total} session{total !== 1 ? 's' : ''}</span>
        <button
          onClick={() => setShowRecord(true)}
          className="flex items-center gap-1 px-2.5 py-1 text-[10px] font-medium rounded bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
          data-testid="record-cook-btn"
        >
          <Plus size={10} /> Record
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {showRecord && (
          <RecordCookPanel
            onClose={() => setShowRecord(false)}
            onSaved={() => setShowRecord(false)}
          />
        )}
        {isLoading && (
          <div className="flex items-center justify-center py-16 text-text-muted gap-2">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        )}
        {isError && (
          <div className="flex items-center justify-center py-16 text-danger/70 gap-2">
            <AlertCircle size={16} /> Failed to load cook log.
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-text-faint">
            <UtensilsCrossed size={24} className="opacity-30" />
            <p className="text-sm">No sessions logged yet.</p>
          </div>
        )}
        {!isLoading && !isError && items.length > 0 && (
          <div className="space-y-2">
            {items.map((entry) => (
              <div
                key={entry.id}
                className="flex items-start gap-3 p-3 rounded border border-border bg-surface text-sm"
              >
                <div className="flex-1 min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-text font-medium truncate">{entry.recipe_id}</span>
                    <StarRating rating={entry.rating} />
                  </div>
                  <div className="flex items-center gap-2 text-xs text-text-faint">
                    <span>{formatDate(entry.cooked_at)}</span>
                    {entry.serves_made > 1 && <span>×{entry.serves_made} servings</span>}
                    {entry.stock_deducted && <Badge variant="muted">stock deducted</Badge>}
                  </div>
                  {entry.notes && (
                    <p className="text-xs text-text-muted mt-1">{entry.notes}</p>
                  )}
                  {entry.warnings.length > 0 && (
                    <p className="text-xs text-warning mt-1">⚠ {entry.warnings.join(', ')}</p>
                  )}
                </div>
              </div>
            ))}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 pt-2">
                <Button variant="ghost" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                  Previous
                </Button>
                <span className="text-xs text-text-faint">{currentPage} / {totalPages}</span>
                <Button variant="ghost" size="sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                  Next
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
