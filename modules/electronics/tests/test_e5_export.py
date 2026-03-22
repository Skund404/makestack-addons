"""E5 tests — Exporters (SPICE, BOM, CSV) and circuit templates."""

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
exporters = _load("exporters", "backend/exporters.py")
templates = _load("templates", "backend/templates.py")

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
# SPICE export unit tests
# ---------------------------------------------------------------------------

class TestSPICEExport:

    def test_resistor_netlist(self):
        components = [
            {"id": "c1", "component_type": "resistor", "ref_designator": "R1",
             "value": "1000", "properties": "{}"},
        ]
        nets = [
            {"id": "n1", "name": "VCC", "net_type": "signal"},
            {"id": "n2", "name": "GND", "net_type": "ground"},
        ]
        pins = [
            {"component_id": "c1", "pin_name": "p", "net_id": "n1"},
            {"component_id": "c1", "pin_name": "n", "net_id": "n2"},
        ]
        spice = exporters.export_spice(components, nets, pins, "test")
        assert "RR1" in spice
        assert "VCC" in spice
        assert "0" in spice  # GND mapped to 0
        assert ".end" in spice

    def test_voltage_source_netlist(self):
        components = [
            {"id": "c1", "component_type": "voltage_source", "ref_designator": "V1",
             "value": "5", "properties": "{}"},
        ]
        nets = [
            {"id": "n1", "name": "VCC", "net_type": "signal"},
            {"id": "n2", "name": "GND", "net_type": "ground"},
        ]
        pins = [
            {"component_id": "c1", "pin_name": "p", "net_id": "n1"},
            {"component_id": "c1", "pin_name": "n", "net_id": "n2"},
        ]
        spice = exporters.export_spice(components, nets, pins)
        assert "VV1" in spice
        assert "DC 5" in spice

    def test_bjt_with_model(self):
        components = [
            {"id": "c1", "component_type": "npn_bjt", "ref_designator": "Q1",
             "value": "0", "properties": '{"model": "2N3904"}'},
        ]
        nets = [
            {"id": "n1", "name": "C", "net_type": "signal"},
            {"id": "n2", "name": "B", "net_type": "signal"},
            {"id": "n3", "name": "GND", "net_type": "ground"},
        ]
        pins = [
            {"component_id": "c1", "pin_name": "collector", "net_id": "n1"},
            {"component_id": "c1", "pin_name": "base", "net_id": "n2"},
            {"component_id": "c1", "pin_name": "emitter", "net_id": "n3"},
        ]
        spice = exporters.export_spice(components, nets, pins)
        assert "QQ1" in spice
        assert "2N3904" in spice
        assert ".model 2N3904 NPN" in spice

    def test_diode_with_model_card(self):
        components = [
            {"id": "c1", "component_type": "diode", "ref_designator": "D1",
             "value": "0", "properties": '{"model": "1N4148"}'},
        ]
        nets = [
            {"id": "n1", "name": "A", "net_type": "signal"},
            {"id": "n2", "name": "GND", "net_type": "ground"},
        ]
        pins = [
            {"component_id": "c1", "pin_name": "anode", "net_id": "n1"},
            {"component_id": "c1", "pin_name": "cathode", "net_id": "n2"},
        ]
        spice = exporters.export_spice(components, nets, pins)
        assert "DD1" in spice
        assert "1N4148" in spice
        assert ".model 1N4148 D" in spice

    def test_ground_components_excluded(self):
        components = [
            {"id": "c1", "component_type": "ground", "ref_designator": "GND1",
             "value": "", "properties": "{}"},
        ]
        spice = exporters.export_spice(components, [], [])
        assert "GND1" not in spice


# ---------------------------------------------------------------------------
# BOM unit tests
# ---------------------------------------------------------------------------

class TestBOMExport:

    def test_bom_groups_identical(self):
        components = [
            {"id": "c1", "component_type": "resistor", "ref_designator": "R1",
             "value": "1000", "unit": "Ω", "properties": "{}"},
            {"id": "c2", "component_type": "resistor", "ref_designator": "R2",
             "value": "1000", "unit": "Ω", "properties": "{}"},
            {"id": "c3", "component_type": "resistor", "ref_designator": "R3",
             "value": "2000", "unit": "Ω", "properties": "{}"},
        ]
        bom = exporters.export_bom(components)
        assert len(bom) == 2  # Two groups: 1k and 2k
        r1k = [b for b in bom if b["value"] == "1000"][0]
        assert r1k["quantity"] == 2
        assert "R1" in r1k["ref_designators"]
        assert "R2" in r1k["ref_designators"]

    def test_bom_excludes_ground(self):
        components = [
            {"id": "c1", "component_type": "ground", "ref_designator": "GND1",
             "value": "", "unit": "", "properties": "{}"},
            {"id": "c2", "component_type": "resistor", "ref_designator": "R1",
             "value": "100", "unit": "", "properties": "{}"},
        ]
        bom = exporters.export_bom(components)
        types = [b["component_type"] for b in bom]
        assert "ground" not in types
        assert len(bom) == 1

    def test_bom_csv_format(self):
        components = [
            {"id": "c1", "component_type": "resistor", "ref_designator": "R1",
             "value": "1000", "unit": "Ω", "properties": "{}"},
        ]
        bom = exporters.export_bom(components)
        csv = exporters.export_bom_csv(bom)
        assert "Ref,Type,Value" in csv
        assert "R1" in csv

    def test_bom_includes_model(self):
        components = [
            {"id": "c1", "component_type": "diode", "ref_designator": "D1",
             "value": "0", "unit": "", "properties": '{"model": "1N4148"}'},
        ]
        bom = exporters.export_bom(components)
        assert bom[0]["model"] == "1N4148"


# ---------------------------------------------------------------------------
# Templates unit tests
# ---------------------------------------------------------------------------

class TestTemplates:

    def test_list_templates(self):
        items = templates.list_templates()
        assert len(items) >= 6
        names = [t["name"] for t in items]
        assert "Voltage Divider" in names
        assert "Apple 1 Clock Generator" in names

    def test_get_template(self):
        t = templates.get_template("voltage_divider")
        assert t is not None
        assert t["name"] == "Voltage Divider"
        assert len(t["components"]) >= 3

    def test_get_nonexistent_template(self):
        assert templates.get_template("nonexistent") is None

    def test_all_templates_have_ground(self):
        for tid, t in templates.TEMPLATES.items():
            types = [c["type"] for c in t["components"]]
            assert "ground" in types, f"Template '{tid}' missing ground component"

    def test_apple1_templates_exist(self):
        items = templates.list_templates()
        categories = [t["category"] for t in items]
        assert "apple1" in categories


# ---------------------------------------------------------------------------
# API export tests
# ---------------------------------------------------------------------------

class TestExportAPI:

    @pytest.mark.asyncio
    async def test_spice_export(self, client):
        # Create a circuit from template
        resp = await client.post("/circuits/from-template?template_id=voltage_divider")
        cid = resp.json()["id"]

        resp = await client.get(f"/circuits/{cid}/export/spice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "spice"
        assert ".end" in data["content"]
        assert "RR1" in data["content"] or "RV1" in data["content"]

    @pytest.mark.asyncio
    async def test_bom_export_json(self, client):
        resp = await client.post("/circuits/from-template?template_id=voltage_divider")
        cid = resp.json()["id"]

        resp = await client.get(f"/circuits/{cid}/export/bom")
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "json"
        assert len(data["items"]) >= 2  # At least resistors + voltage source

    @pytest.mark.asyncio
    async def test_bom_export_csv(self, client):
        resp = await client.post("/circuits/from-template?template_id=voltage_divider")
        cid = resp.json()["id"]

        resp = await client.get(f"/circuits/{cid}/export/bom?format=csv")
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "csv"
        assert "Ref,Type,Value" in data["content"]

    @pytest.mark.asyncio
    async def test_bundle_export(self, client):
        resp = await client.post("/circuits/from-template?template_id=common_emitter_amp")
        cid = resp.json()["id"]

        resp = await client.get(f"/circuits/{cid}/export/bundle")
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "electronics_circuit_v1"
        assert len(data["components"]) >= 4
        assert len(data["connections"]) >= 4


# ---------------------------------------------------------------------------
# Template API tests
# ---------------------------------------------------------------------------

class TestTemplateAPI:

    @pytest.mark.asyncio
    async def test_list_templates(self, client):
        resp = await client.get("/templates")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 6

    @pytest.mark.asyncio
    async def test_create_from_template(self, client):
        resp = await client.post("/circuits/from-template?template_id=voltage_divider")
        assert resp.status_code == 201
        data = resp.json()
        assert data["template_id"] == "voltage_divider"
        assert data["components"] >= 3

        # Verify circuit was created and can be simulated
        cid = data["id"]
        sim = await client.post(f"/circuits/{cid}/simulate")
        assert sim.status_code == 200
        sim_data = sim.json()
        assert sim_data["status"] == "complete"

    @pytest.mark.asyncio
    async def test_create_from_template_custom_name(self, client):
        resp = await client.post(
            "/circuits/from-template?template_id=voltage_divider&name=My%20Divider")
        assert resp.status_code == 201
        assert resp.json()["name"] == "My Divider"

    @pytest.mark.asyncio
    async def test_template_not_found(self, client):
        resp = await client.post("/circuits/from-template?template_id=nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_template_ce_amp_simulates(self, client):
        resp = await client.post("/circuits/from-template?template_id=common_emitter_amp")
        assert resp.status_code == 201
        cid = resp.json()["id"]

        sim = await client.post(f"/circuits/{cid}/simulate")
        assert sim.status_code == 200
        assert sim.json()["status"] == "complete"

    @pytest.mark.asyncio
    async def test_template_cmos_inverter_simulates(self, client):
        resp = await client.post("/circuits/from-template?template_id=cmos_inverter")
        assert resp.status_code == 201
        cid = resp.json()["id"]

        sim = await client.post(f"/circuits/{cid}/simulate")
        assert sim.status_code == 200
        assert sim.json()["status"] == "complete"

    @pytest.mark.asyncio
    async def test_template_opamp_simulates(self, client):
        resp = await client.post("/circuits/from-template?template_id=opamp_inverting")
        assert resp.status_code == 201
        cid = resp.json()["id"]

        sim = await client.post(f"/circuits/{cid}/simulate")
        assert sim.status_code == 200
        assert sim.json()["status"] == "complete"
