/**
 * Electronics module API client — typed wrappers around the shell's API helpers.
 */
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CircuitListItem {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface CircuitPin {
  id: string
  pin_name: string
  net_id: string | null
  net_name: string | null
}

export interface CircuitComponent {
  id: string
  circuit_id: string
  catalogue_path: string | null
  ref_designator: string
  component_type: string
  value: string
  unit: string
  x: number
  y: number
  rotation: number
  properties: string
  created_at: string
  pins: CircuitPin[]
}

export interface CircuitNet {
  id: string
  circuit_id: string
  name: string
  net_type: string
  color: string
}

export interface SimResultSummary {
  id: string
  sim_type: string
  status: string
  error_message: string | null
  ran_at: string
  duration_ms: number
}

export interface NodeResult {
  id: string
  sim_result_id: string
  net_id: string
  net_name: string
  net_type: string
  voltage: number
}

export interface ComponentResult {
  id: string
  sim_result_id: string
  component_id: string
  ref_designator: string
  component_type: string
  value: string
  unit: string
  current: number
  power: number
  voltage_drop: number
}

export interface SweepNodeVoltage {
  real: number
  imag: number
  magnitude: number
  phase_deg: number
}

export interface SweepDataPoint {
  point_index: number
  parameter_value: number
  node_voltages: Record<string, number | SweepNodeVoltage>
  component_results: Record<string, { current: number; power: number }>
}

export interface SimResult {
  id: string
  circuit_id: string
  sim_type: string
  status: string
  error_message: string | null
  result_data: Record<string, unknown>
  ran_at: string
  duration_ms: number
  node_results: NodeResult[]
  component_results: ComponentResult[]
  sweep_data?: SweepDataPoint[]
}

export interface WireSegment {
  id: string
  circuit_id: string
  net_id: string
  x1: number
  y1: number
  x2: number
  y2: number
  sort_order: number
}

export interface Junction {
  id: string
  circuit_id: string
  net_id: string
  x: number
  y: number
}

export interface DrcWarning {
  type: string
  severity: string
  message: string
  component_ids: string[]
  net_ids: string[]
}

export interface Region {
  id: string
  circuit_id: string
  name: string
  color: string
  description: string
  created_by: string
  members: RegionMember[]
}

export interface RegionMember {
  id: string
  region_id: string
  member_type: string
  member_id: string
}

export interface Circuit {
  id: string
  name: string
  description: string
  canvas_width: number
  canvas_height: number
  sim_settings: string
  created_at: string
  updated_at: string
  components: CircuitComponent[]
  nets: CircuitNet[]
  wire_segments: WireSegment[]
  junctions: Junction[]
  last_sim_result: SimResultSummary | null
}

export interface ComponentTypeInfo {
  type: string
  label: string
  pins: string[]
  value_unit: string
  value_label: string
  default_value: string
  description: string
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

const BASE = '/modules/electronics'

export const electronicsApi = {
  // Circuits
  listCircuits: () =>
    apiGet<{ items: CircuitListItem[]; total: number }>(`${BASE}/circuits`),

  createCircuit: (data: { name: string; description?: string }) =>
    apiPost<Circuit>(`${BASE}/circuits`, data),

  getCircuit: (id: string) =>
    apiGet<Circuit>(`${BASE}/circuits/${id}`),

  updateCircuit: (id: string, data: { name?: string; description?: string }) =>
    apiPut<Circuit>(`${BASE}/circuits/${id}`, data),

  deleteCircuit: (id: string) =>
    apiDelete<{ deleted: boolean }>(`${BASE}/circuits/${id}`),

  // Components
  addComponent: (circuitId: string, data: {
    component_type: string
    value?: string
    x?: number
    y?: number
    rotation?: number
  }) =>
    apiPost<CircuitComponent>(`${BASE}/circuits/${circuitId}/components`, data),

  updateComponent: (componentId: string, data: {
    value?: string
    x?: number
    y?: number
    rotation?: number
  }) =>
    apiPut<CircuitComponent>(`${BASE}/components/${componentId}`, data),

  deleteComponent: (componentId: string) =>
    apiDelete<{ deleted: boolean }>(`${BASE}/components/${componentId}`),

  // Wiring
  connectPins: (circuitId: string, data: {
    component_id: string
    pin_name: string
    net_name: string
  }) =>
    apiPost<{ pin_id: string; net_id: string; net_name: string }>(
      `${BASE}/circuits/${circuitId}/connect`, data
    ),

  disconnectPin: (pinId: string) =>
    apiDelete<{ disconnected: boolean }>(`${BASE}/pins/${pinId}/disconnect`),

  // Simulation
  simulate: (circuitId: string, params?: {
    sim_type?: string
    f_start?: number
    f_stop?: number
    points_per_decade?: number
    sweep_source_id?: string
    sweep_start?: number
    sweep_stop?: number
    sweep_steps?: number
    t_stop?: number
    t_step?: number
  }) =>
    apiPost<SimResult>(`${BASE}/circuits/${circuitId}/simulate`, params ?? { sim_type: 'op' }),

  getResults: (circuitId: string) =>
    apiGet<SimResult>(`${BASE}/circuits/${circuitId}/results`),

  // Library
  listLibrary: () =>
    apiGet<{ items: ComponentTypeInfo[] }>(`${BASE}/library`),

  getComponentType: (type: string) =>
    apiGet<ComponentTypeInfo>(`${BASE}/library/${type}`),

  // Wire Segments (E1b)
  listWires: (circuitId: string) =>
    apiGet<{ wire_segments: WireSegment[]; junctions: Junction[] }>(
      `${BASE}/circuits/${circuitId}/wires`
    ),

  createWire: (circuitId: string, data: {
    net_id?: string
    net_name?: string
    x1: number; y1: number; x2: number; y2: number
  }) =>
    apiPost<WireSegment>(`${BASE}/circuits/${circuitId}/wires`, data),

  deleteWire: (wireId: string) =>
    apiDelete<{ deleted: boolean }>(`${BASE}/wires/${wireId}`),

  splitWire: (circuitId: string, data: { wire_id: string; x: number; y: number }) =>
    apiPost<{ junction: Junction; segments: WireSegment[] }>(
      `${BASE}/circuits/${circuitId}/wires/split`, data
    ),

  autoRoute: (circuitId: string, data: {
    net_id?: string; net_name?: string
    from_x: number; from_y: number; to_x: number; to_y: number
    route_style?: string
  }) =>
    apiPost<{ net_id: string; segments: WireSegment[] }>(
      `${BASE}/circuits/${circuitId}/wires/auto-route`, data
    ),

  // DRC (E1b)
  runDrc: (circuitId: string) =>
    apiGet<{ warnings: DrcWarning[]; count: number }>(`${BASE}/circuits/${circuitId}/drc`),

  // Regions (E1b)
  listRegions: (circuitId: string) =>
    apiGet<{ items: Region[] }>(`${BASE}/circuits/${circuitId}/regions`),

  createRegion: (circuitId: string, data: {
    name: string; color?: string; description?: string; created_by?: string
  }) =>
    apiPost<Region>(`${BASE}/circuits/${circuitId}/regions`, data),

  updateRegion: (regionId: string, data: {
    name?: string; color?: string; description?: string
  }) =>
    apiPut<Region>(`${BASE}/regions/${regionId}`, data),

  deleteRegion: (regionId: string) =>
    apiDelete<{ deleted: boolean }>(`${BASE}/regions/${regionId}`),

  addRegionMember: (regionId: string, data: { member_type: string; member_id: string }) =>
    apiPost<RegionMember>(`${BASE}/regions/${regionId}/members`, data),

  removeRegionMember: (regionId: string, memberId: string) =>
    apiDelete<{ deleted: boolean }>(`${BASE}/regions/${regionId}/members/${memberId}`),
}
