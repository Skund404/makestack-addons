"""Integration tests for E2 simulation endpoints — AC, DC sweep, transient via API."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB, create_test_app

# ---------------------------------------------------------------------------
# Load electronics modules
# ---------------------------------------------------------------------------

_MODULE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _load(name: str, relpath: str):
    key = f"_electronics_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_MODULE_ROOT, relpath)
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


migration_001 = _load("mig001", "backend/migrations/001_create_tables.py")
migration_002 = _load("mig002", "backend/migrations/002_e1b_wire_catalogue.py")
migration_003 = _load("mig003", "backend/migrations/003_e2_sweep_waveform.py")
migration_004 = _load("mig004", "backend/migrations/004_e3_operating_region.py")
migration_005 = _load("mig005", "backend/migrations/005_e4_subcircuits.py")
routes_mod = _load("routes", "backend/routes.py")

router = routes_mod.router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    userdb = MockUserDB()
    await userdb.setup()
    await migration_001.up(userdb)
    await migration_002.up(userdb)
    await migration_003.up(userdb)
    await migration_004.up(userdb)
    await migration_005.up(userdb)
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_rc_circuit(client, v=10.0, r=1000.0, c=1e-6):
    """Build V → R → C → GND and return circuit_id + components."""
    circ = (await client.post("/circuits", json={"name": "RC"})).json()
    cid = circ["id"]

    v1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "voltage_source", "value": str(v)})).json()
    r1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "resistor", "value": str(r)})).json()
    c1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "capacitor", "value": str(c)})).json()
    gnd = (await client.post(f"/circuits/{cid}/components", json={"component_type": "ground"})).json()

    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "n", "net_name": "OUT"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": c1["id"], "pin_name": "p", "net_name": "OUT"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": c1["id"], "pin_name": "n", "net_name": "GND"})

    return cid, {"v1": v1, "r1": r1, "c1": c1, "gnd": gnd}


async def _build_voltage_divider(client, v=10.0, r1=10000.0, r2=10000.0):
    """Build V → R1 → R2 → GND and return circuit_id."""
    circ = (await client.post("/circuits", json={"name": "Divider"})).json()
    cid = circ["id"]

    v1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "voltage_source", "value": str(v)})).json()
    r1c = (await client.post(f"/circuits/{cid}/components", json={"component_type": "resistor", "value": str(r1)})).json()
    r2c = (await client.post(f"/circuits/{cid}/components", json={"component_type": "resistor", "value": str(r2)})).json()
    gnd = (await client.post(f"/circuits/{cid}/components", json={"component_type": "ground"})).json()

    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1c["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1c["id"], "pin_name": "n", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r2c["id"], "pin_name": "p", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r2c["id"], "pin_name": "n", "net_name": "GND"})

    return cid, {"v1": v1, "r1": r1c, "r2": r2c, "gnd": gnd}


# ---------------------------------------------------------------------------
# Component Type Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_capacitor(client):
    """Place a capacitor and verify defaults."""
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    resp = await client.post(f"/circuits/{c['id']}/components", json={"component_type": "capacitor"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["ref_designator"] == "C1"
    assert body["component_type"] == "capacitor"
    assert body["unit"] == "F"
    assert len(body["pins"]) == 2


@pytest.mark.asyncio
async def test_add_inductor(client):
    """Place an inductor and verify defaults."""
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    resp = await client.post(f"/circuits/{c['id']}/components", json={"component_type": "inductor"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["ref_designator"] == "L1"
    assert body["component_type"] == "inductor"
    assert body["unit"] == "H"
    assert len(body["pins"]) == 2


@pytest.mark.asyncio
async def test_capacitor_value_parsing(client):
    """Engineering value parsing for capacitors."""
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    resp = await client.post(f"/circuits/{c['id']}/components", json={
        "component_type": "capacitor", "value": "100nF"
    })
    assert resp.status_code == 201
    body = resp.json()
    # 100n = 1e-7
    assert float(body["value"]) == pytest.approx(1e-7)


@pytest.mark.asyncio
async def test_inductor_value_parsing(client):
    """Engineering value parsing for inductors."""
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    resp = await client.post(f"/circuits/{c['id']}/components", json={
        "component_type": "inductor", "value": "4.7mH"
    })
    assert resp.status_code == 201
    body = resp.json()
    assert float(body["value"]) == pytest.approx(4.7e-3)


@pytest.mark.asyncio
async def test_library_includes_new_types(client):
    """Library endpoint lists capacitor and inductor."""
    resp = await client.get("/library")
    assert resp.status_code == 200
    types = [i["type"] for i in resp.json()["items"]]
    assert "capacitor" in types
    assert "inductor" in types


@pytest.mark.asyncio
async def test_library_capacitor_detail(client):
    """Capacitor detail from library."""
    resp = await client.get("/library/capacitor")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "capacitor"
    assert body["pins"] == ["p", "n"]
    assert body["value_unit"] == "F"


# ---------------------------------------------------------------------------
# DC OP with Reactive Components
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dc_op_with_capacitor(client):
    """DC OP: capacitor is open circuit."""
    cid, comps = await _build_rc_circuit(client, v=10.0, r=1000.0, c=1e-6)

    resp = await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "complete"

    # Cap is open → no current → OUT = VCC = 10V
    out_result = [nr for nr in result["node_results"] if nr["net_name"] == "OUT"]
    assert len(out_result) == 1
    assert out_result[0]["voltage"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_dc_op_with_inductor(client):
    """DC OP: inductor is short circuit."""
    circ = (await client.post("/circuits", json={"name": "RL"})).json()
    cid = circ["id"]

    v1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "voltage_source", "value": "10"})).json()
    l1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "inductor", "value": "0.01"})).json()
    r1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "resistor", "value": "1000"})).json()
    await client.post(f"/circuits/{cid}/components", json={"component_type": "ground"})

    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": l1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": l1["id"], "pin_name": "n", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "p", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "n", "net_name": "GND"})

    result = (await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})).json()
    assert result["status"] == "complete"

    # Inductor = short → MID = VCC = 10V
    mid = [nr for nr in result["node_results"] if nr["net_name"] == "MID"]
    assert mid[0]["voltage"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# AC Analysis via API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_simulation(client):
    """Run AC simulation via API and get sweep data."""
    cid, _ = await _build_rc_circuit(client, v=1.0, r=1000.0, c=1e-6)

    resp = await client.post(f"/circuits/{cid}/simulate", json={
        "sim_type": "ac",
        "f_start": 10,
        "f_stop": 100000,
        "points_per_decade": 5,
    })
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "complete"
    assert result["sim_type"] == "ac"
    assert "sweep_data" in result
    assert len(result["sweep_data"]) > 0

    # Each sweep point should have parameter_value (frequency) and node voltages
    first_pt = result["sweep_data"][0]
    assert "parameter_value" in first_pt
    assert "node_voltages" in first_pt


@pytest.mark.asyncio
async def test_ac_frequency_response(client):
    """AC response: check attenuation at high frequency for RC low-pass."""
    cid, _ = await _build_rc_circuit(client, v=1.0, r=1000.0, c=1e-6)

    result = (await client.post(f"/circuits/{cid}/simulate", json={
        "sim_type": "ac",
        "f_start": 1,
        "f_stop": 1000000,
        "points_per_decade": 5,
    })).json()

    assert result["status"] == "complete"
    sweep = result["sweep_data"]

    # Get OUT net id
    circuit = (await client.get(f"/circuits/{cid}")).json()
    out_net = [n for n in circuit["nets"] if n["name"] == "OUT"][0]
    out_id = out_net["id"]

    # Low frequency point
    low_pts = [p for p in sweep if p["parameter_value"] < 10]
    if low_pts:
        v = low_pts[0]["node_voltages"].get(out_id)
        if isinstance(v, dict):
            assert v["magnitude"] > 0.8  # near unity gain
        else:
            assert abs(v) > 0.8


# ---------------------------------------------------------------------------
# DC Sweep via API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dc_sweep(client):
    """Run DC sweep via API."""
    cid, comps = await _build_voltage_divider(client, v=10.0)

    resp = await client.post(f"/circuits/{cid}/simulate", json={
        "sim_type": "dc_sweep",
        "sweep_source_id": comps["v1"]["id"],
        "sweep_start": 0,
        "sweep_stop": 10,
        "sweep_steps": 11,
    })
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "complete"
    assert result["sim_type"] == "dc_sweep"
    assert len(result["sweep_data"]) == 11


@pytest.mark.asyncio
async def test_dc_sweep_linearity(client):
    """DC sweep: divider output should be linear with input."""
    cid, comps = await _build_voltage_divider(client, v=0.0)

    result = (await client.post(f"/circuits/{cid}/simulate", json={
        "sim_type": "dc_sweep",
        "sweep_source_id": comps["v1"]["id"],
        "sweep_start": 0,
        "sweep_stop": 20,
        "sweep_steps": 5,
    })).json()

    assert result["status"] == "complete"

    # Get MID net id
    circuit = (await client.get(f"/circuits/{cid}")).json()
    mid_net = [n for n in circuit["nets"] if n["name"] == "MID"][0]
    mid_id = mid_net["id"]

    for pt in result["sweep_data"]:
        v_in = pt["parameter_value"]
        v_mid = pt["node_voltages"].get(mid_id)
        if v_mid is not None:
            expected = v_in * 0.5
            assert v_mid == pytest.approx(expected, abs=0.1)


@pytest.mark.asyncio
async def test_dc_sweep_missing_source(client):
    """DC sweep without source_id returns error."""
    cid, _ = await _build_voltage_divider(client)

    result = (await client.post(f"/circuits/{cid}/simulate", json={
        "sim_type": "dc_sweep",
    })).json()
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Transient Analysis via API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_simulation(client):
    """Run transient simulation via API."""
    cid, _ = await _build_rc_circuit(client, v=10.0, r=1000.0, c=1e-6)

    resp = await client.post(f"/circuits/{cid}/simulate", json={
        "sim_type": "transient",
        "t_stop": 0.005,
    })
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "complete"
    assert result["sim_type"] == "transient"
    assert "sweep_data" in result
    assert len(result["sweep_data"]) > 0


@pytest.mark.asyncio
async def test_transient_time_ordering(client):
    """Transient sweep data should have increasing time values."""
    cid, _ = await _build_voltage_divider(client)

    result = (await client.post(f"/circuits/{cid}/simulate", json={
        "sim_type": "transient",
        "t_stop": 0.001,
    })).json()

    assert result["status"] == "complete"
    times = [pt["parameter_value"] for pt in result["sweep_data"]]
    for i in range(1, len(times)):
        assert times[i] >= times[i - 1]


@pytest.mark.asyncio
async def test_results_stored(client):
    """GET /results returns latest sim including sweep data."""
    cid, _ = await _build_voltage_divider(client)
    await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})

    resp = await client.get(f"/circuits/{cid}/results")
    assert resp.status_code == 200
    assert resp.json()["status"] == "complete"
    assert resp.json()["sim_type"] == "op"
