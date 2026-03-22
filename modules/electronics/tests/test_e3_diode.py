"""E3 tests — Diode, Zener, LED with Newton-Raphson solver."""

import importlib.util
import math
import os
import sys

import pytest

_BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")


def _load(name: str):
    key = f"_electronics_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_BACKEND_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


solver = _load("solver")
dm = _load("device_models")

CircuitGraph = solver.CircuitGraph
ComponentInstance = solver.ComponentInstance
SolverError = solver.SolverError
solve_dc_op = solver.solve_dc_op
solve_transient = solver.solve_transient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resistor(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="resistor", value=value, pins={"p": p_net, "n": n_net})

def _vsource(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="voltage_source", value=value, pins={"p": p_net, "n": n_net})

def _ground(id, net):
    return ComponentInstance(id=id, component_type="ground", value=0, pins={"gnd": net})

def _diode(id, anode_net, cathode_net, params=None):
    return ComponentInstance(id=id, component_type="diode", value=0, pins={"anode": anode_net, "cathode": cathode_net}, params=params or {})

def _zener(id, anode_net, cathode_net, params=None):
    return ComponentInstance(id=id, component_type="zener", value=0, pins={"anode": anode_net, "cathode": cathode_net}, params=params or {})

def _led(id, anode_net, cathode_net, params=None):
    return ComponentInstance(id=id, component_type="led", value=0, pins={"anode": anode_net, "cathode": cathode_net}, params=params or {})

def _capacitor(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="capacitor", value=value, pins={"p": p_net, "n": n_net})


# ---------------------------------------------------------------------------
# Device model unit tests
# ---------------------------------------------------------------------------

class TestDiodeModel:
    """Test the Shockley diode equation directly."""

    def test_forward_current_positive(self):
        """Forward voltage should produce positive current."""
        model = dm.DiodeModel()
        Id, Gd = dm.diode_current(0.7, model)
        assert Id > 0
        assert Gd > 0

    def test_reverse_current_near_zero(self):
        """Reverse voltage should give near-zero (negative) current."""
        model = dm.DiodeModel()
        Id, Gd = dm.diode_current(-1.0, model)
        assert Id < 0
        assert abs(Id) < 1e-10  # Very small reverse current

    def test_zero_voltage_zero_current(self):
        """At Vd=0, Id should be nearly zero."""
        model = dm.DiodeModel()
        Id, Gd = dm.diode_current(0.0, model)
        assert abs(Id) < 1e-12

    def test_conductance_increases_with_voltage(self):
        """Conductance should increase exponentially with forward voltage."""
        model = dm.DiodeModel()
        _, Gd_low = dm.diode_current(0.3, model)
        _, Gd_high = dm.diode_current(0.6, model)
        assert Gd_high > Gd_low * 10  # Should be much larger

    def test_overflow_protection(self):
        """Very large forward voltage should not cause overflow."""
        model = dm.DiodeModel()
        Id, Gd = dm.diode_current(10.0, model)
        assert math.isfinite(Id)
        assert math.isfinite(Gd)
        assert Id > 0

    def test_breakdown_region(self):
        """Beyond Bv, large reverse current should flow."""
        model = dm.DiodeModel(Bv=50.0, Ibv=1e-3)
        Id, Gd = dm.diode_current(-55.0, model)
        assert Id < -1e-6  # Significant reverse current

    def test_1n4148_preset(self):
        """1N4148 preset should have correct parameters."""
        model = dm.DIODE_PRESETS["1N4148"]
        assert model.Is == pytest.approx(2.52e-9)
        assert model.N == pytest.approx(1.752)


# ---------------------------------------------------------------------------
# Diode circuit solver tests
# ---------------------------------------------------------------------------

class TestDiodeCircuit:
    """Test NR solver with diode circuits."""

    def test_forward_biased_diode_with_resistor(self):
        """V=5V, R=1k, D in series. Vd should be ~0.6-0.7V."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vd = result.node_voltages["mid"]  # Diode anode voltage (cathode at GND=0)
        assert 0.5 < vd < 0.9  # Typical diode forward voltage
        # Current should be (5 - Vd) / 1000
        ir = result.component_results["R1"].current
        assert ir > 0.004  # At least 4mA
        assert ir < 0.005  # At most 5mA

    def test_forward_biased_1n4148(self):
        """1N4148 with specific model parameters."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "mid", "gnd", params={"model": "1N4148"}),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vd = result.node_voltages["mid"]
        assert 0.5 < vd < 1.0  # 1N4148 has higher Is so lower Vf

    def test_reverse_biased_diode(self):
        """Diode in reverse — almost no current should flow."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "gnd", "mid"),  # Reversed: anode at GND, cathode at mid
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        # With reverse-biased diode, almost no current flows
        # So mid should be close to 5V (no voltage drop across R1)
        assert result.node_voltages["mid"] > 4.9

    def test_two_diodes_in_series(self):
        """Two diodes in series should drop ~1.2-1.4V total."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid1", "mid2", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid1"),
                _diode("D1", "mid1", "mid2"),
                _diode("D2", "mid2", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        total_drop = result.node_voltages["mid1"]
        assert 1.0 < total_drop < 1.8  # Two diode drops

    def test_diodes_in_parallel(self):
        """Two diodes in parallel share current."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "mid", "gnd"),
                _diode("D2", "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vd = result.node_voltages["mid"]
        # With two diodes in parallel, the forward voltage should be similar
        # but the total current through R1 is split
        assert 0.4 < vd < 0.9

    def test_operating_region_forward(self):
        """Check that operating region is reported as 'forward'."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        assert result.component_results["D1"].operating_region == "forward"

    def test_operating_region_reverse(self):
        """Check that operating region is reported as 'reverse'."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "gnd", "mid"),  # Reversed
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        assert result.component_results["D1"].operating_region == "reverse"

    def test_nr_metadata(self):
        """Solver metadata should include NR iteration count."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        assert "nr_iterations" in result.solver_metadata
        assert "nr_converged" in result.solver_metadata
        assert result.solver_metadata["nr_converged"] is True
        assert result.solver_metadata["nr_iterations"] > 1

    def test_extra_data_includes_vd_id(self):
        """Component result extra_data should have Vd and Id."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        d1 = result.component_results["D1"]
        assert "Vd" in d1.extra_data
        assert "Id" in d1.extra_data
        assert d1.extra_data["Vd"] > 0.5

    def test_linear_circuits_still_use_direct_solve(self):
        """Linear-only circuits should NOT use NR (backward compat)."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        # Linear solver doesn't produce NR metadata
        assert "nr_iterations" not in result.solver_metadata
        assert result.node_voltages["vcc"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Zener diode tests
# ---------------------------------------------------------------------------

class TestZenerCircuit:
    """Zener diode voltage regulation tests."""

    def test_zener_regulator(self):
        """Zener regulator: 12V source, R=1k, Zener Vz=5.1V.
        Output should clamp near Vz."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "out", "gnd"],
            components=[
                _vsource("V1", 12.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "out"),
                _zener("DZ1", "gnd", "out", params={"Bv": 5.1}),  # Cathode at out, anode at GND
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        # Zener conducts in reverse: cathode more positive than anode by Vz
        # So V(out) should be approximately Vz
        v_out = result.node_voltages["out"]
        assert 4.5 < v_out < 5.5  # Should be near 5.1V

    def test_zener_below_breakdown(self):
        """If source voltage is below Vz, zener acts as open circuit."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "out", "gnd"],
            components=[
                _vsource("V1", 3.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "out"),
                _resistor("R2", 10000.0, "out", "gnd"),  # Load
                _zener("DZ1", "gnd", "out", params={"Bv": 5.1}),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        # Below breakdown, zener is off — voltage divider determines output
        v_out = result.node_voltages["out"]
        expected = 3.0 * 10000 / (1000 + 10000)
        assert abs(v_out - expected) < 0.5  # Should be close to voltage divider


# ---------------------------------------------------------------------------
# LED tests
# ---------------------------------------------------------------------------

class TestLEDCircuit:
    """LED tests with higher forward voltage."""

    def test_led_with_resistor(self):
        """LED with current-limiting resistor. Vf should be higher than standard diode."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 330.0, "vcc", "mid"),
                _led("LED1", "mid", "gnd", params={"model": "red"}),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vf = result.node_voltages["mid"]
        # Red LED Vf is typically 1.8-2.2V
        assert 1.2 < vf < 3.0

    def test_led_current_limiting(self):
        """LED current should be limited by the resistor."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _resistor("R1", 330.0, "vcc", "mid"),
                _led("LED1", "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        i_led = result.component_results["R1"].current
        # Current should be reasonable (5-20mA for typical LED circuit)
        assert 0.001 < i_led < 0.05


# ---------------------------------------------------------------------------
# Transient with diode
# ---------------------------------------------------------------------------

class TestDiodeTransient:
    """Transient analysis with diodes."""

    def test_half_wave_rectifier(self):
        """Diode + resistor with varying source — half-wave rectification.
        For simplicity, we use DC transient and just verify the NR works
        at each timestep."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 5.0, "vcc", "gnd"),
                _diode("D1", "vcc", "mid"),
                _resistor("R1", 1000.0, "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_transient(graph, t_stop=0.001, max_points=10)
        assert len(result.points) > 1
        # All points should have mid voltage close to V - Vd
        for pt in result.points:
            assert pt.node_voltages["mid"] > 3.5  # 5V minus diode drop

    def test_diode_clamp_transient(self):
        """RC circuit with diode clamp — verify stability over time."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "out", "gnd"],
            components=[
                _vsource("V1", 10.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "mid", "out"),
                _resistor("R2", 10000.0, "out", "gnd"),
                _capacitor("C1", 1e-6, "out", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_transient(graph, t_stop=0.01, max_points=20)
        assert len(result.points) > 1
        # Output should stabilize
        last_v = result.points[-1].node_voltages["out"]
        assert last_v > 0  # Should have some voltage


# ---------------------------------------------------------------------------
# Mixed linear + nonlinear
# ---------------------------------------------------------------------------

class TestMixedCircuit:
    """Circuits with both linear and nonlinear components."""

    def test_voltage_divider_with_diode(self):
        """Voltage divider where one arm contains a diode."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", 10.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "mid"),
                _diode("D1", "mid", "gnd"),
                _resistor("R2", 1000.0, "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        # The diode in parallel with R2 clamps mid voltage
        v_mid = result.node_voltages["mid"]
        assert 0.4 < v_mid < 0.9  # Diode dominates at low voltage

    def test_bridge_rectifier(self):
        """Full-wave bridge rectifier: 4 diodes."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["in_p", "in_n", "out_p", "gnd"],
            components=[
                _vsource("V1", 10.0, "in_p", "in_n"),
                # Bridge: D1 in_p→out_p, D2 gnd→in_n, D3 in_n→out_p, D4 gnd→in_p
                # For positive half: current flows V+ → D1 → out_p → R → gnd → D2 → V-
                _diode("D1", "in_p", "out_p"),
                _diode("D2", "gnd", "in_n"),
                _diode("D3", "in_n", "out_p"),
                _diode("D4", "gnd", "in_p"),
                _resistor("R1", 1000.0, "out_p", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        # Output should be roughly V_in minus two diode drops
        v_out = result.node_voltages["out_p"]
        assert v_out > 7.0  # 10V - 2*0.7V ≈ 8.6V
        assert v_out < 10.0
