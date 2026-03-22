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
DC/AC/transient analysis, and AI-powered circuit explanation. It runs as a
standalone app (app_mode) with a branded sidebar.

### What this module owns
- electronics_* UserDB tables (circuits, components, nets, pins, sim results, sweep data)
- MNA solver (Modified Nodal Analysis, pure Python + NumPy) — DC, AC, DC sweep, transient
- Component type registry (built-in library: resistor, capacitor, inductor, voltage source, current source, ground)
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

The solver implements Modified Nodal Analysis with four simulation modes:

### DC Operating Point (sim_type: "op")
- Builds conductance matrix G and augments with voltage source equations
- Capacitors = open circuit (no stamp), Inductors = 0V voltage source (short)
- Solves Ax=z using numpy.linalg.solve
- Returns node voltages and component currents/power

### AC Small-Signal (sim_type: "ac")
- Complex MNA matrix at each frequency point (log-spaced sweep)
- Capacitor admittance: Y = jωC, Inductor admittance: Y = 1/(jωL)
- Returns magnitude and phase at each node per frequency
- Parameters: f_start, f_stop, points_per_decade

### DC Sweep (sim_type: "dc_sweep")
- Varies a voltage/current source across a range, solves DC OP at each step
- Parameters: sweep_source_id, sweep_start, sweep_stop, sweep_steps

### Transient (sim_type: "transient")
- Trapezoidal integration with companion models
- Capacitor companion: parallel G = 2C/h + current source I_eq
- Inductor companion: voltage source with series R = 2L/h
- Initial conditions from DC OP
- Parameters: t_stop, t_step (auto if None)

### Newton-Raphson Nonlinear (E3)
- Iterative linearization for diodes, BJTs, MOSFETs
- Convergence aids: voltage damping, Gmin stepping, source stepping
- Operating region detection and reporting
- Nonlinear transient: NR inner loop at each timestep

### Monte Carlo (sim_type: "monte_carlo")
- Tolerance analysis with component value variations
- Parameters: mc_tolerances, mc_runs, mc_seed

### Parameter Sweep (sim_type: "param_sweep")
- Varies a model parameter or component value across a range
- Parameters: ps_component_id, ps_param, ps_start, ps_stop, ps_steps

### Temperature Sweep (sim_type: "temp_sweep")
- Solves at each temperature point
- Parameters: temp_start, temp_stop, temp_steps

### Component support
- Linear: resistors, capacitors, inductors, voltage sources, current sources, ground
- Nonlinear: diodes (1N4148, 1N4001), zener, LED, NPN/PNP BJT (2N3904, 2N3906), NMOS/PMOS FET (2N7000), ideal op-amp
- MCU: microcontroller with configurable GPIO, sandboxed Python tick function
- Error cases: no ground, singular matrix, unconnected pins, zero/negative values, NR non-convergence

## Code Standards

- All endpoints async, typed (Pydantic 2.x), follow kitchen module pattern
- All migrations have both up() and down()
- Use makestack_sdk imports: get_module_userdb_factory, get_logger
- Error responses include suggestion field for AI consumption
- Component types defined in components.py registry
- Solver is pure Python — no side effects, fully testable

## Build Order

E1 DC linear foundation →
E1b Wire segments, DRC, regions →
E2 Reactive components (capacitor, inductor, AC/transient) →
E3 Active components (diode, BJT, MOSFET, op-amp, Newton-Raphson solver) →
E4 Subcircuits + advanced analysis (Monte Carlo, parameter sweep, temperature sweep) →
E5 Export (SPICE, BOM, CSV) + circuit templates →
E6 Educational features (calculators, MNA explainer) →
E7 MCU co-simulation (sandboxed Python tick functions) →
E8 Frontend (all component symbols, simulation panel) →
E9 Apple 1 templates + final polish

## Current State

E9 complete: 360 tests passing, frontend fully updated.
- E1: DC solver, circuit CRUD, component placement, wiring, simulation (16 endpoints)
- E1b: Wire segments/junctions, DRC, regions, value parsing, Manhattan routing (12 endpoints)
- E2: Capacitor + inductor, AC/DC sweep/transient analysis, sweep data storage
- E3: Newton-Raphson nonlinear solver, diode/BJT/MOSFET/op-amp models with presets
- E4: Subcircuit definitions + flattening, Monte Carlo, parameter sweep, temperature sweep
- E5: SPICE netlist export, BOM (JSON/CSV), waveform CSV, circuit JSON bundle, 12 circuit templates
- E6: Calculators (voltage divider, LED resistor, RC filter, BJT bias), MNA step-by-step explainer
- E7: MCU component with sandboxed Python tick functions, program CRUD API
- E8: Frontend: all 15 component SVG symbols, grouped palette, sim type selector, operating region display, NR convergence info, export buttons, template gallery, model preset badges
- 15 component types: resistor, capacitor, inductor, voltage_source, current_source, ground, diode, zener, led, npn_bjt, pnp_bjt, nmos, pmos, opamp, mcu
- 12 templates: voltage_divider, led_driver, common_emitter_amp, cmos_inverter, zener_regulator, opamp_inverting, apple1_clock, apple1_power_supply, apple1_reset, half_wave_rectifier, emitter_follower, current_mirror
- 6 migrations, ~60 API endpoints
- Backend files: solver.py, device_models.py, components.py, models.py, routes.py, subcircuit.py, exporters.py, templates.py, education.py, mcu_sandbox.py
- Frontend files: ComponentSymbol.tsx (15 symbols), ComponentPalette.tsx (grouped), SimulationPanel.tsx (sim type + NR + regions), SchematicCanvas.tsx, api.ts (~60 typed endpoints), ElectronicsHome.tsx (templates), ElectronicsComponents.tsx (grouped + presets)

## Test Command

```bash
cd makestack-addons/modules/electronics
python3 -m pytest tests/ -q
```
