/**
 * SVG wire layer — draws connections between pins on the same net.
 *
 * Wires are computed from pin positions, NOT stored in DB.
 * For E1: straight lines between pins. Manhattan routing deferred to E2.
 */
import type { CircuitComponent, CircuitNet } from '../api'
import { getPinPosition } from './ComponentSymbol'

interface WireLayerProps {
  components: CircuitComponent[]
  nets: CircuitNet[]
  highlightNetId?: string | null
}

/** Net color palette — deterministic based on net name. */
function netColor(name: string, type: string): string {
  if (type === 'ground') return '#64748b'
  if (type === 'power') return '#ef4444'
  // Hash the name for consistent coloring
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const hue = Math.abs(hash) % 360
  return `hsl(${hue}, 60%, 55%)`
}

export function WireLayer({ components, nets, highlightNetId }: WireLayerProps) {
  // Build map: net_id -> list of pin positions
  const netPins: Map<string, { x: number; y: number }[]> = new Map()
  const netInfo: Map<string, { name: string; type: string }> = new Map()

  for (const net of nets) {
    netInfo.set(net.id, { name: net.name, type: net.net_type })
  }

  for (const comp of components) {
    for (const pin of comp.pins) {
      if (!pin.net_id) continue
      const pos = getPinPosition(comp.x, comp.y, comp.rotation, comp.component_type, pin.pin_name)
      if (!netPins.has(pin.net_id)) netPins.set(pin.net_id, [])
      netPins.get(pin.net_id)!.push(pos)
    }
  }

  const wires: JSX.Element[] = []

  for (const [netId, positions] of netPins) {
    if (positions.length < 2) continue
    const info = netInfo.get(netId)
    const color = info ? netColor(info.name, info.type) : '#64748b'
    const isHighlighted = netId === highlightNetId

    // Star topology: connect all pins to centroid
    const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length
    const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length

    for (let i = 0; i < positions.length; i++) {
      const p = positions[i]
      wires.push(
        <line
          key={`${netId}-${i}`}
          x1={p.x} y1={p.y}
          x2={cx} y2={cy}
          stroke={isHighlighted ? '#38bdf8' : color}
          strokeWidth={isHighlighted ? 2.5 : 1.5}
          strokeLinecap="round"
        />
      )
    }

    // Junction dot at centroid
    if (positions.length > 2) {
      wires.push(
        <circle
          key={`${netId}-junction`}
          cx={cx} cy={cy} r={3}
          fill={isHighlighted ? '#38bdf8' : color}
        />
      )
    }
  }

  return <g className="wire-layer">{wires}</g>
}
