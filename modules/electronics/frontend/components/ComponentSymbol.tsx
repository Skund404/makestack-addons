/**
 * SVG schematic symbols for electronic components.
 *
 * Each symbol is rendered at the component's (x, y) with rotation applied.
 * Pin positions are computed from the symbol geometry and returned via PIN_OFFSETS.
 */

// Pin offset positions relative to component origin (before rotation).
// Each pin is { dx, dy } from the component's (x, y).
export const PIN_OFFSETS: Record<string, Record<string, { dx: number; dy: number }>> = {
  resistor:       { p: { dx: -40, dy: 0 }, n: { dx: 40, dy: 0 } },
  capacitor:      { p: { dx: -40, dy: 0 }, n: { dx: 40, dy: 0 } },
  inductor:       { p: { dx: -40, dy: 0 }, n: { dx: 40, dy: 0 } },
  voltage_source: { p: { dx: 0, dy: -30 }, n: { dx: 0, dy: 30 } },
  current_source: { p: { dx: 0, dy: -30 }, n: { dx: 0, dy: 30 } },
  ground:         { gnd: { dx: 0, dy: 0 } },
  diode:          { anode: { dx: -40, dy: 0 }, cathode: { dx: 40, dy: 0 } },
  zener:          { anode: { dx: -40, dy: 0 }, cathode: { dx: 40, dy: 0 } },
  led:            { anode: { dx: -40, dy: 0 }, cathode: { dx: 40, dy: 0 } },
  npn_bjt:        { base: { dx: -30, dy: 0 }, collector: { dx: 30, dy: -20 }, emitter: { dx: 30, dy: 20 } },
  pnp_bjt:        { base: { dx: -30, dy: 0 }, collector: { dx: 30, dy: 20 }, emitter: { dx: 30, dy: -20 } },
  nmos:           { gate: { dx: -30, dy: 0 }, drain: { dx: 30, dy: -20 }, source: { dx: 30, dy: 20 } },
  pmos:           { gate: { dx: -30, dy: 0 }, drain: { dx: 30, dy: 20 }, source: { dx: 30, dy: -20 } },
  opamp:          { non_inv: { dx: -35, dy: -15 }, inv: { dx: -35, dy: 15 }, output: { dx: 40, dy: 0 } },
  mcu:            {
    GPIO0: { dx: -45, dy: -28 }, GPIO1: { dx: -45, dy: -20 }, GPIO2: { dx: -45, dy: -12 }, GPIO3: { dx: -45, dy: -4 },
    GPIO4: { dx: -45, dy: 4 },   GPIO5: { dx: -45, dy: 12 },  GPIO6: { dx: -45, dy: 20 },  GPIO7: { dx: -45, dy: 28 },
  },
}

/** Compute pin position after rotation. */
export function getPinPosition(
  x: number, y: number, rotation: number, componentType: string, pinName: string
): { x: number; y: number } {
  const offsets = PIN_OFFSETS[componentType]?.[pinName]
  if (!offsets) return { x, y }

  const rad = (rotation * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  return {
    x: x + offsets.dx * cos - offsets.dy * sin,
    y: y + offsets.dx * sin + offsets.dy * cos,
  }
}

interface SymbolProps {
  type: string
  x: number
  y: number
  rotation: number
  refDesignator: string
  value: string
  unit: string
  selected: boolean
  onClick: () => void
  simResult?: { current?: number; power?: number; voltage_drop?: number; operating_region?: string }
}

export function ComponentSymbol({
  type, x, y, rotation, refDesignator, value, unit,
  selected, onClick, simResult,
}: SymbolProps) {
  const formatValue = () => {
    if (!value) return ''
    const v = parseFloat(value)
    if (isNaN(v)) return value
    if (unit === 'ohm') {
      if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M\u03A9`
      if (v >= 1e3) return `${(v / 1e3).toFixed(1)}k\u03A9`
      return `${v}\u03A9`
    }
    if (unit === 'F') {
      if (v >= 1e-3) return `${(v * 1e3).toFixed(1)}mF`
      if (v >= 1e-6) return `${(v * 1e6).toFixed(1)}\u00B5F`
      if (v >= 1e-9) return `${(v * 1e9).toFixed(1)}nF`
      if (v >= 1e-12) return `${(v * 1e12).toFixed(1)}pF`
      return `${v}F`
    }
    if (unit === 'H') {
      if (v >= 1) return `${v}H`
      if (v >= 1e-3) return `${(v * 1e3).toFixed(1)}mH`
      if (v >= 1e-6) return `${(v * 1e6).toFixed(1)}\u00B5H`
      if (v >= 1e-9) return `${(v * 1e9).toFixed(1)}nH`
      return `${v}H`
    }
    if (unit === 'V') return `${v}V`
    if (unit === 'A') {
      if (v < 0.001) return `${(v * 1e6).toFixed(0)}\u00B5A`
      if (v < 1) return `${(v * 1e3).toFixed(1)}mA`
      return `${v}A`
    }
    return `${value}${unit}`
  }

  return (
    <g
      transform={`translate(${x}, ${y})`}
      onClick={(e) => { e.stopPropagation(); onClick() }}
      className="cursor-pointer"
    >
      <g transform={`rotate(${rotation})`}>
        {/* Hit area */}
        <rect
          x={-45} y={-20} width={90} height={40}
          fill="transparent" stroke="none"
        />

        {/* Component body */}
        {type === 'resistor' && <ResistorBody selected={selected} />}
        {type === 'capacitor' && <CapacitorBody selected={selected} />}
        {type === 'inductor' && <InductorBody selected={selected} />}
        {type === 'voltage_source' && <VoltageSourceBody selected={selected} />}
        {type === 'current_source' && <CurrentSourceBody selected={selected} />}
        {type === 'ground' && <GroundBody selected={selected} />}
        {type === 'diode' && <DiodeBody selected={selected} />}
        {type === 'zener' && <ZenerBody selected={selected} />}
        {type === 'led' && <LEDBody selected={selected} />}
        {type === 'npn_bjt' && <NPNBody selected={selected} />}
        {type === 'pnp_bjt' && <PNPBody selected={selected} />}
        {type === 'nmos' && <NMOSBody selected={selected} />}
        {type === 'pmos' && <PMOSBody selected={selected} />}
        {type === 'opamp' && <OpAmpBody selected={selected} />}
        {type === 'mcu' && <MCUBody selected={selected} />}

        {/* Pin dots */}
        {Object.entries(PIN_OFFSETS[type] || {}).map(([pin, offset]) => (
          <circle
            key={pin}
            cx={offset.dx} cy={offset.dy}
            r={3}
            fill={selected ? '#38bdf8' : '#64748b'}
            stroke="none"
          />
        ))}
      </g>

      {/* Labels (not rotated) */}
      <text
        x={0} y={-25}
        textAnchor="middle"
        fill={selected ? '#38bdf8' : '#94a3b8'}
        fontSize={10}
        fontFamily="monospace"
      >
        {refDesignator}
      </text>
      {type !== 'ground' && (
        <text
          x={0} y={35}
          textAnchor="middle"
          fill="#64748b"
          fontSize={9}
          fontFamily="monospace"
        >
          {formatValue()}
        </text>
      )}

      {/* Sim result */}
      {simResult && type !== 'ground' && (
        <text
          x={50} y={5}
          fill="#22c55e"
          fontSize={8}
          fontFamily="monospace"
        >
          {simResult.current !== undefined
            ? `${(simResult.current * 1000).toFixed(2)}mA`
            : ''}
        </text>
      )}

      {/* Operating region badge for transistors/diodes */}
      {simResult?.operating_region && (
        <text
          x={50} y={15}
          fill={
            simResult.operating_region === 'active' || simResult.operating_region === 'saturation_mosfet'
              ? '#22c55e'
              : simResult.operating_region === 'saturation'
              ? '#eab308'
              : '#ef4444'
          }
          fontSize={7}
          fontFamily="monospace"
        >
          {simResult.operating_region}
        </text>
      )}

      {/* Selection ring */}
      {selected && (
        <rect
          x={-48} y={-22} width={96} height={44}
          rx={4}
          fill="none"
          stroke="#38bdf8"
          strokeWidth={1}
          strokeDasharray="4 2"
        />
      )}
    </g>
  )
}

// --- Individual symbol bodies ---

function ResistorBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Leads */}
      <line x1={-40} y1={0} x2={-25} y2={0} stroke={color} strokeWidth={1.5} />
      <line x1={25} y1={0} x2={40} y2={0} stroke={color} strokeWidth={1.5} />
      {/* Zigzag */}
      <polyline
        points="-25,0 -20,-8 -12,8 -4,-8 4,8 12,-8 20,8 25,0"
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
    </>
  )
}

function VoltageSourceBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Leads */}
      <line x1={0} y1={-30} x2={0} y2={-18} stroke={color} strokeWidth={1.5} />
      <line x1={0} y1={18} x2={0} y2={30} stroke={color} strokeWidth={1.5} />
      {/* Circle */}
      <circle cx={0} cy={0} r={18} fill="none" stroke={color} strokeWidth={1.5} />
      {/* + / - */}
      <text x={0} y={-5} textAnchor="middle" fill={color} fontSize={12} fontWeight="bold">+</text>
      <text x={0} y={12} textAnchor="middle" fill={color} fontSize={14} fontWeight="bold">&minus;</text>
    </>
  )
}

function CurrentSourceBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Leads */}
      <line x1={0} y1={-30} x2={0} y2={-18} stroke={color} strokeWidth={1.5} />
      <line x1={0} y1={18} x2={0} y2={30} stroke={color} strokeWidth={1.5} />
      {/* Circle */}
      <circle cx={0} cy={0} r={18} fill="none" stroke={color} strokeWidth={1.5} />
      {/* Arrow */}
      <line x1={0} y1={10} x2={0} y2={-10} stroke={color} strokeWidth={1.5} />
      <polyline points="-4,-6 0,-10 4,-6" fill="none" stroke={color} strokeWidth={1.5} />
    </>
  )
}

function CapacitorBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Leads */}
      <line x1={-40} y1={0} x2={-5} y2={0} stroke={color} strokeWidth={1.5} />
      <line x1={5} y1={0} x2={40} y2={0} stroke={color} strokeWidth={1.5} />
      {/* Plates */}
      <line x1={-5} y1={-12} x2={-5} y2={12} stroke={color} strokeWidth={2} />
      <line x1={5} y1={-12} x2={5} y2={12} stroke={color} strokeWidth={2} />
    </>
  )
}

function InductorBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Leads */}
      <line x1={-40} y1={0} x2={-24} y2={0} stroke={color} strokeWidth={1.5} />
      <line x1={24} y1={0} x2={40} y2={0} stroke={color} strokeWidth={1.5} />
      {/* Coil arcs */}
      <path
        d="M-24,0 C-24,-10 -16,-10 -16,0 C-16,-10 -8,-10 -8,0 C-8,-10 0,-10 0,0 C0,-10 8,-10 8,0 C8,-10 16,-10 16,0 C16,-10 24,-10 24,0"
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
      />
    </>
  )
}

function GroundBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      <line x1={0} y1={0} x2={0} y2={8} stroke={color} strokeWidth={1.5} />
      <line x1={-12} y1={8} x2={12} y2={8} stroke={color} strokeWidth={2} />
      <line x1={-8} y1={13} x2={8} y2={13} stroke={color} strokeWidth={1.5} />
      <line x1={-4} y1={18} x2={4} y2={18} stroke={color} strokeWidth={1} />
    </>
  )
}

function DiodeBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      <line x1={-40} y1={0} x2={-10} y2={0} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={0} x2={40} y2={0} stroke={color} strokeWidth={1.5} />
      {/* Triangle */}
      <polygon points="-10,-10 -10,10 10,0" fill="none" stroke={color} strokeWidth={1.5} />
      {/* Bar */}
      <line x1={10} y1={-10} x2={10} y2={10} stroke={color} strokeWidth={2} />
    </>
  )
}

function ZenerBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      <line x1={-40} y1={0} x2={-10} y2={0} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={0} x2={40} y2={0} stroke={color} strokeWidth={1.5} />
      <polygon points="-10,-10 -10,10 10,0" fill="none" stroke={color} strokeWidth={1.5} />
      {/* Bent bar */}
      <polyline points="6,-10 10,-10 10,10 14,10" fill="none" stroke={color} strokeWidth={2} />
    </>
  )
}

function LEDBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      <line x1={-40} y1={0} x2={-10} y2={0} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={0} x2={40} y2={0} stroke={color} strokeWidth={1.5} />
      <polygon points="-10,-10 -10,10 10,0" fill="none" stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={-10} x2={10} y2={10} stroke={color} strokeWidth={2} />
      {/* Light arrows */}
      <line x1={2} y1={-14} x2={8} y2={-20} stroke={color} strokeWidth={1} />
      <polyline points="5,-20 8,-20 8,-17" fill="none" stroke={color} strokeWidth={0.8} />
      <line x1={6} y1={-11} x2={12} y2={-17} stroke={color} strokeWidth={1} />
      <polyline points="9,-17 12,-17 12,-14" fill="none" stroke={color} strokeWidth={0.8} />
    </>
  )
}

function NPNBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Base lead */}
      <line x1={-30} y1={0} x2={-8} y2={0} stroke={color} strokeWidth={1.5} />
      {/* Collector lead */}
      <line x1={8} y1={-12} x2={30} y2={-20} stroke={color} strokeWidth={1.5} />
      {/* Emitter lead */}
      <line x1={8} y1={12} x2={30} y2={20} stroke={color} strokeWidth={1.5} />
      {/* Circle */}
      <circle cx={0} cy={0} r={18} fill="none" stroke={color} strokeWidth={1.5} />
      {/* Base vertical bar */}
      <line x1={-8} y1={-12} x2={-8} y2={12} stroke={color} strokeWidth={2} />
      {/* Collector line */}
      <line x1={-8} y1={-6} x2={8} y2={-12} stroke={color} strokeWidth={1.5} />
      {/* Emitter line + arrow */}
      <line x1={-8} y1={6} x2={8} y2={12} stroke={color} strokeWidth={1.5} />
      <polygon points="8,12 3,7 1,12" fill={color} stroke="none" />
    </>
  )
}

function PNPBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      <line x1={-30} y1={0} x2={-8} y2={0} stroke={color} strokeWidth={1.5} />
      <line x1={8} y1={12} x2={30} y2={20} stroke={color} strokeWidth={1.5} />
      <line x1={8} y1={-12} x2={30} y2={-20} stroke={color} strokeWidth={1.5} />
      <circle cx={0} cy={0} r={18} fill="none" stroke={color} strokeWidth={1.5} />
      <line x1={-8} y1={-12} x2={-8} y2={12} stroke={color} strokeWidth={2} />
      <line x1={-8} y1={-6} x2={8} y2={-12} stroke={color} strokeWidth={1.5} />
      <line x1={-8} y1={6} x2={8} y2={12} stroke={color} strokeWidth={1.5} />
      {/* Arrow points toward base (PNP) */}
      <polygon points="-8,6 -3,11 -1,6" fill={color} stroke="none" />
    </>
  )
}

function NMOSBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Gate lead */}
      <line x1={-30} y1={0} x2={-12} y2={0} stroke={color} strokeWidth={1.5} />
      {/* Gate bar */}
      <line x1={-12} y1={-14} x2={-12} y2={14} stroke={color} strokeWidth={2} />
      {/* Channel */}
      <line x1={-8} y1={-14} x2={-8} y2={-6} stroke={color} strokeWidth={1.5} />
      <line x1={-8} y1={-2} x2={-8} y2={6} stroke={color} strokeWidth={1.5} />
      <line x1={-8} y1={10} x2={-8} y2={14} stroke={color} strokeWidth={1.5} />
      {/* Drain */}
      <line x1={-8} y1={-10} x2={10} y2={-10} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={-10} x2={10} y2={-20} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={-20} x2={30} y2={-20} stroke={color} strokeWidth={1.5} />
      {/* Source */}
      <line x1={-8} y1={12} x2={10} y2={12} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={12} x2={10} y2={20} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={20} x2={30} y2={20} stroke={color} strokeWidth={1.5} />
      {/* Body connection */}
      <line x1={-8} y1={2} x2={10} y2={2} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={2} x2={10} y2={12} stroke={color} strokeWidth={1.5} />
      {/* Arrow on source (NMOS: pointing in) */}
      <polygon points="-4,2 -8,5 -8,-1" fill={color} stroke="none" />
    </>
  )
}

function PMOSBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      <line x1={-30} y1={0} x2={-15} y2={0} stroke={color} strokeWidth={1.5} />
      {/* Bubble (inversion) */}
      <circle cx={-13} cy={0} r={2.5} fill="none" stroke={color} strokeWidth={1} />
      {/* Gate bar */}
      <line x1={-10} y1={-14} x2={-10} y2={14} stroke={color} strokeWidth={2} />
      {/* Channel */}
      <line x1={-6} y1={-14} x2={-6} y2={-6} stroke={color} strokeWidth={1.5} />
      <line x1={-6} y1={-2} x2={-6} y2={6} stroke={color} strokeWidth={1.5} />
      <line x1={-6} y1={10} x2={-6} y2={14} stroke={color} strokeWidth={1.5} />
      {/* Drain (bottom for PMOS) */}
      <line x1={-6} y1={12} x2={10} y2={12} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={12} x2={10} y2={20} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={20} x2={30} y2={20} stroke={color} strokeWidth={1.5} />
      {/* Source (top for PMOS) */}
      <line x1={-6} y1={-10} x2={10} y2={-10} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={-10} x2={10} y2={-20} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={-20} x2={30} y2={-20} stroke={color} strokeWidth={1.5} />
      {/* Body */}
      <line x1={-6} y1={2} x2={10} y2={2} stroke={color} strokeWidth={1.5} />
      <line x1={10} y1={2} x2={10} y2={-10} stroke={color} strokeWidth={1.5} />
      {/* Arrow on source (PMOS: pointing out) */}
      <polygon points="-2,2 -6,5 -6,-1" fill={color} stroke="none" />
    </>
  )
}

function OpAmpBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Input leads */}
      <line x1={-35} y1={-15} x2={-20} y2={-15} stroke={color} strokeWidth={1.5} />
      <line x1={-35} y1={15} x2={-20} y2={15} stroke={color} strokeWidth={1.5} />
      {/* Output lead */}
      <line x1={25} y1={0} x2={40} y2={0} stroke={color} strokeWidth={1.5} />
      {/* Triangle body */}
      <polygon points="-20,-25 -20,25 25,0" fill="none" stroke={color} strokeWidth={1.5} />
      {/* + / - labels */}
      <text x={-16} y={-11} fill={color} fontSize={10} fontWeight="bold">+</text>
      <text x={-16} y={20} fill={color} fontSize={12} fontWeight="bold">&minus;</text>
    </>
  )
}

function MCUBody({ selected }: { selected: boolean }) {
  const color = selected ? '#38bdf8' : '#e2e8f0'
  return (
    <>
      {/* Main body rectangle */}
      <rect x={-35} y={-35} width={70} height={70} rx={3} fill="none" stroke={color} strokeWidth={1.5} />
      {/* MCU label */}
      <text x={0} y={-22} textAnchor="middle" fill={color} fontSize={8} fontFamily="monospace" fontWeight="bold">MCU</text>
      {/* Pin leads and labels */}
      {[0,1,2,3,4,5,6,7].map((i) => {
        const py = -28 + i * 8
        return (
          <g key={i}>
            <line x1={-45} y1={py} x2={-35} y2={py} stroke={color} strokeWidth={1} />
            <text x={-32} y={py + 3} fill={color} fontSize={6} fontFamily="monospace">{i}</text>
          </g>
        )
      })}
    </>
  )
}
