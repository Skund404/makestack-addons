"""E4 tests — Advanced analysis: Monte Carlo, parameter sweep, temperature sweep."""

import importlib.util
import os
import sys

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB, create_test_app

_MODULE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND_DIR = os.path.join(_MODULE_ROOT, "backend")


def _load_mod(name: str):
    key = f"_electronics_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_BACKEND_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


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


solver = _load_mod("solver")

migration_001 = _load("mig001", "backend/migrations/001_create_tables.py")
migration_002 = _load("mig002", "backend/migrations/002_e1b_wire_catalogue.py")
migration_003 = _load("mig003", "backend/migrations/003_e2_sweep_waveform.py")
migration_004 = _load("mig004", "backend/migrations/004_e3_operating_region.py")
migration_005 = _load("mig005", "backend/migrations/005_e4_subcircuits.py")
routes_mod = _load("routes", "backend/routes.py")

router = routes_mod.router

CircuitGraph = solver.CircuitGraph
ComponentInstance = solver.ComponentInstance
SolverError = solver.SolverError
solve_dc_op = solver.solve_dc_op
solve_parameter_sweep = solver.solve_parameter_sweep
solve_monte_carlo = solver.solve_monte_carlo
solve_temp_sweep = solver.solve_temp_sweep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resistor(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="resistor", value=value, pins={"p": p_net, "n": n_net})

def _vsource(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="voltage_source", value=value, pins={"p": p_net, "n": n_net})

def _ground(id, net):
    return ComponentInstance(id=id, component_type="ground", value=0, pins={"gnd": net})

def _diode(id, a_net, c_net, params=None):
    return ComponentInstance(id=id, component_type="diode", value=0,
                            pins={"anode": a_net, "cathode": c_net},
                            params=params or {})


def _voltage_divider_graph():
    """Standard voltage divider: V1=10V, R1=R2=1k, output at 'mid'."""
    return CircuitGraph(
        ground_net_id="gnd",
        nodes=["vcc", "mid", "gnd"],
        components=[
            _vsource("V1", 10.0, "vcc", "gnd"),
            _resistor("R1", 1000.0, "vcc", "mid"),
            _resistor("R2", 1000.0, "mid", "gnd"),
            _ground("G1", "gnd"),
        ],
    )


# ---------------------------------------------------------------------------
# Parameter sweep tests
# ---------------------------------------------------------------------------

class TestParameterSweep:

    def test_sweep_resistor_value(self):
        """Sweep R2 from 500 to 2000 — mid voltage should vary."""
        graph = _voltage_divider_graph()
        result = solve_parameter_sweep(graph, "R2", "value", 500.0, 2000.0, steps=5)
        assert len(result.values) == 5
        assert len(result.results) == 5

        # With R2=500: mid = 10 * 500/1500 ≈ 3.33
        # With R2=2000: mid = 10 * 2000/3000 ≈ 6.67
        v_first = result.results[0].node_voltages["mid"]
        v_last = result.results[-1].node_voltages["mid"]
        assert v_first < v_last  # higher R2 → higher mid voltage

    def test_sweep_single_step(self):
        """Single step sweep should still work."""
        graph = _voltage_divider_graph()
        result = solve_parameter_sweep(graph, "R2", "value", 1000.0, 1000.0, steps=1)
        assert len(result.results) == 1
        assert result.results[0].node_voltages["mid"] == pytest.approx(5.0, abs=0.01)

    def test_sweep_nonexistent_component(self):
        """Sweeping a non-existent component should raise SolverError."""
        graph = _voltage_divider_graph()
        with pytest.raises(SolverError, match="not found"):
            solve_parameter_sweep(graph, "R99", "value", 1.0, 10.0, steps=3)

    def test_sweep_metadata(self):
        graph = _voltage_divider_graph()
        result = solve_parameter_sweep(graph, "R1", "value", 100.0, 10000.0, steps=10)
        assert result.solver_metadata["component_id"] == "R1"
        assert result.solver_metadata["steps"] == 10
        assert result.parameter_name == "value"


# ---------------------------------------------------------------------------
# Monte Carlo tests
# ---------------------------------------------------------------------------

class TestMonteCarlo:

    def test_basic_monte_carlo(self):
        """Monte Carlo with 5% tolerance on both resistors."""
        graph = _voltage_divider_graph()
        result = solve_monte_carlo(
            graph,
            tolerances={"R1": {"value": 0.05}, "R2": {"value": 0.05}},
            num_runs=50,
            seed=42,
        )
        assert result.num_runs == 50
        assert "mid" in result.node_statistics

        stats = result.node_statistics["mid"]
        # Mean should be close to 5V (nominal)
        assert 4.5 < stats["mean"] < 5.5
        # Should have some variation
        assert stats["std"] > 0
        assert stats["min"] < stats["max"]

    def test_monte_carlo_zero_tolerance(self):
        """Zero tolerance should give identical results."""
        graph = _voltage_divider_graph()
        result = solve_monte_carlo(
            graph,
            tolerances={"R1": {"value": 0.0}},
            num_runs=10,
            seed=0,
        )
        stats = result.node_statistics["mid"]
        assert stats["std"] == pytest.approx(0.0, abs=1e-10)

    def test_monte_carlo_component_statistics(self):
        """Should report per-component current statistics."""
        graph = _voltage_divider_graph()
        result = solve_monte_carlo(
            graph,
            tolerances={"R1": {"value": 0.1}},
            num_runs=20,
            seed=1,
        )
        assert "R1" in result.component_statistics
        assert result.component_statistics["R1"]["mean"] != 0

    def test_monte_carlo_high_tolerance_spread(self):
        """20% tolerance should produce wider spread than 1%."""
        graph = _voltage_divider_graph()
        r1 = solve_monte_carlo(graph, {"R1": {"value": 0.01}}, num_runs=50, seed=10)
        r2 = solve_monte_carlo(graph, {"R1": {"value": 0.20}}, num_runs=50, seed=10)
        # Higher tolerance → larger std
        assert r2.node_statistics["mid"]["std"] > r1.node_statistics["mid"]["std"]


# ---------------------------------------------------------------------------
# Temperature sweep tests
# ---------------------------------------------------------------------------

class TestTempSweep:

    def test_linear_circuit_temp_invariant(self):
        """Pure linear circuit should be temperature-invariant."""
        graph = _voltage_divider_graph()
        result = solve_temp_sweep(graph, t_start=25.0, t_stop=85.0, steps=5)
        assert len(result.temperatures) == 5
        assert len(result.results) == 5

        # All should give same voltage (linear circuit doesn't use temperature)
        voltages = [r.node_voltages["mid"] for r in result.results]
        for v in voltages:
            assert v == pytest.approx(5.0, abs=0.01)

    def test_temp_sweep_metadata(self):
        graph = _voltage_divider_graph()
        result = solve_temp_sweep(graph, t_start=-40.0, t_stop=125.0, steps=10)
        assert result.solver_metadata["t_start"] == -40.0
        assert result.solver_metadata["t_stop"] == 125.0
        assert len(result.temperatures) == 10
        assert result.temperatures[0] == pytest.approx(-40.0)
        assert result.temperatures[-1] == pytest.approx(125.0)

    def test_temp_sweep_single_point(self):
        graph = _voltage_divider_graph()
        result = solve_temp_sweep(graph, t_start=25.0, t_stop=25.0, steps=1)
        assert len(result.results) == 1


# ---------------------------------------------------------------------------
# API integration tests
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


async def _create_voltage_divider(client):
    """Create a voltage divider circuit via API and return (circuit_id, R1_id, R2_id)."""
    r = await client.post("/circuits", json={"name": "VDiv"})
    cid = r.json()["id"]

    # Add components
    r = await client.post(f"/circuits/{cid}/components", json={
        "component_type": "voltage_source", "value": "10",
    })
    vs_id = r.json()["id"]

    r = await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor", "value": "1000",
    })
    r1_id = r.json()["id"]

    r = await client.post(f"/circuits/{cid}/components", json={
        "component_type": "resistor", "value": "1000",
    })
    r2_id = r.json()["id"]

    r = await client.post(f"/circuits/{cid}/components", json={
        "component_type": "ground",
    })

    # Wire it up — ground component auto-connects to "GND" (uppercase) net,
    # so use "GND" everywhere for consistency
    await client.post(f"/circuits/{cid}/connect", json={
        "component_id": vs_id, "pin_name": "p", "net_name": "vcc",
    })
    await client.post(f"/circuits/{cid}/connect", json={
        "component_id": vs_id, "pin_name": "n", "net_name": "GND",
    })
    await client.post(f"/circuits/{cid}/connect", json={
        "component_id": r1_id, "pin_name": "p", "net_name": "vcc",
    })
    await client.post(f"/circuits/{cid}/connect", json={
        "component_id": r1_id, "pin_name": "n", "net_name": "mid",
    })
    await client.post(f"/circuits/{cid}/connect", json={
        "component_id": r2_id, "pin_name": "p", "net_name": "mid",
    })
    await client.post(f"/circuits/{cid}/connect", json={
        "component_id": r2_id, "pin_name": "n", "net_name": "GND",
    })

    return cid, r1_id, r2_id


class TestAnalysisAPI:

    @pytest.mark.asyncio
    async def test_monte_carlo_api(self, client):
        cid, r1_id, r2_id = await _create_voltage_divider(client)
        resp = await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "monte_carlo",
            "mc_tolerances": {r1_id: {"value": 0.05}, r2_id: {"value": 0.05}},
            "mc_runs": 20,
            "mc_seed": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["sim_type"] == "monte_carlo"
        assert data["status"] == "complete"
        assert data["num_runs"] == 20

    @pytest.mark.asyncio
    async def test_param_sweep_api(self, client):
        cid, r1_id, r2_id = await _create_voltage_divider(client)
        resp = await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "param_sweep",
            "ps_component_id": r2_id,
            "ps_param": "value",
            "ps_start": 500,
            "ps_stop": 2000,
            "ps_steps": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["sim_type"] == "param_sweep"
        assert data["status"] == "complete"
        assert len(data["sweep_data"]) == 5

    @pytest.mark.asyncio
    async def test_temp_sweep_api(self, client):
        cid, _, _ = await _create_voltage_divider(client)
        resp = await client.post(f"/circuits/{cid}/simulate", json={
            "sim_type": "temp_sweep",
            "temp_start": -40,
            "temp_stop": 125,
            "temp_steps": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["sim_type"] == "temp_sweep"
        assert data["status"] == "complete"
        assert len(data["sweep_data"]) == 5
