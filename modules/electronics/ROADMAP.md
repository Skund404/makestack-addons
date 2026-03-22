# Electronics Lab — Product Roadmap

Last updated: March 2026 | Current state: E1 complete (49 tests passing, backend + frontend connected)

---

## Current State (E1 — Complete)

The DC linear foundation is fully built, tested, and connected end-to-end.

**What works today:**
- MNA (Modified Nodal Analysis) DC operating point solver
- Four built-in component types: resistor, voltage source, current source, ground
- Full circuit CRUD via API (circuits, components, nets, pins)
- Simulation results stored per-run with per-node voltages and per-component current/power/voltage
- 16 API endpoints, all auto-generating MCP tools
- 49 passing tests across solver, CRUD, simulation, and migrations
- Frontend fully connected to backend — E2E tested, data saves correctly
- Views, canvas, symbol renderer, wire layer, and simulation panel all wired and working

**What is not yet done:**
- Component types hardcoded in components.py
- No catalogue or inventory system
- No wire junction support (wires computed as star topology to centroid)
- No region/highlight system
- MCP AI flows defined in SKILL.md but untested end-to-end

---

## Guiding Principles

1. **Solver correctness over features** — every new component type needs passing unit tests before it ships
2. **MCP first** — every new capability should be expressible as an AI tool call, not just a UI action
3. **Catalogue over hardcoding** — no new component types get added to components.py; they go into the catalogue
4. **Non-destructive by default** — regions, annotations, AI suggestions never affect simulation data
5. **Migration safety** — every DB change has both up() and down()
6. **Hybrid wire model** — nets for electrical truth (solver), wire segments for visual display (frontend)

---

## Stage Overview

```
E1   DC linear foundation          ✅ Complete
E1b  Wire infrastructure + DRC     ← Current priority
E2   Reactive + AC/Transient
E3   Active + Nonlinear solver
E4   Advanced analysis + Subcircuits
E5   Export, Library & Community
E6   Educational features (AI-first)
E7   Microcontroller behaviour
```

---

## E1b — Wire Infrastructure + Value Parsing + DRC

No new solver math. Fixes the wire/junction problem and adds essential schematic editing features.

### Wire/Junction Architecture

**Problem:** Wires are computed at render time as star-topology lines to a centroid. No stored geometry, no junctions, no Manhattan routing.

**Solution:** Hybrid model — nets remain the electrical truth for the solver, wire segments store visual paths:

```sql
electronics_wire_segments (id, circuit_id, net_id, x1, y1, x2, y2, sort_order)
electronics_junctions    (id, circuit_id, net_id, x, y)
```

The solver never sees wire geometry. The frontend renders from stored segments when available, falls back to centroid for legacy circuits.

### Features

1. **Wire segments & junctions** — stored wire paths, junction dots, T-junction creation by clicking on wire
2. **Manhattan wire drawing** — L-shaped rubber-band preview, click-to-place routing
3. **Units & value parsing** — `1k` → 1000, `4.7µ` → 4.7e-6, prevents silent simulation failures
4. **Design Rule Checking** — static warnings before simulation (unconnected pins, dangling nets, no ground)
5. **Circuit regions** — named colored groupings for annotation and AI explanation
6. **Undo/redo** — command pattern stack for all mutations
7. **Component mirroring** — horizontal/vertical flip

### New Endpoints
- `GET /circuits/{id}/wires` — list wire segments
- `POST /circuits/{id}/wires` — create wire segment
- `DELETE /wires/{id}` — delete wire segment
- `POST /circuits/{id}/wires/split` — split wire at point, create junction
- `POST /circuits/{id}/wires/auto-route` — Manhattan auto-routing
- `GET /circuits/{id}/drc` — run design rule checks
- `GET /circuits/{id}/regions` — list regions
- `POST /circuits/{id}/regions` — create region
- `PUT /regions/{id}` — update region
- `DELETE /regions/{id}` — delete region
- `POST /regions/{id}/members` — add member to region
- `DELETE /regions/{id}/members/{member_id}` — remove member

---

## E2 — Reactive Components + AC/Transient Analysis

Time enters the simulator. Major solver extension.

### New Component Types (via Catalogue)
- Capacitor (C, pins: p/n, unit: F)
- Inductor (L, pins: p/n, unit: H)
- AC voltage source (amplitude, frequency, phase)
- AC current source (amplitude, frequency, phase)

### Solver Extensions
- **AC analysis:** Complex matrices, impedance stamping, frequency sweep
- **DC sweep:** Vary one source value across a range
- **Transient analysis:** Backward Euler/trapezoidal integration, companion models

### Frontend Additions
- Oscilloscope-style waveform viewer with cursors
- Bode plots (magnitude + phase)
- Probe placement on schematic
- Net labels and power flags (connect by name)
- Component value sweeping

---

## E3 — Active Components + Nonlinear Solver

The biggest solver change. Newton-Raphson iteration enables transistors and diodes.

### New Component Types
- Diode, Zener, LED
- NPN/PNP BJT
- N/P-channel MOSFET
- Ideal Op-Amp

### Solver: Newton-Raphson
- Iterative linearization until convergence
- Shockley diode model, Ebers-Moll BJT model, square-law MOSFET
- Convergence helpers: damping, source stepping, Gmin stepping

### Frontend
- 3-terminal component symbols
- Operating point annotations (Vbe, Ic, operating region)
- Convergence status display

---

## E4 — Advanced Analysis + Subcircuits

- Parameter sweep and sensitivity analysis
- Monte Carlo (tolerance analysis, yield)
- Temperature sweep
- Subcircuit support (hierarchical reuse, SPICE .subckt import)
- Noise analysis
- Multi-page schematics

---

## E5 — Export, Library & Community

- SPICE netlist export (.cir format)
- BOM generation (CSV/JSON)
- Schematic SVG/PNG export
- Waveform data CSV export
- Datasheet ingestion pipeline
- Circuit templates (555, voltage regulator, etc.)
- Circuit sharing (JSON bundle import/export)

---

## E6 — Educational Features (AI-First Differentiator)

What separates this from LTspice. Can start in parallel with E2.

- **Step-by-step solving** — show MNA matrix construction interactively
- **Circuit calculators** — voltage divider, LED resistor, RC filter cutoff
- **Goal-directed design** — "I need to drop 12V to 5V" → AI builds it
- **Operating point annotation** — color-code by power dissipation, current arrows
- **Cross-circuit reference** — "build like my LED Driver but for 3.3V"
- **Confidence signalling** — AI warns when results approach solver limits
- **Interactive tutorials** — guided circuit building with AI

---

## E7 — Microcontroller Behaviour (Stretch)

- MCU component with configurable GPIO pins
- Python tick function: `def tick(time_s, pins) -> dict`
- Sandboxed execution (no imports except math, timeout, memory limit)
- Integration with transient solver
- AI generates tick functions from descriptions

---

## Features from Real Simulators

| Feature | Source | Stage |
|---------|--------|-------|
| Manhattan wire routing | KiCad, LTspice | E1b |
| Wire junctions (T-dot) | All editors | E1b |
| Net labels & power flags | KiCad, Altium | E2 |
| Oscilloscope waveform viewer | LTspice, Falstad | E2 |
| Bode plots | LTspice | E2 |
| Probe placement | LTspice, Multisim | E2 |
| DC/component sweep | SPICE, LTspice | E2 |
| Newton-Raphson nonlinear | SPICE | E3 |
| Operating point annotation | Multisim | E3 |
| SPICE model import | LTspice, KiCad | E3 |
| Monte Carlo | LTspice | E4 |
| Subcircuits | SPICE | E4 |
| Multi-page schematics | KiCad, Altium | E4 |
| Netlist/BOM export | All | E5 |
| Circuit templates | Falstad, Tinkercad | E5 |
| Interactive explanation | Novel (AI-first) | E6 |
| Goal-directed design | Novel | E6 |
| MCU co-simulation | Proteus | E7 |

---

## Dependency Graph

```
E1b (Wires + DRC + Editing)
├── Required by: everything
└── No solver changes

E2 (Reactive + AC/Transient)    E3 (Active + Nonlinear)
├── Requires: E1b               ├── Requires: E1b
└── Independent of E3            └── Independent of E2

E4 (Advanced Analysis) ← Requires E2 + E3

E5 (Export + Library) ← Requires E3

E6 (Educational) ← Can start with E1, grows with each stage

E7 (MCU) ← Requires E2 transient engine
```
