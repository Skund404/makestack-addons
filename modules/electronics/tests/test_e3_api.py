"""E3 API tests — model presets, nonlinear component creation, simulation with NR."""

from __future__ import annotations

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
routes_mod = _load("routes", "backend/routes.py")

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
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Model preset endpoint tests
# ---------------------------------------------------------------------------

class TestModelPresets:

    @pytest.mark.asyncio
    async def test_diode_presets(self, client):
        resp = await client.get("/library/diode/models")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "1N4148" in names
        assert "1N4001" in names

    @pytest.mark.asyncio
    async def test_bjt_npn_presets(self, client):
        resp = await client.get("/library/npn_bjt/models")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "2N3904" in names
        assert "2N3906" not in names

    @pytest.mark.asyncio
    async def test_bjt_pnp_presets(self, client):
        resp = await client.get("/library/pnp_bjt/models")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "2N3906" in names
        assert "2N3904" not in names

    @pytest.mark.asyncio
    async def test_mosfet_presets(self, client):
        resp = await client.get("/library/nmos/models")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "2N7000" in names

    @pytest.mark.asyncio
    async def test_zener_presets(self, client):
        resp = await client.get("/library/zener/models")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "1N4733A" in names

    @pytest.mark.asyncio
    async def test_led_presets(self, client):
        resp = await client.get("/library/led/models")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "red" in names

    @pytest.mark.asyncio
    async def test_resistor_has_no_presets(self, client):
        resp = await client.get("/library/resistor/models")
        assert resp.status_code == 200
        assert resp.json()["models"] == []

    @pytest.mark.asyncio
    async def test_unknown_type_404(self, client):
        resp = await client.get("/library/unknown_type/models")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Component creation with model_params
# ---------------------------------------------------------------------------

class TestComponentCreationWithParams:

    @pytest.mark.asyncio
    async def test_create_diode(self, client):
        resp = await client.post("/circuits", json={"name": "test"})
        cid = resp.json()["id"]

        resp = await client.post(f"/circuits/{cid}/components", json={
            "component_type": "diode",
            "model_params": {"model": "1N4148"},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["component_type"] == "diode"
        assert data["ref_designator"].startswith("D")

    @pytest.mark.asyncio
    async def test_create_npn_bjt(self, client):
        resp = await client.post("/circuits", json={"name": "test"})
        cid = resp.json()["id"]

        resp = await client.post(f"/circuits/{cid}/components", json={
            "component_type": "npn_bjt",
            "model_params": {"model": "2N3904"},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["ref_designator"].startswith("Q")
        assert len(data["pins"]) == 3

    @pytest.mark.asyncio
    async def test_create_opamp(self, client):
        resp = await client.post("/circuits", json={"name": "test"})
        cid = resp.json()["id"]

        resp = await client.post(f"/circuits/{cid}/components", json={
            "component_type": "opamp",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["ref_designator"].startswith("U")
        assert len(data["pins"]) == 3
        pin_names = {p["pin_name"] for p in data["pins"]}
        assert pin_names == {"non_inv", "inv", "output"}

    @pytest.mark.asyncio
    async def test_library_includes_new_types(self, client):
        resp = await client.get("/library")
        types = [i["type"] for i in resp.json()["items"]]
        for t in ["diode", "zener", "led", "npn_bjt", "pnp_bjt", "nmos", "pmos", "opamp"]:
            assert t in types, f"{t} not in library"
