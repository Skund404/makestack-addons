/**
 * Kitchen Shopping List view — generated shopping list for current week.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, ShoppingCart, ChevronLeft, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { kitchenApi, currentMondayISO, fmtQty } from '../api'

function addDays(isoDate: string, days: number): string {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

export function KitchenShoppingList() {
  const [week, setWeek] = useState(currentMondayISO)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['kitchen-shopping-list', week],
    queryFn: () => kitchenApi.getShoppingList(week),
    staleTime: 60_000,
  })

  const items = data?.items ?? []
  const needed = items.filter((i) => i.shortfall > 0)
  const covered = items.filter((i) => i.shortfall === 0)

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        <ShoppingCart size={16} className="text-text-muted" />
        <h1 className="text-base font-semibold text-text flex-1">Shopping List</h1>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setWeek(addDays(week, -7))}>
            <ChevronLeft size={14} />
          </Button>
          <span className="text-xs text-text-muted w-24 text-center">{week}</span>
          <Button variant="ghost" size="sm" onClick={() => setWeek(addDays(week, 7))}>
            <ChevronRight size={14} />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setWeek(currentMondayISO())}>
            This week
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {isLoading && (
          <div className="flex items-center justify-center py-16 text-text-muted gap-2">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        )}
        {isError && (
          <div className="flex items-center justify-center py-16 text-danger/70 gap-2">
            <AlertCircle size={16} /> Failed to load shopping list.
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-text-faint">
            <ShoppingCart size={24} className="opacity-30" />
            <p className="text-sm">No meal plan entries this week.</p>
          </div>
        )}
        {!isLoading && !isError && items.length > 0 && (
          <div className="space-y-4">
            {needed.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <h2 className="text-sm font-semibold text-text">Need to buy</h2>
                  <Badge variant="warning">{needed.length}</Badge>
                </div>
                <div className="space-y-1.5">
                  {needed.map((item) => (
                    <div key={`${item.catalogue_path}-${item.unit}`} className="flex items-center gap-2 text-sm">
                      <span className="flex-1 text-text">{item.name}</span>
                      <span className="text-text-muted font-mono">{fmtQty(item.shortfall, item.unit)}</span>
                      <span className="text-text-faint text-xs">of {fmtQty(item.required_quantity, item.unit)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {covered.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <h2 className="text-sm font-semibold text-text-muted">Already in stock</h2>
                  <Badge variant="success">{covered.length}</Badge>
                </div>
                <div className="space-y-1.5">
                  {covered.map((item) => (
                    <div key={`${item.catalogue_path}-${item.unit}`} className="flex items-center gap-2 text-sm">
                      <span className="flex-1 text-text-muted line-through">{item.name}</span>
                      <span className="text-text-faint font-mono text-xs">{fmtQty(item.on_hand_quantity, item.unit)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
