/**
 * Simulation panel — run button + results table (right sidebar in editor).
 */
import { Play, AlertCircle, CheckCircle } from 'lucide-react'
import type { SimResult, CircuitComponent } from '../api'

interface SimulationPanelProps {
  simResult: SimResult | null
  isSimulating: boolean
  onSimulate: () => void
  selectedComponent: CircuitComponent | null
}

function formatValue(v: number, unit: string): string {
  const abs = Math.abs(v)
  if (unit === 'A') {
    if (abs < 1e-6) return `${(v * 1e9).toFixed(1)} nA`
    if (abs < 1e-3) return `${(v * 1e6).toFixed(1)} \u00B5A`
    if (abs < 1) return `${(v * 1e3).toFixed(2)} mA`
    return `${v.toFixed(3)} A`
  }
  if (unit === 'V') {
    if (abs < 1e-3) return `${(v * 1e6).toFixed(1)} \u00B5V`
    if (abs < 1) return `${(v * 1e3).toFixed(1)} mV`
    return `${v.toFixed(3)} V`
  }
  if (unit === 'W') {
    if (abs < 1e-6) return `${(v * 1e9).toFixed(1)} nW`
    if (abs < 1e-3) return `${(v * 1e6).toFixed(1)} \u00B5W`
    if (abs < 1) return `${(v * 1e3).toFixed(2)} mW`
    return `${v.toFixed(3)} W`
  }
  return v.toFixed(4)
}

export function SimulationPanel({
  simResult, isSimulating, onSimulate, selectedComponent,
}: SimulationPanelProps) {
  return (
    <div className="w-56 border-l border-zinc-700 bg-zinc-900/50 flex flex-col shrink-0 overflow-y-auto">
      {/* Run button */}
      <div className="p-3 border-b border-zinc-700">
        <button
          onClick={onSimulate}
          disabled={isSimulating}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50 transition-colors"
        >
          <Play size={14} />
          {isSimulating ? 'Simulating...' : 'Simulate'}
        </button>
      </div>

      {/* Status */}
      {simResult && (
        <div className="p-3 border-b border-zinc-700">
          <div className="flex items-center gap-2 text-xs">
            {simResult.status === 'complete' ? (
              <>
                <CheckCircle size={12} className="text-emerald-400" />
                <span className="text-emerald-400">Complete</span>
                <span className="text-zinc-500 ml-auto">{simResult.duration_ms}ms</span>
              </>
            ) : simResult.status === 'error' ? (
              <>
                <AlertCircle size={12} className="text-red-400" />
                <span className="text-red-400">Error</span>
              </>
            ) : (
              <span className="text-zinc-400">No results</span>
            )}
          </div>
          {simResult.status === 'error' && simResult.error_message && (
            <p className="text-[10px] text-red-300 mt-2 leading-relaxed">
              {simResult.error_message}
            </p>
          )}
        </div>
      )}

      {/* Node voltages */}
      {simResult?.status === 'complete' && simResult.node_results && (
        <div className="p-3 border-b border-zinc-700">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
            Node Voltages
          </div>
          <div className="space-y-1">
            {simResult.node_results
              .sort((a, b) => a.net_name.localeCompare(b.net_name))
              .map((nr) => (
                <div key={nr.id} className="flex justify-between text-xs">
                  <span className="text-zinc-400 font-mono">{nr.net_name}</span>
                  <span className="text-emerald-300 font-mono">
                    {formatValue(nr.voltage, 'V')}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Component results */}
      {simResult?.status === 'complete' && simResult.component_results && (
        <div className="p-3 border-b border-zinc-700">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
            Component Results
          </div>
          <div className="space-y-2">
            {simResult.component_results
              .sort((a, b) => a.ref_designator.localeCompare(b.ref_designator))
              .map((cr) => (
                <div key={cr.id} className="text-xs">
                  <div className="font-mono text-zinc-300 font-medium">{cr.ref_designator}</div>
                  <div className="flex justify-between text-zinc-400 pl-2">
                    <span>I</span>
                    <span className="font-mono text-sky-300">{formatValue(cr.current, 'A')}</span>
                  </div>
                  <div className="flex justify-between text-zinc-400 pl-2">
                    <span>P</span>
                    <span className="font-mono text-amber-300">{formatValue(cr.power, 'W')}</span>
                  </div>
                  <div className="flex justify-between text-zinc-400 pl-2">
                    <span>V</span>
                    <span className="font-mono text-emerald-300">{formatValue(cr.voltage_drop, 'V')}</span>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Selected component details */}
      {selectedComponent && (
        <div className="p-3">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
            Selected
          </div>
          <div className="text-xs space-y-1">
            <div className="font-mono font-medium text-sky-300">
              {selectedComponent.ref_designator}
            </div>
            <div className="text-zinc-400">{selectedComponent.component_type}</div>
            {selectedComponent.value && (
              <div className="text-zinc-300">
                {selectedComponent.value} {selectedComponent.unit}
              </div>
            )}
            <div className="text-zinc-500">
              ({selectedComponent.x.toFixed(0)}, {selectedComponent.y.toFixed(0)})
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
