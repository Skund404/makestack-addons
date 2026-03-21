/**
 * Result overlay — voltage labels on nets, shown after simulation.
 */
import type { NodeResult } from '../api'

interface ResultOverlayProps {
  nodeResults: NodeResult[]
  /** Map of net_id -> array of pin positions (computed in editor) */
  netPositions: Map<string, { x: number; y: number }[]>
}

function formatVoltage(v: number): string {
  if (Math.abs(v) < 0.001) return '0V'
  if (Math.abs(v) < 1) return `${(v * 1000).toFixed(1)}mV`
  return `${v.toFixed(2)}V`
}

export function ResultOverlay({ nodeResults, netPositions }: ResultOverlayProps) {
  return (
    <g className="result-overlay">
      {nodeResults.map((nr) => {
        // Position the label at the centroid of pin positions for this net
        const positions = netPositions.get(nr.net_id)
        if (!positions || positions.length === 0) return null

        const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length
        const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length

        return (
          <g key={nr.id}>
            <rect
              x={cx + 8} y={cy - 12}
              width={50} height={16}
              rx={3}
              fill="#0f172a"
              fillOpacity={0.85}
              stroke="#22c55e"
              strokeWidth={0.5}
            />
            <text
              x={cx + 33} y={cy}
              textAnchor="middle"
              fill="#22c55e"
              fontSize={9}
              fontFamily="monospace"
            >
              {formatVoltage(nr.voltage)}
            </text>
          </g>
        )
      })}
    </g>
  )
}
