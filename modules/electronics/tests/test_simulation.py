"""Integration tests for the simulation endpoint — full round-trip via API."""

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
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers: build standard circuits via API
# ---------------------------------------------------------------------------


async def _build_voltage_divider(client, v=10.0, r1=10000.0, r2=10000.0):
    """Build V1 → R1 → R2 → GND and return circuit_id."""
    c = (await client.post("/circuits", json={"name": "Voltage Divider"})).json()
    cid = c["id"]

    # Place components
    v1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "voltage_source", "value": str(v)})).json()
    r1c = (await client.post(f"/circuits/{cid}/components", json={"component_type": "resistor", "value": str(r1)})).json()
    r2c = (await client.post(f"/circuits/{cid}/components", json={"component_type": "resistor", "value": str(r2)})).json()
    gnd = (await client.post(f"/circuits/{cid}/components", json={"component_type": "ground"})).json()

    # Wire: V1+ → VCC, V1- → GND, R1.p → VCC, R1.n → MID, R2.p → MID, R2.n → GND
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1c["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1c["id"], "pin_name": "n", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r2c["id"], "pin_name": "p", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r2c["id"], "pin_name": "n", "net_name": "GND"})

    return cid, {"v1": v1, "r1": r1c, "r2": r2c, "gnd": gnd}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simulate_voltage_divider(client):
    """Equal resistors → midpoint is half the supply voltage."""
    cid, comps = await _build_voltage_divider(client, v=10.0, r1=10000.0, r2=10000.0)

    resp = await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "complete"

    # Find MID net voltage
    mid_result = [nr for nr in result["node_results"] if nr["net_name"] == "MID"]
    assert len(mid_result) == 1
    assert mid_result[0]["voltage"] == pytest.approx(5.0)

    # Find VCC net voltage
    vcc_result = [nr for nr in result["node_results"] if nr["net_name"] == "VCC"]
    assert len(vcc_result) == 1
    assert vcc_result[0]["voltage"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_simulate_unequal_divider(client):
    """R1=10k, R2=20k → Vout = 10 * 20000 / 30000 ≈ 6.667V."""
    cid, _ = await _build_voltage_divider(client, v=10.0, r1=10000.0, r2=20000.0)

    result = (await client.post(f"/circuits/{cid}/simulate")).json()
    assert result["status"] == "complete"

    mid = [nr for nr in result["node_results"] if nr["net_name"] == "MID"]
    expected = 10.0 * 20000.0 / 30000.0
    assert mid[0]["voltage"] == pytest.approx(expected, rel=1e-6)


@pytest.mark.asyncio
async def test_simulate_component_results(client):
    """Check current and power for each component."""
    cid, comps = await _build_voltage_divider(client, v=10.0, r1=10000.0, r2=10000.0)

    result = (await client.post(f"/circuits/{cid}/simulate")).json()
    assert result["status"] == "complete"

    # Current through series resistors = V / (R1+R2) = 10/20000 = 0.0005A
    r1_result = [cr for cr in result["component_results"] if cr["component_id"] == comps["r1"]["id"]]
    assert len(r1_result) == 1
    assert r1_result[0]["current"] == pytest.approx(0.0005)
    assert r1_result[0]["power"] == pytest.approx(0.0025)  # P = I^2 * R = 0.0005^2 * 10000


@pytest.mark.asyncio
async def test_get_results_after_simulate(client):
    """GET /results returns the latest simulation after running one."""
    cid, _ = await _build_voltage_divider(client)
    await client.post(f"/circuits/{cid}/simulate")

    resp = await client.get(f"/circuits/{cid}/results")
    assert resp.status_code == 200
    assert resp.json()["status"] == "complete"
    assert len(resp.json()["node_results"]) > 0


@pytest.mark.asyncio
async def test_get_results_no_simulation(client):
    """GET /results before any simulation returns status=none."""
    c = (await client.post("/circuits", json={"name": "Empty"})).json()
    resp = await client.get(f"/circuits/{c['id']}/results")
    assert resp.status_code == 200
    assert resp.json()["status"] == "none"


@pytest.mark.asyncio
async def test_simulate_empty_circuit(client):
    """Simulating a circuit with no components returns an error result."""
    c = (await client.post("/circuits", json={"name": "Empty"})).json()
    result = (await client.post(f"/circuits/{c['id']}/simulate")).json()
    assert result["status"] == "error"
    assert result["error_message"]


@pytest.mark.asyncio
async def test_simulate_unconnected_circuit(client):
    """Components placed but not wired → error."""
    c = (await client.post("/circuits", json={"name": "Unwired"})).json()
    cid = c["id"]
    await client.post(f"/circuits/{cid}/components", json={"component_type": "resistor"})
    await client.post(f"/circuits/{cid}/components", json={"component_type": "voltage_source"})
    await client.post(f"/circuits/{cid}/components", json={"component_type": "ground"})

    result = (await client.post(f"/circuits/{cid}/simulate")).json()
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_resimulate_after_value_change(client):
    """Change a resistor value, re-simulate, verify new result."""
    cid, comps = await _build_voltage_divider(client, v=10.0, r1=10000.0, r2=10000.0)

    # First sim
    r1 = (await client.post(f"/circuits/{cid}/simulate")).json()
    mid1 = [nr for nr in r1["node_results"] if nr["net_name"] == "MID"][0]["voltage"]

    # Change R2 to 30k
    await client.put(f"/components/{comps['r2']['id']}", json={"value": "30000"})

    # Second sim
    r2 = (await client.post(f"/circuits/{cid}/simulate")).json()
    mid2 = [nr for nr in r2["node_results"] if nr["net_name"] == "MID"][0]["voltage"]

    assert mid1 == pytest.approx(5.0)
    # New: V * 30000 / (10000 + 30000) = 7.5V
    assert mid2 == pytest.approx(7.5)


@pytest.mark.asyncio
async def test_get_result_detail(client):
    """GET /results/{id} returns a specific result."""
    cid, _ = await _build_voltage_divider(client)
    sim = (await client.post(f"/circuits/{cid}/simulate")).json()

    resp = await client.get(f"/circuits/{cid}/results/{sim['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sim["id"]
    assert resp.json()["status"] == "complete"


@pytest.mark.asyncio
async def test_circuit_full_includes_last_sim(client):
    """GET /circuits/{id} includes last_sim_result after simulation."""
    cid, _ = await _build_voltage_divider(client)
    await client.post(f"/circuits/{cid}/simulate")

    circuit = (await client.get(f"/circuits/{cid}")).json()
    assert circuit["last_sim_result"] is not None
    assert circuit["last_sim_result"]["status"] == "complete"
