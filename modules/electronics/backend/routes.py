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

get_component_type = _c.get_component_type
get_ref_prefix = _c.get_ref_prefix
get_pins = _c.get_pins
validate_component_type = _c.validate_component_type
COMPONENT_TYPES = _c.COMPONENT_TYPES

CircuitGraph = _solver.CircuitGraph
ComponentInstance = _solver.ComponentInstance
SolverError = _solver.SolverError
solve_dc_op = _solver.solve_dc_op


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

    unit = body.unit
    if not unit:
        ct = get_component_type(body.component_type)
        unit = ct["value_unit"] if ct else ""

    comp_id = _uuid()
    await db.execute(
        """INSERT INTO electronics_components
        (id, circuit_id, catalogue_path, ref_designator, component_type, value, unit, x, y, rotation, properties, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)""",
        [comp_id, circuit_id, body.catalogue_path, ref_designator, body.component_type, value, unit, body.x, body.y, body.rotation, _now()],
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
            updates.append(f"{field} = ?")
            params.append(val)

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
    """Run DC operating point analysis on the circuit."""
    if body is None:
        body = SimulateRequest()

    circuit = await db.fetch_one("SELECT * FROM electronics_circuits WHERE id = ?", [circuit_id])
    if not circuit:
        raise HTTPException(404, detail={"error": "Circuit not found"})

    # Load full circuit graph
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

    # Build solver graph
    ground_net_id = None
    for net in nets:
        if net["net_type"] == "ground":
            ground_net_id = net["id"]
            break

    node_ids = [n["id"] for n in nets]

    # Map pins to components
    pin_map: dict[str, dict[str, str | None]] = {}  # component_id -> {pin_name: net_id}
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

        solver_components.append(ComponentInstance(
            id=comp["id"],
            component_type=comp["component_type"],
            value=value,
            pins=pin_map.get(comp["id"], {}),
        ))

    graph = CircuitGraph(
        ground_net_id=ground_net_id,
        nodes=node_ids,
        components=solver_components,
    )

    # Run solver
    sim_id = _uuid()
    start_time = time.monotonic()

    try:
        result = solve_dc_op(graph)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Store results
        await db.execute(
            """INSERT INTO electronics_sim_results
            (id, circuit_id, sim_type, status, error_message, result_data, ran_at, duration_ms)
            VALUES (?, ?, ?, 'complete', NULL, ?, ?, ?)""",
            [sim_id, circuit_id, body.sim_type, _json.dumps(result.solver_metadata), _now(), duration_ms],
        )

        # Store per-net results
        for net_id, voltage in result.node_voltages.items():
            await db.execute(
                "INSERT INTO electronics_sim_node_results (id, sim_result_id, net_id, voltage) VALUES (?, ?, ?, ?)",
                [_uuid(), sim_id, net_id, voltage],
            )

        # Store per-component results
        for comp_id, cr in result.component_results.items():
            await db.execute(
                """INSERT INTO electronics_sim_component_results
                (id, sim_result_id, component_id, current, power, voltage_drop)
                VALUES (?, ?, ?, ?, ?, ?)""",
                [_uuid(), sim_id, comp_id, cr.current, cr.power, cr.voltage_drop],
            )

        return await _get_sim_result_full(sim_id, db)

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

    # Latest sim result
    last_sim = await db.fetch_one(
        "SELECT id, sim_type, status, error_message, ran_at, duration_ms FROM electronics_sim_results WHERE circuit_id = ? ORDER BY ran_at DESC LIMIT 1",
        [circuit_id],
    )

    return {
        **dict(circuit),
        "components": comp_list,
        "nets": [dict(n) for n in nets],
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
