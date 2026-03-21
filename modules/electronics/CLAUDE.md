# CLAUDE.md — Makestack Electronics Lab Module

> Read this entire file before doing any work on this module.

---

## Module Identity

- Name: electronics
- Display name: Electronics Lab
- Repo: makestack-addons
- Type: module (full-stack: backend + frontend)
- No required peers (self-contained)
- Shell compatibility: >=0.1.0
- Python dependency: numpy>=1.24.0

## Architecture

The electronics module provides a circuit simulator with schematic editing,
DC analysis, and AI-powered circuit explanation. It runs as a standalone app
(app_mode) with a branded sidebar.

### What this module owns
- electronics_* UserDB tables (circuits, components, nets, pins, sim results)
- MNA DC solver (Modified Nodal Analysis, pure Python + NumPy)
- Component type registry (built-in library: resistor, voltage source, current source, ground)
- Electronics-specific API endpoints mounted at /modules/electronics/
- Electronics views and panels (standalone app mode)
- SKILL.md — the AI intelligence layer

### What this module does NOT own
- Catalogue primitives — component definitions in Core are optional extensions
- Shell routes, settings, or system endpoints
- Any other module's tables

### Data Model

**Core catalogue (optional, reusable):**
- Component definitions as Material primitives (SPICE models, pin layouts, educational content)
- Not required for E1 — built-in component types suffice

**UserDB (circuit instances, user state):**
- electronics_circuits — circuit metadata
- electronics_components — placed component instances (ref to type, position, value)
- electronics_nets — named electrical nodes
- electronics_pins — pin-to-net connections (the topology)
- electronics_sim_results — simulation run metadata
- electronics_sim_node_results — per-net voltages
- electronics_sim_component_results — per-component current/power/voltage

### Why UserDB, Not Core

Circuit editing is interactive — drag, connect, resize produce many writes per second.
Core writes = Git commits with 200ms debounce. UserDB (SQLite) handles real-time
interactive state without this overhead.

This matches kitchen's pattern: catalogue has reusable definitions,
UserDB has user instance data.

## Primitive Mapping

- Materials = Component definitions (catalogue entries — optional)
- Techniques = Circuit analysis methods (Ohm's law, KVL, KCL — educational)
- Workflows = Reference circuits (voltage divider, amplifier — educational)
- Projects = Not used (circuits are in UserDB)
- Events = Not used

## API Endpoints

All mounted at /modules/electronics/. Auto-generate MCP tools: electronics__{name}

### Circuit CRUD
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| GET | /circuits | list_circuits | List all circuits |
| POST | /circuits | create_circuit | Create empty circuit |
| GET | /circuits/{id} | get_circuit | Full circuit graph |
| PUT | /circuits/{id} | update_circuit | Update metadata |
| DELETE | /circuits/{id} | delete_circuit | Delete circuit + children |

### Component Placement
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| POST | /circuits/{id}/components | add_component | Place component |
| PUT | /components/{id} | update_component | Move/rotate/change value |
| DELETE | /components/{id} | delete_component | Remove component |

### Wiring
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| POST | /circuits/{id}/nets | create_net | Create named net |
| POST | /circuits/{id}/connect | connect_pins | Wire pin to net |
| DELETE | /pins/{id}/disconnect | disconnect_pin | Unwire pin |

### Simulation
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| POST | /circuits/{id}/simulate | run_simulation | Run DC operating point |
| GET | /circuits/{id}/results | get_results | Latest results |
| GET | /circuits/{id}/results/{rid} | get_result_detail | Specific result |

### Component Library
| Method | Path | MCP name | Description |
|--------|------|----------|-------------|
| GET | /library | list_library | List component types |
| GET | /library/{type} | get_component_type | Type detail |

## App Mode (standalone layout)

- Title: "Electronics Lab", subtitle: "Circuit simulator"
- Theme: dark blue (#0a1628 bg, #94a3b8 text, #38bdf8 accent)
- Home route: /electronics
- Nav items: Home, Circuits, Components

## Views

| Route | Component | Description |
|-------|-----------|-------------|
| /electronics | ElectronicsHome | Dashboard: recent circuits, create new |
| /electronics/circuits | ElectronicsCircuits | Circuit list |
| /electronics/circuits/:id | ElectronicsCircuitEditor | Schematic editor + simulation |
| /electronics/components | ElectronicsComponents | Component type browser |

## MNA Solver

The solver implements Modified Nodal Analysis for DC operating point:
- Builds conductance matrix G and augments with voltage source equations
- Solves Ax=z using numpy.linalg.solve
- Returns node voltages and component currents/power
- Handles: resistors, voltage sources, current sources
- Error cases: no ground, singular matrix, unconnected pins, zero resistance

## Code Standards

- All endpoints async, typed (Pydantic 2.x), follow kitchen module pattern
- All migrations have both up() and down()
- Use makestack_sdk imports: get_module_userdb_factory, get_logger
- Error responses include suggestion field for AI consumption
- Component types defined in components.py registry
- Solver is pure Python — no side effects, fully testable

## Build Order

E1 DC linear foundation (current) →
E2 reactive components (capacitor, inductor, AC/transient) →
E3 active components (diode, BJT, op-amp, nonlinear solver) →
E4 microcontroller behaviour (Python tick model) →
E5 community library (datasheet ingestion, federated catalogue)

## Current State

E1 backend complete: 49 tests passing.
- Migration, models, component registry
- MNA solver with full test coverage
- All 16 API endpoints
- Frontend: not yet started

## Test Command

```bash
cd makestack-addons/modules/electronics
python3 -m pytest tests/ -q
```
