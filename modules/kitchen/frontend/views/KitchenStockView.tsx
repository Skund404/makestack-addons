/**
 * Kitchen stock location view — shared by Pantry, Fridge, and Freezer.
 * Accepts a `location` prop to filter the stock list.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, Package } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { kitchenApi, fmtQty, nameFromPath } from '../api'

const PAGE_SIZE = 20

interface KitchenStockViewProps {
  location: 'pantry' | 'fridge' | 'freezer'
  title: string
}

function ExpiryBadge({ expiry }: { expiry: string | null }) {
  if (!expiry) return null
  const days = Math.ceil((new Date(expiry).getTime() - Date.now()) / 86400000)
  if (days < 0) return <Badge variant="danger">expired</Badge>
  if (days <= 1) return <Badge variant="danger">{days === 0 ? 'today' : 'tomorrow'}</Badge>
  if (days <= 7) return <Badge variant="warning">{days}d</Badge>
  return null
}

export function KitchenStockView({ location, title }: KitchenStockViewProps) {
  const [offset, setOffset] = useState(0)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-stock', location, offset],
    queryFn: () => kitchenApi.listStock({ location, limit: PAGE_SIZE, offset }),
    staleTime: 60_000,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <h1 className="text-base font-semibold text-text">{title}</h1>
        <span className="text-xs text-text-faint">{total} item{total !== 1 ? 's' : ''}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {isLoading && (
          <div className="flex items-center justify-center py-16 text-text-muted gap-2">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        )}
        {isError && (
          <div className="flex items-center justify-center py-16 text-danger/70 gap-2">
            <AlertCircle size={16} /> Failed to load stock.
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-text-faint">
            <Package size={24} className="opacity-30" />
            <p className="text-sm">{title} is empty.</p>
          </div>
        )}
        {!isLoading && !isError && items.length > 0 && (
          <div className="space-y-2">
            <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1.5">
              {/* Header */}
              <div className="text-xs font-medium text-text-muted">Item</div>
              <div className="text-xs font-medium text-text-muted text-right">Qty</div>
              <div className="text-xs font-medium text-text-muted">Expiry</div>
              {/* Rows */}
              {items.map((item) => (
                <>
                  <div key={`${item.id}-name`} className="text-sm text-text truncate">{nameFromPath(item.catalogue_path)}</div>
                  <div key={`${item.id}-qty`} className="text-sm text-text-muted font-mono text-right">{fmtQty(item.quantity, item.unit)}</div>
                  <div key={`${item.id}-exp`}><ExpiryBadge expiry={item.expiry_date} /></div>
                </>
              ))}
            </div>
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

export function KitchenPantry() { return <KitchenStockView location="pantry" title="Pantry" /> }
export function KitchenFridge() { return <KitchenStockView location="fridge" title="Fridge" /> }
export function KitchenFreezer() { return <KitchenStockView location="freezer" title="Freezer" /> }
