"""Unit tests for the MNA DC solver — pure math, no HTTP or DB."""

import importlib.util
import os
import sys

import pytest

# Load solver by absolute path (module root is not on sys.path)
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
CircuitGraph = solver.CircuitGraph
ComponentInstance = solver.ComponentInstance
SolverError = solver.SolverError
solve_dc_op = solver.solve_dc_op


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resistor(id: str, value: float, p_net: str, n_net: str) -> ComponentInstance:
    return ComponentInstance(id=id, component_type="resistor", value=value, pins={"p": p_net, "n": n_net})


def _vsource(id: str, value: float, p_net: str, n_net: str) -> ComponentInstance:
    return ComponentInstance(id=id, component_type="voltage_source", value=value, pins={"p": p_net, "n": n_net})


def _isource(id: str, value: float, p_net: str, n_net: str) -> ComponentInstance:
    return ComponentInstance(id=id, component_type="current_source", value=value, pins={"p": p_net, "n": n_net})


def _ground(id: str, net: str) -> ComponentInstance:
    return ComponentInstance(id=id, component_type="ground", value=0, pins={"gnd": net})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSimpleResistorCircuit:
    """V1=5V, R1=1k, between VCC and GND."""

    def test_node_voltage(self):
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
        assert result.node_voltages["vcc"] == pytest.approx(5.0)
        assert result.node_voltages["gnd"] == pytest.approx(0.0)

    def test_current(self):
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
        # I = V/R = 5/1000 = 0.005A
        assert result.component_results["R1"].current == pytest.approx(0.005)

    def test_power(self):
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
        # P = V*I = 5 * 0.005 = 0.025W
        assert result.component_results["R1"].power == pytest.approx(0.025)


class TestVoltageDivider:
    """V1=10V, R1=10k (VCC→MID), R2=10k (MID→GND). Vout = 5V."""

    def _graph(self, r1=10000.0, r2=10000.0, v=10.0):
        return CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "mid", "gnd"],
            components=[
                _vsource("V1", v, "vcc", "gnd"),
                _resistor("R1", r1, "vcc", "mid"),
                _resistor("R2", r2, "mid", "gnd"),
                _ground("G1", "gnd"),
            ],
        )

    def test_midpoint_voltage_equal_resistors(self):
        result = solve_dc_op(self._graph())
        assert result.node_voltages["mid"] == pytest.approx(5.0)

    def test_midpoint_voltage_unequal_resistors(self):
        # R1=10k, R2=20k -> Vout = 10 * 20000 / (10000 + 20000) = 6.667V
        result = solve_dc_op(self._graph(r1=10000.0, r2=20000.0))
        assert result.node_voltages["mid"] == pytest.approx(20000 / 30000 * 10)

    def test_current_through_series_resistors(self):
        result = solve_dc_op(self._graph())
        # I = V / (R1+R2) = 10/20000 = 0.0005A
        assert result.component_results["R1"].current == pytest.approx(0.0005)
        assert result.component_results["R2"].current == pytest.approx(0.0005)


class TestCurrentSource:
    """Current source I=1mA through R=10k. V = I*R = 10V."""

    def test_voltage_from_current_source(self):
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["n1", "gnd"],
            components=[
                _isource("I1", 0.001, "n1", "gnd"),
                _resistor("R1", 10000.0, "n1", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        assert result.node_voltages["n1"] == pytest.approx(10.0)


class TestMultiNodeCircuit:
    """Three resistors in a T network.

    V1=12V at VCC, R1=1k (VCC→A), R2=2k (A→GND), R3=3k (A→GND).
    R2 and R3 are in parallel: Rp = 2000*3000/(2000+3000) = 1200 ohm.
    V_A = 12 * 1200 / (1000 + 1200) = 6.545V
    """

    def test_node_a_voltage(self):
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "a", "gnd"],
            components=[
                _vsource("V1", 12.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "a"),
                _resistor("R2", 2000.0, "a", "gnd"),
                _resistor("R3", 3000.0, "a", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        r_parallel = (2000 * 3000) / (2000 + 3000)
        expected = 12.0 * r_parallel / (1000 + r_parallel)
        assert result.node_voltages["a"] == pytest.approx(expected, rel=1e-9)


class TestWheatstone:
    """Wheatstone bridge: balanced (R1*R4 = R2*R3) → V_bridge = 0."""

    def test_balanced_bridge(self):
        # R1=1k, R2=2k, R3=1k, R4=2k
        # V(A) - V(B) should be 0 when R1/R2 = R3/R4
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "a", "b", "gnd"],
            components=[
                _vsource("V1", 10.0, "vcc", "gnd"),
                _resistor("R1", 1000.0, "vcc", "a"),
                _resistor("R2", 2000.0, "a", "gnd"),
                _resistor("R3", 1000.0, "vcc", "b"),
                _resistor("R4", 2000.0, "b", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        assert result.node_voltages["a"] == pytest.approx(result.node_voltages["b"])


class TestErrorCases:
    def test_no_ground(self):
        graph = CircuitGraph(
            ground_net_id=None,
            nodes=["n1"],
            components=[_resistor("R1", 1000.0, "n1", "n1")],
        )
        with pytest.raises(SolverError, match="No ground"):
            solve_dc_op(graph)

    def test_no_active_components(self):
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["gnd"],
            components=[_ground("G1", "gnd")],
        )
        with pytest.raises(SolverError, match="no active components"):
            solve_dc_op(graph)

    def test_unconnected_pin(self):
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["n1", "gnd"],
            components=[
                _resistor("R1", 1000.0, "n1", None),
                _ground("G1", "gnd"),
            ],
        )
        with pytest.raises(SolverError, match="unconnected pin"):
            solve_dc_op(graph)

    def test_zero_resistance(self):
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["n1", "gnd"],
            components=[
                _vsource("V1", 5.0, "n1", "gnd"),
                _resistor("R1", 0, "n1", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        with pytest.raises(SolverError, match="non-positive resistance"):
            solve_dc_op(graph)

    def test_voltage_source_loop(self):
        """Two voltage sources in a loop with no resistance → singular matrix."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["n1", "gnd"],
            components=[
                _vsource("V1", 5.0, "n1", "gnd"),
                _vsource("V2", 3.0, "n1", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        with pytest.raises(SolverError):
            solve_dc_op(graph)


class TestSolverMetadata:
    def test_metadata_present(self):
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
        assert "matrix_size" in result.solver_metadata
        assert "num_nodes" in result.solver_metadata
        assert "condition_number" in result.solver_metadata
        assert result.solver_metadata["num_nodes"] == 1  # only vcc (gnd excluded)
        assert result.solver_metadata["num_voltage_sources"] == 1
