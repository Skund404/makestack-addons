"""E4 tests — Subcircuit definitions, flattening, and simulation."""

import importlib.util
import json
import os
import sys

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB, create_test_app

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
solver_mod = _load("solver", "backend/solver.py")
subcircuit_mod = _load("subcircuit", "backend/subcircuit.py")

router = routes_mod.router
CircuitGraph = solver_mod.CircuitGraph
ComponentInstance = solver_mod.ComponentInstance
solve_dc_op = solver_mod.solve_dc_op


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

def _resistor(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="resistor", value=value, pins={"p": p_net, "n": n_net})

def _vsource(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="voltage_source", value=value, pins={"p": p_net, "n": n_net})

def _ground(id, net):
    return ComponentInstance(id=id, component_type="ground", value=0, pins={"gnd": net})


# ---------------------------------------------------------------------------
# Subcircuit flattening (unit tests)
# ---------------------------------------------------------------------------

class TestSubcircuitFlattening:
    """Test subcircuit flattening at the solver level."""

    def test_flatten_simple_subcircuit(self):
        """A subcircuit with a single resistor should flatten correctly."""
        defn = subcircuit_mod.SubcircuitDef(
            id="sub1",
            name="10k Resistor",
            description="Just a resistor",
            port_pins=["a", "b"],
            circuit_json={
                "components": [
                    {"id": "R1", "component_type": "resistor", "value": 10000.0,
                     "pins": {"p": "net_a", "n": "net_b"}},
                ],
                "internal_nets": ["net_a", "net_b"],
                "port_nets": {"a": "net_a", "b": "net_b"},
            },
        )
        inst = subcircuit_mod.SubcircuitInstance(
            id="inst1",
            subcircuit_id="sub1",
            port_mapping={"a": "parent_net1", "b": "parent_net2"},
        )
        comps, new_nets = subcircuit_mod.flatten_subcircuit(inst, defn, solver_mod)
        assert len(comps) == 1
        assert comps[0].component_type == "resistor"
        assert comps[0].value == 10000.0
        # Port nets should map to parent nets
        assert comps[0].pins["p"] == "parent_net1"
        assert comps[0].pins["n"] == "parent_net2"
        # No new internal nets (both mapped to ports)
        assert len(new_nets) == 0

    def test_flatten_subcircuit_with_internal_nets(self):
        """Subcircuit with an internal node gets unique net IDs."""
        # Voltage divider subcircuit: R1 + R2 with internal mid-point
        defn = subcircuit_mod.SubcircuitDef(
            id="vdiv",
            name="Voltage Divider",
            description="",
            port_pins=["in", "out", "gnd"],
            circuit_json={
                "components": [
                    {"id": "R1", "component_type": "resistor", "value": 1000.0,
                     "pins": {"p": "net_in", "n": "net_mid"}},
                    {"id": "R2", "component_type": "resistor", "value": 1000.0,
                     "pins": {"p": "net_mid", "n": "net_gnd"}},
                ],
                "internal_nets": ["net_in", "net_mid", "net_gnd"],
                "port_nets": {"in": "net_in", "out": "net_mid", "gnd": "net_gnd"},
            },
        )
        inst = subcircuit_mod.SubcircuitInstance(
            id="inst2",
            subcircuit_id="vdiv",
            port_mapping={"in": "vcc", "out": "output", "gnd": "gnd"},
        )
        comps, new_nets = subcircuit_mod.flatten_subcircuit(inst, defn, solver_mod)
        assert len(comps) == 2
        # All nets map to port nets, so no new internal nets
        assert len(new_nets) == 0
        # R1: p -> vcc, n -> output
        assert comps[0].pins["p"] == "vcc"
        assert comps[0].pins["n"] == "output"

    def test_flatten_with_truly_internal_net(self):
        """Internal net not connected to any port gets a unique prefixed ID."""
        defn = subcircuit_mod.SubcircuitDef(
            id="sub3",
            name="Two-stage",
            description="",
            port_pins=["in", "out"],
            circuit_json={
                "components": [
                    {"id": "R1", "component_type": "resistor", "value": 1000.0,
                     "pins": {"p": "net_in", "n": "internal1"}},
                    {"id": "R2", "component_type": "resistor", "value": 1000.0,
                     "pins": {"p": "internal1", "n": "net_out"}},
                ],
                "internal_nets": ["net_in", "internal1", "net_out"],
                "port_nets": {"in": "net_in", "out": "net_out"},
            },
        )
        inst = subcircuit_mod.SubcircuitInstance(
            id="i3", subcircuit_id="sub3",
            port_mapping={"in": "parent_a", "out": "parent_b"},
        )
        comps, new_nets = subcircuit_mod.flatten_subcircuit(inst, defn, solver_mod)
        assert len(comps) == 2
        assert len(new_nets) == 1
        assert "internal1" in new_nets[0]  # should contain the original name
        # Both resistors should connect through the internal net
        assert comps[0].pins["n"] == comps[1].pins["p"]

    def test_flatten_and_solve(self):
        """Flatten a voltage divider subcircuit and solve it."""
        defn = subcircuit_mod.SubcircuitDef(
            id="vdiv", name="Voltage Divider", description="",
            port_pins=["top", "mid", "bot"],
            circuit_json={
                "components": [
                    {"id": "R1", "component_type": "resistor", "value": 1000.0,
                     "pins": {"p": "n_top", "n": "n_mid"}},
                    {"id": "R2", "component_type": "resistor", "value": 1000.0,
                     "pins": {"p": "n_mid", "n": "n_bot"}},
                ],
                "internal_nets": ["n_top", "n_mid", "n_bot"],
                "port_nets": {"top": "n_top", "mid": "n_mid", "bot": "n_bot"},
            },
        )
        inst = subcircuit_mod.SubcircuitInstance(
            id="i1", subcircuit_id="vdiv",
            port_mapping={"top": "vcc", "mid": "out", "bot": "gnd"},
        )

        # Parent circuit: voltage source + ground + subcircuit
        parent_graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "out", "gnd"],
            components=[
                _vsource("V1", 10.0, "vcc", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        flat_graph = subcircuit_mod.flatten_all_subcircuits(
            parent_graph, [inst], {"vdiv": defn}, solver_mod,
        )
        result = solve_dc_op(flat_graph)
        # Voltage divider: Vout = Vin * R2/(R1+R2) = 10 * 0.5 = 5V
        assert result.node_voltages["out"] == pytest.approx(5.0, abs=0.01)

    def test_multiple_instances(self):
        """Two instances of the same subcircuit should work independently."""
        defn = subcircuit_mod.SubcircuitDef(
            id="res_sub", name="Resistor", description="",
            port_pins=["a", "b"],
            circuit_json={
                "components": [
                    {"id": "R", "component_type": "resistor", "value": 1000.0,
                     "pins": {"p": "na", "n": "nb"}},
                ],
                "internal_nets": ["na", "nb"],
                "port_nets": {"a": "na", "b": "nb"},
            },
        )
        # Two instances in series: V1 -> inst1 -> mid -> inst2 -> gnd
        inst1 = subcircuit_mod.SubcircuitInstance(
            id="i1", subcircuit_id="res_sub",
            port_mapping={"a": "vcc", "b": "mid"},
        )
        inst2 = subcircuit_mod.SubcircuitInstance(
            id="i2", subcircuit_id="res_sub",
            port_mapping={"a": "mid", "b": "gnd"},
        )

        parent = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 10.0, "vcc", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        flat = subcircuit_mod.flatten_all_subcircuits(
            parent, [inst1, inst2], {"res_sub": defn}, solver_mod,
        )
        result = solve_dc_op(flat)
        # Two 1k resistors in series: mid = 5V
        assert result.node_voltages["mid"] == pytest.approx(5.0, abs=0.01)


# ---------------------------------------------------------------------------
# Subcircuit API tests
# ---------------------------------------------------------------------------

class TestSubcircuitAPI:
    """Test subcircuit CRUD via API."""

    @pytest.mark.asyncio
    async def test_create_subcircuit(self, client):
        resp = await client.post("/subcircuits", json={
            "name": "NAND Gate",
            "description": "Basic NAND using BJTs",
            "port_pins": ["A", "B", "Y", "VCC", "GND"],
            "circuit_json": {"components": [], "internal_nets": [], "port_nets": {}},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "NAND Gate"
        assert len(data["port_pins"]) == 5

    @pytest.mark.asyncio
    async def test_list_subcircuits(self, client):
        await client.post("/subcircuits", json={
            "name": "Sub1", "port_pins": ["a", "b"],
        })
        await client.post("/subcircuits", json={
            "name": "Sub2", "port_pins": ["x"],
        })
        resp = await client.get("/subcircuits")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_subcircuit(self, client):
        r = await client.post("/subcircuits", json={
            "name": "Test", "port_pins": ["a"],
            "circuit_json": {"components": [{"id": "R1"}]},
        })
        sub_id = r.json()["id"]
        resp = await client.get(f"/subcircuits/{sub_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test"
        assert len(resp.json()["circuit_json"]["components"]) == 1

    @pytest.mark.asyncio
    async def test_delete_subcircuit(self, client):
        r = await client.post("/subcircuits", json={
            "name": "ToDelete", "port_pins": [],
        })
        sub_id = r.json()["id"]
        resp = await client.delete(f"/subcircuits/{sub_id}")
        assert resp.status_code == 200
        resp2 = await client.get(f"/subcircuits/{sub_id}")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_subcircuit_instance_crud(self, client):
        # Create subcircuit
        r = await client.post("/subcircuits", json={
            "name": "Divider", "port_pins": ["in", "out", "gnd"],
        })
        sub_id = r.json()["id"]

        # Create circuit
        r = await client.post("/circuits", json={"name": "test"})
        cid = r.json()["id"]

        # Add instance
        r = await client.post(f"/circuits/{cid}/subcircuit-instances", json={
            "subcircuit_id": sub_id,
            "port_mapping": {"in": "net1", "out": "net2", "gnd": "net3"},
        })
        assert r.status_code == 201
        inst_id = r.json()["id"]

        # List instances
        r = await client.get(f"/circuits/{cid}/subcircuit-instances")
        assert len(r.json()["items"]) == 1

        # Delete instance
        r = await client.delete(f"/subcircuit-instances/{inst_id}")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_subcircuit_not_found(self, client):
        resp = await client.get("/subcircuits/nonexistent")
        assert resp.status_code == 404
