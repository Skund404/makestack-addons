"""E3 tests — BJT (NPN/PNP) with Newton-Raphson solver."""

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

def _capacitor(id, value, p_net, n_net):
    return ComponentInstance(id=id, component_type="capacitor", value=value, pins={"p": p_net, "n": n_net})

def _npn(id, c_net, b_net, e_net, params=None):
    return ComponentInstance(id=id, component_type="npn_bjt", value=0,
                            pins={"collector": c_net, "base": b_net, "emitter": e_net},
                            params=params or {})

def _pnp(id, c_net, b_net, e_net, params=None):
    return ComponentInstance(id=id, component_type="pnp_bjt", value=0,
                            pins={"collector": c_net, "base": b_net, "emitter": e_net},
                            params=params or {})


# ---------------------------------------------------------------------------
# BJT model unit tests
# ---------------------------------------------------------------------------

class TestBJTModel:
    """Test Ebers-Moll BJT model directly."""

    def test_active_region_forward_current(self):
        """With Vbe > 0.6V and Vbc < 0, BJT should be in active region."""
        result = dm.bjt_currents(0.7, -5.0, dm.BJTModel())
        assert result["Ic"] > 0  # Collector current flows
        assert result["Ib"] > 0  # Base current flows
        assert result["gm"] > 0  # Transconductance positive

    def test_cutoff_region(self):
        """With Vbe < 0, BJT should be in cutoff."""
        result = dm.bjt_currents(-0.5, -5.0, dm.BJTModel())
        assert abs(result["Ic"]) < 1e-10  # Negligible current

    def test_saturation_region(self):
        """With both junctions forward biased, BJT is saturated."""
        result = dm.bjt_currents(0.7, 0.5, dm.BJTModel())
        # In saturation, Ic is less than beta * Ib
        assert result["Ic"] > 0
        assert result["Ib"] > 0

    def test_beta_relationship(self):
        """In active region, Ic should be approximately Bf * Ib."""
        model = dm.BJTModel(Bf=100.0)
        result = dm.bjt_currents(0.65, -5.0, model)
        if result["Ib"] > 1e-12:
            ratio = result["Ic"] / result["Ib"]
            assert 50 < ratio < 200  # Approximately beta

    def test_pnp_reverses_currents(self):
        """PNP should have reversed current directions for equivalent bias."""
        # NPN forward-biased: Vbe=+0.7V → positive Ic
        npn = dm.bjt_currents(0.7, -5.0, dm.BJTModel(), is_pnp=False)
        # PNP forward-biased: Vbe=-0.7V externally (function negates internally)
        pnp = dm.bjt_currents(-0.7, 5.0, dm.BJTModel(), is_pnp=True)
        # NPN Ic is positive (collector current flows in)
        assert npn["Ic"] > 0
        # PNP Ic is negative (current flows opposite direction)
        assert pnp["Ic"] < 0

    def test_2n3904_preset(self):
        model, is_pnp = dm.BJT_PRESETS["2N3904"]
        assert model.Bf == pytest.approx(300.0)
        assert is_pnp is False

    def test_2n3906_preset(self):
        model, is_pnp = dm.BJT_PRESETS["2N3906"]
        assert model.Bf == pytest.approx(180.0)
        assert is_pnp is True


# ---------------------------------------------------------------------------
# BJT circuit tests
# ---------------------------------------------------------------------------

class TestCommonEmitter:
    """Common-emitter amplifier: the most basic BJT circuit."""

    def test_basic_ce_amplifier(self):
        """Vcc=12V, Rb=100k to base, Rc=1k collector, NPN.
        Should be in active region with reasonable Ic and Vce."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "collector", "base", "gnd"],
            components=[
                _vsource("Vcc", 12.0, "vcc", "gnd"),
                _resistor("Rc", 1000.0, "vcc", "collector"),
                _resistor("Rb", 100000.0, "vcc", "base"),
                _npn("Q1", "collector", "base", "gnd", params={"model": "2N3904"}),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)

        # Base voltage should be above 0.6V (Vbe forward bias)
        vb = result.node_voltages["base"]
        assert 0.5 < vb < 1.0

        # Collector voltage should be between 0 and Vcc
        vc = result.node_voltages["collector"]
        assert 0.0 < vc < 12.0

        # Check operating region
        q1 = result.component_results["Q1"]
        assert q1.operating_region in ("active", "saturation")
        assert "Ic" in q1.extra_data
        assert "Vbe" in q1.extra_data

    def test_ce_with_emitter_resistor(self):
        """CE amp with emitter degeneration resistor for stability."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "collector", "base", "emitter", "gnd"],
            components=[
                _vsource("Vcc", 12.0, "vcc", "gnd"),
                _resistor("Rc", 1000.0, "vcc", "collector"),
                _resistor("Rb", 100000.0, "vcc", "base"),
                _resistor("Re", 100.0, "emitter", "gnd"),
                _npn("Q1", "collector", "base", "emitter"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        ve = result.node_voltages["emitter"]
        vb = result.node_voltages["base"]
        # Vbe should be ~0.6-0.7V
        vbe = vb - ve
        assert 0.4 < vbe < 0.9


class TestEmitterFollower:
    """Emitter follower (common-collector) — voltage gain ~1."""

    def test_voltage_follower(self):
        """Input at base, output at emitter. Vout ≈ Vin - Vbe."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "vin_node", "emitter", "gnd"],
            components=[
                _vsource("Vcc", 12.0, "vcc", "gnd"),
                _vsource("Vin", 5.0, "vin_node", "gnd"),
                _resistor("Re", 1000.0, "emitter", "gnd"),
                _npn("Q1", "vcc", "vin_node", "emitter"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        ve = result.node_voltages["emitter"]
        # Emitter should be Vin - Vbe ≈ 5.0 - 0.7 ≈ 4.3V
        assert 3.5 < ve < 5.0


class TestBJTSwitch:
    """BJT as a switch — saturated or cutoff."""

    def test_saturated_switch(self):
        """High base current drives BJT into saturation. Vce should be low."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "collector", "base", "gnd"],
            components=[
                _vsource("Vcc", 5.0, "vcc", "gnd"),
                _resistor("Rc", 1000.0, "vcc", "collector"),
                _resistor("Rb", 1000.0, "vcc", "base"),  # Low Rb = lots of base current
                _npn("Q1", "collector", "base", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vc = result.node_voltages["collector"]
        # In saturation, Vce should be very low
        assert vc < 1.0

    def test_cutoff_switch(self):
        """No base drive — BJT should be in cutoff. Vce ≈ Vcc."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "collector", "base", "gnd"],
            components=[
                _vsource("Vcc", 5.0, "vcc", "gnd"),
                _resistor("Rc", 1000.0, "vcc", "collector"),
                _resistor("Rb", 1000000.0, "base", "gnd"),  # Pull base to GND
                _npn("Q1", "collector", "base", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vc = result.node_voltages["collector"]
        # In cutoff, Vc should be near Vcc
        assert vc > 4.0


class TestCurrentMirror:
    """NPN current mirror — two matched transistors."""

    def test_current_mirror(self):
        """Reference current through Q1, mirrored by Q2."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "ref", "mirror", "base_node", "gnd"],
            components=[
                _vsource("Vcc", 10.0, "vcc", "gnd"),
                _resistor("Rref", 10000.0, "vcc", "ref"),
                _resistor("Rload", 10000.0, "vcc", "mirror"),
                # Q1: diode-connected (collector tied to base)
                _npn("Q1", "ref", "base_node", "gnd"),
                # Q2: mirror
                _npn("Q2", "mirror", "base_node", "gnd"),
                # Tie Q1 collector to base node (diode connection)
                # Actually we need a wire: ref = base_node? No, let's use same net.
                _ground("G1", "gnd"),
            ],
        )
        # For a proper current mirror, Q1's collector should be connected to base.
        # Let's simplify: use ref as the base node too.
        graph2 = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "ref", "mirror", "gnd"],
            components=[
                _vsource("Vcc", 10.0, "vcc", "gnd"),
                _resistor("Rref", 10000.0, "vcc", "ref"),
                _resistor("Rload", 10000.0, "vcc", "mirror"),
                _npn("Q1", "ref", "ref", "gnd"),  # Diode-connected
                _npn("Q2", "mirror", "ref", "gnd"),  # Mirror
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph2)
        # Both transistors should have similar collector currents
        ic1 = result.component_results["Q1"].extra_data.get("Ic", 0)
        ic2 = result.component_results["Q2"].extra_data.get("Ic", 0)
        assert ic1 > 0 and ic2 > 0
        # Mirror ratio should be close to 1 (matched transistors)
        if ic1 > 1e-9:
            ratio = ic2 / ic1
            assert 0.5 < ratio < 2.0


class TestPNPCircuit:
    """PNP transistor tests."""

    def test_pnp_switch(self):
        """PNP with emitter at Vcc, collector load to GND."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "collector", "base", "gnd"],
            components=[
                _vsource("Vcc", 5.0, "vcc", "gnd"),
                _resistor("Rc", 1000.0, "collector", "gnd"),
                _resistor("Rb", 1000.0, "base", "gnd"),  # Pull base low → PNP on
                _pnp("Q1", "collector", "base", "vcc", params={"model": "2N3906"}),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_dc_op(graph)
        vc = result.node_voltages["collector"]
        # PNP with base pulled low should be on, current flows emitter→collector
        assert vc > 1.0  # Collector voltage lifted by current through Rc


class TestBJTTransient:
    """Transient analysis with BJTs."""

    def test_bjt_transient_stability(self):
        """Simple CE amp should remain stable over transient."""
        graph = CircuitGraph(
            ground_net_id="gnd",
            nodes=["vcc", "collector", "base", "gnd"],
            components=[
                _vsource("Vcc", 12.0, "vcc", "gnd"),
                _resistor("Rc", 1000.0, "vcc", "collector"),
                _resistor("Rb", 100000.0, "vcc", "base"),
                _npn("Q1", "collector", "base", "gnd"),
                _ground("G1", "gnd"),
            ],
        )
        result = solve_transient(graph, t_stop=0.001, max_points=10)
        assert len(result.points) > 1
        # All points should have consistent collector voltage (DC circuit)
        voltages = [pt.node_voltages["collector"] for pt in result.points]
        # Should all be within 10% of each other
        assert max(voltages) - min(voltages) < 1.0
