/**
 * StockItemDialog — edit/delete a stock item in a slide-over panel.
 *
 * Rendered inline in KitchenLarder when a stock item row is clicked.
 * Updates quantity/unit/location/expiry via kitchenApi.updateStockItem
 * and deletes via kitchenApi.deleteStockItem.
 */
import { useState, useEffect } from 'react'
import { X, Trash2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { kitchenApi, nameFromPath } from '../api'
import type { KitchenStockItem } from '../api'

const LOCATIONS = [
  { value: 'pantry', label: 'Pantry' },
  { value: 'fridge', label: 'Fridge' },
  { value: 'freezer', label: 'Freezer' },
]

interface StockItemDialogProps {
  item: KitchenStockItem
  onClose: () => void
}

export function StockItemDialog({ item, onClose }: StockItemDialogProps) {
  const queryClient = useQueryClient()
  const [quantity, setQuantity] = useState(item.quantity.toString())
  const [unit, setUnit] = useState(item.unit)
  const [location, setLocation] = useState(item.location)
  const [expiryDate, setExpiryDate] = useState(item.expiry_date ?? '')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Reset form when item changes
  useEffect(() => {
    setQuantity(item.quantity.toString())
    setUnit(item.unit)
    setLocation(item.location)
    setExpiryDate(item.expiry_date ?? '')
  }, [item.id, item.quantity, item.unit, item.location, item.expiry_date])

  const handleSave = async () => {
    setSaving(true)
    try {
      await kitchenApi.updateStockItem(item.id, {
        quantity: parseFloat(quantity) || 0,
        unit,
        location,
        expiry_date: expiryDate || null,
      })
      await queryClient.invalidateQueries({ queryKey: ['kitchen-stock-all'] })
      onClose()
    } catch {
      // silently fail
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirm(`Remove ${nameFromPath(item.catalogue_path)} from stock?`)) return
    setDeleting(true)
    try {
      await kitchenApi.deleteStockItem(item.id)
      await queryClient.invalidateQueries({ queryKey: ['kitchen-stock-all'] })
      onClose()
    } catch {
      // silently fail
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <p className="text-[10px] font-medium uppercase tracking-wider text-text-faint">Edit Item</p>
        <button onClick={onClose} className="text-text-faint hover:text-text">
          <X size={14} />
        </button>
      </div>

      {/* Form */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Name (read-only) */}
        <div>
          <label className="block text-[10px] font-medium text-text-faint mb-1">Name</label>
          <p className="text-xs text-text px-2.5 py-1.5 rounded border border-border/50 bg-bg/50">
            {nameFromPath(item.catalogue_path)}
          </p>
        </div>

        {/* Quantity + Unit */}
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="block text-[10px] font-medium text-text-faint mb-1">Qty</label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              min="0"
              step="any"
              className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
            />
          </div>
          <div className="flex-1">
            <label className="block text-[10px] font-medium text-text-faint mb-1">Unit</label>
            <input
              type="text"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              placeholder="g, ml, piece"
              className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text placeholder:text-text-faint focus:outline-none focus:border-accent/50"
            />
          </div>
        </div>

        {/* Location */}
        <div>
          <label className="block text-[10px] font-medium text-text-faint mb-1">Location</label>
          <select
            value={location}
            onChange={(e) => setLocation(e.target.value)}
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
            value={expiryDate}
            onChange={(e) => setExpiryDate(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs rounded border border-border bg-bg text-text focus:outline-none focus:border-accent/50"
          />
        </div>

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full px-3 py-2 text-xs font-medium rounded transition-colors disabled:opacity-50"
          style={{ backgroundColor: '#c8935a', color: '#15100b' }}
          data-testid="stock-save-btn"
        >
          {saving ? 'Saving...' : 'Save changes'}
        </button>

        {/* Delete button */}
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
          data-testid="stock-delete-btn"
        >
          <Trash2 size={10} />
          {deleting ? 'Removing...' : 'Remove from stock'}
        </button>
      </div>
    </div>
  )
}
