/**
 * Kitchen Stock Overview panel — full-width, three-column (pantry / fridge / freezer).
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, Package } from 'lucide-react'
import { kitchenApi, fmtQty, nameFromPath } from '../api'
import type { PanelProps } from '@/modules/panel-registry'

const LOCATIONS = [
  { key: 'pantry',  label: 'Pantry',  icon: '🥫' },
  { key: 'fridge',  label: 'Fridge',  icon: '🥬' },
  { key: 'freezer', label: 'Freezer', icon: '🧊' },
]

function LocationColumn({ location, label, icon }: { location: string; label: string; icon: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-stock', location],
    queryFn: () => kitchenApi.listStock({ location, limit: 8 }),
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6 text-text-muted">
        <Loader2 size={14} className="animate-spin" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center py-6 gap-1 text-danger/60 text-xs">
        <AlertCircle size={12} /> Error
      </div>
    )
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-base">{icon}</span>
        <span className="text-xs font-semibold text-text">{label}</span>
        <span className="ml-auto text-xs text-text-faint">{total}</span>
      </div>
      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-4 gap-1 text-text-faint">
          <Package size={14} className="opacity-30" />
          <span className="text-xs">Empty</span>
        </div>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-text truncate flex-1">{nameFromPath(item.catalogue_path)}</span>
              <span className="text-text-muted shrink-0 font-mono">{fmtQty(item.quantity, item.unit)}</span>
            </li>
          ))}
          {total > 8 && (
            <li className="text-xs text-text-faint text-center pt-1">+{total - 8} more</li>
          )}
        </ul>
      )}
    </div>
  )
}

export function KitchenStockOverview(_props: PanelProps) {
  return (
    <div className="grid grid-cols-3 gap-4 divide-x divide-border">
      {LOCATIONS.map(({ key, label, icon }) => (
        <div key={key} className="pl-4 first:pl-0">
          <LocationColumn location={key} label={label} icon={icon} />
        </div>
      ))}
    </div>
  )
}
