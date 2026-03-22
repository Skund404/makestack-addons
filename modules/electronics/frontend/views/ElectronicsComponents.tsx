/**
 * Component library browser — shows available component types with presets.
 */
import { useQuery } from '@tanstack/react-query'
import { electronicsApi } from '../api'
import type { ComponentTypeInfo } from '../api'

const PREFIX_MAP: Record<string, string> = {
  resistor: 'R', capacitor: 'C', inductor: 'L',
  voltage_source: 'V', current_source: 'I', ground: 'G',
  diode: 'D', zener: 'DZ', led: 'LED',
  npn_bjt: 'Q', pnp_bjt: 'Q', nmos: 'M', pmos: 'M',
  opamp: 'U', mcu: 'MCU',
}

const CATEGORY_ORDER = ['Passive', 'Sources', 'Semiconductor', 'Transistor', 'IC', 'MCU']
const TYPE_CATEGORY: Record<string, string> = {
  resistor: 'Passive', capacitor: 'Passive', inductor: 'Passive',
  voltage_source: 'Sources', current_source: 'Sources', ground: 'Sources',
  diode: 'Semiconductor', zener: 'Semiconductor', led: 'Semiconductor',
  npn_bjt: 'Transistor', pnp_bjt: 'Transistor', nmos: 'Transistor', pmos: 'Transistor',
  opamp: 'IC', mcu: 'MCU',
}

function groupByCategory(items: ComponentTypeInfo[]): Map<string, ComponentTypeInfo[]> {
  const groups = new Map<string, ComponentTypeInfo[]>()
  for (const cat of CATEGORY_ORDER) groups.set(cat, [])
  for (const item of items) {
    const cat = TYPE_CATEGORY[item.type] || 'Other'
    if (!groups.has(cat)) groups.set(cat, [])
    groups.get(cat)!.push(item)
  }
  return groups
}

export function ElectronicsComponents() {
  const { data } = useQuery({
    queryKey: ['electronics-library'],
    queryFn: electronicsApi.listLibrary,
  })

  const grouped = data?.items ? groupByCategory(data.items) : new Map()

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold mb-6">Component Library</h1>

      {Array.from(grouped.entries()).map(([category, items]) =>
        items.length === 0 ? null : (
          <div key={category} className="mb-6">
            <h2 className="text-sm uppercase tracking-wider text-zinc-500 mb-3">{category}</h2>
            <div className="space-y-2">
              {items.map((comp) => (
                <div
                  key={comp.type}
                  className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4"
                >
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-8 h-8 rounded bg-sky-900/50 flex items-center justify-center text-sky-400 text-[10px] font-mono font-bold">
                      {PREFIX_MAP[comp.type] || '?'}
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">{comp.label}</div>
                      <div className="text-xs text-zinc-400">
                        Pins: {comp.pins.join(', ')}
                        {comp.value_unit && ` | Default: ${comp.default_value} ${comp.value_unit}`}
                      </div>
                    </div>
                    {comp.presets && comp.presets.length > 0 && (
                      <div className="flex gap-1 flex-wrap justify-end">
                        {comp.presets.slice(0, 4).map((p) => (
                          <span key={p} className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 font-mono">
                            {p}
                          </span>
                        ))}
                        {comp.presets.length > 4 && (
                          <span className="text-[9px] text-zinc-500">+{comp.presets.length - 4}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {comp.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )
      )}
    </div>
  )
}
