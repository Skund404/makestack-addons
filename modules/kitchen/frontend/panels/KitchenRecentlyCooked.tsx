/**
 * Recently Cooked panel — third-width, last 5 cook log entries.
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, UtensilsCrossed, Star } from 'lucide-react'
import { kitchenApi } from '../api'
import type { PanelProps } from '@/modules/panel-registry'

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function KitchenRecentlyCooked(_props: PanelProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-cook-log-recent'],
    queryFn: () => kitchenApi.listCookLog({ limit: 5 }),
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

  const entries = data?.items ?? []

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-6 gap-2 text-text-faint">
        <UtensilsCrossed size={20} className="opacity-30" />
        <span className="text-xs">No sessions logged yet</span>
      </div>
    )
  }

  return (
    <ul className="space-y-2">
      {entries.map((entry) => (
        <li key={entry.id} className="flex items-start gap-2 text-xs">
          <div className="flex-1 min-w-0">
            <div className="text-text truncate">{entry.recipe_id}</div>
            <div className="text-text-faint">{formatDate(entry.cooked_at)}</div>
          </div>
          {entry.rating != null && (
            <div className="flex items-center gap-0.5 text-warning shrink-0">
              <Star size={10} fill="currentColor" />
              <span>{entry.rating}</span>
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}
