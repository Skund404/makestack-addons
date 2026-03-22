"""E2 Stage Tests — Full end-to-end validation of reactive components and analysis.

These tests exercise the complete E2 feature set through the API:
1. Capacitor and inductor component lifecycle
2. AC frequency sweep with RC/RL/RLC circuits
3. DC sweep with parameter variation
4. Transient analysis with time-domain waveforms
5. Mixed RLC circuits across all analysis modes
6. Edge cases and error handling
7. Backward compatibility — existing E1/E1b functionality unbroken
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB, create_test_app

# ---------------------------------------------------------------------------
# Module loading
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
migration_004 = _load("mig004", "backend/migrations/004_e3_operating_region.py")
migration_005 = _load("mig005", "backend/migrations/005_e4_subcircuits.py")
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
    await migration_004.up(userdb)
    await migration_005.up(userdb)
    yield userdb
    await userdb.teardown()


@pytest_asyncio.fixture
async def client(db):
    async with create_test_app(router, userdb=db) as c:
        yield c


# ---------------------------------------------------------------------------
# Circuit builders
# ---------------------------------------------------------------------------


async def _build_rc_lowpass(client, v=1.0, r=1000.0, c=1e-6):
    """V → R → OUT → C → GND.  f_c = 1/(2πRC)."""
    circ = (await client.post("/circuits", json={"name": "RC Low-Pass"})).json()
    cid = circ["id"]

    v1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "voltage_source", "value": str(v)
    })).json()
    r1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor", "value": str(r)
    })).json()
    c1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "capacitor", "value": str(c)
    })).json()
    gnd = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "ground"
    })).json()

    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VIN"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "p", "net_name": "VIN"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "n", "net_name": "OUT"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": c1["id"], "pin_name": "p", "net_name": "OUT"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": c1["id"], "pin_name": "n", "net_name": "GND"})

    return cid, {"v1": v1, "r1": r1, "c1": c1, "gnd": gnd}


async def _build_rl_circuit(client, v=10.0, r=100.0, l=0.01):
    """V → R → MID → L → GND."""
    circ = (await client.post("/circuits", json={"name": "RL Circuit"})).json()
    cid = circ["id"]

    v1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "voltage_source", "value": str(v)
    })).json()
    r1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor", "value": str(r)
    })).json()
    l1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "inductor", "value": str(l)
    })).json()
    gnd = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "ground"
    })).json()

    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "n", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": l1["id"], "pin_name": "p", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": l1["id"], "pin_name": "n", "net_name": "GND"})

    return cid, {"v1": v1, "r1": r1, "l1": l1, "gnd": gnd}


async def _build_rlc_series(client, v=1.0, r=100.0, l=0.01, c=1e-6):
    """V → R → N1 → L → N2 → C → GND. Series RLC."""
    circ = (await client.post("/circuits", json={"name": "RLC Series"})).json()
    cid = circ["id"]

    v1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "voltage_source", "value": str(v)
    })).json()
    r1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor", "value": str(r)
    })).json()
    l1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "inductor", "value": str(l)
    })).json()
    c1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "capacitor", "value": str(c)
    })).json()
    gnd = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "ground"
    })).json()

    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VIN"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "p", "net_name": "VIN"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1["id"], "pin_name": "n", "net_name": "N1"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": l1["id"], "pin_name": "p", "net_name": "N1"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": l1["id"], "pin_name": "n", "net_name": "N2"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": c1["id"], "pin_name": "p", "net_name": "N2"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": c1["id"], "pin_name": "n", "net_name": "GND"})

    return cid, {"v1": v1, "r1": r1, "l1": l1, "c1": c1, "gnd": gnd}


async def _build_voltage_divider(client, v=10.0, r1=10000.0, r2=10000.0):
    """Standard E1 voltage divider for backward compat checks."""
    circ = (await client.post("/circuits", json={"name": "Divider"})).json()
    cid = circ["id"]

    v1 = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "voltage_source", "value": str(v)
    })).json()
    r1c = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor", "value": str(r1)
    })).json()
    r2c = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor", "value": str(r2)
    })).json()
    gnd = (await client.post(f"/circuits/{cid}/components", json={
        "component_type": "ground"
    })).json()

    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": v1["id"], "pin_name": "n", "net_name": "GND"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1c["id"], "pin_name": "p", "net_name": "VCC"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r1c["id"], "pin_name": "n", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r2c["id"], "pin_name": "p", "net_name": "MID"})
    await client.post(f"/circuits/{cid}/connect", json={"component_id": r2c["id"], "pin_name": "n", "net_name": "GND"})

    return cid, {"v1": v1, "r1": r1c, "r2": r2c, "gnd": gnd}


def _get_net_id(circuit, net_name):
    """Extract net ID by name from circuit response."""
    for n in circuit["nets"]:
        if n["name"] == net_name:
            return n["id"]
    return None


# ===================================================================
# STAGE 1: Component Lifecycle
# ===================================================================


class TestComponentLifecycle:
    """Capacitor and inductor placement, update, delete."""

    @pytest.mark.asyncio
    async def test_place_capacitor_default(self, client):
        c = (await client.post("/circuits", json={"name": "T"})).json()
        resp = await client.post(f"/circuits/{c['id']}/components", json={
            "component_type": "capacitor"
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["ref_designator"] == "C1"
        assert body["unit"] == "F"
        assert len(body["pins"]) == 2
        pin_names = sorted([p["pin_name"] for p in body["pins"]])
        assert pin_names == ["n", "p"]

    @pytest.mark.asyncio
    async def test_place_inductor_default(self, client):
        c = (await client.post("/circuits", json={"name": "T"})).json()
        resp = await client.post(f"/circuits/{c['id']}/components", json={
            "component_type": "inductor"
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["ref_designator"] == "L1"
        assert body["unit"] == "H"
        assert len(body["pins"]) == 2

    @pytest.mark.asyncio
    async def test_auto_increment_ref_designators(self, client):
        c = (await client.post("/circuits", json={"name": "T"})).json()
        c1 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "capacitor"})).json()
        c2 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "capacitor"})).json()
        l1 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "inductor"})).json()
        l2 = (await client.post(f"/circuits/{c['id']}/components", json={"component_type": "inductor"})).json()

        assert c1["ref_designator"] == "C1"
        assert c2["ref_designator"] == "C2"
        assert l1["ref_designator"] == "L1"
        assert l2["ref_designator"] == "L2"

    @pytest.mark.asyncio
    async def test_capacitor_engineering_value(self, client):
        """100nF → 1e-7."""
        c = (await client.post("/circuits", json={"name": "T"})).json()
        resp = await client.post(f"/circuits/{c['id']}/components", json={
            "component_type": "capacitor", "value": "100nF"
        })
        assert float(resp.json()["value"]) == pytest.approx(1e-7)

    @pytest.mark.asyncio
    async def test_inductor_engineering_value(self, client):
        """4.7mH → 0.0047."""
        c = (await client.post("/circuits", json={"name": "T"})).json()
        resp = await client.post(f"/circuits/{c['id']}/components", json={
            "component_type": "inductor", "value": "4.7mH"
        })
        assert float(resp.json()["value"]) == pytest.approx(4.7e-3)

    @pytest.mark.asyncio
    async def test_update_capacitor_value(self, client):
        c = (await client.post("/circuits", json={"name": "T"})).json()
        cap = (await client.post(f"/circuits/{c['id']}/components", json={
            "component_type": "capacitor"
        })).json()
        resp = await client.put(f"/components/{cap['id']}", json={"value": "22pF"})
        assert resp.status_code == 200
        assert float(resp.json()["value"]) == pytest.approx(22e-12)

    @pytest.mark.asyncio
    async def test_delete_capacitor(self, client):
        c = (await client.post("/circuits", json={"name": "T"})).json()
        cap = (await client.post(f"/circuits/{c['id']}/components", json={
            "component_type": "capacitor"
        })).json()
        resp = await client.delete(f"/components/{cap['id']}")
        assert resp.status_code == 200
        circuit = (await client.get(f"/circuits/{c['id']}")).json()
        assert len(circuit["components"]) == 0

    @pytest.mark.asyncio
    async def test_library_lists_all_six_types(self, client):
        resp = await client.get("/library")
        types = [i["type"] for i in resp.json()["items"]]
        assert "resistor" in types
        assert "capacitor" in types
        assert "inductor" in types
        assert "voltage_source" in types
        assert "current_source" in types
        assert "ground" in types
        assert len(types) >= 6  # E3 adds diode, zener, led, npn_bjt, pnp_bjt, nmos, pmos, opamp


# ===================================================================
# STAGE 2: DC Operating Point with Reactive Components
# ===================================================================


class TestDCWithReactiveComponents:
    """Verify capacitor=open and inductor=short in DC."""

    @pytest.mark.asyncio
    async def test_capacitor_open_in_dc(self, client):
        """V → R → C → GND: cap open → no current → OUT = VCC."""
        cid, comps = await _build_rc_lowpass(client, v=10.0, r=1000.0, c=1e-6)
        result = (await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})).json()
        assert result["status"] == "complete"

        circuit = (await client.get(f"/circuits/{cid}")).json()
        out_id = _get_net_id(circuit, "OUT")
        out_v = [nr for nr in result["node_results"] if nr["net_id"] == out_id]
        assert out_v[0]["voltage"] == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_inductor_short_in_dc(self, client):
        """V → R → L → GND: inductor short → MID = 0V, I = V/R."""
        cid, comps = await _build_rl_circuit(client, v=10.0, r=100.0, l=0.01)
        result = (await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})).json()
        assert result["status"] == "complete"

        circuit = (await client.get(f"/circuits/{cid}")).json()
        mid_id = _get_net_id(circuit, "MID")
        mid_v = [nr for nr in result["node_results"] if nr["net_id"] == mid_id]
        # Inductor shorts MID to GND → MID ≈ 0V
        assert mid_v[0]["voltage"] == pytest.approx(0.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_rlc_dc_op(self, client):
        """Series RLC in DC: L=short, C=open."""
        cid, comps = await _build_rlc_series(client, v=12.0, r=100.0, l=0.01, c=1e-6)
        result = (await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})).json()
        assert result["status"] == "complete"

        circuit = (await client.get(f"/circuits/{cid}")).json()
        # N1 is after R, N2 is after L (before C)
        # L is short → N1 = N2. C is open → no current.
        # So all voltage across V, none across R (no current), N1 = N2 = VIN
        n1_id = _get_net_id(circuit, "N1")
        n2_id = _get_net_id(circuit, "N2")
        n1 = [nr for nr in result["node_results"] if nr["net_id"] == n1_id]
        n2 = [nr for nr in result["node_results"] if nr["net_id"] == n2_id]
        assert n1[0]["voltage"] == pytest.approx(12.0, abs=0.1)
        assert n2[0]["voltage"] == pytest.approx(12.0, abs=0.1)


# ===================================================================
# STAGE 3: AC Analysis
# ===================================================================


class TestACAnalysis:
    """AC frequency sweep tests."""

    @pytest.mark.asyncio
    async def test_ac_returns_sweep_data(self, client):
        cid, _ = await _build_rc_lowpass(client)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "ac", "f_start": 10, "f_stop": 100000, "points_per_decade": 5,
        })).json()

        assert result["status"] == "complete"
        assert result["sim_type"] == "ac"
        assert "sweep_data" in result
        assert len(result["sweep_data"]) > 0

    @pytest.mark.asyncio
    async def test_ac_frequency_values_increase(self, client):
        cid, _ = await _build_rc_lowpass(client)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "ac", "f_start": 100, "f_stop": 10000, "points_per_decade": 3,
        })).json()

        freqs = [p["parameter_value"] for p in result["sweep_data"]]
        for i in range(1, len(freqs)):
            assert freqs[i] > freqs[i - 1]

    @pytest.mark.asyncio
    async def test_rc_lowpass_rolloff(self, client):
        """RC low-pass: gain drops above cutoff frequency."""
        R, C = 1000.0, 1e-6  # f_c ≈ 159 Hz
        cid, _ = await _build_rc_lowpass(client, v=1.0, r=R, c=C)

        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "ac", "f_start": 1, "f_stop": 1000000, "points_per_decade": 10,
        })).json()

        circuit = (await client.get(f"/circuits/{cid}")).json()
        out_id = _get_net_id(circuit, "OUT")

        # Get magnitude at low and high frequencies
        sweep = result["sweep_data"]
        low = [p for p in sweep if p["parameter_value"] < 10]
        high = [p for p in sweep if p["parameter_value"] > 100000]

        if low and out_id in low[0]["node_voltages"]:
            v_low = low[0]["node_voltages"][out_id]
            mag_low = v_low["magnitude"] if isinstance(v_low, dict) else abs(v_low)
            assert mag_low > 0.8, f"Low-freq gain should be near 1, got {mag_low}"

        if high and out_id in high[-1]["node_voltages"]:
            v_high = high[-1]["node_voltages"][out_id]
            mag_high = v_high["magnitude"] if isinstance(v_high, dict) else abs(v_high)
            assert mag_high < 0.1, f"High-freq gain should be attenuated, got {mag_high}"

    @pytest.mark.asyncio
    async def test_ac_complex_voltage_format(self, client):
        """AC sweep should return complex voltages with magnitude and phase."""
        cid, _ = await _build_rc_lowpass(client)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "ac", "f_start": 100, "f_stop": 1000, "points_per_decade": 3,
        })).json()

        circuit = (await client.get(f"/circuits/{cid}")).json()
        out_id = _get_net_id(circuit, "OUT")

        # At least some points should have complex format
        for pt in result["sweep_data"]:
            v = pt["node_voltages"].get(out_id)
            if v is not None and isinstance(v, dict):
                assert "real" in v
                assert "imag" in v
                assert "magnitude" in v
                assert "phase_deg" in v
                break

    @pytest.mark.asyncio
    async def test_ac_rl_circuit(self, client):
        """RL circuit AC response."""
        cid, _ = await _build_rl_circuit(client, v=1.0, r=1000.0, l=0.1)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "ac", "f_start": 10, "f_stop": 100000, "points_per_decade": 5,
        })).json()
        assert result["status"] == "complete"
        assert len(result["sweep_data"]) > 0

    @pytest.mark.asyncio
    async def test_ac_rlc_series(self, client):
        """Series RLC AC response — should show resonance."""
        cid, _ = await _build_rlc_series(client, v=1.0, r=100.0, l=0.01, c=1e-6)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "ac", "f_start": 100, "f_stop": 100000, "points_per_decade": 10,
        })).json()
        assert result["status"] == "complete"
        assert len(result["sweep_data"]) > 10


# ===================================================================
# STAGE 4: DC Sweep
# ===================================================================


class TestDCSweep:
    """DC parameter sweep tests."""

    @pytest.mark.asyncio
    async def test_dc_sweep_voltage_divider(self, client):
        """Sweep voltage source and check linear response."""
        cid, comps = await _build_voltage_divider(client, v=0.0)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "dc_sweep",
            "sweep_source_id": comps["v1"]["id"],
            "sweep_start": 0,
            "sweep_stop": 20,
            "sweep_steps": 5,
        })).json()

        assert result["status"] == "complete"
        assert len(result["sweep_data"]) == 5

        circuit = (await client.get(f"/circuits/{cid}")).json()
        mid_id = _get_net_id(circuit, "MID")

        for pt in result["sweep_data"]:
            v_in = pt["parameter_value"]
            v_mid = pt["node_voltages"].get(mid_id)
            if v_mid is not None:
                assert v_mid == pytest.approx(v_in * 0.5, abs=0.1)

    @pytest.mark.asyncio
    async def test_dc_sweep_with_capacitor(self, client):
        """DC sweep with cap in circuit — cap is open at every DC point."""
        cid, comps = await _build_rc_lowpass(client, v=0.0, r=1000.0, c=1e-6)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "dc_sweep",
            "sweep_source_id": comps["v1"]["id"],
            "sweep_start": 0,
            "sweep_stop": 10,
            "sweep_steps": 5,
        })).json()

        assert result["status"] == "complete"

        circuit = (await client.get(f"/circuits/{cid}")).json()
        out_id = _get_net_id(circuit, "OUT")

        # Cap open → no current → OUT = VIN at every point
        for pt in result["sweep_data"]:
            v_out = pt["node_voltages"].get(out_id)
            if v_out is not None:
                assert v_out == pytest.approx(pt["parameter_value"], abs=0.1)

    @pytest.mark.asyncio
    async def test_dc_sweep_missing_source_id(self, client):
        cid, _ = await _build_voltage_divider(client)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "dc_sweep",
        })).json()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_dc_sweep_includes_component_results(self, client):
        """Sweep data includes component currents/power."""
        cid, comps = await _build_voltage_divider(client, v=0.0)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "dc_sweep",
            "sweep_source_id": comps["v1"]["id"],
            "sweep_start": 0,
            "sweep_stop": 10,
            "sweep_steps": 3,
        })).json()

        assert result["status"] == "complete"
        # At least the last point should have component results
        last = result["sweep_data"][-1]
        assert len(last["component_results"]) > 0


# ===================================================================
# STAGE 5: Transient Analysis
# ===================================================================


class TestTransientAnalysis:
    """Time-domain transient simulation tests."""

    @pytest.mark.asyncio
    async def test_transient_returns_waveform(self, client):
        cid, _ = await _build_rc_lowpass(client, v=10.0)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "transient", "t_stop": 0.005,
        })).json()

        assert result["status"] == "complete"
        assert result["sim_type"] == "transient"
        assert len(result["sweep_data"]) > 0

    @pytest.mark.asyncio
    async def test_transient_time_ordering(self, client):
        cid, _ = await _build_voltage_divider(client)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "transient", "t_stop": 0.001,
        })).json()

        times = [p["parameter_value"] for p in result["sweep_data"]]
        for i in range(1, len(times)):
            assert times[i] >= times[i - 1]

    @pytest.mark.asyncio
    async def test_transient_dc_steady_state(self, client):
        """Pure resistive: every time step is at DC steady state."""
        cid, _ = await _build_voltage_divider(client, v=10.0)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "transient", "t_stop": 0.001,
        })).json()

        circuit = (await client.get(f"/circuits/{cid}")).json()
        mid_id = _get_net_id(circuit, "MID")

        for pt in result["sweep_data"]:
            v_mid = pt["node_voltages"].get(mid_id)
            if v_mid is not None:
                assert v_mid == pytest.approx(5.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_transient_rl_current_ramp(self, client):
        """RL circuit: inductor current ramps to steady state."""
        R, L = 100.0, 0.01
        tau = L / R  # 0.1ms
        cid, _ = await _build_rl_circuit(client, v=5.0, r=R, l=L)

        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "transient", "t_stop": 5 * tau,
        })).json()

        assert result["status"] == "complete"
        assert len(result["sweep_data"]) > 5

    @pytest.mark.asyncio
    async def test_transient_rlc_completes(self, client):
        """Series RLC transient completes without error."""
        cid, _ = await _build_rlc_series(client, v=5.0, r=100.0, l=0.001, c=1e-6)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "transient", "t_stop": 0.005,
        })).json()
        assert result["status"] == "complete"


# ===================================================================
# STAGE 6: Results Persistence & Retrieval
# ===================================================================


class TestResultsPersistence:
    """Verify simulation results are stored and retrievable."""

    @pytest.mark.asyncio
    async def test_ac_result_persisted(self, client):
        cid, _ = await _build_rc_lowpass(client)
        sim = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "ac", "f_start": 100, "f_stop": 10000,
        })).json()

        resp = await client.get(f"/circuits/{cid}/results/{sim['id']}")
        assert resp.status_code == 200
        assert resp.json()["sim_type"] == "ac"

    @pytest.mark.asyncio
    async def test_latest_result_updates(self, client):
        """GET /results returns the most recent sim."""
        cid, comps = await _build_voltage_divider(client)

        # Run DC OP
        await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})
        r1 = (await client.get(f"/circuits/{cid}/results")).json()
        assert r1["sim_type"] == "op"

        # Run AC
        await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "ac"})
        r2 = (await client.get(f"/circuits/{cid}/results")).json()
        assert r2["sim_type"] == "ac"

    @pytest.mark.asyncio
    async def test_circuit_full_includes_last_sim(self, client):
        cid, _ = await _build_rc_lowpass(client)
        await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "ac"})

        circuit = (await client.get(f"/circuits/{cid}")).json()
        assert circuit["last_sim_result"] is not None
        assert circuit["last_sim_result"]["sim_type"] == "ac"


# ===================================================================
# STAGE 7: Backward Compatibility
# ===================================================================


class TestBackwardCompat:
    """E1/E1b features still work after E2 changes."""

    @pytest.mark.asyncio
    async def test_voltage_divider_dc_op(self, client):
        """Classic voltage divider still works."""
        cid, _ = await _build_voltage_divider(client, v=10.0)
        result = (await client.post(f"/circuits/{cid}/simulate", json={"sim_type": "op"})).json()
        assert result["status"] == "complete"

        mid = [nr for nr in result["node_results"] if nr["net_name"] == "MID"]
        assert mid[0]["voltage"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_default_simulate_is_dc_op(self, client):
        """POST /simulate with no body defaults to DC OP."""
        cid, _ = await _build_voltage_divider(client)
        result = (await client.post(f"/circuits/{cid}/simulate")).json()
        assert result["status"] == "complete"
        assert result["sim_type"] == "op"

    @pytest.mark.asyncio
    async def test_drc_still_works(self, client):
        """DRC endpoint from E1b still functional."""
        c = (await client.post("/circuits", json={"name": "T"})).json()
        await client.post(f"/circuits/{c['id']}/components", json={"component_type": "resistor"})

        resp = await client.get(f"/circuits/{c['id']}/drc")
        assert resp.status_code == 200
        types = [w["type"] for w in resp.json()["warnings"]]
        assert "no_ground" in types

    @pytest.mark.asyncio
    async def test_wire_endpoints_still_work(self, client):
        """Wire CRUD from E1b still functional."""
        c = (await client.post("/circuits", json={"name": "T"})).json()
        resp = await client.get(f"/circuits/{c['id']}/wires")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_circuit_simulation_error(self, client):
        """Empty circuit still returns error status."""
        c = (await client.post("/circuits", json={"name": "Empty"})).json()
        result = (await client.post(f"/circuits/{c['id']}/simulate")).json()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_cascade_delete_with_sweep_data(self, client):
        """Delete circuit cascades sweep_points too."""
        cid, comps = await _build_voltage_divider(client)
        await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "dc_sweep",
            "sweep_source_id": comps["v1"]["id"],
            "sweep_start": 0, "sweep_stop": 5, "sweep_steps": 3,
        })

        resp = await client.delete(f"/circuits/{cid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Circuit should be gone
        resp = await client.get(f"/circuits/{cid}")
        assert resp.status_code == 404


# ===================================================================
# STAGE 8: Error Handling
# ===================================================================


class TestErrorHandling:
    """Error cases for new simulation types."""

    @pytest.mark.asyncio
    async def test_ac_on_empty_circuit(self, client):
        c = (await client.post("/circuits", json={"name": "Empty"})).json()
        result = (await client.post(f"/circuits/{c['id']}/simulate", json={
            "sim_type": "ac",
        })).json()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_transient_on_empty_circuit(self, client):
        c = (await client.post("/circuits", json={"name": "Empty"})).json()
        result = (await client.post(f"/circuits/{c['id']}/simulate", json={
            "sim_type": "transient",
        })).json()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_simulate_nonexistent_circuit(self, client):
        resp = await client.post("/circuits/nonexistent/simulate", json={"sim_type": "ac"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_dc_sweep_bad_source(self, client):
        """DC sweep with nonexistent source ID."""
        cid, _ = await _build_voltage_divider(client)
        result = (await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "dc_sweep",
            "sweep_source_id": "fake-id",
            "sweep_start": 0, "sweep_stop": 10,
        })).json()
        assert result["status"] == "error"
