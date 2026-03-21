/**
 * Component palette — sidebar list of component types to place on the canvas.
 */

interface PaletteItem {
  type: string
  label: string
  shortLabel: string
}

const ITEMS: PaletteItem[] = [
  { type: 'resistor',       label: 'Resistor',       shortLabel: 'R' },
  { type: 'voltage_source', label: 'Voltage Source',  shortLabel: 'V' },
  { type: 'current_source', label: 'Current Source',  shortLabel: 'I' },
  { type: 'ground',         label: 'Ground',          shortLabel: 'G' },
]

interface ComponentPaletteProps {
  activeType: string | null
  onSelect: (type: string | null) => void
}

export function ComponentPalette({ activeType, onSelect }: ComponentPaletteProps) {
  return (
    <div className="w-36 border-r border-zinc-700 bg-zinc-900/50 p-2 space-y-1 shrink-0">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500 px-2 py-1">
        Components
      </div>
      {ITEMS.map((item) => (
        <button
          key={item.type}
          onClick={() => onSelect(activeType === item.type ? null : item.type)}
          className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors ${
            activeType === item.type
              ? 'bg-sky-900/50 text-sky-300'
              : 'text-zinc-300 hover:bg-zinc-800'
          }`}
        >
          <span className="w-5 h-5 rounded bg-zinc-800 flex items-center justify-center text-[10px] font-mono font-bold text-sky-400">
            {item.shortLabel}
          </span>
          {item.label}
        </button>
      ))}
      {activeType && (
        <div className="text-[10px] text-zinc-500 px-2 pt-2">
          Click on canvas to place
        </div>
      )}
    </div>
  )
}
