"""Tests for E1b Design Rule Checking (DRC)."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB, create_test_app

# ---------------------------------------------------------------------------
# Load electronics modules by file path
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
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# DRC Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drc_no_ground(client):
    """Circuit without ground should warn."""
    c = (await client.post("/circuits", json={"name": "No Ground"})).json()
    await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})

    resp = await client.get(f"/circuits/{c['id']}/drc")
    assert resp.status_code == 200
    warnings = resp.json()["warnings"]
    types = [w["type"] for w in warnings]
    assert "no_ground" in types


@pytest.mark.asyncio
async def test_drc_unconnected_component(client):
    """Component with no connected pins should warn."""
    c = (await client.post("/circuits", json={"name": "Unconnected"})).json()
    await client.post(f"/circuits/{c['id']}/components", json={"component_type": "ground"})
    await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})

    resp = await client.get(f"/circuits/{c['id']}/drc")
    warnings = resp.json()["warnings"]
    types = [w["type"] for w in warnings]
    assert "unconnected_component" in types


@pytest.mark.asyncio
async def test_drc_dangling_net(client):
    """Net with only one pin connected should warn."""
    c = (await client.post("/circuits", json={"name": "Dangling"})).json()
    await client.post(f"/circuits/{c['id']}/components", json={"component_type": "ground"})
    r = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()

    # Connect only one pin to a net
    await client.post(f"/circuits/{c['id']}/connect", json={
        "component_id": r["id"], "pin_name": "p", "net_name": "Lonely",
    })

    resp = await client.get(f"/circuits/{c['id']}/drc")
    warnings = resp.json()["warnings"]
    types = [w["type"] for w in warnings]
    assert "dangling_net" in types


@pytest.mark.asyncio
async def test_drc_low_resistance(client):
    """Resistor with value < 0.1Ω should warn."""
    c = (await client.post("/circuits", json={"name": "Low R"})).json()
    await client.post(f"/circuits/{c['id']}/components", json={"component_type": "ground"})
    await client.post(f"/circuits/{c['id']}/components", json={
        "component_type": "resistor", "value": "0.01",
    })

    resp = await client.get(f"/circuits/{c['id']}/drc")
    warnings = resp.json()["warnings"]
    types = [w["type"] for w in warnings]
    assert "low_resistance" in types


@pytest.mark.asyncio
async def test_drc_parallel_voltage_sources(client):
    """Two voltage sources on the same nets should warn."""
    c = (await client.post("/circuits", json={"name": "Parallel V"})).json()
    await client.post(f"/circuits/{c['id']}/components", json={"component_type": "ground"})
    v1 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "voltage_source"})).json()
    v2 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "voltage_source"})).json()

    # Connect both to same nets
    await client.post(f"/circuits/{c['id']}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{c['id']}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{c['id']}/connect", json={"component_id": v2["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{c['id']}/connect", json={"component_id": v2["id"], "pin_name": "n", "net_name": "GND"})

    resp = await client.get(f"/circuits/{c['id']}/drc")
    warnings = resp.json()["warnings"]
    types = [w["type"] for w in warnings]
    assert "parallel_voltage_sources" in types


@pytest.mark.asyncio
async def test_drc_clean_circuit_no_warnings(client):
    """A properly wired circuit should have no warnings (except maybe dangling nets)."""
    c = (await client.post("/circuits", json={"name": "Clean"})).json()
    cid = c["id"]
    gnd = (await client.post(f"/circuits/{cid}/components", json={"component_type": "ground"})).json()
    v1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "voltage_source"})).json()
    r1 = (await client.post(f"/circuits/{cid}/components", json={"component_type": "resistor"})).json()

    # Wire: V1.p → R1.p → N001, V1.n → R1.n → GND
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "n", "net_name": "GND"})

    resp = await client.get(f"/circuits/{cid}/drc")
    warnings = resp.json()["warnings"]
    # Should have no warnings (clean circuit)
    assert len(warnings) == 0


@pytest.mark.asyncio
async def test_drc_empty_circuit(client):
    """Empty circuit should have no warnings."""
    c = (await client.post("/circuits", json={"name": "Empty"})).json()
    resp = await client.get(f"/circuits/{c['id']}/drc")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_drc_not_found(client):
    resp = await client.get("/circuits/nonexistent/drc")
    assert resp.status_code == 404
