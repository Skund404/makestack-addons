/**
 * SVG schematic canvas — the main interactive drawing surface.
 *
 * Handles: pan (middle-click drag), zoom (scroll), component placement,
 * wire drawing (Manhattan routing), component selection, undo/redo.
 */
import { useCallback, useRef, useState, useEffect } from 'react'
import type { CircuitComponent, CircuitNet, SimResult, WireSegment, Junction } from '../api'
import { ComponentSymbol, getPinPosition, PIN_OFFSETS } from './ComponentSymbol'
import { WireLayer } from './WireLayer'
import { ResultOverlay } from './ResultOverlay'

interface SchematicCanvasProps {
  components: CircuitComponent[]
  nets: CircuitNet[]
  wireSegments: WireSegment[]
  junctions: Junction[]
  simResult: SimResult | null
  selectedComponentId: string | null
  placingType: string | null
  onSelectComponent: (id: string | null) => void
  onPlaceComponent: (type: string, x: number, y: number) => void
  onConnectPins: (componentId: string, pinName: string, targetComponentId: string, targetPinName: string) => void
  onMoveComponent: (id: string, x: number, y: number) => void
  onWireClick?: (wireId: string, x: number, y: number) => void
}

/** Snap value to grid */
const snap = (v: number) => Math.round(v / 20) * 20

export function SchematicCanvas({
  components, nets, wireSegments, junctions, simResult,
  selectedComponentId, placingType,
  onSelectComponent, onPlaceComponent, onConnectPins, onMoveComponent,
  onWireClick,
}: SchematicCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null)

  // Viewport state
  const [viewBox, setViewBox] = useState({ x: -100, y: -100, w: 1000, h: 600 })

  // Pan state
  const [isPanning, setIsPanning] = useState(false)
  const panStart = useRef({ x: 0, y: 0, vx: 0, vy: 0 })

  // Drag state
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const dragOffset = useRef({ dx: 0, dy: 0 })

  // Wire drawing state
  const [wireStart, setWireStart] = useState<{
    componentId: string; pinName: string; x: number; y: number
  } | null>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })

  // Manhattan routing toggle: horizontal-first vs vertical-first
  const [routeHorizontalFirst, setRouteHorizontalFirst] = useState(true)

  // Toggle route direction with Shift key while drawing
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Shift' && wireStart) {
        setRouteHorizontalFirst(prev => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [wireStart])

  /** Convert screen coordinates to SVG coordinates. */
  const screenToSvg = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current
    if (!svg) return { x: 0, y: 0 }
    const rect = svg.getBoundingClientRect()
    return {
      x: viewBox.x + (clientX - rect.left) / rect.width * viewBox.w,
      y: viewBox.y + (clientY - rect.top) / rect.height * viewBox.h,
    }
  }, [viewBox])

  // --- Event handlers ---

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const factor = e.deltaY > 0 ? 1.1 : 0.9
    const pt = screenToSvg(e.clientX, e.clientY)
    setViewBox((vb) => {
      const nw = vb.w * factor
      const nh = vb.h * factor
      return {
        x: pt.x - (pt.x - vb.x) * factor,
        y: pt.y - (pt.y - vb.y) * factor,
        w: nw,
        h: nh,
      }
    })
  }, [screenToSvg])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // Middle button or Alt+left for pan
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      e.preventDefault()
      setIsPanning(true)
      panStart.current = { x: e.clientX, y: e.clientY, vx: viewBox.x, vy: viewBox.y }
      return
    }

    if (e.button !== 0) return

    const pt = screenToSvg(e.clientX, e.clientY)

    // Placing mode — drop component at click location
    if (placingType) {
      const sx = snap(pt.x)
      const sy = snap(pt.y)
      onPlaceComponent(placingType, sx, sy)
      return
    }

    // Check if clicked on a pin (for wire drawing)
    for (const comp of components) {
      const pins = PIN_OFFSETS[comp.component_type]
      if (!pins) continue
      for (const [pinName] of Object.entries(pins)) {
        const pinPos = getPinPosition(comp.x, comp.y, comp.rotation, comp.component_type, pinName)
        const dx = pt.x - pinPos.x
        const dy = pt.y - pinPos.y
        if (dx * dx + dy * dy < 100) { // 10px radius
          if (wireStart) {
            // Complete wire
            if (wireStart.componentId !== comp.id || wireStart.pinName !== pinName) {
              onConnectPins(wireStart.componentId, wireStart.pinName, comp.id, pinName)
            }
            setWireStart(null)
            setRouteHorizontalFirst(true)
          } else {
            // Start wire
            setWireStart({ componentId: comp.id, pinName, x: pinPos.x, y: pinPos.y })
            setRouteHorizontalFirst(true)
          }
          return
        }
      }
    }

    // Check if clicked on a component (for selection/drag)
    for (const comp of components) {
      const dx = pt.x - comp.x
      const dy = pt.y - comp.y
      if (Math.abs(dx) < 50 && Math.abs(dy) < 25) {
        onSelectComponent(comp.id)
        setDraggingId(comp.id)
        dragOffset.current = { dx, dy }
        return
      }
    }

    // Clicked on empty space
    onSelectComponent(null)
    if (wireStart) {
      setWireStart(null)
      setRouteHorizontalFirst(true)
    }
  }, [placingType, components, wireStart, viewBox, screenToSvg, onPlaceComponent, onConnectPins, onSelectComponent])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const pt = screenToSvg(e.clientX, e.clientY)
    setMousePos(pt)

    if (isPanning) {
      const svg = svgRef.current
      if (!svg) return
      const rect = svg.getBoundingClientRect()
      const scaleX = viewBox.w / rect.width
      const scaleY = viewBox.h / rect.height
      setViewBox({
        ...viewBox,
        x: panStart.current.vx - (e.clientX - panStart.current.x) * scaleX,
        y: panStart.current.vy - (e.clientY - panStart.current.y) * scaleY,
      })
      return
    }

    if (draggingId) {
      onMoveComponent(draggingId, snap(pt.x - dragOffset.current.dx), snap(pt.y - dragOffset.current.dy))
    }
  }, [isPanning, draggingId, viewBox, screenToSvg, onMoveComponent])

  const handleMouseUp = useCallback(() => {
    setIsPanning(false)
    setDraggingId(null)
  }, [])

  // Build net positions for result overlay
  const netPositions = new Map<string, { x: number; y: number }[]>()
  for (const comp of components) {
    for (const pin of comp.pins) {
      if (!pin.net_id) continue
      const pos = getPinPosition(comp.x, comp.y, comp.rotation, comp.component_type, pin.pin_name)
      if (!netPositions.has(pin.net_id)) netPositions.set(pin.net_id, [])
      netPositions.get(pin.net_id)!.push(pos)
    }
  }

  // Build component result map for symbol overlays
  const compResults = new Map<string, { current: number; power: number; voltage_drop: number }>()
  if (simResult?.status === 'complete' && simResult.component_results) {
    for (const cr of simResult.component_results) {
      compResults.set(cr.component_id, { current: cr.current, power: cr.power, voltage_drop: cr.voltage_drop })
    }
  }

  // Compute Manhattan wire preview path
  const wirePreviewPoints = wireStart ? (() => {
    const snappedMouse = { x: snap(mousePos.x), y: snap(mousePos.y) }
    if (wireStart.x === snappedMouse.x || wireStart.y === snappedMouse.y) {
      // Straight line
      return [wireStart, snappedMouse]
    }
    // L-shaped path
    const mid = routeHorizontalFirst
      ? { x: snappedMouse.x, y: wireStart.y }
      : { x: wireStart.x, y: snappedMouse.y }
    return [wireStart, mid, snappedMouse]
  })() : null

  return (
    <svg
      ref={svgRef}
      viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
      className="flex-1 bg-zinc-950"
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      style={{ cursor: placingType ? 'crosshair' : wireStart ? 'crosshair' : isPanning ? 'grabbing' : 'default' }}
    >
      {/* Grid */}
      <defs>
        <pattern id="grid" width={20} height={20} patternUnits="userSpaceOnUse">
          <circle cx={10} cy={10} r={0.5} fill="#1e293b" />
        </pattern>
      </defs>
      <rect
        x={viewBox.x - 1000} y={viewBox.y - 1000}
        width={viewBox.w + 2000} height={viewBox.h + 2000}
        fill="url(#grid)"
      />

      {/* Wires */}
      <WireLayer
        components={components}
        nets={nets}
        wireSegments={wireSegments}
        junctions={junctions}
        onWireClick={onWireClick}
      />

      {/* Components */}
      {components.map((comp) => (
        <ComponentSymbol
          key={comp.id}
          type={comp.component_type}
          x={comp.x}
          y={comp.y}
          rotation={comp.rotation}
          refDesignator={comp.ref_designator}
          value={comp.value}
          unit={comp.unit}
          selected={comp.id === selectedComponentId}
          onClick={() => onSelectComponent(comp.id)}
          simResult={compResults.get(comp.id)}
        />
      ))}

      {/* Result overlay */}
      {simResult?.status === 'complete' && simResult.node_results && (
        <ResultOverlay
          nodeResults={simResult.node_results}
          netPositions={netPositions}
        />
      )}

      {/* Manhattan wire being drawn */}
      {wirePreviewPoints && wirePreviewPoints.length >= 2 && (
        <g>
          {wirePreviewPoints.slice(0, -1).map((pt, i) => {
            const next = wirePreviewPoints[i + 1]
            return (
              <line
                key={`preview-${i}`}
                x1={pt.x} y1={pt.y}
                x2={next.x} y2={next.y}
                stroke="#38bdf8"
                strokeWidth={1.5}
                strokeDasharray="4 2"
                pointerEvents="none"
              />
            )
          })}
          {/* Endpoint dot */}
          <circle
            cx={wirePreviewPoints[wirePreviewPoints.length - 1].x}
            cy={wirePreviewPoints[wirePreviewPoints.length - 1].y}
            r={3}
            fill="#38bdf8"
            pointerEvents="none"
          />
        </g>
      )}

      {/* Placement cursor */}
      {placingType && (
        <g opacity={0.4} pointerEvents="none">
          <circle cx={snap(mousePos.x)} cy={snap(mousePos.y)} r={8} fill="#38bdf8" />
        </g>
      )}

      {/* Route direction hint while drawing */}
      {wireStart && (
        <text
          x={viewBox.x + viewBox.w - 10}
          y={viewBox.y + 15}
          textAnchor="end"
          fill="#64748b"
          fontSize={9}
          fontFamily="monospace"
          pointerEvents="none"
        >
          Shift: flip route
        </text>
      )}
    </svg>
  )
}
