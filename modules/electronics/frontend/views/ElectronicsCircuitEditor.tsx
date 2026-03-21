/**
 * Circuit editor — the main schematic editing view.
 *
 * Orchestrates: ComponentPalette + SchematicCanvas + SimulationPanel.
 * All state flows through this component; child components are presentational.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useCallback } from 'react'
import { electronicsApi } from '../api'
import type { Circuit, SimResult } from '../api'
import { ComponentPalette } from '../components/ComponentPalette'
import { SchematicCanvas } from '../components/SchematicCanvas'
import { SimulationPanel } from '../components/SimulationPanel'
import { RotateCw, Trash2 } from 'lucide-react'

interface EditorProps {
  params: { id: string }
}

export function ElectronicsCircuitEditor({ params }: EditorProps) {
  const circuitId = params.id
  const queryClient = useQueryClient()

  const [placingType, setPlacingType] = useState<string | null>(null)
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null)
  const [simResult, setSimResult] = useState<SimResult | null>(null)
  const [isSimulating, setIsSimulating] = useState(false)

  // Fetch circuit
  const { data: circuit } = useQuery({
    queryKey: ['electronics-circuit', circuitId],
    queryFn: () => electronicsApi.getCircuit(circuitId),
  })

  // Fetch latest sim result on load
  useQuery({
    queryKey: ['electronics-results', circuitId],
    queryFn: () => electronicsApi.getResults(circuitId),
    enabled: !!circuit,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onSuccess: (data: any) => {
      if (data?.status === 'complete' || data?.status === 'error') {
        setSimResult(data)
      }
    },
  } as Record<string, unknown>)

  const refetch = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['electronics-circuit', circuitId] })
  }, [queryClient, circuitId])

  // --- Mutations ---

  const addComponentMut = useMutation({
    mutationFn: (vars: { type: string; x: number; y: number }) =>
      electronicsApi.addComponent(circuitId, {
        component_type: vars.type,
        x: vars.x,
        y: vars.y,
      }),
    onSuccess: () => refetch(),
  })

  const moveComponentMut = useMutation({
    mutationFn: (vars: { id: string; x: number; y: number }) =>
      electronicsApi.updateComponent(vars.id, { x: vars.x, y: vars.y }),
    onSuccess: () => refetch(),
  })

  const deleteComponentMut = useMutation({
    mutationFn: electronicsApi.deleteComponent,
    onSuccess: () => {
      setSelectedComponentId(null)
      refetch()
    },
  })

  const rotateComponentMut = useMutation({
    mutationFn: (id: string) => {
      const comp = circuit?.components.find((c) => c.id === id)
      if (!comp) return Promise.resolve(null)
      const newRotation = (comp.rotation + 90) % 360
      return electronicsApi.updateComponent(id, { rotation: newRotation })
    },
    onSuccess: () => refetch(),
  })

  // --- Handlers ---

  const handlePlaceComponent = useCallback((type: string, x: number, y: number) => {
    addComponentMut.mutate({ type, x, y })
    // Stay in placement mode for quick multi-place
  }, [addComponentMut])

  const handleConnectPins = useCallback(async (
    compId1: string, pinName1: string,
    compId2: string, pinName2: string,
  ) => {
    // Find existing net on either pin, or generate a new net name
    const comp1 = circuit?.components.find((c) => c.id === compId1)
    const comp2 = circuit?.components.find((c) => c.id === compId2)
    const pin1 = comp1?.pins.find((p) => p.pin_name === pinName1)
    const pin2 = comp2?.pins.find((p) => p.pin_name === pinName2)

    let netName: string
    if (pin1?.net_name) {
      netName = pin1.net_name
    } else if (pin2?.net_name) {
      netName = pin2.net_name
    } else {
      // Generate net name
      const existingNames = new Set(circuit?.nets.map((n) => n.name) || [])
      let i = 1
      while (existingNames.has(`N${String(i).padStart(3, '0')}`)) i++
      netName = `N${String(i).padStart(3, '0')}`
    }

    // Connect both pins to the same net
    await electronicsApi.connectPins(circuitId, {
      component_id: compId1,
      pin_name: pinName1,
      net_name: netName,
    })
    await electronicsApi.connectPins(circuitId, {
      component_id: compId2,
      pin_name: pinName2,
      net_name: netName,
    })

    refetch()
  }, [circuit, circuitId, refetch])

  const handleMoveComponent = useCallback((id: string, x: number, y: number) => {
    // Update local state immediately for smooth dragging
    // (mutation fires on mouse-up via the SchematicCanvas)
    moveComponentMut.mutate({ id, x, y })
  }, [moveComponentMut])

  const handleSimulate = useCallback(async () => {
    setIsSimulating(true)
    try {
      const result = await electronicsApi.simulate(circuitId)
      setSimResult(result)
    } catch {
      // Error is shown in the panel
    } finally {
      setIsSimulating(false)
    }
  }, [circuitId])

  const selectedComponent = circuit?.components.find((c) => c.id === selectedComponentId) || null

  if (!circuit) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-400 text-sm">
        Loading circuit...
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-700 bg-zinc-900/80 shrink-0">
        <h2 className="text-sm font-medium truncate flex-1">{circuit.name}</h2>

        {selectedComponentId && (
          <>
            <button
              onClick={() => rotateComponentMut.mutate(selectedComponentId)}
              className="p-1.5 rounded text-zinc-400 hover:text-sky-400 hover:bg-zinc-800"
              title="Rotate 90deg"
            >
              <RotateCw size={14} />
            </button>
            <button
              onClick={() => deleteComponentMut.mutate(selectedComponentId)}
              className="p-1.5 rounded text-zinc-400 hover:text-red-400 hover:bg-zinc-800"
              title="Delete component"
            >
              <Trash2 size={14} />
            </button>
          </>
        )}

        <span className="text-[10px] text-zinc-500">
          {circuit.components.length} components | {circuit.nets.length} nets
        </span>
      </div>

      {/* Main area */}
      <div className="flex flex-1 min-h-0">
        <ComponentPalette activeType={placingType} onSelect={setPlacingType} />

        <SchematicCanvas
          components={circuit.components}
          nets={circuit.nets}
          simResult={simResult}
          selectedComponentId={selectedComponentId}
          placingType={placingType}
          onSelectComponent={setSelectedComponentId}
          onPlaceComponent={handlePlaceComponent}
          onConnectPins={handleConnectPins}
          onMoveComponent={handleMoveComponent}
        />

        <SimulationPanel
          simResult={simResult}
          isSimulating={isSimulating}
          onSimulate={handleSimulate}
          selectedComponent={selectedComponent}
        />
      </div>
    </div>
  )
}
