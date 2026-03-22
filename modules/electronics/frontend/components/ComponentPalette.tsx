/**
 * Component palette — sidebar list of component types to place on the canvas.
 * Grouped by category: Passive, Sources, Semiconductor, Transistor, IC, MCU.
 */

interface PaletteItem {
  type: string
  label: string
  shortLabel: string
}

interface PaletteGroup {
  name: string
  items: PaletteItem[]
}

const GROUPS: PaletteGroup[] = [
  {
    name: 'Passive',
    items: [
      { type: 'resistor',  label: 'Resistor',  shortLabel: 'R' },
      { type: 'capacitor', label: 'Capacitor', shortLabel: 'C' },
      { type: 'inductor',  label: 'Inductor',  shortLabel: 'L' },
    ],
  },
  {
    name: 'Sources',
    items: [
      { type: 'voltage_source', label: 'Voltage Source', shortLabel: 'V' },
      { type: 'current_source', label: 'Current Source', shortLabel: 'I' },
      { type: 'ground',         label: 'Ground',         shortLabel: 'G' },
    ],
  },
  {
    name: 'Semiconductor',
    items: [
      { type: 'diode', label: 'Diode',       shortLabel: 'D' },
      { type: 'zener', label: 'Zener Diode', shortLabel: 'DZ' },
      { type: 'led',   label: 'LED',         shortLabel: 'LED' },
    ],
  },
  {
    name: 'Transistor',
    items: [
      { type: 'npn_bjt', label: 'NPN BJT', shortLabel: 'Q' },
      { type: 'pnp_bjt', label: 'PNP BJT', shortLabel: 'Q' },
      { type: 'nmos',    label: 'NMOS FET', shortLabel: 'M' },
      { type: 'pmos',    label: 'PMOS FET', shortLabel: 'M' },
    ],
  },
  {
    name: 'IC',
    items: [
      { type: 'opamp', label: 'Op-Amp', shortLabel: 'U' },
    ],
  },
  {
    name: 'MCU',
    items: [
      { type: 'mcu', label: 'Microcontroller', shortLabel: 'MCU' },
    ],
  },
]

interface ComponentPaletteProps {
  activeType: string | null
  onSelect: (type: string | null) => void
}

export function ComponentPalette({ activeType, onSelect }: ComponentPaletteProps) {
  return (
    <div className="w-40 border-r border-zinc-700 bg-zinc-900/50 p-2 space-y-0.5 shrink-0 overflow-y-auto">
      {GROUPS.map((group) => (
        <div key={group.name}>
          <div className="text-[9px] uppercase tracking-wider text-zinc-500 px-2 py-1 mt-1 first:mt-0">
            {group.name}
          </div>
          {group.items.map((item) => (
            <button
              key={item.type}
              onClick={() => onSelect(activeType === item.type ? null : item.type)}
              className={`flex w-full items-center gap-2 rounded px-2 py-1 text-xs transition-colors ${
                activeType === item.type
                  ? 'bg-sky-900/50 text-sky-300'
                  : 'text-zinc-300 hover:bg-zinc-800'
              }`}
            >
              <span className="w-5 h-5 rounded bg-zinc-800 flex items-center justify-center text-[8px] font-mono font-bold text-sky-400 shrink-0">
                {item.shortLabel}
              </span>
              <span className="truncate">{item.label}</span>
            </button>
          ))}
        </div>
      ))}
      {activeType && (
        <div className="text-[10px] text-zinc-500 px-2 pt-2">
          Click on canvas to place
        </div>
      )}
    </div>
  )
}
