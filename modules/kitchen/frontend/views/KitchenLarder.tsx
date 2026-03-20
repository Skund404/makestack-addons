/**
 * KitchenLarder — three-column stock view (Pantry / Fridge / Freezer).
 *
 * Matches the mockup's Larder screen with color-coded column headers,
 * search bar, and slide-out add-item panel.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Plus, X } from 'lucide-react'
import { apiGet } from '@/lib/api'

interface StockItem {
  id: string
  name: string
  quantity: number
  unit: string
  location: string
  expiry_date?: string | null
}

interface StockResponse {
  items: StockItem[]
  total: number
}

const COLUMNS = [
  { key: 'pantry',  label: 'Pantry',  color: '#BA7517', headerClass: 'border-t-[3px]' },
  { key: 'fridge',  label: 'Fridge',  color: '#888780', headerClass: 'border-t-[3px]' },
  { key: 'freezer', label: 'Freezer', color: '#378ADD', headerClass: 'border-t-[3px]' },
] as const

export function KitchenLarder() {
  const [search, setSearch] = useState('')
  const [addPanelOpen, setAddPanelOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['kitchen-stock-all'],
    queryFn: () => apiGet<StockResponse>('/modules/kitchen/stock'),
    staleTime: 30_000,
  })

  const items = (data?.items ?? []).filter((item) =>
    !search || item.name.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-surface shrink-0">
        <h2
          className="text-xl flex-1"
          style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
        >
          Larder
        </h2>
        <div className="text-[11px] text-text-faint">{data?.total ?? 0} items</div>
      </div>

      {/* Search bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-surface shrink-0">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search larder..."
          className="flex-1 px-3 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
        />
        <button
          onClick={() => setAddPanelOpen(true)}
          className="flex items-center gap-1 px-3 py-1.5 text-[10px] font-medium rounded bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
        >
          <Plus size={10} /> Add item
        </button>
      </div>

      {/* Three-column grid */}
      <div className="flex flex-1 min-h-0 overflow-hidden relative">
        {isLoading ? (
          <div className="flex items-center justify-center w-full py-12 text-text-muted gap-2">
            <Loader2 size={14} className="animate-spin" />
            <span className="text-xs">Loading stock...</span>
          </div>
        ) : (
          COLUMNS.map((col, i) => {
            const colItems = items.filter((item) => item.location === col.key)
            return (
              <div
                key={col.key}
                className="flex-1 min-w-0 flex flex-col border-r border-border last:border-r-0 bg-surface"
              >
                {/* Column header */}
                <div
                  className="px-3 py-2 border-b border-border shrink-0"
                  style={{ borderTopWidth: 3, borderTopColor: col.color, borderTopStyle: 'solid' }}
                >
                  <p className="text-[10px] font-medium uppercase tracking-wider" style={{ color: col.color }}>
                    {col.label}
                  </p>
                  <p className="text-[10px] mt-0.5" style={{ color: col.color }}>
                    {colItems.length} items
                  </p>
                </div>

                {/* Items */}
                <div className="flex-1 overflow-y-auto">
                  {colItems.length === 0 ? (
                    <p className="text-xs text-text-faint italic p-3">Empty</p>
                  ) : (
                    colItems.map((item) => (
                      <div
                        key={item.id}
                        className="flex items-center gap-2 px-3 py-2 border-b border-border/50"
                      >
                        <span className="flex-1 text-xs text-text truncate">{item.name}</span>
                        <span className="text-[11px] text-text-faint shrink-0">
                          {item.quantity} {item.unit}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )
          })
        )}

        {/* Add item slide-out panel */}
        <div
          className="absolute right-0 top-0 bottom-0 w-60 flex flex-col border-l border-border bg-surface shadow-lg transition-transform duration-200"
          style={{ transform: addPanelOpen ? 'translateX(0)' : 'translateX(100%)' }}
        >
          <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
            <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint">Add Item</p>
            <button onClick={() => setAddPanelOpen(false)} className="text-text-faint hover:text-text">
              <X size={14} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <p className="text-xs text-text-faint italic">
              Add item form — coming in kitchen frontend rebuild.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
