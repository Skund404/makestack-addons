"""Educational tools — circuit calculators and MNA step-by-step explainer.

These are pure functions with no side effects, designed for AI-powered
circuit education and goal-directed design.
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Circuit Calculators
# ---------------------------------------------------------------------------


def voltage_divider(v_in: float, r1: float, r2: float) -> dict:
    """Calculate voltage divider output.

    Args:
        v_in: Input voltage (V)
        r1: Top resistor (Ω)
        r2: Bottom resistor (Ω)
    """
    if r1 + r2 == 0:
        return {"error": "Total resistance cannot be zero"}

    v_out = v_in * r2 / (r1 + r2)
    i = v_in / (r1 + r2)
    p_r1 = i * i * r1
    p_r2 = i * i * r2

    return {
        "v_out": round(v_out, 6),
        "current_a": round(i, 9),
        "current_ma": round(i * 1000, 6),
        "p_r1_w": round(p_r1, 9),
        "p_r2_w": round(p_r2, 9),
        "p_total_w": round(p_r1 + p_r2, 9),
        "formula": f"Vout = Vin × R2/(R1+R2) = {v_in} × {r2}/({r1}+{r2}) = {round(v_out, 4)}V",
    }


# E24 standard resistor values (multiplied by decade)
E24_VALUES = [
    1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
    3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
]


def _nearest_e24(value: float) -> float:
    """Find the nearest E24 standard resistor value."""
    if value <= 0:
        return 1.0
    decade = 10 ** math.floor(math.log10(value))
    normalized = value / decade
    best = min(E24_VALUES, key=lambda x: abs(x - normalized))
    return best * decade


def led_resistor(v_supply: float, v_led: float = 2.0, i_led_ma: float = 20.0) -> dict:
    """Calculate LED current-limiting resistor.

    Args:
        v_supply: Supply voltage (V)
        v_led: LED forward voltage (V), default 2.0V (red)
        i_led_ma: Desired LED current (mA), default 20mA
    """
    i_led = i_led_ma / 1000.0
    v_drop = v_supply - v_led
    if v_drop <= 0:
        return {"error": f"Supply voltage ({v_supply}V) must exceed LED voltage ({v_led}V)"}
    if i_led <= 0:
        return {"error": "LED current must be positive"}

    r_exact = v_drop / i_led
    r_e24 = _nearest_e24(r_exact)
    i_actual = v_drop / r_e24
    p_resistor = v_drop * i_actual

    return {
        "r_exact_ohm": round(r_exact, 2),
        "r_nearest_e24": r_e24,
        "i_actual_ma": round(i_actual * 1000, 3),
        "p_resistor_mw": round(p_resistor * 1000, 3),
        "formula": f"R = (Vsupply - Vled) / Iled = ({v_supply} - {v_led}) / {i_led_ma}mA = {round(r_exact, 1)}Ω",
    }


def rc_filter(r: float, c: float) -> dict:
    """Calculate RC filter cutoff frequency.

    Args:
        r: Resistance (Ω)
        c: Capacitance (F)
    """
    if r <= 0 or c <= 0:
        return {"error": "R and C must be positive"}

    fc = 1.0 / (2.0 * math.pi * r * c)
    tau = r * c

    return {
        "cutoff_freq_hz": round(fc, 4),
        "time_constant_s": round(tau, 9),
        "time_constant_ms": round(tau * 1000, 6),
        "formula": f"fc = 1/(2πRC) = 1/(2π × {r} × {c}) = {round(fc, 2)} Hz",
    }


def bjt_bias(vcc: float, ic_ma: float, beta: float = 100.0, vce: float = None) -> dict:
    """Calculate BJT bias resistors for common-emitter configuration.

    Uses voltage divider bias (4-resistor bias network).

    Args:
        vcc: Supply voltage (V)
        ic_ma: Desired collector current (mA)
        beta: Current gain (hFE), default 100
        vce: Desired Vce (V), default Vcc/2
    """
    ic = ic_ma / 1000.0
    if vce is None:
        vce = vcc / 2.0

    ib = ic / beta
    ie = ic + ib

    # Design for Re = 0.1 * Vcc / Ie (rule of thumb)
    ve = 0.1 * vcc
    re = ve / ie if ie > 0 else 100.0

    vb = ve + 0.7  # Vbe ≈ 0.7V
    rc = (vcc - vce - ve) / ic if ic > 0 else 1000.0

    # Voltage divider bias: make divider current >> Ib (10x)
    i_div = 10.0 * ib
    r2 = vb / i_div if i_div > 0 else 10000.0
    r1 = (vcc - vb) / i_div if i_div > 0 else 100000.0

    return {
        "r1_ohm": round(_nearest_e24(r1), 1),
        "r2_ohm": round(_nearest_e24(r2), 1),
        "rc_ohm": round(_nearest_e24(rc), 1),
        "re_ohm": round(_nearest_e24(re), 1),
        "r1_exact": round(r1, 1),
        "r2_exact": round(r2, 1),
        "rc_exact": round(rc, 1),
        "re_exact": round(re, 1),
        "ib_ua": round(ib * 1e6, 2),
        "ic_ma": ic_ma,
        "vce_v": round(vce, 2),
        "vb_v": round(vb, 2),
        "ve_v": round(ve, 2),
    }


# ---------------------------------------------------------------------------
# MNA Step-by-Step Explainer
# ---------------------------------------------------------------------------


def explain_mna(components: list[dict], nets: list[dict], pins: list[dict]) -> list[dict]:
    """Generate step-by-step MNA matrix construction explanation.

    Returns a list of steps, each with a description and optional matrix details.
    """
    steps = []

    # Step 1: Identify nodes
    ground_net = None
    signal_nets = []
    for net in nets:
        if net.get("net_type") == "ground":
            ground_net = net
        else:
            signal_nets.append(net)

    net_names = [n["name"] for n in signal_nets]
    ground_name = ground_net["name"] if ground_net else "GND"

    steps.append({
        "step": 1,
        "title": "Identify Nodes",
        "description": f"Found {len(signal_nets)} signal node(s): {', '.join(net_names)}. "
                       f"Ground reference: {ground_name}.",
        "detail": f"Matrix size: {len(signal_nets)} × {len(signal_nets)} "
                  f"(plus branch variables for voltage sources)",
    })

    # Build pin map
    pin_map: dict[str, dict[str, str]] = {}
    for pin in pins:
        cid = pin["component_id"]
        if cid not in pin_map:
            pin_map[cid] = {}
        pin_map[cid][pin["pin_name"]] = pin.get("net_id", "")

    # Net ID to name
    net_id_to_name = {n["id"]: n["name"] for n in nets}
    ground_id = ground_net["id"] if ground_net else None

    # Step 2: Count voltage sources
    vs_count = sum(1 for c in components if c["component_type"] == "voltage_source")
    opamp_count = sum(1 for c in components if c["component_type"] == "opamp")
    inductor_count = sum(1 for c in components if c["component_type"] == "inductor")
    branch_vars = vs_count + opamp_count + inductor_count

    if branch_vars > 0:
        steps.append({
            "step": 2,
            "title": "Count Branch Variables",
            "description": f"Found {branch_vars} branch variable(s): "
                           f"{vs_count} voltage source(s), {opamp_count} op-amp(s), "
                           f"{inductor_count} inductor(s).",
            "detail": f"Augmented matrix size: "
                      f"{len(signal_nets) + branch_vars} × {len(signal_nets) + branch_vars}",
        })

    # Step 3+: Stamp each component
    step_num = 3
    for comp in components:
        ctype = comp["component_type"]
        ref = comp.get("ref_designator", comp["id"])
        comp_pins = pin_map.get(comp["id"], {})

        def _net_name(pin_name: str) -> str:
            net_id = comp_pins.get(pin_name, "")
            if net_id == ground_id:
                return ground_name
            return net_id_to_name.get(net_id, "?")

        if ctype == "ground":
            continue

        if ctype == "resistor":
            value = comp.get("value", "?")
            p_name = _net_name("p")
            n_name = _net_name("n")
            g = f"1/{value}" if value and value != "0" else "∞"
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} ({value}Ω resistor)",
                "description": f"Add conductance G={g}S between nodes {p_name} and {n_name}. "
                               f"G[{p_name},{p_name}] += {g}, G[{n_name},{n_name}] += {g}, "
                               f"G[{p_name},{n_name}] -= {g}, G[{n_name},{p_name}] -= {g}.",
            })

        elif ctype == "voltage_source":
            value = comp.get("value", "?")
            p_name = _net_name("p")
            n_name = _net_name("n")
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} ({value}V source)",
                "description": f"Add voltage source equation: V({p_name}) - V({n_name}) = {value}V. "
                               f"Branch variable I_{ref} added. B and C matrices link {p_name}/{n_name} "
                               f"to the branch current.",
            })

        elif ctype == "current_source":
            value = comp.get("value", "?")
            p_name = _net_name("p")
            n_name = _net_name("n")
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} ({value}A source)",
                "description": f"Inject {value}A: i[{p_name}] += {value}, i[{n_name}] -= {value}.",
            })

        elif ctype == "capacitor":
            value = comp.get("value", "?")
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} ({value}F capacitor)",
                "description": f"DC: open circuit (no stamp). "
                               f"AC: admittance Y = jωC = j·2π·f·{value}. "
                               f"Transient: trapezoidal companion G_eq = 2C/h.",
            })

        elif ctype == "inductor":
            value = comp.get("value", "?")
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} ({value}H inductor)",
                "description": f"DC: short circuit (0V voltage source). "
                               f"AC: admittance Y = 1/(jωL). "
                               f"Transient: companion voltage source with R_eq = 2L/h.",
            })

        elif ctype in ("diode", "zener", "led"):
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} ({ctype})",
                "description": f"Nonlinear: Newton-Raphson linearization at each iteration. "
                               f"Norton companion: parallel conductance G_d + current source I_eq.",
            })

        elif ctype in ("npn_bjt", "pnp_bjt"):
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} (BJT {ctype.upper()})",
                "description": f"Nonlinear 3-terminal: Ebers-Moll model linearized via NR. "
                               f"Small-signal: gπ (B-E), gμ (B-C), gm·Vbe (transconductance), "
                               f"go (Early effect output conductance).",
            })

        elif ctype in ("nmos", "pmos"):
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} (MOSFET {ctype.upper()})",
                "description": f"Nonlinear 3-terminal: square-law model linearized via NR. "
                               f"Small-signal: gm (transconductance), gds (output conductance).",
            })

        elif ctype == "opamp":
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} (ideal op-amp)",
                "description": f"VCVS constraint: V(+) - V(-) = 0. "
                               f"Branch variable supplies output current. "
                               f"Augments matrix with one additional row/column.",
            })
        else:
            steps.append({
                "step": step_num,
                "title": f"Stamp {ref} ({ctype})",
                "description": f"Component type: {ctype}",
            })

        step_num += 1

    # Final step: Solve
    steps.append({
        "step": step_num,
        "title": "Solve Ax = z",
        "description": f"Solve the {len(signal_nets) + branch_vars}×"
                       f"{len(signal_nets) + branch_vars} system using "
                       f"{'Newton-Raphson iteration' if any(c['component_type'] in ('diode', 'zener', 'led', 'npn_bjt', 'pnp_bjt', 'nmos', 'pmos') for c in components) else 'direct linear solve'}. "
                       f"Result: node voltages and branch currents.",
    })

    return steps
