"""Tests for circuit CRUD, component placement, and wiring endpoints."""

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
# Circuit CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_circuit(client):
    resp = await client.post("/circuits", json={"name": "Test Circuit"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Test Circuit"
    assert body["id"]
    assert body["components"] == []
    assert body["nets"] == []


@pytest.mark.asyncio
async def test_list_circuits(client):
    await client.post("/circuits", json={"name": "C1"})
    await client.post("/circuits", json={"name": "C2"})
    await client.post("/circuits", json={"name": "C3"})
    resp = await client.get("/circuits")
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_get_circuit(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    resp = await client.get(f"/circuits/{c['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test"


@pytest.mark.asyncio
async def test_update_circuit(client):
    c = (await client.post("/circuits", json={"name": "Old"})).json()
    resp = await client.put(f"/circuits/{c['id']}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


@pytest.mark.asyncio
async def test_delete_circuit(client):
    c = (await client.post("/circuits", json={"name": "Gone"})).json()
    resp = await client.delete(f"/circuits/{c['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    resp = await client.get("/circuits")
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_circuit_not_found(client):
    resp = await client.get("/circuits/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Component Placement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_resistor(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    resp = await client.post(f"/circuits/{c['id']}/components", json={
        "component_type": "resistor",
        "value": "10000",
        "x": 100,
        "y": 200,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["ref_designator"] == "R1"
    assert body["component_type"] == "resistor"
    assert body["value"] == "10000.0"
    assert len(body["pins"]) == 2  # p, n


@pytest.mark.asyncio
async def test_ref_designator_auto_increment(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    r1 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()
    r2 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()
    v1 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "voltage_source"})).json()
    assert r1["ref_designator"] == "R1"
    assert r2["ref_designator"] == "R2"
    assert v1["ref_designator"] == "V1"


@pytest.mark.asyncio
async def test_default_value_applied(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    r = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()
    assert r["value"] == "1000"  # default
    assert r["unit"] == "ohm"


@pytest.mark.asyncio
async def test_ground_auto_creates_net(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    g = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "ground"})).json()
    assert g["ref_designator"] == "GND1"
    # Pin should be connected to GND net
    assert g["pins"][0]["net_name"] == "GND"

    # Verify GND net exists
    circuit = (await client.get(f"/circuits/{c['id']}")).json()
    gnd_nets = [n for n in circuit["nets"] if n["name"] == "GND"]
    assert len(gnd_nets) == 1
    assert gnd_nets[0]["net_type"] == "ground"


@pytest.mark.asyncio
async def test_invalid_component_type(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    resp = await client.post(f"/circuits/{c['id']}/components", json={"component_type": "quantum_entangler"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_component(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    r = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()
    resp = await client.put(f"/components/{r['id']}", json={"value": "4700", "x": 300})
    assert resp.status_code == 200
    assert resp.json()["value"] == "4700.0"


@pytest.mark.asyncio
async def test_delete_component(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    r = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()
    resp = await client.delete(f"/components/{r['id']}")
    assert resp.status_code == 200
    # Verify removed from circuit
    circuit = (await client.get(f"/circuits/{c['id']}")).json()
    assert len(circuit["components"]) == 0


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_pins_creates_net(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    r = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()
    resp = await client.post(f"/circuits/{c['id']}/connect", json={
        "component_id": r["id"],
        "pin_name": "p",
        "net_name": "VCC",
    })
    assert resp.status_code == 200
    assert resp.json()["net_name"] == "VCC"


@pytest.mark.asyncio
async def test_connect_two_components_to_same_net(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    r1 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()
    r2 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()

    await client.post(f"/circuits/{c['id']}/connect", json={"component_id": r1["id"], "pin_name": "n", "net_name": "MID"})
    await client.post(f"/circuits/{c['id']}/connect", json={"component_id": r2["id"], "pin_name": "p", "net_name": "MID"})

    circuit = (await client.get(f"/circuits/{c['id']}")).json()
    mid_nets = [n for n in circuit["nets"] if n["name"] == "MID"]
    assert len(mid_nets) == 1  # same net, not duplicated


@pytest.mark.asyncio
async def test_disconnect_pin(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    r = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})).json()
    await client.post(f"/circuits/{c['id']}/connect", json={"component_id": r["id"], "pin_name": "p", "net_name": "VCC"})

    pin_id = r["pins"][0]["id"]  # p pin
    resp = await client.delete(f"/pins/{pin_id}/disconnect")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_explicit_net(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    resp = await client.post(f"/circuits/{c['id']}/nets", json={"name": "VCC", "net_type": "power"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "VCC"


@pytest.mark.asyncio
async def test_duplicate_net_name_rejected(client):
    c = (await client.post("/circuits", json={"name": "Test"})).json()
    await client.post(f"/circuits/{c['id']}/nets", json={"name": "VCC"})
    resp = await client.post(f"/circuits/{c['id']}/nets", json={"name": "VCC"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Component Library
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_library(client):
    resp = await client.get("/library")
    assert resp.status_code == 200
    items = resp.json()["items"]
    types = [i["type"] for i in items]
    assert "resistor" in types
    assert "voltage_source" in types
    assert "current_source" in types
    assert "ground" in types


@pytest.mark.asyncio
async def test_get_library_type(client):
    resp = await client.get("/library/resistor")
    assert resp.status_code == 200
    assert resp.json()["type"] == "resistor"
    assert resp.json()["pins"] == ["p", "n"]


@pytest.mark.asyncio
async def test_get_library_unknown_type(client):
    resp = await client.get("/library/flux_capacitor")
    assert resp.status_code == 404
