/**
 * SVG wire layer — renders wire segments and junction dots.
 *
 * E1b: Renders from stored wire segments when available.
 * Falls back to centroid star topology for legacy circuits (no stored segments).
 */
import type { CircuitComponent, CircuitNet, WireSegment, Junction } from '../api'
import { getPinPosition } from './ComponentSymbol'

interface WireLayerProps {
  components: CircuitComponent[]
  nets: CircuitNet[]
  wireSegments: WireSegment[]
  junctions: Junction[]
  highlightNetId?: string | null
  onWireClick?: (wireId: string, x: number, y: number) => void
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

/** Check if a point is near a line segment (for hit detection). */
export function pointToSegmentDistance(
  px: number, py: number,
  x1: number, y1: number, x2: number, y2: number,
): number {
  const dx = x2 - x1
  const dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  if (lenSq === 0) return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2)

  let t = ((px - x1) * dx + (py - y1) * dy) / lenSq
  t = Math.max(0, Math.min(1, t))

  const projX = x1 + t * dx
  const projY = y1 + t * dy
  return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2)
}

export function WireLayer({
  components, nets, wireSegments, junctions,
  highlightNetId, onWireClick,
}: WireLayerProps) {
  // Build net info map
  const netInfo = new Map<string, { name: string; type: string }>()
  for (const net of nets) {
    netInfo.set(net.id, { name: net.name, type: net.net_type })
  }

  const getColor = (netId: string, isHighlighted: boolean) => {
    if (isHighlighted) return '#38bdf8'
    const info = netInfo.get(netId)
    return info ? netColor(info.name, info.type) : '#64748b'
  }

  const elements: JSX.Element[] = []

  // Check if we have stored wire segments
  const hasStoredSegments = wireSegments.length > 0

  if (hasStoredSegments) {
    // === Segment-based rendering (E1b) ===

    // Render wire segments
    for (const seg of wireSegments) {
      const isHighlighted = seg.net_id === highlightNetId
      const color = getColor(seg.net_id, isHighlighted)

      elements.push(
        <line
          key={`ws-${seg.id}`}
          x1={seg.x1} y1={seg.y1}
          x2={seg.x2} y2={seg.y2}
          stroke={color}
          strokeWidth={isHighlighted ? 2.5 : 1.5}
          strokeLinecap="round"
          className={onWireClick ? 'cursor-pointer' : undefined}
          onClick={onWireClick ? (e) => {
            e.stopPropagation()
            // Compute click point on the segment
            const svg = (e.target as SVGElement).ownerSVGElement
            if (!svg) return
            const pt = svg.createSVGPoint()
            pt.x = e.clientX
            pt.y = e.clientY
            const svgPt = pt.matrixTransform(svg.getScreenCTM()?.inverse())
            onWireClick(seg.id, svgPt.x, svgPt.y)
          } : undefined}
        />
      )

      // Invisible wider hit area for easier clicking
      if (onWireClick) {
        elements.push(
          <line
            key={`ws-hit-${seg.id}`}
            x1={seg.x1} y1={seg.y1}
            x2={seg.x2} y2={seg.y2}
            stroke="transparent"
            strokeWidth={10}
            onClick={(e) => {
              e.stopPropagation()
              const svg = (e.target as SVGElement).ownerSVGElement
              if (!svg) return
              const pt = svg.createSVGPoint()
              pt.x = e.clientX
              pt.y = e.clientY
              const svgPt = pt.matrixTransform(svg.getScreenCTM()?.inverse())
              onWireClick(seg.id, svgPt.x, svgPt.y)
            }}
          />
        )
      }
    }

    // Render junction dots
    for (const junc of junctions) {
      const isHighlighted = junc.net_id === highlightNetId
      const color = getColor(junc.net_id, isHighlighted)

      elements.push(
        <circle
          key={`junc-${junc.id}`}
          cx={junc.x} cy={junc.y} r={3.5}
          fill={color}
        />
      )
    }

    // Also render pin-to-nearest-segment connections for any nets
    // that have both stored segments AND pins (so pins connect visually)
    // This is handled by the segments already touching pin positions.

  } else {
    // === Legacy fallback: centroid star topology ===

    const netPins = new Map<string, { x: number; y: number }[]>()

    for (const comp of components) {
      for (const pin of comp.pins) {
        if (!pin.net_id) continue
        const pos = getPinPosition(comp.x, comp.y, comp.rotation, comp.component_type, pin.pin_name)
        if (!netPins.has(pin.net_id)) netPins.set(pin.net_id, [])
        netPins.get(pin.net_id)!.push(pos)
      }
    }

    for (const [netId, positions] of netPins) {
      if (positions.length < 2) continue
      const isHighlighted = netId === highlightNetId
      const color = getColor(netId, isHighlighted)

      // Star topology: connect all pins to centroid
      const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length
      const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length

      for (let i = 0; i < positions.length; i++) {
        const p = positions[i]
        elements.push(
          <line
            key={`${netId}-${i}`}
            x1={p.x} y1={p.y}
            x2={cx} y2={cy}
            stroke={color}
            strokeWidth={isHighlighted ? 2.5 : 1.5}
            strokeLinecap="round"
          />
        )
      }

      // Junction dot at centroid when 3+ pins
      if (positions.length > 2) {
        elements.push(
          <circle
            key={`${netId}-junction`}
            cx={cx} cy={cy} r={3}
            fill={color}
          />
        )
      }
    }
  }

  return <g className="wire-layer">{elements}</g>
}
