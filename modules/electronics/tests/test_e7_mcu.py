"""E7 tests — MCU co-simulation with sandboxed Python tick functions."""

import importlib.util
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
migration_006 = _load("mig006", "backend/migrations/006_e7_mcu.py")
routes_mod = _load("routes", "backend/routes.py")
mcu_mod = _load("mcu_sandbox", "backend/mcu_sandbox.py")

router = routes_mod.router


@pytest_asyncio.fixture
async def db():
    userdb = MockUserDB()
    await userdb.setup()
    await migration_001.up(userdb)
    await migration_002.up(userdb)
    await migration_003.up(userdb)
    await migration_004.up(userdb)
    await migration_005.up(userdb)
    await migration_006.up(userdb)
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Sandbox unit tests
# ---------------------------------------------------------------------------

class TestMCUSandbox:

    def test_compile_valid_function(self):
        code = """
def tick(time_s, pins, state):
    return {"GPIO0": "HIGH"}
"""
        fn = mcu_mod.compile_tick_function(code)
        assert callable(fn)

    def test_compile_empty_code(self):
        with pytest.raises(mcu_mod.MCUSandboxError, match="Empty"):
            mcu_mod.compile_tick_function("")

    def test_compile_missing_tick(self):
        code = """
def not_tick(time_s, pins, state):
    return {}
"""
        with pytest.raises(mcu_mod.MCUSandboxError, match="must define"):
            mcu_mod.compile_tick_function(code)

    def test_compile_import_blocked(self):
        code = """
import os
def tick(time_s, pins, state):
    return {}
"""
        with pytest.raises(mcu_mod.MCUSandboxError, match="Forbidden"):
            mcu_mod.compile_tick_function(code)

    def test_compile_exec_blocked(self):
        code = """
def tick(time_s, pins, state):
    exec("print(1)")
    return {}
"""
        with pytest.raises(mcu_mod.MCUSandboxError, match="Forbidden"):
            mcu_mod.compile_tick_function(code)

    def test_compile_dunder_blocked(self):
        code = """
def tick(time_s, pins, state):
    return {"__class__": "HIGH"}
"""
        with pytest.raises(mcu_mod.MCUSandboxError, match="Forbidden"):
            mcu_mod.compile_tick_function(code)

    def test_execute_simple_tick(self):
        code = """
def tick(time_s, pins, state):
    return {"GPIO0": "HIGH", "GPIO1": "LOW"}
"""
        fn = mcu_mod.compile_tick_function(code)
        result = mcu_mod.execute_tick(fn, 0.0, {}, {})
        assert result["GPIO0"] == "HIGH"
        assert result["GPIO1"] == "LOW"

    def test_execute_with_pin_reading(self):
        code = """
def tick(time_s, pins, state):
    if pins.get("GPIO0", 0) > 2.5:
        return {"GPIO1": "HIGH"}
    return {"GPIO1": "LOW"}
"""
        fn = mcu_mod.compile_tick_function(code)
        result = mcu_mod.execute_tick(fn, 0.0, {"GPIO0": 3.3}, {})
        assert result["GPIO1"] == "HIGH"

        result = mcu_mod.execute_tick(fn, 0.0, {"GPIO0": 1.0}, {})
        assert result["GPIO1"] == "LOW"

    def test_execute_with_state(self):
        code = """
def tick(time_s, pins, state):
    count = state.get("count", 0) + 1
    state["count"] = count
    if count % 2 == 0:
        return {"GPIO0": "HIGH"}
    return {"GPIO0": "LOW"}
"""
        fn = mcu_mod.compile_tick_function(code)
        state = {}
        r1 = mcu_mod.execute_tick(fn, 0.0, {}, state)
        assert r1["GPIO0"] == "LOW"
        r2 = mcu_mod.execute_tick(fn, 0.001, {}, state)
        assert r2["GPIO0"] == "HIGH"

    def test_execute_invalid_output(self):
        code = """
def tick(time_s, pins, state):
    return {"GPIO0": "INVALID"}
"""
        fn = mcu_mod.compile_tick_function(code)
        with pytest.raises(mcu_mod.MCUSandboxError, match="Invalid pin state"):
            mcu_mod.execute_tick(fn, 0.0, {}, {})

    def test_execute_with_math(self):
        code = """
def tick(time_s, pins, state):
    if math.sin(2 * math.pi * 1000 * time_s) > 0:
        return {"GPIO0": "HIGH"}
    return {"GPIO0": "LOW"}
"""
        fn = mcu_mod.compile_tick_function(code)
        result = mcu_mod.execute_tick(fn, 0.0001, {}, {})
        assert result["GPIO0"] in ("HIGH", "LOW")

    def test_apply_mcu_outputs(self):
        outputs = {"GPIO0": "HIGH", "GPIO1": "LOW", "GPIO2": "HIZ"}
        pin_net_map = {"GPIO0": "net1", "GPIO1": "net2", "GPIO2": "net3"}
        result = mcu_mod.apply_mcu_outputs(outputs, pin_net_map, {})
        assert result["net1"] == 5.0
        assert result["net2"] == 0.0
        assert result["net3"] is None


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TestMCUAPI:

    @pytest.mark.asyncio
    async def test_upload_program(self, client):
        r = await client.post("/circuits", json={"name": "test"})
        cid = r.json()["id"]

        r = await client.post(f"/circuits/{cid}/components", json={
            "component_type": "mcu",
        })
        mcu_id = r.json()["id"]

        code = "def tick(time_s, pins, state):\n    return {'GPIO0': 'HIGH'}\n"
        r = await client.post(f"/circuits/{cid}/mcu/{mcu_id}/program", json={
            "source_code": code,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "compiled"

    @pytest.mark.asyncio
    async def test_get_program(self, client):
        r = await client.post("/circuits", json={"name": "test"})
        cid = r.json()["id"]
        r = await client.post(f"/circuits/{cid}/components", json={"component_type": "mcu"})
        mcu_id = r.json()["id"]

        code = "def tick(time_s, pins, state):\n    return {}\n"
        await client.post(f"/circuits/{cid}/mcu/{mcu_id}/program", json={"source_code": code})

        r = await client.get(f"/circuits/{cid}/mcu/{mcu_id}/program")
        assert r.status_code == 200
        assert "def tick" in r.json()["source_code"]

    @pytest.mark.asyncio
    async def test_delete_program(self, client):
        r = await client.post("/circuits", json={"name": "test"})
        cid = r.json()["id"]
        r = await client.post(f"/circuits/{cid}/components", json={"component_type": "mcu"})
        mcu_id = r.json()["id"]

        code = "def tick(time_s, pins, state):\n    return {}\n"
        await client.post(f"/circuits/{cid}/mcu/{mcu_id}/program", json={"source_code": code})

        r = await client.delete(f"/circuits/{cid}/mcu/{mcu_id}/program")
        assert r.status_code == 200

        r = await client.get(f"/circuits/{cid}/mcu/{mcu_id}/program")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_invalid_code(self, client):
        r = await client.post("/circuits", json={"name": "test"})
        cid = r.json()["id"]
        r = await client.post(f"/circuits/{cid}/components", json={"component_type": "mcu"})
        mcu_id = r.json()["id"]

        r = await client.post(f"/circuits/{cid}/mcu/{mcu_id}/program", json={
            "source_code": "import os\ndef tick(t,p,s): return {}",
        })
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_to_non_mcu(self, client):
        r = await client.post("/circuits", json={"name": "test"})
        cid = r.json()["id"]
        r = await client.post(f"/circuits/{cid}/components", json={
            "component_type": "resistor", "value": "1000",
        })
        res_id = r.json()["id"]

        r = await client.post(f"/circuits/{cid}/mcu/{res_id}/program", json={
            "source_code": "def tick(t,p,s): return {}",
        })
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_program_not_found(self, client):
        r = await client.post("/circuits", json={"name": "test"})
        cid = r.json()["id"]
        r = await client.post(f"/circuits/{cid}/components", json={"component_type": "mcu"})
        mcu_id = r.json()["id"]

        r = await client.get(f"/circuits/{cid}/mcu/{mcu_id}/program")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_mcu_in_library(self, client):
        resp = await client.get("/library")
        types = [i["type"] for i in resp.json()["items"]]
        assert "mcu" in types
