"""Catalogue integration tests — seed, resolve, create model, fallback."""

from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockCatalogueClient, MockUserDB, create_test_app
from backend.app.models import Primitive

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
cat_seed_mod = _load("cat_seed", "backend/catalogue_seed.py")

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


def _make_electronics_primitive(
    name: str, component_type: str, spice_params: dict, domain: str = "electronics"
) -> Primitive:
    slug = name.lower().replace(" ", "-")
    type_slug = component_type.replace("_", "-")
    return Primitive(
        id=f"elec-{slug}",
        type="material",
        name=name,
        slug=slug,
        path=f"materials/electronics-{type_slug}-{slug}",
        domain=domain,
        description=f"Electronics component: {name}",
        tags=["electronics", component_type],
        properties={
            "component_type": component_type,
            "spice_params": spice_params,
        },
    )


# ---------------------------------------------------------------------------
# Catalogue seed tests
# ---------------------------------------------------------------------------


class TestCatalogueSeed:

    def test_build_seed_entries_has_content(self):
        entries = cat_seed_mod.build_seed_entries()
        assert len(entries) > 0
        # Should have at least 1N4148, 2N3904
        names = [e["name"] for e in entries]
        assert "1N4148" in names
        assert "2N3904" in names

    def test_build_seed_entries_excludes_defaults(self):
        entries = cat_seed_mod.build_seed_entries()
        names = [e["name"] for e in entries]
        assert "default" not in names
        assert "default_npn" not in names
        assert "default_pnp" not in names

    def test_catalogue_path_for(self):
        assert cat_seed_mod.catalogue_path_for("diode", "1N4148") == "materials/electronics-diode-1n4148"
        assert cat_seed_mod.catalogue_path_for("npn_bjt", "2N3904") == "materials/electronics-npn-bjt-2n3904"
        assert cat_seed_mod.catalogue_path_for("pmos", "IRF9510") == "materials/electronics-pmos-irf9510"

    def test_seed_entries_have_required_fields(self):
        entries = cat_seed_mod.build_seed_entries()
        for entry in entries:
            assert "name" in entry
            assert "component_type" in entry
            assert "spice_params" in entry
            assert "description" in entry
            assert "tags" in entry
            assert isinstance(entry["spice_params"], dict)
            assert len(entry["spice_params"]) > 0

    def test_seed_entries_component_types(self):
        entries = cat_seed_mod.build_seed_entries()
        types = set(e["component_type"] for e in entries)
        # Should cover all nonlinear types
        assert "diode" in types
        assert "npn_bjt" in types or "pnp_bjt" in types

    @pytest.mark.asyncio
    async def test_seed_catalogue_endpoint(self, db):
        catalogue = MockCatalogueClient()
        # create_primitive returns a Primitive-like mock by default
        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            resp = await client.post("/catalogue/seed")
            assert resp.status_code == 200
            data = resp.json()
            assert "seeded" in data
            assert "skipped" in data
            assert data["seeded"] > 0

    @pytest.mark.asyncio
    async def test_seed_catalogue_skips_duplicates(self, db):
        catalogue = MockCatalogueClient()
        # Make create_primitive raise a conflict for every call
        catalogue.create_primitive = AsyncMock(side_effect=Exception("409 Conflict: already exists"))
        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            resp = await client.post("/catalogue/seed")
            assert resp.status_code == 200
            data = resp.json()
            assert data["seeded"] == 0
            assert data["skipped"] > 0


# ---------------------------------------------------------------------------
# Catalogue model listing
# ---------------------------------------------------------------------------


class TestCatalogueModels:

    @pytest.mark.asyncio
    async def test_list_catalogue_models(self, db):
        diode_prim = _make_electronics_primitive("1N4148", "diode", {"Is": 2.52e-9, "N": 1.752})
        catalogue = MockCatalogueClient()
        catalogue.search = AsyncMock(return_value=[diode_prim])

        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            resp = await client.get("/catalogue/models")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 1
            assert any(m["name"] == "1N4148" for m in data["items"])

    @pytest.mark.asyncio
    async def test_list_catalogue_models_filters_non_electronics(self, db):
        # A non-electronics primitive should be filtered out
        non_elec = Primitive(
            id="food-1",
            type="material",
            name="Flour",
            slug="flour",
            path="materials/flour",
            domain="kitchen",
            tags=["food"],
            properties={"category": "grain"},
        )
        catalogue = MockCatalogueClient()
        catalogue.search = AsyncMock(return_value=[non_elec])

        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            resp = await client.get("/catalogue/models")
            assert resp.status_code == 200
            assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_list_catalogue_models_with_type_filter(self, db):
        diode = _make_electronics_primitive("1N4148", "diode", {"Is": 2.52e-9})
        bjt = _make_electronics_primitive("2N3904", "npn_bjt", {"Bf": 300})
        catalogue = MockCatalogueClient()
        catalogue.search = AsyncMock(return_value=[diode, bjt])

        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            resp = await client.get("/catalogue/models?component_type=diode")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert all(m["component_type"] == "diode" for m in items)


# ---------------------------------------------------------------------------
# Create catalogue model
# ---------------------------------------------------------------------------


class TestCreateCatalogueModel:

    @pytest.mark.asyncio
    async def test_create_model(self, db):
        created_prim = _make_electronics_primitive("BAT54", "diode", {"Is": 2e-7, "N": 1.04})
        catalogue = MockCatalogueClient()
        catalogue.create_primitive = AsyncMock(return_value=created_prim)

        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            resp = await client.post("/catalogue/models", json={
                "component_type": "diode",
                "name": "BAT54",
                "spice_params": {"Is": 2e-7, "N": 1.04, "Bv": 30},
                "description": "Schottky barrier diode",
                "package": "SOT-23",
                "manufacturer": "Nexperia",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "BAT54"
            assert data["component_type"] == "diode"

    @pytest.mark.asyncio
    async def test_create_model_missing_fields(self, db):
        async with create_test_app(router, userdb=db) as client:
            # Missing component_type
            resp = await client.post("/catalogue/models", json={
                "name": "BAT54",
                "spice_params": {"Is": 2e-7},
            })
            assert resp.status_code == 400

            # Missing name
            resp = await client.post("/catalogue/models", json={
                "component_type": "diode",
                "spice_params": {"Is": 2e-7},
            })
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_model_invalid_type(self, db):
        async with create_test_app(router, userdb=db) as client:
            resp = await client.post("/catalogue/models", json={
                "component_type": "unknown_type",
                "name": "Test",
                "spice_params": {"Is": 1e-14},
            })
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_model_empty_spice_params(self, db):
        async with create_test_app(router, userdb=db) as client:
            resp = await client.post("/catalogue/models", json={
                "component_type": "diode",
                "name": "Test",
                "spice_params": {},
            })
            assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Catalogue resolution in component creation
# ---------------------------------------------------------------------------


class TestCatalogueResolution:

    @pytest.mark.asyncio
    async def test_add_component_with_catalogue_path(self, db):
        """Adding a component with catalogue_path should resolve SPICE params."""
        diode_prim = _make_electronics_primitive("1N4148", "diode", {"Is": 2.52e-9, "N": 1.752})
        catalogue = MockCatalogueClient()
        catalogue.get_primitive = AsyncMock(return_value=diode_prim)

        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            # Create circuit
            resp = await client.post("/circuits", json={"name": "Test"})
            circuit_id = resp.json()["id"]

            # Add diode with catalogue_path
            resp = await client.post(f"/circuits/{circuit_id}/components", json={
                "component_type": "diode",
                "catalogue_path": "materials/electronics-diode-1n4148",
                "x": 200,
                "y": 100,
            })
            assert resp.status_code == 201
            comp = resp.json()
            assert comp["component_type"] == "diode"
            assert comp["catalogue_path"] == "materials/electronics-diode-1n4148"

    @pytest.mark.asyncio
    async def test_add_component_catalogue_auto_type(self, db):
        """If component_type not provided, it should be inferred from catalogue."""
        bjt_prim = _make_electronics_primitive("2N3904", "npn_bjt", {"Bf": 300, "Is": 6.734e-15})
        catalogue = MockCatalogueClient()
        catalogue.get_primitive = AsyncMock(return_value=bjt_prim)

        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            resp = await client.post("/circuits", json={"name": "Test"})
            circuit_id = resp.json()["id"]

            # component_type should be auto-detected from catalogue
            resp = await client.post(f"/circuits/{circuit_id}/components", json={
                "component_type": "npn_bjt",
                "catalogue_path": "materials/electronics-npn-bjt-2n3904",
                "x": 200,
                "y": 100,
            })
            assert resp.status_code == 201
            assert resp.json()["component_type"] == "npn_bjt"

    @pytest.mark.asyncio
    async def test_add_component_without_catalogue_still_works(self, db):
        """Components without catalogue_path should work as before."""
        async with create_test_app(router, userdb=db) as client:
            resp = await client.post("/circuits", json={"name": "Test"})
            circuit_id = resp.json()["id"]

            resp = await client.post(f"/circuits/{circuit_id}/components", json={
                "component_type": "resistor",
                "value": "1k",
                "x": 200,
                "y": 100,
            })
            assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_catalogue_unavailable_falls_back(self, db):
        """If catalogue is unavailable, component creation should still work."""
        catalogue = MockCatalogueClient()
        catalogue.get_primitive = AsyncMock(side_effect=Exception("Core unavailable"))

        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            resp = await client.post("/circuits", json={"name": "Test"})
            circuit_id = resp.json()["id"]

            # Should still succeed — falls back to built-in presets
            resp = await client.post(f"/circuits/{circuit_id}/components", json={
                "component_type": "diode",
                "catalogue_path": "materials/electronics-diode-1n4148",
                "model_params": {"model": "1N4148"},
                "x": 200,
                "y": 100,
            })
            assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Catalogue resolution in simulation
# ---------------------------------------------------------------------------


class TestCatalogueSimulation:

    @pytest.mark.asyncio
    async def test_simulate_with_catalogue_component(self, db):
        """Simulation should resolve catalogue SPICE params for components."""
        diode_prim = _make_electronics_primitive(
            "1N4148", "diode", {"Is": 2.52e-9, "N": 1.752, "Vt": 0.02585, "Bv": 100.0, "Rs": 0.0}
        )
        catalogue = MockCatalogueClient()
        catalogue.get_primitive = AsyncMock(return_value=diode_prim)

        async with create_test_app(router, userdb=db, catalogue=catalogue) as client:
            # Create circuit with diode + resistor + source + ground
            resp = await client.post("/circuits", json={"name": "Diode Test"})
            cid = resp.json()["id"]

            # Add voltage source
            resp = await client.post(f"/circuits/{cid}/components", json={
                "component_type": "voltage_source", "value": "5", "x": 100, "y": 100,
            })
            vs_id = resp.json()["id"]

            # Add resistor
            resp = await client.post(f"/circuits/{cid}/components", json={
                "component_type": "resistor", "value": "1k", "x": 200, "y": 100,
            })
            r_id = resp.json()["id"]

            # Add diode with catalogue_path
            resp = await client.post(f"/circuits/{cid}/components", json={
                "component_type": "diode",
                "catalogue_path": "materials/electronics-diode-1n4148",
                "x": 300, "y": 100,
            })
            d_id = resp.json()["id"]

            # Add ground
            resp = await client.post(f"/circuits/{cid}/components", json={
                "component_type": "ground", "x": 100, "y": 300,
            })
            gnd_id = resp.json()["id"]

            # Wire: VS+ -> R -> D_anode, D_cathode -> GND, VS- -> GND
            await client.post(f"/circuits/{cid}/connect", json={
                "component_id": vs_id, "pin_name": "p", "net_name": "VCC",
            })
            await client.post(f"/circuits/{cid}/connect", json={
                "component_id": r_id, "pin_name": "p", "net_name": "VCC",
            })
            await client.post(f"/circuits/{cid}/connect", json={
                "component_id": r_id, "pin_name": "n", "net_name": "MID",
            })
            await client.post(f"/circuits/{cid}/connect", json={
                "component_id": d_id, "pin_name": "anode", "net_name": "MID",
            })
            await client.post(f"/circuits/{cid}/connect", json={
                "component_id": d_id, "pin_name": "cathode", "net_name": "GND",
            })
            await client.post(f"/circuits/{cid}/connect", json={
                "component_id": vs_id, "pin_name": "n", "net_name": "GND",
            })
            await client.post(f"/circuits/{cid}/connect", json={
                "component_id": gnd_id, "pin_name": "gnd", "net_name": "GND",
            })

            # Simulate
            resp = await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "complete"

            # Diode should have a forward voltage drop
            node_results = {n["net_name"]: n["voltage"] for n in data["node_results"]}
            assert "MID" in node_results
            # MID should be around 0.6-0.8V (diode forward voltage)
            assert 0.3 < node_results["MID"] < 1.0
