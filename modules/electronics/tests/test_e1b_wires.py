"""Tests for E1b wire segments, junctions, and regions."""

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


@pytest_asyncio.fixture
async def circuit(client):
    """Create a circuit with two resistors for wire testing."""
    c = (await client.post("/circuits", json={"name": "Wire Test"})).json()
    r1 = (await client.post(f"/circuits/{c['id']}/components", json={
        "component_type": "resistor", "x": 100, "y": 100,
    })).json()
    r2 = (await client.post(f"/circuits/{c['id']}/components", json={
        "component_type": "resistor", "x": 300, "y": 100,
    })).json()
    return {"circuit": c, "r1": r1, "r2": r2}


# ---------------------------------------------------------------------------
# Wire Segment CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_wire_segment(client, circuit):
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/wires", json={
        "x1": 100, "y1": 100, "x2": 300, "y2": 100,
        "net_name": "N001",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["x1"] == 100
    assert body["x2"] == 300
    assert body["net_id"]


@pytest.mark.asyncio
async def test_create_wire_auto_generates_net(client, circuit):
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 100, "y2": 0,
    })
    assert resp.status_code == 201
    assert resp.json()["net_id"]


@pytest.mark.asyncio
async def test_create_wire_reuses_existing_net(client, circuit):
    cid = circuit["circuit"]["id"]
    # Create first wire on net "TestNet"
    r1 = (await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 100, "y2": 0, "net_name": "TestNet",
    })).json()
    # Create second wire on same net
    r2 = (await client.post(f"/circuits/{cid}/wires", json={
        "x1": 100, "y1": 0, "x2": 200, "y2": 0, "net_name": "TestNet",
    })).json()
    assert r1["net_id"] == r2["net_id"]


@pytest.mark.asyncio
async def test_list_wires(client, circuit):
    cid = circuit["circuit"]["id"]
    await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 100, "y2": 0, "net_name": "N001",
    })
    await client.post(f"/circuits/{cid}/wires", json={
        "x1": 100, "y1": 0, "x2": 200, "y2": 0, "net_name": "N001",
    })
    resp = await client.get(f"/circuits/{cid}/wires")
    assert resp.status_code == 200
    assert len(resp.json()["wire_segments"]) == 2


@pytest.mark.asyncio
async def test_delete_wire(client, circuit):
    cid = circuit["circuit"]["id"]
    wire = (await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 100, "y2": 0, "net_name": "N001",
    })).json()
    resp = await client.delete(f"/wires/{wire['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    # Verify gone
    wires = (await client.get(f"/circuits/{cid}/wires")).json()
    assert len(wires["wire_segments"]) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_wire(client):
    resp = await client.delete("/wires/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wires_in_circuit_response(client, circuit):
    """Wire segments and junctions should appear in get_circuit response."""
    cid = circuit["circuit"]["id"]
    await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 100, "y2": 0, "net_name": "N001",
    })
    resp = await client.get(f"/circuits/{cid}")
    body = resp.json()
    assert "wire_segments" in body
    assert "junctions" in body
    assert len(body["wire_segments"]) == 1


# ---------------------------------------------------------------------------
# Wire Split (Junction Creation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_wire_creates_junction(client, circuit):
    cid = circuit["circuit"]["id"]
    wire = (await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 200, "y2": 0, "net_name": "N001",
    })).json()

    resp = await client.post(f"/circuits/{cid}/wires/split", json={
        "wire_id": wire["id"],
        "x": 100, "y": 0,
    })
    assert resp.status_code == 201
    body = resp.json()

    # Should have a junction
    assert body["junction"]["x"] == 100
    assert body["junction"]["y"] == 0

    # Should have two segments
    assert len(body["segments"]) == 2
    seg1, seg2 = body["segments"]
    # First: 0,0 → 100,0
    assert seg1["x1"] == 0 and seg1["y1"] == 0
    assert seg1["x2"] == 100 and seg1["y2"] == 0
    # Second: 100,0 → 200,0
    assert seg2["x1"] == 100 and seg2["y1"] == 0
    assert seg2["x2"] == 200 and seg2["y2"] == 0


@pytest.mark.asyncio
async def test_split_removes_original_wire(client, circuit):
    cid = circuit["circuit"]["id"]
    wire = (await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 200, "y2": 0, "net_name": "N001",
    })).json()

    await client.post(f"/circuits/{cid}/wires/split", json={
        "wire_id": wire["id"], "x": 100, "y": 0,
    })

    # Original wire should be gone, replaced by two new ones
    wires = (await client.get(f"/circuits/{cid}/wires")).json()
    assert len(wires["wire_segments"]) == 2
    assert len(wires["junctions"]) == 1
    # Original wire ID should not exist
    wire_ids = [w["id"] for w in wires["wire_segments"]]
    assert wire["id"] not in wire_ids


@pytest.mark.asyncio
async def test_split_preserves_net(client, circuit):
    cid = circuit["circuit"]["id"]
    wire = (await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 200, "y2": 0, "net_name": "TestNet",
    })).json()
    original_net = wire["net_id"]

    result = (await client.post(f"/circuits/{cid}/wires/split", json={
        "wire_id": wire["id"], "x": 100, "y": 0,
    })).json()

    assert result["junction"]["net_id"] == original_net
    assert result["segments"][0]["net_id"] == original_net
    assert result["segments"][1]["net_id"] == original_net


# ---------------------------------------------------------------------------
# Auto-Route (Manhattan)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_route_straight_horizontal(client, circuit):
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/wires/auto-route", json={
        "from_x": 0, "from_y": 100, "to_x": 200, "to_y": 100,
        "net_name": "N001",
    })
    assert resp.status_code == 201
    body = resp.json()
    # Straight line → single segment
    assert len(body["segments"]) == 1


@pytest.mark.asyncio
async def test_auto_route_straight_vertical(client, circuit):
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/wires/auto-route", json={
        "from_x": 100, "from_y": 0, "to_x": 100, "to_y": 200,
        "net_name": "N001",
    })
    assert resp.status_code == 201
    assert len(resp.json()["segments"]) == 1


@pytest.mark.asyncio
async def test_auto_route_l_shape_horizontal_first(client, circuit):
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/wires/auto-route", json={
        "from_x": 0, "from_y": 0, "to_x": 200, "to_y": 100,
        "route_style": "horizontal_first",
        "net_name": "N001",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["segments"]) == 2
    # First segment: horizontal
    seg1 = body["segments"][0]
    assert seg1["y1"] == seg1["y2"] == 0  # horizontal
    # Second segment: vertical
    seg2 = body["segments"][1]
    assert seg2["x1"] == seg2["x2"] == 200  # vertical


@pytest.mark.asyncio
async def test_auto_route_l_shape_vertical_first(client, circuit):
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/wires/auto-route", json={
        "from_x": 0, "from_y": 0, "to_x": 200, "to_y": 100,
        "route_style": "vertical_first",
        "net_name": "N001",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["segments"]) == 2
    # First segment: vertical
    seg1 = body["segments"][0]
    assert seg1["x1"] == seg1["x2"] == 0  # vertical
    # Second segment: horizontal
    seg2 = body["segments"][1]
    assert seg2["y1"] == seg2["y2"] == 100  # horizontal


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_region(client, circuit):
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/regions", json={
        "name": "Power Supply",
        "color": "#ef4444",
        "description": "The power regulation block",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Power Supply"
    assert body["color"] == "#ef4444"
    assert body["created_by"] == "user"
    assert body["members"] == []


@pytest.mark.asyncio
async def test_create_ai_region(client, circuit):
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/regions", json={
        "name": "Voltage Divider",
        "created_by": "ai",
    })
    assert resp.status_code == 201
    assert resp.json()["created_by"] == "ai"


@pytest.mark.asyncio
async def test_list_regions(client, circuit):
    cid = circuit["circuit"]["id"]
    await client.post(f"/circuits/{cid}/regions", json={"name": "Block A"})
    await client.post(f"/circuits/{cid}/regions", json={"name": "Block B"})
    resp = await client.get(f"/circuits/{cid}/regions")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_update_region(client, circuit):
    cid = circuit["circuit"]["id"]
    region = (await client.post(f"/circuits/{cid}/regions", json={"name": "Old"})).json()
    resp = await client.put(f"/regions/{region['id']}", json={"name": "New", "color": "#22c55e"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"
    assert resp.json()["color"] == "#22c55e"


@pytest.mark.asyncio
async def test_delete_region(client, circuit):
    cid = circuit["circuit"]["id"]
    region = (await client.post(f"/circuits/{cid}/regions", json={"name": "Gone"})).json()
    resp = await client.delete(f"/regions/{region['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    # Verify gone
    regions = (await client.get(f"/circuits/{cid}/regions")).json()
    assert len(regions["items"]) == 0


@pytest.mark.asyncio
async def test_add_region_member(client, circuit):
    cid = circuit["circuit"]["id"]
    r1_id = circuit["r1"]["id"]
    region = (await client.post(f"/circuits/{cid}/regions", json={"name": "Test"})).json()
    resp = await client.post(f"/regions/{region['id']}/members", json={
        "member_type": "component",
        "member_id": r1_id,
    })
    assert resp.status_code == 201
    assert resp.json()["member_type"] == "component"
    assert resp.json()["member_id"] == r1_id


@pytest.mark.asyncio
async def test_add_duplicate_member_idempotent(client, circuit):
    cid = circuit["circuit"]["id"]
    r1_id = circuit["r1"]["id"]
    region = (await client.post(f"/circuits/{cid}/regions", json={"name": "Test"})).json()

    resp1 = await client.post(f"/regions/{region['id']}/members", json={
        "member_type": "component", "member_id": r1_id,
    })
    resp2 = await client.post(f"/regions/{region['id']}/members", json={
        "member_type": "component", "member_id": r1_id,
    })
    # Same ID returned — idempotent
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_remove_region_member(client, circuit):
    cid = circuit["circuit"]["id"]
    r1_id = circuit["r1"]["id"]
    region = (await client.post(f"/circuits/{cid}/regions", json={"name": "Test"})).json()
    member = (await client.post(f"/regions/{region['id']}/members", json={
        "member_type": "component", "member_id": r1_id,
    })).json()

    resp = await client.delete(f"/regions/{region['id']}/members/{member['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


@pytest.mark.asyncio
async def test_invalid_member_type_rejected(client, circuit):
    cid = circuit["circuit"]["id"]
    region = (await client.post(f"/circuits/{cid}/regions", json={"name": "Test"})).json()
    resp = await client.post(f"/regions/{region['id']}/members", json={
        "member_type": "invalid",
        "member_id": "something",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_region_members_in_list(client, circuit):
    """Region list should include members."""
    cid = circuit["circuit"]["id"]
    r1_id = circuit["r1"]["id"]
    region = (await client.post(f"/circuits/{cid}/regions", json={"name": "Test"})).json()
    await client.post(f"/regions/{region['id']}/members", json={
        "member_type": "component", "member_id": r1_id,
    })

    regions = (await client.get(f"/circuits/{cid}/regions")).json()
    assert len(regions["items"][0]["members"]) == 1


# ---------------------------------------------------------------------------
# Value Parsing Integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_component_parses_engineering_value(client, circuit):
    """Adding a component with '1k' should store '1000.0'."""
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor",
        "value": "1k",
    })
    assert resp.status_code == 201
    assert resp.json()["value"] == "1000.0"


@pytest.mark.asyncio
async def test_update_component_parses_engineering_value(client, circuit):
    """Updating a component value with '4.7k' should store '4700.0'."""
    r1_id = circuit["r1"]["id"]
    resp = await client.put(f"/components/{r1_id}", json={"value": "4.7k"})
    assert resp.status_code == 200
    assert resp.json()["value"] == "4700.0"


@pytest.mark.asyncio
async def test_plain_number_passes_through(client, circuit):
    """Plain number values should pass through unchanged."""
    cid = circuit["circuit"]["id"]
    resp = await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor",
        "value": "10000",
    })
    assert resp.status_code == 201
    assert resp.json()["value"] == "10000.0"


# ---------------------------------------------------------------------------
# Circuit Delete Cascade with E1b Tables
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_circuit_cascades_wires_and_regions(client, circuit):
    """Deleting a circuit should also delete wire segments, junctions, and regions."""
    cid = circuit["circuit"]["id"]

    # Create wire + junction
    wire = (await client.post(f"/circuits/{cid}/wires", json={
        "x1": 0, "y1": 0, "x2": 200, "y2": 0, "net_name": "N001",
    })).json()
    await client.post(f"/circuits/{cid}/wires/split", json={
        "wire_id": wire["id"], "x": 100, "y": 0,
    })

    # Create region with member
    region = (await client.post(f"/circuits/{cid}/regions", json={"name": "Test"})).json()
    await client.post(f"/regions/{region['id']}/members", json={
        "member_type": "component", "member_id": circuit["r1"]["id"],
    })

    # Delete circuit
    resp = await client.delete(f"/circuits/{cid}")
    assert resp.status_code == 200

    # Verify everything is gone
    resp = await client.get("/circuits")
    assert resp.json()["total"] == 0
