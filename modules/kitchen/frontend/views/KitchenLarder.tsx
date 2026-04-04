/**
 * KitchenLarder — three-column stock view (Pantry / Fridge / Freezer).
 *
 * Matches the mockup's Larder screen with color-coded column headers,
 * search bar, expiry badges, and slide-out add-item panel.
 */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, X, GitFork } from 'lucide-react'
import { kitchenApi, nameFromPath, fmtQty } from '../api'
import type { KitchenStockList, KitchenStockItem } from '../api'
import { StockItemDialog } from '../components/StockItemDialog'

const COLUMNS = [
  { key: 'pantry',  label: 'Pantry',  color: '#BA7517' },
  { key: 'fridge',  label: 'Fridge',  color: '#888780' },
  { key: 'freezer', label: 'Freezer', color: '#378ADD' },
] as const

function expiryBadge(expiryDate: string | null) {
  if (!expiryDate) return null
  const days = Math.ceil((new Date(expiryDate).getTime() - Date.now()) / 86400000)
  if (days < 0) return <span className="text-[9px] font-medium px-1 py-px rounded-full" style={{ color: '#ef4444', backgroundColor: '#ef444415' }}>expired</span>
  if (days <= 1) return <span className="text-[9px] font-medium px-1 py-px rounded-full" style={{ color: '#ef4444', backgroundColor: '#ef444415' }}>{days === 0 ? 'today' : '1d'}</span>
  if (days <= 3) return <span className="text-[9px] font-medium px-1 py-px rounded-full" style={{ color: '#f97316', backgroundColor: '#f9731615' }}>{days}d</span>
  if (days <= 7) return <span className="text-[9px] font-medium px-1 py-px rounded-full" style={{ color: '#9ca3af', backgroundColor: '#9ca3af15' }}>{days}d</span>
  return null
}

const LOCATIONS = [
  { value: 'pantry', label: 'Pantry' },
  { value: 'fridge', label: 'Fridge' },
  { value: 'freezer', label: 'Freezer' },
]

export function KitchenLarder() {
  const [search, setSearch] = useState('')
  const [addPanelOpen, setAddPanelOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<KitchenStockItem | null>(null)
  const queryClient = useQueryClient()

  // Form state
  const [formName, setFormName] = useState('')
  const [formQty, setFormQty] = useState('1')
  const [formUnit, setFormUnit] = useState('')
  const [formLocation, setFormLocation] = useState('pantry')
  const [formExpiry, setFormExpiry] = useState('')
  const [formSaving, setFormSaving] = useState(false)
  const [forkingPrimitive, setForkingPrimitive] = useState<string | null>(null)
  const [forkFlash, setForkFlash] = useState<string | null>(null) // catalogue_path that just got forked

  const { data, isLoading } = useQuery({
    queryKey: ['kitchen-stock-all'],
    queryFn: () => kitchenApi.listStock({ limit: 200 }),
    staleTime: 30_000,
  })

  const items = (data?.items ?? []).filter((item) => {
    if (!search) return true
    const name = nameFromPath(item.catalogue_path)
    return name.toLowerCase().includes(search.toLowerCase())
  })

  const resetForm = () => {
    setFormName('')
    setFormQty('1')
    setFormUnit('')
    setFormLocation('pantry')
    setFormExpiry('')
  }

  const handleForkPrimitive = async (e: React.MouseEvent, cataloguePath: string) => {
    e.stopPropagation()
    if (!cataloguePath) return
    const name = nameFromPath(cataloguePath)
    setForkingPrimitive(cataloguePath)
    try {
      await kitchenApi.forkCataloguePrimitive(cataloguePath, `${name} (fork)`)
      setForkFlash(cataloguePath)
      setTimeout(() => setForkFlash(null), 3000)
    } catch {
      // silently fail
    } finally {
      setForkingPrimitive(null)
    }
  }

  const handleAddItem = async () => {
    if (!formName.trim()) return
    setFormSaving(true)
    try {
      await kitchenApi.addStockItem({
        name: formName.trim(),
        quantity: parseFloat(formQty) || 1,
        unit: formUnit,
        location: formLocation,
        expiry_date: formExpiry || undefined,
      })
      await queryClient.invalidateQueries({ queryKey: ['kitchen-stock-all'] })
      resetForm()
      setAddPanelOpen(false)
    } catch {
      // silently fail — user can retry
    } finally {
      setFormSaving(false)
    }
  }

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
          onClick={() => { setAddPanelOpen(true); setEditingItem(null) }}
          className="flex items-center gap-1 px-3 py-1.5 text-[10px] font-medium rounded bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
        >
          <Plus size={10} /> Add item
        </button>
      </div>

      {/* Three-column grid + side panel */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* Columns */}
        <div className="flex flex-1 min-w-0 overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center w-full py-12 text-text-muted gap-2">
              <Loader2 size={14} className="animate-spin" />
              <span className="text-xs">Loading stock...</span>
            </div>
          ) : (
            COLUMNS.map((col) => {
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
                          onClick={() => { setEditingItem(item); setAddPanelOpen(false) }}
                          className="group flex items-center gap-2 px-3 py-2 border-b border-border/50 cursor-pointer hover:bg-accent/5 transition-colors"
                        >
                          <span className="flex-1 text-xs text-text truncate">{nameFromPath(item.catalogue_path)}</span>
                          <span className="text-[11px] text-text-faint shrink-0">
                            {fmtQty(item.quantity, item.unit)}
                          </span>
                          {expiryBadge(item.expiry_date)}
                          {forkFlash === item.catalogue_path ? (
                            <span className="text-[9px] text-accent shrink-0">forked</span>
                          ) : (
                            <button
                              onClick={(e) => handleForkPrimitive(e, item.catalogue_path)}
                              disabled={forkingPrimitive === item.catalogue_path}
                              className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-text-faint hover:text-accent hover:bg-accent/10 transition-all disabled:opacity-30 shrink-0"
                              title={`Fork ${nameFromPath(item.catalogue_path)}`}
                            >
                              {forkingPrimitive === item.catalogue_path
                                ? <Loader2 size={10} className="animate-spin" />
                                : <GitFork size={10} />}
                            </button>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Side panel — add item OR edit item */}
        <div
          className="shrink-0 flex flex-col border-l border-border bg-surface overflow-hidden transition-[width] duration-200"
          style={{ width: (addPanelOpen || editingItem) ? 240 : 0 }}
        >
          <div className="w-60 flex flex-col flex-1 overflow-hidden">
          {editingItem ? (
            <StockItemDialog
              item={editingItem}
              onClose={() => setEditingItem(null)}
            />
          ) : (
            <>
            <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
              <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint">Add Item</p>
              <button onClick={() => setAddPanelOpen(false)} className="text-text-faint hover:text-text">
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {/* Name */}
              <div>
                <label className="block text-[10px] font-medium text-text-faint mb-1">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Flour"
                  className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
                />
              </div>

              {/* Quantity + Unit */}
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
                    placeholder="g, ml, piece"
                    className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
                  />
                </div>
              </div>

              {/* Location */}
              <div>
                <label className="block text-[10px] font-medium text-text-faint mb-1">Location</label>
                <select
                  value={formLocation}
                  onChange={(e) => setFormLocation(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
                >
                  {LOCATIONS.map((loc) => (
                    <option key={loc.value} value={loc.value}>{loc.label}</option>
                  ))}
                </select>
              </div>

              {/* Expiry date */}
              <div>
                <label className="block text-[10px] font-medium text-text-faint mb-1">Expiry date</label>
                <input
                  type="date"
                  value={formExpiry}
                  onChange={(e) => setFormExpiry(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
                />
              </div>

              {/* Save button */}
              <button
                onClick={handleAddItem}
                disabled={!formName.trim() || formSaving}
                className="w-full px-3 py-2 text-xs font-medium rounded transition-colors disabled:opacity-50"
                style={{ backgroundColor: '#c8935a', color: '#15100b' }}
              >
                {formSaving ? 'Saving...' : 'Add to larder'}
              </button>
            </div>
            </>
          )}
          </div>
        </div>

      </div>
    </div>
  )
}
