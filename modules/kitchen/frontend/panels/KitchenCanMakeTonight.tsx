/**
 * Can Make Tonight panel — half-width, shows recipes makeable from current stock.
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, ChefHat, Clock } from 'lucide-react'
import { kitchenApi } from '../api'
import type { PanelProps } from '@/modules/panel-registry'

export function KitchenCanMakeTonight(_props: PanelProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-can-make'],
    queryFn: () => kitchenApi.canMake(true, 6),
    staleTime: 120_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6 text-text-muted gap-2">
        <Loader2 size={14} className="animate-spin" />
        <span className="text-xs">Checking stock…</span>
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

  const recipes = data?.recipes ?? []
  const total = data?.total ?? 0

  if (recipes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-6 gap-2 text-text-faint">
        <ChefHat size={20} className="opacity-30" />
        <span className="text-xs">Nothing makeable from current stock</span>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1 mb-2">
        <ChefHat size={12} className="text-accent" />
        <span className="text-xs text-text-muted">{total} recipe{total !== 1 ? 's' : ''} ready</span>
      </div>
      <ul className="space-y-1.5">
        {recipes.map((r) => (
          <li key={r.recipe_id} className="flex items-center gap-2 text-xs">
            <span className="text-text flex-1 truncate">{r.recipe_title}</span>
          </li>
        ))}
        {total > 6 && (
          <li className="text-xs text-text-faint text-center pt-1">+{total - 6} more</li>
        )}
      </ul>
    </div>
  )
}
