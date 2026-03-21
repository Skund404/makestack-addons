/**
 * Component library browser — shows available component types.
 */
import { useQuery } from '@tanstack/react-query'
import { electronicsApi } from '../api'

export function ElectronicsComponents() {
  const { data } = useQuery({
    queryKey: ['electronics-library'],
    queryFn: electronicsApi.listLibrary,
  })

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold mb-6">Component Library</h1>

      <div className="space-y-3">
        {data?.items.map((comp) => (
          <div
            key={comp.type}
            className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4"
          >
            <div className="flex items-center gap-3 mb-2">
              <div className="w-8 h-8 rounded bg-sky-900/50 flex items-center justify-center text-sky-400 text-xs font-mono font-bold">
                {comp.type === 'resistor' ? 'R' :
                 comp.type === 'voltage_source' ? 'V' :
                 comp.type === 'current_source' ? 'I' :
                 comp.type === 'ground' ? 'G' : '?'}
              </div>
              <div>
                <div className="text-sm font-medium">{comp.label}</div>
                <div className="text-xs text-zinc-400">
                  Pins: {comp.pins.join(', ')}
                  {comp.value_unit && ` | Default: ${comp.default_value} ${comp.value_unit}`}
                </div>
              </div>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed">
              {comp.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
