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
  simulate: (circuitId: string) =>
    apiPost<SimResult>(`${BASE}/circuits/${circuitId}/simulate`, { sim_type: 'op' }),

  getResults: (circuitId: string) =>
    apiGet<SimResult>(`${BASE}/circuits/${circuitId}/results`),

  // Library
  listLibrary: () =>
    apiGet<{ items: ComponentTypeInfo[] }>(`${BASE}/library`),

  getComponentType: (type: string) =>
    apiGet<ComponentTypeInfo>(`${BASE}/library/${type}`),
}
