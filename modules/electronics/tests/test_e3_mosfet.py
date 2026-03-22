"""E3 tests — MOSFET (NMOS/PMOS) and Op-Amp with Newton-Raphson solver."""

import importlib.util
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resistor(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="resistor", value=value, pins={"p": p_net, "n": n_net})

def _vsource(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="voltage_source", value=value, pins={"p": p_net, "n": n_net})

def _ground(id, net):
    return ComponentInstance(id=id, component_type="ground", value=0, pins={"gnd": net})

def _nmos(id, g_net, d_net, s_net, params=None):
    return ComponentInstance(id=id, component_type="nmos", value=0,
                            pins={"gate": g_net, "drain": d_net, "source": s_net},
                            params=params or {})

def _pmos(id, g_net, d_net, s_net, params=None):
    return ComponentInstance(id=id, component_type="pmos", value=0,
                            pins={"gate": g_net, "drain": d_net, "source": s_net},
                            params=params or {})

def _opamp(id, non_inv, inv, output):
    return ComponentInstance(id=id, component_type="opamp", value=0,
                            pins={"non_inv": non_inv, "inv": inv, "output": output})


# ---------------------------------------------------------------------------
# MOSFET model unit tests
# ---------------------------------------------------------------------------

class TestMOSFETModel:
    """Test square-law MOSFET model."""

    def test_cutoff(self):
        """Vgs < Vth should give zero drain current."""
        result = dm.mosfet_current(0.3, 5.0, dm.MOSFETModel(Vth=0.7))
        assert result["Id"] == pytest.approx(0.0)
        assert result["region"] == "cutoff"

    def test_saturation(self):
        """Vgs > Vth and Vds > Vgs-Vth → saturation."""
        model = dm.MOSFETModel(Kp=110e-6, Vth=0.7, W=10e-6, L=1e-6)
        result = dm.mosfet_current(2.0, 5.0, model)
        assert result["Id"] > 0
        assert result["region"] == "saturation"

    def test_linear_region(self):
        """Vgs > Vth and Vds < Vgs-Vth → linear (triode)."""
        model = dm.MOSFETModel(Kp=110e-6, Vth=0.7, W=10e-6, L=1e-6)
        result = dm.mosfet_current(3.0, 0.5, model)
        assert result["Id"] > 0
        assert result["region"] == "linear"

    def test_current_increases_with_vgs(self):
        """In saturation, Id increases with Vgs."""
        model = dm.MOSFETModel()
        r1 = dm.mosfet_current(1.5, 5.0, model)
        r2 = dm.mosfet_current(2.5, 5.0, model)
        assert r2["Id"] > r1["Id"]

    def test_pmos_negative_current(self):
        """PMOS should have negative Id for equivalent bias."""
        model = dm.MOSFETModel(Vth=-0.7)
        result = dm.mosfet_current(-2.0, -5.0, model, is_pmos=True)
        assert result["Id"] < 0

    def test_2n7000_preset(self):
        model, is_pmos = dm.MOSFET_PRESETS["2N7000"]
        assert model.Vth == pytest.approx(2.0)
        assert is_pmos is False


# ---------------------------------------------------------------------------
# MOSFET circuit tests
# ---------------------------------------------------------------------------

class TestNMOSCircuit:
    """NMOS transistor circuit tests."""

    def test_nmos_switch_on(self):
        """NMOS with gate driven high — should be on, drain low."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vdd", "gate", "drain", "gnd"],
            components=[
                _vsource("Vdd", 5.0, "vdd", "gnd"),
                _vsource("Vg", 5.0, "gate", "gnd"),
                _resistor("Rd", 1000.0, "vdd", "drain"),
                _nmos("M1", "gate", "drain", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vd = result.node_voltages["drain"]
        # NMOS on: drain should be pulled low
        assert vd < 2.0

    def test_nmos_switch_off(self):
        """NMOS with gate at ground — should be off, drain near Vdd."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vdd", "drain", "gnd"],
            components=[
                _vsource("Vdd", 5.0, "vdd", "gnd"),
                _resistor("Rd", 1000.0, "vdd", "drain"),
                _nmos("M1", "gnd", "drain", "gnd"),  # Gate at GND
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vd = result.node_voltages["drain"]
        # NMOS off: drain should be near Vdd
        assert vd > 4.5

    def test_nmos_operating_region_reported(self):
        """Check that operating region is reported."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vdd", "gate", "drain", "gnd"],
            components=[
                _vsource("Vdd", 5.0, "vdd", "gnd"),
                _vsource("Vg", 5.0, "gate", "gnd"),
                _resistor("Rd", 1000.0, "vdd", "drain"),
                _nmos("M1", "gate", "drain", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        m1 = result.component_results["M1"]
        assert m1.operating_region in ("linear", "saturation")
        assert "Id" in m1.extra_data
        assert "Vgs" in m1.extra_data

    def test_nmos_common_source(self):
        """Common-source amplifier with NMOS."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vdd", "gate", "drain", "gnd"],
            components=[
                _vsource("Vdd", 10.0, "vdd", "gnd"),
                _vsource("Vg", 3.0, "gate", "gnd"),
                _resistor("Rd", 5000.0, "vdd", "drain"),
                _nmos("M1", "gate", "drain", "gnd", params={"model": "2N7000"}),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vd = result.node_voltages["drain"]
        # Should be somewhere between 0 and Vdd
        assert 0.0 < vd < 10.0


class TestCMOSInverter:
    """CMOS inverter: NMOS + PMOS."""

    def test_cmos_input_high(self):
        """Input high → output low."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vdd", "input", "output", "gnd"],
            components=[
                _vsource("Vdd", 5.0, "vdd", "gnd"),
                _vsource("Vin", 5.0, "input", "gnd"),
                # PMOS: gate=input, source=vdd, drain=output
                _pmos("Mp", "input", "output", "vdd", params={"Vth": -0.7}),
                # NMOS: gate=input, source=gnd, drain=output
                _nmos("Mn", "input", "output", "gnd", params={"Vth": 0.7}),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        v_out = result.node_voltages["output"]
        # Input high → NMOS on, PMOS off → output low
        assert v_out < 1.0

    def test_cmos_input_low(self):
        """Input low → output high."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vdd", "output", "gnd"],
            components=[
                _vsource("Vdd", 5.0, "vdd", "gnd"),
                # Input = GND (0V)
                _pmos("Mp", "gnd", "output", "vdd", params={"Vth": -0.7}),
                _nmos("Mn", "gnd", "output", "gnd", params={"Vth": 0.7}),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        v_out = result.node_voltages["output"]
        # Input low → NMOS off, PMOS on → output high
        assert v_out > 4.0


# ---------------------------------------------------------------------------
# Op-Amp tests
# ---------------------------------------------------------------------------

class TestOpAmp:
    """Ideal op-amp circuit tests."""

    def test_voltage_follower(self):
        """Op-amp voltage follower: output = input."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vin_node", "output", "gnd"],
            components=[
                _vsource("Vin", 3.0, "vin_node", "gnd"),
                _opamp("U1", "vin_node", "output", "output"),  # non_inv=vin, inv=output (feedback)
                _resistor("Rload", 1000.0, "output", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        v_out = result.node_voltages["output"]
        assert v_out == pytest.approx(3.0, abs=0.01)

    def test_inverting_amplifier(self):
        """Inverting amp: gain = -Rf/Rin. Vin=1V, Rin=1k, Rf=10k → Vout=-10V."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vin_node", "inv_node", "output", "gnd"],
            components=[
                _vsource("Vin", 1.0, "vin_node", "gnd"),
                _resistor("Rin", 1000.0, "vin_node", "inv_node"),
                _resistor("Rf", 10000.0, "inv_node", "output"),
                _opamp("U1", "gnd", "inv_node", "output"),  # non_inv=GND, inv=inv_node
                _resistor("Rload", 10000.0, "output", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        v_out = result.node_voltages["output"]
        # Gain = -Rf/Rin = -10
        assert v_out == pytest.approx(-10.0, abs=0.1)

    def test_non_inverting_amplifier(self):
        """Non-inverting amp: gain = 1 + Rf/Rin. Vin=1V, Rin=1k, Rf=4k → Vout=5V."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vin_node", "inv_node", "output", "gnd"],
            components=[
                _vsource("Vin", 1.0, "vin_node", "gnd"),
                _resistor("Rin", 1000.0, "inv_node", "gnd"),
                _resistor("Rf", 4000.0, "inv_node", "output"),
                _opamp("U1", "vin_node", "inv_node", "output"),
                _resistor("Rload", 10000.0, "output", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        v_out = result.node_voltages["output"]
        # Gain = 1 + Rf/Rin = 1 + 4 = 5
        assert v_out == pytest.approx(5.0, abs=0.1)

    def test_summing_amplifier(self):
        """Summing amplifier: Vout = -(Rf/R1*V1 + Rf/R2*V2).
        V1=1V, V2=2V, R1=R2=1k, Rf=1k → Vout = -(1+2) = -3V."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["v1_node", "v2_node", "inv_node", "output", "gnd"],
            components=[
                _vsource("V1", 1.0, "v1_node", "gnd"),
                _vsource("V2", 2.0, "v2_node", "gnd"),
                _resistor("R1", 1000.0, "v1_node", "inv_node"),
                _resistor("R2", 1000.0, "v2_node", "inv_node"),
                _resistor("Rf", 1000.0, "inv_node", "output"),
                _opamp("U1", "gnd", "inv_node", "output"),
                _resistor("Rload", 10000.0, "output", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        v_out = result.node_voltages["output"]
        assert v_out == pytest.approx(-3.0, abs=0.1)

    def test_difference_amplifier(self):
        """Difference amp: Vout = (V2 - V1) * Rf/Rin.
        V1=2V, V2=3V, all R=1k → Vout = 1V."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["v1_node", "v2_node", "inv_node", "noninv_node", "output", "gnd"],
            components=[
                _vsource("V1", 2.0, "v1_node", "gnd"),
                _vsource("V2", 3.0, "v2_node", "gnd"),
                _resistor("R1", 1000.0, "v1_node", "inv_node"),
                _resistor("Rf", 1000.0, "inv_node", "output"),
                _resistor("R2", 1000.0, "v2_node", "noninv_node"),
                _resistor("R3", 1000.0, "noninv_node", "gnd"),
                _opamp("U1", "noninv_node", "inv_node", "output"),
                _resistor("Rload", 10000.0, "output", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        v_out = result.node_voltages["output"]
        assert v_out == pytest.approx(1.0, abs=0.1)
