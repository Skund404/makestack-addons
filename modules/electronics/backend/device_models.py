"""Nonlinear device models for the electronics simulator.

Each device model provides:
- A parameter dataclass with sensible defaults
- An evaluation function returning current and conductance (Jacobian entries)
- A stamp function for the linearized Norton companion model

The solver calls stamp functions at each Newton-Raphson iteration with the
current operating point voltages. The stamp function linearizes the device
at that point and adds the companion conductance + current source to the
MNA matrix.

Supported devices:
- Diode (Shockley equation) — includes Zener and LED variants
- BJT (Ebers-Moll transport model) — NPN and PNP
- MOSFET (Square-law model) — NMOS and PMOS
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Thermal voltage
# ---------------------------------------------------------------------------

BOLTZMANN = 1.380649e-23  # J/K
CHARGE_Q = 1.602176634e-19  # C
T_NOMINAL = 300.15  # 27°C in Kelvin (SPICE default)

def thermal_voltage(temp_k: float = T_NOMINAL) -> float:
    """Thermal voltage Vt = kT/q."""
    return BOLTZMANN * temp_k / CHARGE_Q


VT_DEFAULT = thermal_voltage(T_NOMINAL)  # ~0.02585V


# ---------------------------------------------------------------------------
# Voltage limiting (critical for NR convergence)
# ---------------------------------------------------------------------------

def voltage_limit_pn(v_new: float, v_old: float, vt: float, v_crit: float) -> float:
    """Limit PN junction voltage change per NR iteration.

    Uses the SPICE pnjlim algorithm to prevent overflow in exp().
    v_crit = N * Vt * ln(N * Vt / (sqrt(2) * Is))
    """
    if v_new > v_crit and abs(v_new - v_old) > 2.0 * vt:
        if v_old > 0:
            arg = (v_new - v_old) / vt
            if arg > 0:
                v_new = v_old + vt * (2.0 + math.log(arg - 2.0)) if arg > 4.0 else v_old + vt * arg * 0.5
            else:
                v_new = v_old - vt * (2.0 + math.log(-arg - 2.0)) if arg < -4.0 else v_old + vt * arg * 0.5
        else:
            v_new = vt * math.log(v_new / vt) if v_new > 0 else v_crit
    return v_new


def pn_critical_voltage(is_val: float, n: float, vt: float) -> float:
    """Critical voltage above which we must limit NR steps."""
    return n * vt * math.log(n * vt / (math.sqrt(2.0) * is_val))


# ---------------------------------------------------------------------------
# Diode Model
# ---------------------------------------------------------------------------

@dataclass
class DiodeModel:
    """Shockley diode model parameters."""
    Is: float = 1e-14       # Saturation current (A)
    N: float = 1.0          # Emission coefficient
    Bv: float = 100.0       # Reverse breakdown voltage (V)
    Ibv: float = 1e-3       # Current at breakdown (A)
    Rs: float = 0.0         # Series resistance (Ω) — not yet used in stamp
    Vt: float = VT_DEFAULT  # Thermal voltage


@dataclass
class ZenerModel(DiodeModel):
    """Zener diode — diode with well-defined reverse breakdown."""
    Bv: float = 5.1         # Zener voltage
    Ibv: float = 1e-3
    Is: float = 1e-13
    N: float = 1.0


@dataclass
class LEDModel(DiodeModel):
    """LED — higher emission coefficient for higher forward voltage."""
    Is: float = 1e-20       # Very low Is gives higher Vf
    N: float = 2.0          # Higher N
    Bv: float = 5.0         # LEDs have low reverse tolerance


def diode_current(vd: float, model: DiodeModel) -> tuple[float, float]:
    """Evaluate diode current and conductance at voltage vd.

    Returns:
        (Id, Gd) where Id is the current and Gd = dId/dVd is the conductance.
    """
    nv = model.N * model.Vt
    # Forward / moderate reverse
    if vd > -model.Bv:
        # Prevent overflow: limit exponent argument
        arg = vd / nv
        if arg > 40.0:
            # Linear extrapolation above overflow threshold
            exp_40 = math.exp(40.0)
            Id = model.Is * (exp_40 * (1.0 + arg - 40.0) - 1.0)
            Gd = model.Is * exp_40 / nv
        elif arg < -40.0:
            # Deep reverse (but not breakdown)
            Id = -model.Is
            Gd = model.Is / nv * 1e-12  # Tiny conductance for convergence
        else:
            exp_val = math.exp(arg)
            Id = model.Is * (exp_val - 1.0)
            Gd = model.Is * exp_val / nv
    else:
        # Reverse breakdown region
        arg_bv = -(vd + model.Bv) / nv
        if arg_bv > 40.0:
            exp_40 = math.exp(40.0)
            Id = -model.Is - model.Ibv * exp_40 * (1.0 + arg_bv - 40.0)
            Gd = model.Ibv * exp_40 / nv
        else:
            exp_val = math.exp(arg_bv)
            Id = -model.Is - model.Ibv * exp_val
            Gd = model.Ibv * exp_val / nv

    # Ensure minimum conductance for convergence (Gmin)
    Gd = max(Gd, 1e-12)
    return Id, Gd


def stamp_diode(
    comp_id: str,
    anode_idx: int | None,
    cathode_idx: int | None,
    G: "np.ndarray",
    i_vec: "np.ndarray",
    x_current: "np.ndarray",
    model: DiodeModel,
) -> tuple[float, float, str]:
    """Stamp linearized diode companion into MNA matrix.

    The Norton companion at operating point (Vd0, Id0, Gd0):
        Stamp Gd0 as conductance between anode and cathode.
        Stamp current source Ieq = Id0 - Gd0 * Vd0 into anode/cathode.

    Returns:
        (Id, Vd, region) for result annotation.
    """
    # Get current operating point voltage
    va = float(x_current[anode_idx]) if anode_idx is not None else 0.0
    vc = float(x_current[cathode_idx]) if cathode_idx is not None else 0.0
    vd = va - vc

    Id, Gd = diode_current(vd, model)
    Ieq = Id - Gd * vd

    # Stamp conductance
    if anode_idx is not None:
        G[anode_idx, anode_idx] += Gd
    if cathode_idx is not None:
        G[cathode_idx, cathode_idx] += Gd
    if anode_idx is not None and cathode_idx is not None:
        G[anode_idx, cathode_idx] -= Gd
        G[cathode_idx, anode_idx] -= Gd

    # Stamp current source (Ieq flows into anode)
    if anode_idx is not None:
        i_vec[anode_idx] -= Ieq
    if cathode_idx is not None:
        i_vec[cathode_idx] += Ieq

    # Determine operating region
    if vd > 0.1:
        region = "forward"
    elif vd < -model.Bv:
        region = "breakdown"
    else:
        region = "reverse"

    return Id, vd, region


# ---------------------------------------------------------------------------
# BJT Model (Ebers-Moll Transport)
# ---------------------------------------------------------------------------

@dataclass
class BJTModel:
    """Ebers-Moll BJT model parameters."""
    Bf: float = 100.0       # Forward current gain (beta)
    Br: float = 1.0         # Reverse current gain
    Is: float = 1e-15       # Transport saturation current (A)
    Nf: float = 1.0         # Forward emission coefficient
    Nr: float = 1.0         # Reverse emission coefficient
    Vaf: float = 100.0      # Forward Early voltage (V), 0 = disabled
    Var: float = 0.0        # Reverse Early voltage (V), 0 = disabled
    Vt: float = VT_DEFAULT


def bjt_currents(
    vbe: float, vbc: float, model: BJTModel, is_pnp: bool = False,
) -> dict:
    """Evaluate BJT terminal currents and small-signal parameters.

    Uses the Ebers-Moll transport model:
        If = Is * (exp(Vbe/(Nf*Vt)) - 1)  (forward transport current)
        Ir = Is * (exp(Vbc/(Nr*Vt)) - 1)  (reverse transport current)
        Ic = If - Ir/Br  (with Early effect if Vaf > 0)
        Ib = If/Bf + Ir/Br

    For PNP: negate all junction voltages.

    Returns dict with: Ic, Ib, Ie, gm, gpi, gmu, go, If, Ir
    """
    if is_pnp:
        vbe = -vbe
        vbc = -vbc

    nf_vt = model.Nf * model.Vt
    nr_vt = model.Nr * model.Vt

    # Forward transport current
    arg_f = vbe / nf_vt
    if arg_f > 40.0:
        exp_40 = math.exp(40.0)
        exp_f = exp_40 * (1.0 + arg_f - 40.0)
        gm_f = model.Is * exp_40 / nf_vt  # derivative
    elif arg_f < -40.0:
        exp_f = 0.0
        gm_f = 1e-15
    else:
        exp_f = math.exp(arg_f)
        gm_f = model.Is * exp_f / nf_vt

    If = model.Is * (exp_f - 1.0)

    # Reverse transport current
    arg_r = vbc / nr_vt
    if arg_r > 40.0:
        exp_40 = math.exp(40.0)
        exp_r = exp_40 * (1.0 + arg_r - 40.0)
        gm_r = model.Is * exp_40 / nr_vt
    elif arg_r < -40.0:
        exp_r = 0.0
        gm_r = 1e-15
    else:
        exp_r = math.exp(arg_r)
        gm_r = model.Is * exp_r / nr_vt

    Ir = model.Is * (exp_r - 1.0)

    # Terminal currents
    Ic = If - Ir * (1.0 + 1.0 / model.Br)
    Ib = If / model.Bf + Ir / model.Br
    Ie = -(Ic + Ib)

    # Small-signal parameters (conductances for linearized model)
    gm = gm_f                           # transconductance dIc/dVbe
    gpi = gm_f / model.Bf               # input conductance dIb/dVbe
    gmu = gm_r / model.Br               # feedback conductance dIb/dVbc
    go = 0.0                            # output conductance (Early effect)
    if model.Vaf > 0 and Ic > 0:
        go = Ic / model.Vaf

    # Ensure minimum conductances
    gpi = max(gpi, 1e-12)
    gmu = max(gmu, 1e-12)
    gm = max(gm, 1e-15)

    result = {
        "Ic": Ic, "Ib": Ib, "Ie": Ie,
        "gm": gm, "gpi": gpi, "gmu": gmu, "go": go,
        "If": If, "Ir": Ir,
    }

    if is_pnp:
        result["Ic"] = -Ic
        result["Ib"] = -Ib
        result["Ie"] = -Ie

    return result


def stamp_bjt(
    comp_id: str,
    collector_idx: int | None,
    base_idx: int | None,
    emitter_idx: int | None,
    G: "np.ndarray",
    i_vec: "np.ndarray",
    x_current: "np.ndarray",
    model: BJTModel,
    is_pnp: bool = False,
) -> dict:
    """Stamp linearized BJT companion into MNA matrix.

    The linearized model has:
    - gpi conductance between base and emitter
    - gmu conductance between base and collector
    - gm * vbe dependent current source from collector to emitter
    - go conductance between collector and emitter (Early)

    The Norton equivalent stamps:
    - Conductances: gpi, gmu, gm, go into G matrix
    - Current sources: Ieq_c and Ieq_b from operating point

    Returns dict with operating point data.
    """
    # Get operating point voltages
    vc = float(x_current[collector_idx]) if collector_idx is not None else 0.0
    vb = float(x_current[base_idx]) if base_idx is not None else 0.0
    ve = float(x_current[emitter_idx]) if emitter_idx is not None else 0.0
    vbe = vb - ve
    vbc = vb - vc
    vce = vc - ve

    # Evaluate device
    bjt = bjt_currents(vbe, vbc, model, is_pnp)
    gm = bjt["gm"]
    gpi = bjt["gpi"]
    gmu = bjt["gmu"]
    go = bjt["go"]
    Ic = bjt["Ic"]
    Ib = bjt["Ib"]

    # Companion current sources (Norton form)
    # Ic_linear = gm*vbe + go*vce - gmu*vbc + Ieq_c
    # Ib_linear = gpi*vbe + gmu*vbc + Ieq_b
    Ieq_c = Ic - gm * vbe - go * vce + gmu * vbc
    Ieq_b = Ib - gpi * vbe - gmu * vbc

    # Helper to stamp a conductance between two nodes
    def _stamp_g(n1, n2, g):
        if n1 is not None:
            G[n1, n1] += g
        if n2 is not None:
            G[n2, n2] += g
        if n1 is not None and n2 is not None:
            G[n1, n2] -= g
            G[n2, n1] -= g

    # Helper to stamp a transconductance (current from n1→n2 controlled by v(n3)-v(n4))
    def _stamp_gm(n1, n2, n3, n4, gval):
        """Current into n1, out of n2, controlled by V(n3)-V(n4)."""
        if n1 is not None and n3 is not None:
            G[n1, n3] += gval
        if n1 is not None and n4 is not None:
            G[n1, n4] -= gval
        if n2 is not None and n3 is not None:
            G[n2, n3] -= gval
        if n2 is not None and n4 is not None:
            G[n2, n4] += gval

    c, b, e = collector_idx, base_idx, emitter_idx

    # gpi: base-emitter conductance
    _stamp_g(b, e, gpi)

    # gmu: base-collector conductance
    _stamp_g(b, c, gmu)

    # go: collector-emitter output conductance (Early effect)
    if go > 0:
        _stamp_g(c, e, go)

    # gm: transconductance — Ic depends on Vbe
    # Current flows collector→emitter, controlled by V(base)-V(emitter)
    _stamp_gm(c, e, b, e, gm)

    # Stamp companion current sources
    if c is not None:
        i_vec[c] -= Ieq_c
    if e is not None:
        i_vec[e] += Ieq_c

    if b is not None:
        i_vec[b] -= Ieq_b
    if e is not None:
        i_vec[e] += Ieq_b

    # Determine operating region
    if is_pnp:
        vbe_check, vbc_check = -vbe, -vbc
    else:
        vbe_check, vbc_check = vbe, vbc

    if vbe_check < 0.5:
        region = "cutoff"
    elif vbc_check < 0.5:
        region = "active"
    else:
        region = "saturation"

    return {
        "Ic": Ic, "Ib": Ib, "Ie": bjt["Ie"],
        "Vbe": vbe, "Vbc": vbc, "Vce": vce,
        "gm": gm, "region": region,
    }


# ---------------------------------------------------------------------------
# MOSFET Model (Square-Law / Level 1)
# ---------------------------------------------------------------------------

@dataclass
class MOSFETModel:
    """Level-1 MOSFET (square-law) model parameters."""
    Kp: float = 110e-6      # Transconductance parameter (A/V²)
    Vth: float = 0.7        # Threshold voltage (V)
    Lambda: float = 0.04    # Channel-length modulation (1/V)
    W: float = 10e-6        # Channel width (m)
    L: float = 1e-6         # Channel length (m)


def mosfet_current(
    vgs: float, vds: float, model: MOSFETModel, is_pmos: bool = False,
) -> dict:
    """Evaluate MOSFET drain current and small-signal parameters.

    Level-1 (square-law) model:
        Cutoff:     Vgs < Vth → Id = 0
        Linear:     Vds < Vgs-Vth → Id = β*((Vgs-Vth)*Vds - Vds²/2)*(1+λ*Vds)
        Saturation: Id = β/2*(Vgs-Vth)²*(1+λ*Vds)

    For PMOS: negate Vgs, Vds, Vth; negate resulting Id.

    Returns dict with: Id, gm, gds, region
    """
    if is_pmos:
        vgs = -vgs
        vds = -vds
        vth = -model.Vth  # PMOS has negative Vth
    else:
        vth = model.Vth

    beta = model.Kp * model.W / model.L
    vov = vgs - vth  # overdrive voltage

    if vov <= 0:
        # Cutoff
        Id = 0.0
        gm = 1e-12   # Minimal conductance
        gds = 1e-12
        region = "cutoff"
    elif vds <= vov:
        # Linear (triode) region
        Id = beta * (vov * vds - 0.5 * vds * vds) * (1.0 + model.Lambda * vds)
        gm = beta * vds * (1.0 + model.Lambda * vds)
        gds = beta * (vov - vds) * (1.0 + model.Lambda * vds) + beta * (vov * vds - 0.5 * vds * vds) * model.Lambda
        region = "linear"
    else:
        # Saturation
        Id = 0.5 * beta * vov * vov * (1.0 + model.Lambda * vds)
        gm = beta * vov * (1.0 + model.Lambda * vds)
        gds = 0.5 * beta * vov * vov * model.Lambda
        region = "saturation"

    # Ensure minimum conductances
    gm = max(gm, 1e-12)
    gds = max(gds, 1e-12)

    if is_pmos:
        Id = -Id

    return {"Id": Id, "gm": gm, "gds": gds, "region": region}


def stamp_mosfet(
    comp_id: str,
    gate_idx: int | None,
    drain_idx: int | None,
    source_idx: int | None,
    G: "np.ndarray",
    i_vec: "np.ndarray",
    x_current: "np.ndarray",
    model: MOSFETModel,
    is_pmos: bool = False,
) -> dict:
    """Stamp linearized MOSFET companion into MNA matrix.

    The linearized model:
    - Gate draws no DC current (infinite input impedance)
    - gm: transconductance (drain current controlled by Vgs)
    - gds: output conductance (drain-source)

    Norton companion:
    Id_linear = gm * vgs + gds * vds + Ieq
    """
    # Get operating point voltages
    vg = float(x_current[gate_idx]) if gate_idx is not None else 0.0
    vd = float(x_current[drain_idx]) if drain_idx is not None else 0.0
    vs = float(x_current[source_idx]) if source_idx is not None else 0.0
    vgs = vg - vs
    vds = vd - vs

    # Evaluate device
    mos = mosfet_current(vgs, vds, model, is_pmos)
    Id = mos["Id"]
    gm = mos["gm"]
    gds = mos["gds"]

    # Companion current source
    Ieq = Id - gm * vgs - gds * vds

    g, d, s = gate_idx, drain_idx, source_idx

    # gds: drain-source conductance
    if d is not None:
        G[d, d] += gds
    if s is not None:
        G[s, s] += gds
    if d is not None and s is not None:
        G[d, s] -= gds
        G[s, d] -= gds

    # gm: transconductance — Id controlled by Vgs = V(gate) - V(source)
    # Current into drain, out of source
    if d is not None and g is not None:
        G[d, g] += gm
    if d is not None and s is not None:
        G[d, s] -= gm
    if s is not None and g is not None:
        G[s, g] -= gm
    if s is not None and s is not None:
        G[s, s] += gm

    # Stamp companion current source (Id flows into drain, out of source)
    if d is not None:
        i_vec[d] -= Ieq
    if s is not None:
        i_vec[s] += Ieq

    return {
        "Id": Id, "Vgs": vgs, "Vds": vds,
        "gm": gm, "gds": gds, "region": mos["region"],
    }


# ---------------------------------------------------------------------------
# Preset Model Libraries
# ---------------------------------------------------------------------------

DIODE_PRESETS: dict[str, DiodeModel] = {
    "1N4148": DiodeModel(Is=2.52e-9, N=1.752, Bv=100.0),
    "1N4001": DiodeModel(Is=14.11e-9, N=1.984, Bv=50.0),
    "1N4002": DiodeModel(Is=14.11e-9, N=1.984, Bv=100.0),
    "1N4007": DiodeModel(Is=14.11e-9, N=1.984, Bv=1000.0),
    "1N5817": DiodeModel(Is=3.12e-8, N=1.042, Bv=20.0),   # Schottky
    "1N5819": DiodeModel(Is=3.12e-8, N=1.042, Bv=40.0),   # Schottky
    "default": DiodeModel(),
}

ZENER_PRESETS: dict[str, ZenerModel] = {
    "1N4733A": ZenerModel(Bv=5.1, Is=1e-13),
    "1N4734A": ZenerModel(Bv=5.6, Is=1e-13),
    "1N4742A": ZenerModel(Bv=12.0, Is=1e-13),
    "1N4744A": ZenerModel(Bv=15.0, Is=1e-13),
    "BZX55C3V3": ZenerModel(Bv=3.3, Is=1e-13),
    "default": ZenerModel(),
}

LED_PRESETS: dict[str, LEDModel] = {
    "red": LEDModel(Is=1e-20, N=2.0),
    "green": LEDModel(Is=1e-22, N=2.2),
    "blue": LEDModel(Is=1e-24, N=2.5),
    "white": LEDModel(Is=1e-23, N=2.3),
    "default": LEDModel(),
}

BJT_PRESETS: dict[str, tuple[BJTModel, bool]] = {
    # (model, is_pnp)
    "2N3904": (BJTModel(Bf=300.0, Br=4.0, Is=6.734e-15, Nf=1.0, Nr=1.0, Vaf=74.03), False),
    "2N3906": (BJTModel(Bf=180.0, Br=4.0, Is=1.305e-14, Nf=1.0, Nr=1.0, Vaf=18.7), True),
    "2N2222": (BJTModel(Bf=200.0, Br=3.0, Is=1.4e-14, Nf=1.0, Nr=1.0, Vaf=74.0), False),
    "BC547": (BJTModel(Bf=330.0, Br=6.0, Is=1.8e-14, Nf=1.0, Nr=1.0, Vaf=69.0), False),
    "BC557": (BJTModel(Bf=270.0, Br=3.0, Is=2.0e-14, Nf=1.0, Nr=1.0, Vaf=50.0), True),
    "default_npn": (BJTModel(), False),
    "default_pnp": (BJTModel(), True),
}

MOSFET_PRESETS: dict[str, tuple[MOSFETModel, bool]] = {
    # (model, is_pmos)
    "2N7000": (MOSFETModel(Kp=0.1, Vth=2.0, Lambda=0.04, W=1.0, L=1.0), False),
    "BS170": (MOSFETModel(Kp=0.15, Vth=1.5, Lambda=0.03, W=1.0, L=1.0), False),
    "IRF510": (MOSFETModel(Kp=6.0, Vth=3.7, Lambda=0.01, W=1.0, L=1.0), False),
    "IRF9510": (MOSFETModel(Kp=3.0, Vth=-3.7, Lambda=0.01, W=1.0, L=1.0), True),
    "default_nmos": (MOSFETModel(), False),
    "default_pmos": (MOSFETModel(Vth=-0.7), True),
}


def get_diode_model(params: dict) -> DiodeModel:
    """Build a DiodeModel from component params dict."""
    preset = params.get("model")
    if preset and preset in DIODE_PRESETS:
        base = DIODE_PRESETS[preset]
    else:
        base = DiodeModel()
    # Override individual params
    return DiodeModel(
        Is=params.get("Is", base.Is),
        N=params.get("N", base.N),
        Bv=params.get("Bv", base.Bv),
        Ibv=params.get("Ibv", base.Ibv),
        Rs=params.get("Rs", base.Rs),
        Vt=params.get("Vt", base.Vt),
    )


def get_zener_model(params: dict) -> ZenerModel:
    """Build a ZenerModel from component params dict."""
    preset = params.get("model")
    if preset and preset in ZENER_PRESETS:
        base = ZENER_PRESETS[preset]
    else:
        base = ZenerModel()
    return ZenerModel(
        Is=params.get("Is", base.Is),
        N=params.get("N", base.N),
        Bv=params.get("Bv", base.Bv),
        Ibv=params.get("Ibv", base.Ibv),
        Rs=params.get("Rs", base.Rs),
        Vt=params.get("Vt", base.Vt),
    )


def get_led_model(params: dict) -> LEDModel:
    """Build an LEDModel from component params dict."""
    preset = params.get("model")
    if preset and preset in LED_PRESETS:
        base = LED_PRESETS[preset]
    else:
        base = LEDModel()
    return LEDModel(
        Is=params.get("Is", base.Is),
        N=params.get("N", base.N),
        Bv=params.get("Bv", base.Bv),
        Ibv=params.get("Ibv", base.Ibv),
        Rs=params.get("Rs", base.Rs),
        Vt=params.get("Vt", base.Vt),
    )


def get_bjt_model(params: dict, is_pnp: bool = False) -> BJTModel:
    """Build a BJTModel from component params dict."""
    preset = params.get("model")
    if preset and preset in BJT_PRESETS:
        base, _ = BJT_PRESETS[preset]
    else:
        base = BJTModel()
    return BJTModel(
        Bf=params.get("Bf", base.Bf),
        Br=params.get("Br", base.Br),
        Is=params.get("Is", base.Is),
        Nf=params.get("Nf", base.Nf),
        Nr=params.get("Nr", base.Nr),
        Vaf=params.get("Vaf", base.Vaf),
        Var=params.get("Var", base.Var),
        Vt=params.get("Vt", base.Vt),
    )


def get_mosfet_model(params: dict) -> MOSFETModel:
    """Build a MOSFETModel from component params dict."""
    preset = params.get("model")
    if preset and preset in MOSFET_PRESETS:
        base, _ = MOSFET_PRESETS[preset]
    else:
        base = MOSFETModel()
    return MOSFETModel(
        Kp=params.get("Kp", base.Kp),
        Vth=params.get("Vth", base.Vth),
        Lambda=params.get("Lambda", base.Lambda),
        W=params.get("W", base.W),
        L=params.get("L", base.L),
    )


# ---------------------------------------------------------------------------
# Nonlinear component type classification
# ---------------------------------------------------------------------------

NONLINEAR_TYPES = {"diode", "zener", "led", "npn_bjt", "pnp_bjt", "nmos", "pmos"}

def is_nonlinear(component_type: str) -> bool:
    """Check if a component type requires Newton-Raphson iteration."""
    return component_type in NONLINEAR_TYPES
