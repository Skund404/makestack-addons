/**
 * Expiring Soon panel — half-width, items expiring within 7 days.
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, Clock } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { kitchenApi, fmtQty, nameFromPath } from '../api'
import type { PanelProps } from '@/modules/panel-registry'

function urgencyVariant(days: number): 'danger' | 'warning' | 'muted' {
  if (days <= 1) return 'danger'
  if (days <= 3) return 'warning'
  return 'muted'
}

export function KitchenExpiringSoon(_props: PanelProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-expiring', 7],
    queryFn: () => kitchenApi.listExpiring(7),
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

  const items = data ?? []

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-6 gap-2 text-text-faint">
        <Clock size={20} className="opacity-30" />
        <span className="text-xs">Nothing expiring soon</span>
      </div>
    )
  }

  return (
    <ul className="space-y-1.5">
      {items.map((item) => {
        const name = item.catalogue_path ? nameFromPath(item.catalogue_path) : item.inventory_id
        const variant = urgencyVariant(item.days_until_expiry)
        const label = item.days_until_expiry === 0
          ? 'today'
          : item.days_until_expiry === 1
          ? 'tomorrow'
          : `${item.days_until_expiry}d`
        return (
          <li key={item.stock_item_id} className="flex items-center gap-2 text-xs">
            <span className="text-text flex-1 truncate">{name}</span>
            <span className="text-text-muted shrink-0">{fmtQty(item.quantity, item.unit)}</span>
            <Badge variant={variant}>{label}</Badge>
          </li>
        )
      })}
    </ul>
  )
}
