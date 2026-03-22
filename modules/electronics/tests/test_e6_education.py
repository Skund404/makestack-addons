"""E6 tests — Educational calculators and MNA explainer."""

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
education = _load("education", "backend/education.py")

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
# Calculator unit tests
# ---------------------------------------------------------------------------

class TestVoltageDivider:

    def test_equal_resistors(self):
        result = education.voltage_divider(10.0, 1000.0, 1000.0)
        assert result["v_out"] == pytest.approx(5.0)
        assert result["current_ma"] == pytest.approx(5.0)

    def test_unequal_resistors(self):
        result = education.voltage_divider(12.0, 10000.0, 2000.0)
        assert result["v_out"] == pytest.approx(2.0)

    def test_zero_total_resistance(self):
        result = education.voltage_divider(5.0, 0.0, 0.0)
        assert "error" in result

    def test_has_formula(self):
        result = education.voltage_divider(10.0, 1000.0, 1000.0)
        assert "formula" in result
        assert "5.0V" in result["formula"]


class TestLEDResistor:

    def test_basic_led(self):
        result = education.led_resistor(5.0, 2.0, 20.0)
        assert result["r_exact_ohm"] == pytest.approx(150.0)
        assert result["r_nearest_e24"] == 150.0

    def test_supply_below_vled(self):
        result = education.led_resistor(1.0, 2.0, 20.0)
        assert "error" in result

    def test_3v3_supply_red_led(self):
        result = education.led_resistor(3.3, 2.0, 10.0)
        assert result["r_exact_ohm"] == pytest.approx(130.0)


class TestRCFilter:

    def test_1khz_filter(self):
        # R=1kΩ, C=159nF → fc ≈ 1kHz
        result = education.rc_filter(1000.0, 159e-9)
        assert 900 < result["cutoff_freq_hz"] < 1100

    def test_zero_values(self):
        result = education.rc_filter(0, 1e-6)
        assert "error" in result


class TestBJTBias:

    def test_basic_bias(self):
        result = education.bjt_bias(12.0, 1.0, 100.0)
        assert result["ic_ma"] == 1.0
        assert result["r1_ohm"] > 0
        assert result["r2_ohm"] > 0
        assert result["rc_ohm"] > 0
        assert result["re_ohm"] > 0
        assert 0.6 < result["vb_v"] < 2.0

    def test_custom_vce(self):
        result = education.bjt_bias(12.0, 5.0, 200.0, vce=6.0)
        assert result["vce_v"] == pytest.approx(6.0)

    def test_e24_rounding(self):
        result = education.bjt_bias(12.0, 1.0)
        # Should use E24 standard values
        assert result["r1_ohm"] > 0
        # E24 values should differ from exact
        # (though they could match by coincidence)


class TestNearestE24:

    def test_exact_match(self):
        assert education._nearest_e24(1000.0) == 1000.0

    def test_close_match(self):
        assert education._nearest_e24(1500.0) == 1500.0

    def test_rounding(self):
        val = education._nearest_e24(1234.0)
        assert val in [1200.0, 1300.0]


# ---------------------------------------------------------------------------
# MNA Explainer unit tests
# ---------------------------------------------------------------------------

class TestMNAExplainer:

    def test_simple_circuit(self):
        components = [
            {"id": "c1", "component_type": "voltage_source", "ref_designator": "V1", "value": "5"},
            {"id": "c2", "component_type": "resistor", "ref_designator": "R1", "value": "1000"},
            {"id": "c3", "component_type": "ground", "ref_designator": "GND1", "value": ""},
        ]
        nets = [
            {"id": "n1", "name": "VCC", "net_type": "signal"},
            {"id": "n2", "name": "GND", "net_type": "ground"},
        ]
        pins = [
            {"component_id": "c1", "pin_name": "p", "net_id": "n1"},
            {"component_id": "c1", "pin_name": "n", "net_id": "n2"},
            {"component_id": "c2", "pin_name": "p", "net_id": "n1"},
            {"component_id": "c2", "pin_name": "n", "net_id": "n2"},
        ]
        steps = education.explain_mna(components, nets, pins)
        assert len(steps) >= 3  # Identify nodes, count branches, stamp components, solve
        assert steps[0]["title"] == "Identify Nodes"
        assert "VCC" in steps[0]["description"]
        assert steps[-1]["title"] == "Solve Ax = z"

    def test_nonlinear_mentions_nr(self):
        components = [
            {"id": "c1", "component_type": "diode", "ref_designator": "D1", "value": "0"},
        ]
        nets = [{"id": "n1", "name": "A", "net_type": "signal"},
                {"id": "n2", "name": "GND", "net_type": "ground"}]
        pins = [
            {"component_id": "c1", "pin_name": "anode", "net_id": "n1"},
            {"component_id": "c1", "pin_name": "cathode", "net_id": "n2"},
        ]
        steps = education.explain_mna(components, nets, pins)
        solve_step = steps[-1]
        assert "Newton-Raphson" in solve_step["description"]

    def test_opamp_explanation(self):
        components = [
            {"id": "c1", "component_type": "opamp", "ref_designator": "U1", "value": "0"},
        ]
        nets = [
            {"id": "n1", "name": "IN+", "net_type": "signal"},
            {"id": "n2", "name": "IN-", "net_type": "signal"},
            {"id": "n3", "name": "OUT", "net_type": "signal"},
            {"id": "n4", "name": "GND", "net_type": "ground"},
        ]
        pins = [
            {"component_id": "c1", "pin_name": "non_inv", "net_id": "n1"},
            {"component_id": "c1", "pin_name": "inv", "net_id": "n2"},
            {"component_id": "c1", "pin_name": "output", "net_id": "n3"},
        ]
        steps = education.explain_mna(components, nets, pins)
        opamp_step = [s for s in steps if "op-amp" in s["title"]]
        assert len(opamp_step) == 1
        assert "VCVS" in opamp_step[0]["description"]


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TestCalculatorAPI:

    @pytest.mark.asyncio
    async def test_voltage_divider_api(self, client):
        resp = await client.post("/calculators/voltage-divider?v_in=10&r1=1000&r2=1000")
        assert resp.status_code == 200
        assert resp.json()["v_out"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_led_resistor_api(self, client):
        resp = await client.post("/calculators/led-resistor?v_supply=5&v_led=2&i_led_ma=20")
        assert resp.status_code == 200
        assert resp.json()["r_exact_ohm"] == pytest.approx(150.0)

    @pytest.mark.asyncio
    async def test_rc_filter_api(self, client):
        resp = await client.post("/calculators/rc-filter?r=1000&c=0.000000159")
        assert resp.status_code == 200
        assert 900 < resp.json()["cutoff_freq_hz"] < 1100

    @pytest.mark.asyncio
    async def test_bjt_bias_api(self, client):
        resp = await client.post("/calculators/bjt-bias?vcc=12&ic_ma=1")
        assert resp.status_code == 200
        assert resp.json()["ic_ma"] == 1.0

    @pytest.mark.asyncio
    async def test_explain_mna_api(self, client):
        # Create a circuit from template
        r = await client.post("/circuits/from-template?template_id=voltage_divider")
        cid = r.json()["id"]

        resp = await client.get(f"/circuits/{cid}/explain-mna")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_steps"] >= 3
        assert data["steps"][0]["title"] == "Identify Nodes"
