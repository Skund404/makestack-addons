"""Electronics simulator module routes.

NOTE ON IMPORTS
--------------
The shell loader imports this file by absolute file path via importlib
(spec_from_file_location), so the module root is NOT on sys.path.
Internal imports use _elec_import() — same pattern as the kitchen module.
"""

from __future__ import annotations

import importlib.util
import json as _json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from makestack_sdk.userdb import get_module_userdb_factory, ModuleUserDB


# ---------------------------------------------------------------------------
# Internal module loader
# ---------------------------------------------------------------------------


def _elec_import(name: str):
    """Load a sibling Python file from the electronics backend directory."""
    key = f"_electronics_backend_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load electronics backend module: {name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


_m = _elec_import("models")
_c = _elec_import("components")
_solver = _elec_import("solver")

CircuitCreate = _m.CircuitCreate
CircuitUpdate = _m.CircuitUpdate
ComponentCreate = _m.ComponentCreate
ComponentUpdate = _m.ComponentUpdate
NetCreate = _m.NetCreate
ConnectPinsRequest = _m.ConnectPinsRequest
SimulateRequest = _m.SimulateRequest
WireSegmentCreate = _m.WireSegmentCreate
WireSplitRequest = _m.WireSplitRequest
AutoRouteRequest = _m.AutoRouteRequest
RegionCreate = _m.RegionCreate
RegionUpdate = _m.RegionUpdate
RegionMemberAdd = _m.RegionMemberAdd
SubcircuitCreate = _m.SubcircuitCreate
SubcircuitInstanceCreate = _m.SubcircuitInstanceCreate
MCUProgramUpload = _m.MCUProgramUpload

_vp = _elec_import("value_parser")
parse_engineering_value = _vp.parse_engineering_value

get_component_type = _c.get_component_type
get_ref_prefix = _c.get_ref_prefix
get_pins = _c.get_pins
validate_component_type = _c.validate_component_type
COMPONENT_TYPES = _c.COMPONENT_TYPES

CircuitGraph = _solver.CircuitGraph
ComponentInstance = _solver.ComponentInstance
SolverError = _solver.SolverError
_exporters = _elec_import("exporters")
_templates = _elec_import("templates")
_education = _elec_import("education")
solve_dc_op = _solver.solve_dc_op
solve_ac = _solver.solve_ac
solve_dc_sweep = _solver.solve_dc_sweep
solve_transient = _solver.solve_transient
solve_parameter_sweep = _solver.solve_parameter_sweep
solve_monte_carlo = _solver.solve_monte_carlo
solve_temp_sweep = _solver.solve_temp_sweep


# ---------------------------------------------------------------------------
# Router + DB
# ---------------------------------------------------------------------------

router = APIRouter()

get_db = get_module_userdb_factory(
    module_name="electronics",
    allowed_tables=[
        "electronics_circuits",
        "electronics_components",
        "electronics_nets",
        "electronics_pins",
        "electronics_sim_results",
        "electronics_sim_node_results",
        "electronics_sim_component_results",
        "electronics_wire_segments",
        "electronics_junctions",
        "electronics_regions",
        "electronics_region_members",
        "electronics_sweep_points",
        "electronics_subcircuits",
        "electronics_subcircuit_instances",
        "electronics_mcu_programs",
    ],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# ===================================================================
# CIRCUIT CRUD
# ===================================================================


@router.get("/circuits")
async def list_circuits(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: ModuleUserDB = Depends(get_db),
):
    """List all circuits with pagination."""
    rows = await db.fetch_all(
        "SELECT * FROM electronics_circuits ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        [limit, offset],
    )
    total = await db.count("electronics_circuits")
    return {"items": rows, "total": total}


@router.post("/circuits", status_code=201)
async def create_circuit(
    body: CircuitCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Create a new empty circuit."""
    now = _now()
    circuit_id = _uuid()
    await db.execute(
        """INSERT INTO electronics_circuits (id, name, description, canvas_width, canvas_height, sim_settings, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, '{}', ?, ?)""",
        [circuit_id, body.name, body.description, body.canvas_width, body.canvas_height, now, now],
    )
    return await _get_circuit_full(circuit_id, db)


@router.get("/circuits/{circuit_id}")
async def get_circuit(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Full circuit with components, nets, pins, and latest simulation result."""
    return await _get_circuit_full(circuit_id, db)


@router.put("/circuits/{circuit_id}")
async def update_circuit(
    circuit_id: str,
    body: CircuitUpdate,
    db: ModuleUserDB = Depends(get_db),
):
    """Update circuit metadata."""
    row = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not row:
        raise HTTPException(404, detail={"error": "Circuit not found", "suggestion": "Use GET /circuits to list circuits"})

    updates = []
    params = []
    for field in ["name", "description", "canvas_width", "canvas_height"]:
        val = getattr(body, field, None)
        if val is not None:
            updates.append(f"{field} = ?")
            params.append(val)

    if updates:
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(circuit_id)
        await db.execute(
            f"UPDATE electronics_circuits SET {', '.join(updates)} WHERE id = ?",
            params,
        )

    return await _get_circuit_full(circuit_id, db)


@router.delete("/circuits/{circuit_id}")
async def delete_circuit(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Delete circuit and all children (CASCADE)."""
    row = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not row:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    # Delete in FK order (SQLite CASCADE may not be enabled)
    await db.execute("DELETE FROM electronics_region_members WHERE region_id IN (SELECT id FROM electronics_regions WHERE circuit_id = ?)", [circuit_id])
    await db.execute("DELETE FROM electronics_regions WHERE circuit_id = ?", [circuit_id])
    await db.execute("DELETE FROM electronics_junctions WHERE circuit_id = ?", [circuit_id])
    await db.execute("DELETE FROM electronics_wire_segments WHERE circuit_id = ?", [circuit_id])
    await db.execute("DELETE FROM electronics_sweep_points WHERE sim_result_id IN (SELECT id FROM electronics_sim_results WHERE circuit_id = ?)", [circuit_id])
    await db.execute("DELETE FROM electronics_sim_component_results WHERE sim_result_id IN (SELECT id FROM electronics_sim_results WHERE circuit_id = ?)", [circuit_id])
    await db.execute("DELETE FROM electronics_sim_node_results WHERE sim_result_id IN (SELECT id FROM electronics_sim_results WHERE circuit_id = ?)", [circuit_id])
    await db.execute("DELETE FROM electronics_sim_results WHERE circuit_id = ?", [circuit_id])
    await db.execute("DELETE FROM electronics_pins WHERE component_id IN (SELECT id FROM electronics_components WHERE circuit_id = ?)", [circuit_id])
    await db.execute("DELETE FROM electronics_components WHERE circuit_id = ?", [circuit_id])
    await db.execute("DELETE FROM electronics_nets WHERE circuit_id = ?", [circuit_id])
    await db.execute("DELETE FROM electronics_circuits WHERE id = ?", [circuit_id])

    return {"deleted": True}


# ===================================================================
# COMPONENT PLACEMENT
# ===================================================================


@router.post("/circuits/{circuit_id}/components", status_code=201)
async def add_component(
    circuit_id: str,
    body: ComponentCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Place a component on the canvas. Auto-assigns ref designator and creates pins."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    if not validate_component_type(body.component_type):
        raise HTTPException(400, detail={
            "error": f"Unknown component type: {body.component_type}",
            "suggestion": f"Valid types: {', '.join(COMPONENT_TYPES.keys())}",
        })

    # Auto-assign ref designator
    prefix = get_ref_prefix(body.component_type)
    existing = await db.fetch_all(
        "SELECT ref_designator FROM electronics_components WHERE circuit_id = ? AND component_type = ?",
        [circuit_id, body.component_type],
    )
    existing_nums = []
    for r in existing:
        ref = r["ref_designator"]
        suffix = ref[len(prefix):]
        if suffix.isdigit():
            existing_nums.append(int(suffix))
    next_num = max(existing_nums, default=0) + 1
    ref_designator = f"{prefix}{next_num}"

    # Use default value if not provided
    value = body.value
    if not value:
        ct = get_component_type(body.component_type)
        value = ct["default_value"] if ct else "0"
    else:
        # Parse engineering notation (e.g. "1k" → "1000.0")
        parsed = parse_engineering_value(value)
        if parsed is not None:
            value = str(parsed)

    unit = body.unit
    if not unit:
        ct = get_component_type(body.component_type)
        unit = ct["value_unit"] if ct else ""

    # Serialize model_params to properties JSON
    properties = _json.dumps(body.model_params) if body.model_params else '{}'

    comp_id = _uuid()
    await db.execute(
        """INSERT INTO electronics_components
        (id, circuit_id, catalogue_path, ref_designator, component_type, value, unit, x, y, rotation, properties, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [comp_id, circuit_id, body.catalogue_path, ref_designator, body.component_type, value, unit, body.x, body.y, body.rotation, properties, _now()],
    )

    # Create pin rows
    pins = get_pins(body.component_type)
    for pin_name in pins:
        pin_id = _uuid()
        await db.execute(
            "INSERT INTO electronics_pins (id, component_id, pin_name, net_id) VALUES (?, ?, ?, NULL)",
            [pin_id, comp_id, pin_name],
        )

    # If ground component, auto-connect to GND net
    if body.component_type == "ground":
        gnd_net = await db.fetch_one(
            "SELECT id FROM electronics_nets WHERE circuit_id = ? AND name = 'GND'",
            [circuit_id],
        )
        if not gnd_net:
            gnd_net_id = _uuid()
            await db.execute(
                "INSERT INTO electronics_nets (id, circuit_id, name, net_type, color) VALUES (?, ?, 'GND', 'ground', '')",
                [gnd_net_id, circuit_id],
            )
        else:
            gnd_net_id = gnd_net["id"]

        await db.execute(
            "UPDATE electronics_pins SET net_id = ? WHERE component_id = ? AND pin_name = 'gnd'",
            [gnd_net_id, comp_id],
        )

    await db.execute("UPDATE electronics_circuits SET updated_at = ? WHERE id = ?", [_now(), circuit_id])

    return await _get_component_with_pins(comp_id, db)


@router.put("/components/{component_id}")
async def update_component(
    component_id: str,
    body: ComponentUpdate,
    db: ModuleUserDB = Depends(get_db),
):
    """Move, rotate, or change value of a component."""
    row = await db.fetch_one("SELECT * FROM electronics_components WHERE id = ?", [component_id])
    if not row:
        raise HTTPException(404, detail={"error": "Component not found"})

    updates = []
    params = []
    for field in ["value", "unit", "x", "y", "rotation"]:
        val = getattr(body, field, None)
        if val is not None:
            # Parse engineering notation for value field
            if field == "value" and isinstance(val, str):
                parsed = parse_engineering_value(val)
                if parsed is not None:
                    val = str(parsed)
            updates.append(f"{field} = ?")
            params.append(val)

    # Handle model_params update
    if body.model_params is not None:
        # Merge with existing properties
        existing_props = {}
        try:
            existing_props = _json.loads(row.get("properties", "{}") or "{}")
        except (ValueError, TypeError):
            pass
        existing_props.update(body.model_params)
        updates.append("properties = ?")
        params.append(_json.dumps(existing_props))

    if updates:
        params.append(component_id)
        await db.execute(
            f"UPDATE electronics_components SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.execute("UPDATE electronics_circuits SET updated_at = ? WHERE id = ?", [_now(), row["circuit_id"]])

    return await _get_component_with_pins(component_id, db)


@router.delete("/components/{component_id}")
async def delete_component(
    component_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Remove a component and its pins."""
    row = await db.fetch_one("SELECT circuit_id FROM electronics_components WHERE id = ?", [component_id])
    if not row:
        raise HTTPException(404, detail={"error": "Component not found"})

    await db.execute("DELETE FROM electronics_pins WHERE component_id = ?", [component_id])
    await db.execute("DELETE FROM electronics_components WHERE id = ?", [component_id])
    await db.execute("UPDATE electronics_circuits SET updated_at = ? WHERE id = ?", [_now(), row["circuit_id"]])

    return {"deleted": True}


# ===================================================================
# NETS / WIRING
# ===================================================================


@router.post("/circuits/{circuit_id}/nets", status_code=201)
async def create_net(
    circuit_id: str,
    body: NetCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Create a named net."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    existing = await db.fetch_one(
        "SELECT id FROM electronics_nets WHERE circuit_id = ? AND name = ?",
        [circuit_id, body.name],
    )
    if existing:
        raise HTTPException(409, detail={
            "error": f"Net '{body.name}' already exists in this circuit",
            "suggestion": "Use a different name or connect to the existing net",
        })

    net_id = _uuid()
    await db.execute(
        "INSERT INTO electronics_nets (id, circuit_id, name, net_type, color) VALUES (?, ?, ?, ?, ?)",
        [net_id, circuit_id, body.name, body.net_type, body.color],
    )

    return {"id": net_id, "name": body.name, "net_type": body.net_type, "color": body.color}


@router.post("/circuits/{circuit_id}/connect")
async def connect_pins(
    circuit_id: str,
    body: ConnectPinsRequest,
    db: ModuleUserDB = Depends(get_db),
):
    """Connect a component pin to a net. Auto-creates net if it doesn't exist."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    # Verify component belongs to this circuit
    comp = await db.fetch_one(
        "SELECT id FROM electronics_components WHERE id = ? AND circuit_id = ?",
        [body.component_id, circuit_id],
    )
    if not comp:
        raise HTTPException(404, detail={"error": "Component not found in this circuit"})

    # Find pin
    pin = await db.fetch_one(
        "SELECT id FROM electronics_pins WHERE component_id = ? AND pin_name = ?",
        [body.component_id, body.pin_name],
    )
    if not pin:
        raise HTTPException(404, detail={
            "error": f"Pin '{body.pin_name}' not found on component",
            "suggestion": f"Check component type for valid pin names",
        })

    # Find or create net
    net = await db.fetch_one(
        "SELECT id, net_type FROM electronics_nets WHERE circuit_id = ? AND name = ?",
        [circuit_id, body.net_name],
    )
    if not net:
        net_type = "ground" if body.net_name.upper() == "GND" else "signal"
        net_id = _uuid()
        await db.execute(
            "INSERT INTO electronics_nets (id, circuit_id, name, net_type, color) VALUES (?, ?, ?, ?, '')",
            [net_id, circuit_id, body.net_name, net_type],
        )
    else:
        net_id = net["id"]

    # Connect
    await db.execute(
        "UPDATE electronics_pins SET net_id = ? WHERE id = ?",
        [net_id, pin["id"]],
    )
    await db.execute("UPDATE electronics_circuits SET updated_at = ? WHERE id = ?", [_now(), circuit_id])

    return {"pin_id": pin["id"], "net_id": net_id, "net_name": body.net_name}


@router.delete("/pins/{pin_id}/disconnect")
async def disconnect_pin(
    pin_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Remove a pin's net connection."""
    pin = await db.fetch_one("SELECT id, component_id FROM electronics_pins WHERE id = ?", [pin_id])
    if not pin:
        raise HTTPException(404, detail={"error": "Pin not found"})

    await db.execute("UPDATE electronics_pins SET net_id = NULL WHERE id = ?", [pin_id])

    return {"disconnected": True}


# ===================================================================
# SIMULATION
# ===================================================================


@router.post("/circuits/{circuit_id}/simulate")
async def run_simulation(
    circuit_id: str,
    body: SimulateRequest = None,
    db: ModuleUserDB = Depends(get_db),
):
    """Run simulation on the circuit. Supports: op, ac, dc_sweep, transient."""
    if body is None:
        body = SimulateRequest()

    circuit = await db.fetch_one("SELECT * FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    graph = await _build_solver_graph(circuit_id, db)

    sim_id = _uuid()
    start_time = time.monotonic()

    try:
        if body.sim_type == "ac":
            return await _run_ac(sim_id, circuit_id, body, graph, start_time, db)
        elif body.sim_type == "dc_sweep":
            return await _run_dc_sweep(sim_id, circuit_id, body, graph, start_time, db)
        elif body.sim_type == "transient":
            return await _run_transient(sim_id, circuit_id, body, graph, start_time, db)
        elif body.sim_type == "monte_carlo":
            return await _run_monte_carlo(sim_id, circuit_id, body, graph, start_time, db)
        elif body.sim_type == "param_sweep":
            return await _run_param_sweep(sim_id, circuit_id, body, graph, start_time, db)
        elif body.sim_type == "temp_sweep":
            return await _run_temp_sweep(sim_id, circuit_id, body, graph, start_time, db)
        else:
            # Default: DC operating point
            return await _run_dc_op(sim_id, circuit_id, body, graph, start_time, db)

    except SolverError as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await db.execute(
            """INSERT INTO electronics_sim_results
            (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
            VALUES (?, ?, ?, 'error', ?, '{}', ?, ?)""",
            [sim_id, circuit_id, body.sim_type, str(e), _now(), duration_ms],
        )
        return {
            "id": sim_id,
            "circuit_id": circuit_id,
            "sim_type": body.sim_type,
            "status": "error",
            "error_message": str(e),
            "node_results": [],
            "component_results": [],
            "sweep_data": [],
        }


@router.get("/circuits/{circuit_id}/results")
async def get_results(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Get the latest simulation results for a circuit."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    sim = await db.fetch_one(
        "SELECT id FROM electronics_sim_results WHERE circuit_id = ? ORDER BY ran_at DESC LIMIT 1",
        [circuit_id],
    )
    if not sim:
        return {"id": None, "status": "none", "message": "No simulation has been run yet"}

    return await _get_sim_result_full(sim["id"], db)


@router.get("/circuits/{circuit_id}/results/{result_id}")
async def get_result_detail(
    circuit_id: str,
    result_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Get a specific simulation result with full breakdown."""
    sim = await db.fetch_one(
        "SELECT * FROM electronics_sim_results WHERE id = ? AND circuit_id = ?",
        [result_id, circuit_id],
    )
    if not sim:
        raise HTTPException(404, detail={"error": "Simulation result not found"})

    return await _get_sim_result_full(result_id, db)


# ===================================================================
# SIMULATION HELPERS (E2)
# ===================================================================


async def _build_solver_graph(circuit_id: str, db: ModuleUserDB) -> CircuitGraph:
    """Load circuit data and build a CircuitGraph for the solver."""
    components = await db.fetch_all(
        "SELECT * FROM electronics_components WHERE circuit_id = ?", [circuit_id]
    )
    nets = await db.fetch_all(
        "SELECT * FROM electronics_nets WHERE circuit_id = ?", [circuit_id]
    )
    pins = await db.fetch_all(
        """SELECT p.*, c.circuit_id FROM electronics_pins p
           JOIN electronics_components c ON p.component_id = c.id
           WHERE c.circuit_id = ?""",
        [circuit_id],
    )

    ground_net_id = None
    for net in nets:
        if net["net_type"] == "ground":
            ground_net_id = net["id"]
            break

    node_ids = [n["id"] for n in nets]

    pin_map: dict[str, dict[str, str | None]] = {}
    for pin in pins:
        cid = pin["component_id"]
        if cid not in pin_map:
            pin_map[cid] = {}
        pin_map[cid][pin["pin_name"]] = pin["net_id"]

    solver_components = []
    for comp in components:
        value_str = comp["value"] or "0"
        try:
            value = float(value_str)
        except ValueError:
            value = 0.0

        # Parse model_params from properties JSON
        props_str = comp.get("properties", "{}")
        try:
            params = _json.loads(props_str) if props_str else {}
        except (ValueError, TypeError):
            params = {}

        solver_components.append(ComponentInstance(
            id=comp["id"],
            component_type=comp["component_type"],
            value=value,
            pins=pin_map.get(comp["id"], {}),
            params=params,
        ))

    graph = CircuitGraph(
        ground_net_id=ground_net_id,
        nodes=node_ids,
        components=solver_components,
    )

    # Flatten subcircuit instances into the graph
    sub_instances = await db.fetch_all(
        "SELECT * FROM electronics_subcircuit_instances WHERE circuit_id = ?",
        [circuit_id],
    )
    if sub_instances:
        _sub_mod = _elec_import("subcircuit")
        sub_defs = {}
        for si in sub_instances:
            sid = si["subcircuit_id"]
            if sid not in sub_defs:
                row = await db.fetch_one("SELECT * FROM electronics_subcircuits WHERE id = ?", [sid])
                if row:
                    sub_defs[sid] = _sub_mod.SubcircuitDef(
                        id=row["id"],
                        name=row["name"],
                        description=row["description"],
                        port_pins=_json.loads(row["port_pins"]),
                        circuit_json=_json.loads(row["circuit_json"]),
                    )

        instances = [
            _sub_mod.SubcircuitInstance(
                id=si["id"],
                subcircuit_id=si["subcircuit_id"],
                port_mapping=_json.loads(si["port_mapping"]),
            )
            for si in sub_instances
        ]
        graph = _sub_mod.flatten_all_subcircuits(graph, instances, sub_defs, _solver)

    return graph


async def _run_dc_op(sim_id, circuit_id, body, graph, start_time, db):
    """Run DC operating point and store results."""
    result = solve_dc_op(graph)
    duration_ms = int((time.monotonic() - start_time) * 1000)

    await db.execute(
        """INSERT INTO electronics_sim_results
        (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
        VALUES (?, ?, ?, 'complete', NULL, ?, ?, ?)""",
        [sim_id, circuit_id, body.sim_type, _json.dumps(result.solver_metadata), _now(), duration_ms],
    )

    for net_id, voltage in result.node_voltages.items():
        await db.execute(
            "INSERT INTO electronics_sim_node_results (id, sim_result_id, net_id, voltage) VALUES (?, ?, ?, ?)",
            [_uuid(), sim_id, net_id, voltage],
        )

    for comp_id, cr in result.component_results.items():
        extra_json = _json.dumps(cr.extra_data) if cr.extra_data else '{}'
        await db.execute(
            """INSERT INTO electronics_sim_component_results
            (id, sim_result_id, component_id, current, power, voltage_drop, operating_region, extra_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [_uuid(), sim_id, comp_id, cr.current, cr.power, cr.voltage_drop,
             cr.operating_region, extra_json],
        )

    return await _get_sim_result_full(sim_id, db)


async def _run_ac(sim_id, circuit_id, body, graph, start_time, db):
    """Run AC analysis and store sweep results."""
    result = solve_ac(
        graph,
        f_start=body.f_start,
        f_stop=body.f_stop,
        points_per_decade=body.points_per_decade,
    )
    duration_ms = int((time.monotonic() - start_time) * 1000)

    await db.execute(
        """INSERT INTO electronics_sim_results
        (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
        VALUES (?, ?, ?, 'complete', NULL, ?, ?, ?)""",
        [sim_id, circuit_id, "ac", _json.dumps(result.solver_metadata), _now(), duration_ms],
    )

    # Store AC sweep data as sweep_points
    for i, point in enumerate(result.points):
        for net_id, v_complex in point.node_voltages.items():
            await db.execute(
                """INSERT INTO electronics_sweep_points
                (id, sim_result_id, point_index, parameter_value, net_id,
                 voltage_real, voltage_imag, component_id, current, power)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)""",
                [_uuid(), sim_id, i, point.frequency, net_id,
                 v_complex.real, v_complex.imag],
            )

    return await _get_sim_result_with_sweep(sim_id, db)


async def _run_dc_sweep(sim_id, circuit_id, body, graph, start_time, db):
    """Run DC sweep and store results."""
    if not body.sweep_source_id:
        raise SolverError("sweep_source_id is required for dc_sweep simulation.")

    result = solve_dc_sweep(
        graph,
        source_id=body.sweep_source_id,
        start=body.sweep_start,
        stop=body.sweep_stop,
        steps=body.sweep_steps,
    )
    duration_ms = int((time.monotonic() - start_time) * 1000)

    await db.execute(
        """INSERT INTO electronics_sim_results
        (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
        VALUES (?, ?, ?, 'complete', NULL, ?, ?, ?)""",
        [sim_id, circuit_id, "dc_sweep", _json.dumps(result.solver_metadata), _now(), duration_ms],
    )

    for i, point in enumerate(result.points):
        for net_id, voltage in point.node_voltages.items():
            await db.execute(
                """INSERT INTO electronics_sweep_points
                (id, sim_result_id, point_index, parameter_value, net_id,
                 voltage_real, voltage_imag, component_id, current, power)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
                [_uuid(), sim_id, i, point.parameter_value, net_id, voltage],
            )
        for comp_id, cr in point.component_results.items():
            await db.execute(
                """INSERT INTO electronics_sweep_points
                (id, sim_result_id, point_index, parameter_value, net_id,
                 voltage_real, voltage_imag, component_id, current, power)
                VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)""",
                [_uuid(), sim_id, i, point.parameter_value, comp_id, cr.current, cr.power],
            )

    return await _get_sim_result_with_sweep(sim_id, db)


async def _run_transient(sim_id, circuit_id, body, graph, start_time, db):
    """Run transient analysis and store waveform results."""
    result = solve_transient(
        graph,
        t_stop=body.t_stop,
        t_step=body.t_step,
    )
    duration_ms = int((time.monotonic() - start_time) * 1000)

    await db.execute(
        """INSERT INTO electronics_sim_results
        (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
        VALUES (?, ?, ?, 'complete', NULL, ?, ?, ?)""",
        [sim_id, circuit_id, "transient", _json.dumps(result.solver_metadata), _now(), duration_ms],
    )

    for i, point in enumerate(result.points):
        for net_id, voltage in point.node_voltages.items():
            await db.execute(
                """INSERT INTO electronics_sweep_points
                (id, sim_result_id, point_index, parameter_value, net_id,
                 voltage_real, voltage_imag, component_id, current, power)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
                [_uuid(), sim_id, i, point.time, net_id, voltage],
            )
        for comp_id, cr in point.component_results.items():
            await db.execute(
                """INSERT INTO electronics_sweep_points
                (id, sim_result_id, point_index, parameter_value, net_id,
                 voltage_real, voltage_imag, component_id, current, power)
                VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)""",
                [_uuid(), sim_id, i, point.time, comp_id, cr.current, cr.power],
            )

    return await _get_sim_result_with_sweep(sim_id, db)


async def _get_sim_result_with_sweep(sim_id: str, db: ModuleUserDB) -> dict:
    """Load a simulation result including sweep data."""
    base = await _get_sim_result_full(sim_id, db)

    sweep_rows = await db.fetch_all(
        """SELECT * FROM electronics_sweep_points
           WHERE sim_result_id = ?
           ORDER BY point_index""",
        [sim_id],
    )

    # Group by point_index
    sweep_data: dict[int, dict] = {}
    for row in sweep_rows:
        idx = row["point_index"]
        if idx not in sweep_data:
            sweep_data[idx] = {
                "point_index": idx,
                "parameter_value": row["parameter_value"],
                "node_voltages": {},
                "component_results": {},
            }
        if row["net_id"]:
            v = row["voltage_real"]
            if row["voltage_imag"] is not None and row["voltage_imag"] != 0:
                v = {"real": row["voltage_real"], "imag": row["voltage_imag"],
                     "magnitude": (row["voltage_real"]**2 + row["voltage_imag"]**2)**0.5,
                     "phase_deg": _atan2_deg(row["voltage_imag"], row["voltage_real"])}
            sweep_data[idx]["node_voltages"][row["net_id"]] = v
        if row["component_id"]:
            sweep_data[idx]["component_results"][row["component_id"]] = {
                "current": row["current"],
                "power": row["power"],
            }

    base["sweep_data"] = sorted(sweep_data.values(), key=lambda x: x["point_index"])
    return base


def _atan2_deg(y: float, x: float) -> float:
    """atan2 in degrees."""
    import math
    return math.degrees(math.atan2(y, x))


# ===================================================================
# ADVANCED ANALYSIS (E4)
# ===================================================================


async def _run_monte_carlo(sim_id, circuit_id, body, graph, start_time, db):
    """Run Monte Carlo tolerance analysis."""
    tolerances = body.mc_tolerances or {}
    result = solve_monte_carlo(graph, tolerances, num_runs=body.mc_runs, seed=body.mc_seed)
    duration_ms = int((time.monotonic() - start_time) * 1000)

    metadata = result.solver_metadata
    metadata["node_statistics"] = result.node_statistics
    metadata["component_statistics"] = result.component_statistics

    await db.execute(
        """INSERT INTO electronics_sim_results
        (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
        VALUES (?, ?, ?, 'complete', NULL, ?, ?, ?)""",
        [sim_id, circuit_id, "monte_carlo", _json.dumps(metadata), _now(), duration_ms],
    )

    return {
        "id": sim_id,
        "circuit_id": circuit_id,
        "sim_type": "monte_carlo",
        "status": "complete",
        "duration_ms": duration_ms,
        "num_runs": result.num_runs,
        "node_statistics": result.node_statistics,
        "component_statistics": result.component_statistics,
    }


async def _run_param_sweep(sim_id, circuit_id, body, graph, start_time, db):
    """Run parameter sweep analysis."""
    if not body.ps_component_id:
        raise SolverError("ps_component_id is required for param_sweep")

    result = solve_parameter_sweep(
        graph,
        component_id=body.ps_component_id,
        param_name=body.ps_param,
        start=body.ps_start,
        stop=body.ps_stop,
        steps=body.ps_steps,
    )
    duration_ms = int((time.monotonic() - start_time) * 1000)

    await db.execute(
        """INSERT INTO electronics_sim_results
        (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
        VALUES (?, ?, ?, 'complete', NULL, ?, ?, ?)""",
        [sim_id, circuit_id, "param_sweep", _json.dumps(result.solver_metadata), _now(), duration_ms],
    )

    # Store sweep points
    for i, (val, res) in enumerate(zip(result.values, result.results)):
        for net_id, voltage in res.node_voltages.items():
            await db.execute(
                """INSERT INTO electronics_sweep_points
                (id, sim_result_id, point_index, parameter_value, net_id,
                 voltage_real, voltage_imag, component_id, current, power)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
                [_uuid(), sim_id, i, val, net_id, voltage],
            )
        for comp_id, cr in res.component_results.items():
            await db.execute(
                """INSERT INTO electronics_sweep_points
                (id, sim_result_id, point_index, parameter_value, net_id,
                 voltage_real, voltage_imag, component_id, current, power)
                VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)""",
                [_uuid(), sim_id, i, val, comp_id, cr.current, cr.power],
            )

    return await _get_sim_result_with_sweep(sim_id, db)


async def _run_temp_sweep(sim_id, circuit_id, body, graph, start_time, db):
    """Run temperature sweep analysis."""
    result = solve_temp_sweep(
        graph,
        t_start=body.temp_start,
        t_stop=body.temp_stop,
        steps=body.temp_steps,
    )
    duration_ms = int((time.monotonic() - start_time) * 1000)

    await db.execute(
        """INSERT INTO electronics_sim_results
        (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
        VALUES (?, ?, ?, 'complete', NULL, ?, ?, ?)""",
        [sim_id, circuit_id, "temp_sweep", _json.dumps(result.solver_metadata), _now(), duration_ms],
    )

    for i, (temp, res) in enumerate(zip(result.temperatures, result.results)):
        for net_id, voltage in res.node_voltages.items():
            await db.execute(
                """INSERT INTO electronics_sweep_points
                (id, sim_result_id, point_index, parameter_value, net_id,
                 voltage_real, voltage_imag, component_id, current, power)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
                [_uuid(), sim_id, i, temp, net_id, voltage],
            )

    return await _get_sim_result_with_sweep(sim_id, db)


# ===================================================================
# SUBCIRCUITS (E4)
# ===================================================================


@router.post("/subcircuits", status_code=201)
async def create_subcircuit(
    body: SubcircuitCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Create a reusable subcircuit definition."""
    sub_id = _uuid()
    now = _now()
    await db.execute(
        """INSERT INTO electronics_subcircuits
        (id, name, description, port_pins, circuit_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [sub_id, body.name, body.description,
         _json.dumps(body.port_pins), _json.dumps(body.circuit_json),
         now, now],
    )
    return {
        "id": sub_id,
        "name": body.name,
        "description": body.description,
        "port_pins": body.port_pins,
        "circuit_json": body.circuit_json,
    }


@router.get("/subcircuits")
async def list_subcircuits(
    db: ModuleUserDB = Depends(get_db),
):
    """List all subcircuit definitions."""
    rows = await db.fetch_all("SELECT * FROM electronics_subcircuits ORDER BY name")
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "port_pins": _json.loads(r["port_pins"]),
            "created_at": r["created_at"],
        })
    return {"items": items}


@router.get("/subcircuits/{subcircuit_id}")
async def get_subcircuit(
    subcircuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Get a subcircuit definition with its internal netlist."""
    row = await db.fetch_one("SELECT * FROM electronics_subcircuits WHERE id = ?", [subcircuit_id])
    if not row:
        raise HTTPException(404, detail={"error": "Subcircuit not found"})
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "port_pins": _json.loads(row["port_pins"]),
        "circuit_json": _json.loads(row["circuit_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.delete("/subcircuits/{subcircuit_id}")
async def delete_subcircuit(
    subcircuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Delete a subcircuit definition."""
    row = await db.fetch_one("SELECT id FROM electronics_subcircuits WHERE id = ?", [subcircuit_id])
    if not row:
        raise HTTPException(404, detail={"error": "Subcircuit not found"})
    await db.execute("DELETE FROM electronics_subcircuit_instances WHERE subcircuit_id = ?", [subcircuit_id])
    await db.execute("DELETE FROM electronics_subcircuits WHERE id = ?", [subcircuit_id])
    return {"deleted": True}


@router.post("/circuits/{circuit_id}/subcircuit-instances", status_code=201)
async def add_subcircuit_instance(
    circuit_id: str,
    body: SubcircuitInstanceCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Place a subcircuit instance in a circuit."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    sub = await db.fetch_one("SELECT id FROM electronics_subcircuits WHERE id = ?", [body.subcircuit_id])
    if not sub:
        raise HTTPException(404, detail={"error": "Subcircuit definition not found"})

    inst_id = _uuid()
    await db.execute(
        """INSERT INTO electronics_subcircuit_instances
        (id, circuit_id, subcircuit_id, port_mapping, x, y, rotation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [inst_id, circuit_id, body.subcircuit_id,
         _json.dumps(body.port_mapping), body.x, body.y, body.rotation, _now()],
    )
    return {
        "id": inst_id,
        "circuit_id": circuit_id,
        "subcircuit_id": body.subcircuit_id,
        "port_mapping": body.port_mapping,
    }


@router.get("/circuits/{circuit_id}/subcircuit-instances")
async def list_subcircuit_instances(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """List subcircuit instances in a circuit."""
    rows = await db.fetch_all(
        """SELECT si.*, s.name as subcircuit_name
           FROM electronics_subcircuit_instances si
           JOIN electronics_subcircuits s ON si.subcircuit_id = s.id
           WHERE si.circuit_id = ?""",
        [circuit_id],
    )
    return {"items": [
        {
            "id": r["id"],
            "subcircuit_id": r["subcircuit_id"],
            "subcircuit_name": r["subcircuit_name"],
            "port_mapping": _json.loads(r["port_mapping"]),
            "x": r["x"],
            "y": r["y"],
        }
        for r in rows
    ]}


@router.delete("/subcircuit-instances/{instance_id}")
async def delete_subcircuit_instance(
    instance_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Remove a subcircuit instance from a circuit."""
    row = await db.fetch_one("SELECT id FROM electronics_subcircuit_instances WHERE id = ?", [instance_id])
    if not row:
        raise HTTPException(404, detail={"error": "Subcircuit instance not found"})
    await db.execute("DELETE FROM electronics_subcircuit_instances WHERE id = ?", [instance_id])
    return {"deleted": True}


# ===================================================================
# EXPORT (E5)
# ===================================================================


@router.get("/circuits/{circuit_id}/export/spice")
async def export_spice(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Export circuit as SPICE netlist (.cir format)."""
    circuit = await db.fetch_one("SELECT * FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    components = await db.fetch_all(
        "SELECT * FROM electronics_components WHERE circuit_id = ?", [circuit_id])
    nets = await db.fetch_all(
        "SELECT * FROM electronics_nets WHERE circuit_id = ?", [circuit_id])
    pins = await db.fetch_all(
        """SELECT p.*, c.circuit_id FROM electronics_pins p
           JOIN electronics_components c ON p.component_id = c.id
           WHERE c.circuit_id = ?""", [circuit_id])

    spice = _exporters.export_spice(
        [dict(c) for c in components],
        [dict(n) for n in nets],
        [dict(p) for p in pins],
        circuit_name=circuit["name"],
    )
    return {"circuit_id": circuit_id, "format": "spice", "content": spice}


@router.get("/circuits/{circuit_id}/export/bom")
async def export_bom(
    circuit_id: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    db: ModuleUserDB = Depends(get_db),
):
    """Export Bill of Materials (JSON or CSV)."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    components = await db.fetch_all(
        "SELECT * FROM electronics_components WHERE circuit_id = ?", [circuit_id])
    bom = _exporters.export_bom([dict(c) for c in components])

    if format == "csv":
        return {"circuit_id": circuit_id, "format": "csv",
                "content": _exporters.export_bom_csv(bom)}
    return {"circuit_id": circuit_id, "format": "json", "items": bom}


@router.get("/results/{result_id}/export/csv")
async def export_waveform_csv(
    result_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Export sweep/transient waveform data as CSV."""
    sim = await db.fetch_one("SELECT * FROM electronics_sim_results WHERE id = ?", [result_id])
    if not sim:
        raise HTTPException(404, detail={"error": "Result not found"})

    sweep_rows = await db.fetch_all(
        "SELECT * FROM electronics_sweep_points WHERE sim_result_id = ? ORDER BY point_index",
        [result_id])

    # Group into points
    points: dict[int, dict] = {}
    for row in sweep_rows:
        idx = row["point_index"]
        if idx not in points:
            points[idx] = {"parameter_value": row["parameter_value"],
                           "node_voltages": {}, "component_results": {}}
        if row["net_id"]:
            points[idx]["node_voltages"][row["net_id"]] = row["voltage_real"]
        if row["component_id"]:
            points[idx]["component_results"][row["component_id"]] = {"current": row["current"]}

    sweep_data = sorted(points.values(), key=lambda x: x["parameter_value"])
    csv_content = _exporters.export_waveform_csv(sweep_data)
    return {"result_id": result_id, "format": "csv", "content": csv_content}


@router.get("/circuits/{circuit_id}/export/bundle")
async def export_circuit_bundle(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Export full circuit as JSON bundle (for import/sharing)."""
    circuit = await db.fetch_one("SELECT * FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    components = await db.fetch_all(
        "SELECT * FROM electronics_components WHERE circuit_id = ?", [circuit_id])
    nets = await db.fetch_all(
        "SELECT * FROM electronics_nets WHERE circuit_id = ?", [circuit_id])
    pins = await db.fetch_all(
        """SELECT p.*, c.circuit_id FROM electronics_pins p
           JOIN electronics_components c ON p.component_id = c.id
           WHERE c.circuit_id = ?""", [circuit_id])
    wires = await db.fetch_all(
        "SELECT * FROM electronics_wire_segments WHERE circuit_id = ?", [circuit_id])

    bundle = _exporters.export_circuit_bundle(
        dict(circuit), [dict(c) for c in components],
        [dict(n) for n in nets], [dict(p) for p in pins],
        [dict(w) for w in wires],
    )
    return bundle


# ===================================================================
# TEMPLATES (E5)
# ===================================================================


@router.get("/templates")
async def list_templates():
    """List available circuit templates."""
    return {"items": _templates.list_templates()}


@router.post("/circuits/from-template", status_code=201)
async def create_from_template(
    template_id: str = Query(...),
    name: str = Query(None),
    db: ModuleUserDB = Depends(get_db),
):
    """Create a circuit from a built-in template."""
    tmpl = _templates.get_template(template_id)
    if not tmpl:
        raise HTTPException(404, detail={
            "error": f"Template '{template_id}' not found",
            "suggestion": f"Available: {', '.join(_templates.TEMPLATES.keys())}",
        })

    circuit_name = name or tmpl["circuit"]["name"]
    circuit_id = _uuid()
    now = _now()

    await db.execute(
        """INSERT INTO electronics_circuits
        (id, name, description, canvas_width, canvas_height, created_at, updated_at)
        VALUES (?, ?, ?, 1200, 800, ?, ?)""",
        [circuit_id, circuit_name, tmpl["circuit"].get("description", ""), now, now],
    )

    # Create nets from template connections
    net_ids: dict[str, str] = {}  # net_name -> net_id

    for comp_def in tmpl["components"]:
        for pin_name, net_name in comp_def.get("pins", {}).items():
            if net_name not in net_ids:
                net_id = _uuid()
                net_type = "ground" if net_name.upper() == "GND" else "signal"
                await db.execute(
                    "INSERT INTO electronics_nets (id, circuit_id, name, net_type, color) VALUES (?, ?, ?, ?, '')",
                    [net_id, circuit_id, net_name, net_type],
                )
                net_ids[net_name] = net_id

    # Create components and wire pins
    for comp_def in tmpl["components"]:
        comp_id = _uuid()
        ctype = comp_def["type"]
        value = comp_def.get("value", "")
        ref = comp_def.get("ref", "")
        params = comp_def.get("params", {})
        props_json = _json.dumps(params) if params else "{}"

        await db.execute(
            """INSERT INTO electronics_components
            (id, circuit_id, catalogue_path, ref_designator, component_type,
             value, unit, x, y, rotation, properties, created_at)
            VALUES (?, ?, '', ?, ?, ?, '', 0, 0, 0, ?, ?)""",
            [comp_id, circuit_id, ref, ctype, value, props_json, now],
        )

        # Create and connect pins
        comp_type_def = get_component_type(ctype)
        pin_names = comp_type_def["pins"] if comp_type_def else []
        for pin_name in pin_names:
            pin_id = _uuid()
            net_name = comp_def.get("pins", {}).get(pin_name)
            net_id = net_ids.get(net_name) if net_name else None
            await db.execute(
                "INSERT INTO electronics_pins (id, component_id, pin_name, net_id) VALUES (?, ?, ?, ?)",
                [pin_id, comp_id, pin_name, net_id],
            )

    return {
        "id": circuit_id,
        "name": circuit_name,
        "template_id": template_id,
        "components": len(tmpl["components"]),
    }


# ===================================================================
# MCU CO-SIMULATION (E7)
# ===================================================================


@router.post("/circuits/{circuit_id}/mcu/{component_id}/program")
async def set_mcu_program(
    circuit_id: str,
    component_id: str,
    body: MCUProgramUpload,
    db: ModuleUserDB = Depends(get_db),
):
    """Set the Python tick function for an MCU component."""
    _mcu = _elec_import("mcu_sandbox")
    source_code = body.source_code

    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    comp = await db.fetch_one(
        "SELECT * FROM electronics_components WHERE id = ? AND circuit_id = ?",
        [component_id, circuit_id])
    if not comp:
        raise HTTPException(404, detail={"error": "Component not found"})
    if comp["component_type"] != "mcu":
        raise HTTPException(400, detail={"error": "Component is not an MCU"})

    # Validate by compiling
    try:
        _mcu.compile_tick_function(source_code)
    except _mcu.MCUSandboxError as e:
        raise HTTPException(400, detail={"error": str(e)})

    now = _now()
    existing = await db.fetch_one(
        "SELECT id FROM electronics_mcu_programs WHERE circuit_id = ? AND component_id = ?",
        [circuit_id, component_id])

    if existing:
        await db.execute(
            "UPDATE electronics_mcu_programs SET source_code = ?, updated_at = ? WHERE id = ?",
            [source_code, now, existing["id"]])
        prog_id = existing["id"]
    else:
        prog_id = _uuid()
        await db.execute(
            """INSERT INTO electronics_mcu_programs
            (id, circuit_id, component_id, source_code, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [prog_id, circuit_id, component_id, source_code, now, now])

    return {"id": prog_id, "component_id": component_id, "status": "compiled"}


@router.get("/circuits/{circuit_id}/mcu/{component_id}/program")
async def get_mcu_program(
    circuit_id: str,
    component_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Get the current MCU program for a component."""
    row = await db.fetch_one(
        "SELECT * FROM electronics_mcu_programs WHERE circuit_id = ? AND component_id = ?",
        [circuit_id, component_id])
    if not row:
        raise HTTPException(404, detail={"error": "No program found for this MCU"})
    return {
        "id": row["id"],
        "component_id": component_id,
        "source_code": row["source_code"],
        "updated_at": row["updated_at"],
    }


@router.delete("/circuits/{circuit_id}/mcu/{component_id}/program")
async def delete_mcu_program(
    circuit_id: str,
    component_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Delete the MCU program for a component."""
    row = await db.fetch_one(
        "SELECT id FROM electronics_mcu_programs WHERE circuit_id = ? AND component_id = ?",
        [circuit_id, component_id])
    if not row:
        raise HTTPException(404, detail={"error": "No program found for this MCU"})
    await db.execute("DELETE FROM electronics_mcu_programs WHERE id = ?", [row["id"]])
    return {"deleted": True}


# ===================================================================
# EDUCATIONAL (E6)
# ===================================================================


@router.post("/calculators/voltage-divider")
async def calc_voltage_divider(
    v_in: float = Query(...),
    r1: float = Query(...),
    r2: float = Query(...),
):
    """Calculate voltage divider output."""
    return _education.voltage_divider(v_in, r1, r2)


@router.post("/calculators/led-resistor")
async def calc_led_resistor(
    v_supply: float = Query(...),
    v_led: float = Query(2.0),
    i_led_ma: float = Query(20.0),
):
    """Calculate LED current-limiting resistor value."""
    return _education.led_resistor(v_supply, v_led, i_led_ma)


@router.post("/calculators/rc-filter")
async def calc_rc_filter(
    r: float = Query(...),
    c: float = Query(...),
):
    """Calculate RC filter cutoff frequency."""
    return _education.rc_filter(r, c)


@router.post("/calculators/bjt-bias")
async def calc_bjt_bias(
    vcc: float = Query(...),
    ic_ma: float = Query(...),
    beta: float = Query(100.0),
    vce: float = Query(None),
):
    """Calculate BJT bias resistors for common-emitter configuration."""
    return _education.bjt_bias(vcc, ic_ma, beta, vce)


@router.get("/circuits/{circuit_id}/explain-mna")
async def explain_mna(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Get step-by-step MNA matrix construction explanation."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    components = await db.fetch_all(
        "SELECT * FROM electronics_components WHERE circuit_id = ?", [circuit_id])
    nets = await db.fetch_all(
        "SELECT * FROM electronics_nets WHERE circuit_id = ?", [circuit_id])
    pins = await db.fetch_all(
        """SELECT p.*, c.circuit_id FROM electronics_pins p
           JOIN electronics_components c ON p.component_id = c.id
           WHERE c.circuit_id = ?""", [circuit_id])

    steps = _education.explain_mna(
        [dict(c) for c in components],
        [dict(n) for n in nets],
        [dict(p) for p in pins],
    )
    return {"circuit_id": circuit_id, "steps": steps, "total_steps": len(steps)}


# ===================================================================
# WIRE SEGMENTS & JUNCTIONS (E1b)
# ===================================================================


@router.get("/circuits/{circuit_id}/wires")
async def list_wires(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """List all wire segments and junctions for a circuit."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    segments = await db.fetch_all(
        "SELECT * FROM electronics_wire_segments WHERE circuit_id = ? ORDER BY sort_order",
        [circuit_id],
    )
    junctions = await db.fetch_all(
        "SELECT * FROM electronics_junctions WHERE circuit_id = ?",
        [circuit_id],
    )
    return {
        "wire_segments": [dict(s) for s in segments],
        "junctions": [dict(j) for j in junctions],
    }


@router.post("/circuits/{circuit_id}/wires", status_code=201)
async def create_wire(
    circuit_id: str,
    body: WireSegmentCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Create a wire segment. Auto-creates or reuses net."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    # Resolve net
    net_id = body.net_id
    if not net_id and body.net_name:
        net = await db.fetch_one(
            "SELECT id FROM electronics_nets WHERE circuit_id = ? AND name = ?",
            [circuit_id, body.net_name],
        )
        if net:
            net_id = net["id"]
        else:
            net_id = _uuid()
            net_type = "ground" if body.net_name.upper() == "GND" else "signal"
            await db.execute(
                "INSERT INTO electronics_nets (id, circuit_id, name, net_type, color) VALUES (?, ?, ?, ?, '')",
                [net_id, circuit_id, body.net_name, net_type],
            )
    elif not net_id:
        # Generate a new net name
        existing = await db.fetch_all(
            "SELECT name FROM electronics_nets WHERE circuit_id = ?", [circuit_id]
        )
        existing_names = {r["name"] for r in existing}
        i = 1
        while f"N{i:03d}" in existing_names:
            i += 1
        net_name = f"N{i:03d}"
        net_id = _uuid()
        await db.execute(
            "INSERT INTO electronics_nets (id, circuit_id, name, net_type, color) VALUES (?, ?, ?, 'signal', '')",
            [net_id, circuit_id, net_name],
        )

    seg_id = _uuid()
    await db.execute(
        """INSERT INTO electronics_wire_segments (id, circuit_id, net_id, x1, y1, x2, y2, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
        [seg_id, circuit_id, net_id, body.x1, body.y1, body.x2, body.y2],
    )
    await db.execute("UPDATE electronics_circuits SET updated_at = ? WHERE id = ?", [_now(), circuit_id])

    return {"id": seg_id, "circuit_id": circuit_id, "net_id": net_id,
            "x1": body.x1, "y1": body.y1, "x2": body.x2, "y2": body.y2}


@router.delete("/wires/{wire_id}")
async def delete_wire(
    wire_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Delete a wire segment."""
    wire = await db.fetch_one("SELECT circuit_id FROM electronics_wire_segments WHERE id = ?", [wire_id])
    if not wire:
        raise HTTPException(404, detail={"error": "Wire segment not found"})

    await db.execute("DELETE FROM electronics_wire_segments WHERE id = ?", [wire_id])
    await db.execute("UPDATE electronics_circuits SET updated_at = ? WHERE id = ?", [_now(), wire["circuit_id"]])
    return {"deleted": True}


@router.post("/circuits/{circuit_id}/wires/split", status_code=201)
async def split_wire(
    circuit_id: str,
    body: WireSplitRequest,
    db: ModuleUserDB = Depends(get_db),
):
    """Split a wire segment at a point, creating a junction and two new segments."""
    wire = await db.fetch_one(
        "SELECT * FROM electronics_wire_segments WHERE id = ? AND circuit_id = ?",
        [body.wire_id, circuit_id],
    )
    if not wire:
        raise HTTPException(404, detail={"error": "Wire segment not found in this circuit"})

    net_id = wire["net_id"]

    # Create junction at split point
    junction_id = _uuid()
    await db.execute(
        "INSERT INTO electronics_junctions (id, circuit_id, net_id, x, y) VALUES (?, ?, ?, ?, ?)",
        [junction_id, circuit_id, net_id, body.x, body.y],
    )

    # Create two new segments (original start → split, split → original end)
    seg1_id = _uuid()
    seg2_id = _uuid()
    await db.execute(
        """INSERT INTO electronics_wire_segments (id, circuit_id, net_id, x1, y1, x2, y2, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
        [seg1_id, circuit_id, net_id, wire["x1"], wire["y1"], body.x, body.y],
    )
    await db.execute(
        """INSERT INTO electronics_wire_segments (id, circuit_id, net_id, x1, y1, x2, y2, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
        [seg2_id, circuit_id, net_id, body.x, body.y, wire["x2"], wire["y2"]],
    )

    # Delete original segment
    await db.execute("DELETE FROM electronics_wire_segments WHERE id = ?", [body.wire_id])
    await db.execute("UPDATE electronics_circuits SET updated_at = ? WHERE id = ?", [_now(), circuit_id])

    return {
        "junction": {"id": junction_id, "net_id": net_id, "x": body.x, "y": body.y},
        "segments": [
            {"id": seg1_id, "net_id": net_id, "x1": wire["x1"], "y1": wire["y1"], "x2": body.x, "y2": body.y},
            {"id": seg2_id, "net_id": net_id, "x1": body.x, "y1": body.y, "x2": wire["x2"], "y2": wire["y2"]},
        ],
    }


@router.post("/circuits/{circuit_id}/wires/auto-route", status_code=201)
async def auto_route(
    circuit_id: str,
    body: AutoRouteRequest,
    db: ModuleUserDB = Depends(get_db),
):
    """Generate Manhattan-routed wire segments between two points."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    # Resolve net
    net_id = body.net_id
    if not net_id and body.net_name:
        net = await db.fetch_one(
            "SELECT id FROM electronics_nets WHERE circuit_id = ? AND name = ?",
            [circuit_id, body.net_name],
        )
        if net:
            net_id = net["id"]
        else:
            net_id = _uuid()
            net_type = "ground" if body.net_name.upper() == "GND" else "signal"
            await db.execute(
                "INSERT INTO electronics_nets (id, circuit_id, name, net_type, color) VALUES (?, ?, ?, ?, '')",
                [net_id, circuit_id, body.net_name, net_type],
            )
    elif not net_id:
        existing = await db.fetch_all(
            "SELECT name FROM electronics_nets WHERE circuit_id = ?", [circuit_id]
        )
        existing_names = {r["name"] for r in existing}
        i = 1
        while f"N{i:03d}" in existing_names:
            i += 1
        net_id = _uuid()
        await db.execute(
            "INSERT INTO electronics_nets (id, circuit_id, name, net_type, color) VALUES (?, ?, ?, 'signal', '')",
            [net_id, circuit_id, f"N{i:03d}"],
        )

    # Generate Manhattan path
    segments = []
    if body.from_x == body.to_x or body.from_y == body.to_y:
        # Straight line — single segment
        seg_id = _uuid()
        await db.execute(
            """INSERT INTO electronics_wire_segments (id, circuit_id, net_id, x1, y1, x2, y2, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
            [seg_id, circuit_id, net_id, body.from_x, body.from_y, body.to_x, body.to_y],
        )
        segments.append({"id": seg_id, "net_id": net_id,
                         "x1": body.from_x, "y1": body.from_y, "x2": body.to_x, "y2": body.to_y})
    else:
        # Two segments forming an L
        if body.route_style == "horizontal_first":
            mid_x, mid_y = body.to_x, body.from_y
        else:
            mid_x, mid_y = body.from_x, body.to_y

        seg1_id = _uuid()
        seg2_id = _uuid()
        await db.execute(
            """INSERT INTO electronics_wire_segments (id, circuit_id, net_id, x1, y1, x2, y2, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
            [seg1_id, circuit_id, net_id, body.from_x, body.from_y, mid_x, mid_y],
        )
        await db.execute(
            """INSERT INTO electronics_wire_segments (id, circuit_id, net_id, x1, y1, x2, y2, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            [seg2_id, circuit_id, net_id, mid_x, mid_y, body.to_x, body.to_y],
        )
        segments.append({"id": seg1_id, "net_id": net_id,
                         "x1": body.from_x, "y1": body.from_y, "x2": mid_x, "y2": mid_y})
        segments.append({"id": seg2_id, "net_id": net_id,
                         "x1": mid_x, "y1": mid_y, "x2": body.to_x, "y2": body.to_y})

    await db.execute("UPDATE electronics_circuits SET updated_at = ? WHERE id = ?", [_now(), circuit_id])
    return {"net_id": net_id, "segments": segments}


# ===================================================================
# DESIGN RULE CHECKING (E1b)
# ===================================================================


@router.get("/circuits/{circuit_id}/drc")
async def run_drc(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Run static design rule checks. Returns warnings, not errors."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    components = await db.fetch_all(
        "SELECT * FROM electronics_components WHERE circuit_id = ?", [circuit_id]
    )
    nets = await db.fetch_all(
        "SELECT * FROM electronics_nets WHERE circuit_id = ?", [circuit_id]
    )
    pins = await db.fetch_all(
        """SELECT p.*, c.component_type, c.ref_designator
           FROM electronics_pins p
           JOIN electronics_components c ON p.component_id = c.id
           WHERE c.circuit_id = ?""",
        [circuit_id],
    )

    warnings = []

    # Check 1: No ground present
    has_ground = any(n["net_type"] == "ground" for n in nets)
    if not has_ground and components:
        warnings.append({
            "type": "no_ground",
            "severity": "error",
            "message": "No ground reference. Every circuit needs a ground component.",
            "component_ids": [],
            "net_ids": [],
        })

    # Check 2: Component with all pins unconnected
    comp_pins: dict[str, list] = {}
    for pin in pins:
        cid = pin["component_id"]
        if cid not in comp_pins:
            comp_pins[cid] = []
        comp_pins[cid].append(pin)

    for comp in components:
        cpins = comp_pins.get(comp["id"], [])
        if comp["component_type"] == "ground":
            continue  # ground only has 1 pin, auto-connected
        all_disconnected = all(p["net_id"] is None for p in cpins)
        if all_disconnected and cpins:
            warnings.append({
                "type": "unconnected_component",
                "severity": "warning",
                "message": f"{comp['ref_designator']} has no connected pins.",
                "component_ids": [comp["id"]],
                "net_ids": [],
            })

    # Check 3: Net with only 1 pin (dangling wire)
    net_pin_counts: dict[str, int] = {}
    for pin in pins:
        if pin["net_id"]:
            net_pin_counts[pin["net_id"]] = net_pin_counts.get(pin["net_id"], 0) + 1

    for net in nets:
        count = net_pin_counts.get(net["id"], 0)
        if count == 1:
            warnings.append({
                "type": "dangling_net",
                "severity": "warning",
                "message": f"Net '{net['name']}' has only 1 pin connected (dangling wire).",
                "component_ids": [],
                "net_ids": [net["id"]],
            })

    # Check 4: Resistor with very low value
    for comp in components:
        if comp["component_type"] == "resistor":
            try:
                val = float(comp["value"])
                if val < 0.1:
                    warnings.append({
                        "type": "low_resistance",
                        "severity": "warning",
                        "message": f"{comp['ref_designator']} has resistance {val}Ω (< 0.1Ω). Possible wrong units.",
                        "component_ids": [comp["id"]],
                        "net_ids": [],
                    })
            except (ValueError, TypeError):
                pass

    # Check 5: Parallel voltage sources (same two nets)
    vs_nets = []
    for comp in components:
        if comp["component_type"] == "voltage_source":
            cpins = comp_pins.get(comp["id"], [])
            pin_nets = sorted([p["net_id"] for p in cpins if p["net_id"]])
            if len(pin_nets) == 2:
                vs_nets.append((comp, tuple(pin_nets)))

    seen_pairs: dict[tuple, list] = {}
    for comp, pair in vs_nets:
        if pair in seen_pairs:
            seen_pairs[pair].append(comp)
        else:
            seen_pairs[pair] = [comp]
    for pair, comps in seen_pairs.items():
        if len(comps) > 1:
            warnings.append({
                "type": "parallel_voltage_sources",
                "severity": "error",
                "message": f"Voltage sources {', '.join(c['ref_designator'] for c in comps)} are in parallel.",
                "component_ids": [c["id"] for c in comps],
                "net_ids": list(pair),
            })

    return {"warnings": warnings, "count": len(warnings)}


# ===================================================================
# REGIONS (E1b)
# ===================================================================


@router.get("/circuits/{circuit_id}/regions")
async def list_regions(
    circuit_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """List all regions for a circuit with their members."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    regions = await db.fetch_all(
        "SELECT * FROM electronics_regions WHERE circuit_id = ? ORDER BY name",
        [circuit_id],
    )

    result = []
    for region in regions:
        members = await db.fetch_all(
            "SELECT * FROM electronics_region_members WHERE region_id = ?",
            [region["id"]],
        )
        result.append({**dict(region), "members": [dict(m) for m in members]})

    return {"items": result}


@router.post("/circuits/{circuit_id}/regions", status_code=201)
async def create_region(
    circuit_id: str,
    body: RegionCreate,
    db: ModuleUserDB = Depends(get_db),
):
    """Create a named region for annotation."""
    circuit = await db.fetch_one("SELECT id FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    region_id = _uuid()
    await db.execute(
        """INSERT INTO electronics_regions (id, circuit_id, name, color, description, created_by)
        VALUES (?, ?, ?, ?, ?, ?)""",
        [region_id, circuit_id, body.name, body.color, body.description, body.created_by],
    )

    return {"id": region_id, "circuit_id": circuit_id, "name": body.name,
            "color": body.color, "description": body.description,
            "created_by": body.created_by, "members": []}


@router.put("/regions/{region_id}")
async def update_region(
    region_id: str,
    body: RegionUpdate,
    db: ModuleUserDB = Depends(get_db),
):
    """Update region name, color, or description."""
    region = await db.fetch_one("SELECT * FROM electronics_regions WHERE id = ?", [region_id])
    if not region:
        raise HTTPException(404, detail={"error": "Region not found"})

    updates = []
    params = []
    for field in ["name", "color", "description"]:
        val = getattr(body, field, None)
        if val is not None:
            updates.append(f"{field} = ?")
            params.append(val)

    if updates:
        params.append(region_id)
        await db.execute(
            f"UPDATE electronics_regions SET {', '.join(updates)} WHERE id = ?",
            params,
        )

    row = await db.fetch_one("SELECT * FROM electronics_regions WHERE id = ?", [region_id])
    members = await db.fetch_all(
        "SELECT * FROM electronics_region_members WHERE region_id = ?", [region_id]
    )
    return {**dict(row), "members": [dict(m) for m in members]}


@router.delete("/regions/{region_id}")
async def delete_region(
    region_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Delete a region and its members."""
    region = await db.fetch_one("SELECT id FROM electronics_regions WHERE id = ?", [region_id])
    if not region:
        raise HTTPException(404, detail={"error": "Region not found"})

    await db.execute("DELETE FROM electronics_region_members WHERE region_id = ?", [region_id])
    await db.execute("DELETE FROM electronics_regions WHERE id = ?", [region_id])
    return {"deleted": True}


@router.post("/regions/{region_id}/members", status_code=201)
async def add_region_member(
    region_id: str,
    body: RegionMemberAdd,
    db: ModuleUserDB = Depends(get_db),
):
    """Add a component or net to a region."""
    region = await db.fetch_one("SELECT * FROM electronics_regions WHERE id = ?", [region_id])
    if not region:
        raise HTTPException(404, detail={"error": "Region not found"})

    if body.member_type not in ("component", "net"):
        raise HTTPException(400, detail={
            "error": f"Invalid member_type: {body.member_type}",
            "suggestion": "Use 'component' or 'net'",
        })

    # Check for duplicate
    existing = await db.fetch_one(
        "SELECT id FROM electronics_region_members WHERE region_id = ? AND member_type = ? AND member_id = ?",
        [region_id, body.member_type, body.member_id],
    )
    if existing:
        return {"id": existing["id"], "region_id": region_id,
                "member_type": body.member_type, "member_id": body.member_id}

    member_id = _uuid()
    await db.execute(
        "INSERT INTO electronics_region_members (id, region_id, member_type, member_id) VALUES (?, ?, ?, ?)",
        [member_id, region_id, body.member_type, body.member_id],
    )

    return {"id": member_id, "region_id": region_id,
            "member_type": body.member_type, "member_id": body.member_id}


@router.delete("/regions/{region_id}/members/{member_id}")
async def remove_region_member(
    region_id: str,
    member_id: str,
    db: ModuleUserDB = Depends(get_db),
):
    """Remove a member from a region."""
    member = await db.fetch_one(
        "SELECT id FROM electronics_region_members WHERE id = ? AND region_id = ?",
        [member_id, region_id],
    )
    if not member:
        raise HTTPException(404, detail={"error": "Region member not found"})

    await db.execute("DELETE FROM electronics_region_members WHERE id = ?", [member_id])
    return {"deleted": True}


# ===================================================================
# COMPONENT LIBRARY
# ===================================================================


@router.get("/library")
async def list_library():
    """List available built-in component types."""
    items = []
    for type_key, typedef in COMPONENT_TYPES.items():
        items.append({
            "type": type_key,
            "label": typedef["label"],
            "pins": typedef["pins"],
            "value_unit": typedef["value_unit"],
            "value_label": typedef["value_label"],
            "default_value": typedef["default_value"],
            "description": typedef["description"],
        })
    return {"items": items}


@router.get("/library/{component_type}")
async def get_component_type_detail(component_type: str):
    """Get full detail for a component type."""
    ct = get_component_type(component_type)
    if not ct:
        raise HTTPException(404, detail={
            "error": f"Unknown component type: {component_type}",
            "suggestion": f"Valid types: {', '.join(COMPONENT_TYPES.keys())}",
        })
    return {"type": component_type, **ct}


@router.get("/library/{component_type}/models")
async def list_component_models(component_type: str):
    """List available preset models for a component type (e.g. 1N4148 for diode)."""
    _dm = _elec_import("device_models")

    preset_map = {
        "diode": _dm.DIODE_PRESETS,
        "zener": _dm.ZENER_PRESETS,
        "led": _dm.LED_PRESETS,
    }

    bjt_map = {"npn_bjt": False, "pnp_bjt": True}
    mosfet_map = {"nmos": False, "pmos": True}

    if component_type in preset_map:
        presets = preset_map[component_type]
        items = []
        for name, model in presets.items():
            if name == "default":
                continue
            params = {k: v for k, v in model.__dict__.items() if not k.startswith("_")}
            items.append({"name": name, "params": params})
        return {"component_type": component_type, "models": items}

    if component_type in bjt_map:
        items = []
        for name, (model, is_pnp) in _dm.BJT_PRESETS.items():
            if name.startswith("default"):
                continue
            # Filter by NPN/PNP
            expected_pnp = bjt_map[component_type]
            if is_pnp != expected_pnp:
                continue
            params = {k: v for k, v in model.__dict__.items() if not k.startswith("_")}
            items.append({"name": name, "params": params})
        return {"component_type": component_type, "models": items}

    if component_type in mosfet_map:
        items = []
        for name, (model, is_pmos) in _dm.MOSFET_PRESETS.items():
            if name.startswith("default"):
                continue
            expected_pmos = mosfet_map[component_type]
            if is_pmos != expected_pmos:
                continue
            params = {k: v for k, v in model.__dict__.items() if not k.startswith("_")}
            items.append({"name": name, "params": params})
        return {"component_type": component_type, "models": items}

    if component_type == "opamp":
        return {"component_type": "opamp", "models": []}

    ct = get_component_type(component_type)
    if not ct:
        raise HTTPException(404, detail={"error": f"Unknown component type: {component_type}"})
    return {"component_type": component_type, "models": []}


# ===================================================================
# INTERNAL HELPERS
# ===================================================================


async def _get_circuit_full(circuit_id: str, db: ModuleUserDB) -> dict:
    """Load a complete circuit with components, nets, pins, and last sim result."""
    circuit = await db.fetch_one("SELECT * FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    components = await db.fetch_all(
        "SELECT * FROM electronics_components WHERE circuit_id = ? ORDER BY ref_designator",
        [circuit_id],
    )
    nets = await db.fetch_all(
        "SELECT * FROM electronics_nets WHERE circuit_id = ? ORDER BY name",
        [circuit_id],
    )

    # Attach pins to components
    comp_list = []
    for comp in components:
        pins = await db.fetch_all(
            """SELECT p.id, p.pin_name, p.net_id, n.name as net_name
               FROM electronics_pins p
               LEFT JOIN electronics_nets n ON p.net_id = n.id
               WHERE p.component_id = ?""",
            [comp["id"]],
        )
        comp_list.append({**dict(comp), "pins": [dict(p) for p in pins]})

    # Wire segments and junctions
    wire_segments = await db.fetch_all(
        "SELECT * FROM electronics_wire_segments WHERE circuit_id = ? ORDER BY sort_order",
        [circuit_id],
    )
    junctions = await db.fetch_all(
        "SELECT * FROM electronics_junctions WHERE circuit_id = ?",
        [circuit_id],
    )

    # Latest sim result
    last_sim = await db.fetch_one(
        "SELECT id, sim_type, status, error_message, ran_at, duration_ms FROM electronics_sim_results WHERE circuit_id = ? ORDER BY ran_at DESC LIMIT 1",
        [circuit_id],
    )

    return {
        **dict(circuit),
        "components": comp_list,
        "nets": [dict(n) for n in nets],
        "wire_segments": [dict(w) for w in wire_segments],
        "junctions": [dict(j) for j in junctions],
        "last_sim_result": dict(last_sim) if last_sim else None,
    }


async def _get_component_with_pins(component_id: str, db: ModuleUserDB) -> dict:
    """Load a component with its pins."""
    comp = await db.fetch_one("SELECT * FROM electronics_components WHERE id = ?", [component_id])
    if not comp:
        raise HTTPException(404, detail={"error": "Component not found"})

    pins = await db.fetch_all(
        """SELECT p.id, p.pin_name, p.net_id, n.name as net_name
           FROM electronics_pins p
           LEFT JOIN electronics_nets n ON p.net_id = n.id
           WHERE p.component_id = ?""",
        [component_id],
    )

    return {**dict(comp), "pins": [dict(p) for p in pins]}


async def _get_sim_result_full(sim_id: str, db: ModuleUserDB) -> dict:
    """Load a simulation result with per-node and per-component data."""
    sim = await db.fetch_one("SELECT * FROM electronics_sim_results WHERE id = ?", [sim_id])
    if not sim:
        raise HTTPException(404, detail={"error": "Simulation result not found"})

    node_results = await db.fetch_all(
        """SELECT nr.*, n.name as net_name, n.net_type
           FROM electronics_sim_node_results nr
           JOIN electronics_nets n ON nr.net_id = n.id
           WHERE nr.sim_result_id = ?""",
        [sim_id],
    )

    comp_results = await db.fetch_all(
        """SELECT cr.*, c.ref_designator, c.component_type, c.value, c.unit
           FROM electronics_sim_component_results cr
           JOIN electronics_components c ON cr.component_id = c.id
           WHERE cr.sim_result_id = ?""",
        [sim_id],
    )

    result = dict(sim)
    if result.get("result_data"):
        try:
            result["result_data"] = _json.loads(result["result_data"])
        except (ValueError, TypeError):
            pass

    result["node_results"] = [dict(r) for r in node_results]
    result["component_results"] = [dict(r) for r in comp_results]

    return result
