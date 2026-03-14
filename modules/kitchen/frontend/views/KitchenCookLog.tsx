/**
 * Kitchen Cook Log view — cooking history with ratings.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, UtensilsCrossed, Star } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { kitchenApi } from '../api'

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

export function KitchenCookLog() {
  const [offset, setOffset] = useState(0)

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
        <h1 className="text-base font-semibold text-text">Cook Log</h1>
        <span className="text-xs text-text-faint">{total} session{total !== 1 ? 's' : ''}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
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
