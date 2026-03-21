"""Modified Nodal Analysis (MNA) solver for linear circuits.

Supports:
- DC operating point (solve_dc_op)
- AC small-signal analysis (solve_ac)
- DC sweep (solve_dc_sweep)
- Transient analysis (solve_transient)

Matrix structure:
    A = | G   B |     x = | v |     z = | i |
        | C   D |         | j |         | e |

Where:
    G (n x n) = conductance (or admittance in AC) matrix
    B (n x m) = voltage source incidence
    C (m x n) = transpose of B
    D (m x m) = zero (independent sources)
    v = node voltages (unknowns)
    j = voltage source branch currents (unknowns)
    i = current source injections (known)
    e = voltage source values (known)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ComponentInstance:
    """A placed component in a circuit, ready for the solver."""

    id: str
    component_type: str  # "resistor", "capacitor", "inductor", "voltage_source", "current_source", "ground"
    value: float
    pins: dict[str, str | None]  # pin_name -> net_id (None if unconnected)


@dataclass
class CircuitGraph:
    """In-memory circuit representation for the solver."""

    ground_net_id: str | None = None
    nodes: list[str] = field(default_factory=list)  # net IDs (excluding ground)
    components: list[ComponentInstance] = field(default_factory=list)


@dataclass
class ComponentResult:
    """Simulation result for a single component."""

    current: float
    power: float
    voltage_drop: float


@dataclass
class SolverResult:
    """Complete DC operating point solution."""

    node_voltages: dict[str, float]  # net_id -> voltage
    component_results: dict[str, ComponentResult]  # component_id -> result
    solver_metadata: dict  # matrix size, condition number, etc.


@dataclass
class ACPoint:
    """AC analysis result at one frequency."""

    frequency: float
    node_voltages: dict[str, complex]  # net_id -> complex voltage (magnitude + phase)


@dataclass
class ACResult:
    """Complete AC small-signal analysis result."""

    points: list[ACPoint]
    solver_metadata: dict


@dataclass
class SweepPoint:
    """DC sweep result at one parameter value."""

    parameter_value: float
    node_voltages: dict[str, float]
    component_results: dict[str, ComponentResult]


@dataclass
class SweepResult:
    """Complete DC sweep result."""

    source_id: str
    points: list[SweepPoint]
    solver_metadata: dict


@dataclass
class TransientPoint:
    """Transient analysis result at one time step."""

    time: float
    node_voltages: dict[str, float]
    component_results: dict[str, ComponentResult]


@dataclass
class TransientResult:
    """Complete transient analysis result."""

    points: list[TransientPoint]
    solver_metadata: dict


class SolverError(Exception):
    """Raised when the circuit cannot be solved."""


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------


def _validate_graph(graph: CircuitGraph) -> list[ComponentInstance]:
    """Validate the graph and return active (non-ground) components."""
    if graph.ground_net_id is None:
        raise SolverError(
            "No ground node defined. Every circuit needs a ground reference. "
            "Place a ground component and connect it to a net."
        )

    active_components = [
        c for c in graph.components if c.component_type != "ground"
    ]

    if not active_components:
        raise SolverError(
            "Circuit has no active components. "
            "Add resistors, voltage sources, or current sources."
        )

    for comp in active_components:
        for pin_name, net_id in comp.pins.items():
            if net_id is None:
                raise SolverError(
                    f"Component {comp.id} has unconnected pin '{pin_name}'. "
                    f"Connect all pins before simulating."
                )

    return active_components


def _build_node_index(graph: CircuitGraph) -> dict[str, int]:
    """Map each non-ground net to a matrix index."""
    node_index: dict[str, int] = {}
    for net_id in graph.nodes:
        if net_id != graph.ground_net_id:
            node_index[net_id] = len(node_index)
    return node_index


def _count_voltage_sources(active_components: list[ComponentInstance]) -> tuple[list[ComponentInstance], dict[str, int]]:
    """Return voltage sources list and id->index map."""
    voltage_sources = [
        c for c in active_components if c.component_type == "voltage_source"
    ]
    vs_index: dict[str, int] = {}
    for k, vs in enumerate(voltage_sources):
        vs_index[vs.id] = k
    return voltage_sources, vs_index


# ---------------------------------------------------------------------------
# DC Operating Point
# ---------------------------------------------------------------------------


def solve_dc_op(graph: CircuitGraph) -> SolverResult:
    """Solve DC operating point using Modified Nodal Analysis.

    In DC:
    - Capacitors are open circuits (infinite impedance, zero current)
    - Inductors are short circuits (zero impedance) — modeled as 0V voltage sources

    Args:
        graph: Circuit topology with components and net connections.

    Returns:
        SolverResult with node voltages and component currents/power.

    Raises:
        SolverError: If the circuit is invalid or the matrix is singular.
    """
    active_components = _validate_graph(graph)
    node_index = _build_node_index(graph)
    n = len(node_index)

    # In DC, inductors act as short circuits (0V voltage sources)
    inductors = [c for c in active_components if c.component_type == "inductor"]
    voltage_sources, vs_index = _count_voltage_sources(active_components)

    # Add inductors as voltage sources (0V) for DC
    inductor_vs_offset = len(voltage_sources)
    for k, ind in enumerate(inductors):
        vs_index[ind.id] = inductor_vs_offset + k

    m = len(voltage_sources) + len(inductors)
    size = n + m
    if size == 0:
        raise SolverError(
            "Circuit has no nodes to solve. "
            "Connect components to form a circuit."
        )

    A = np.zeros((size, size), dtype=float)
    z = np.zeros(size, dtype=float)

    G = A[:n, :n]
    B = A[:n, n:]
    C = A[n:, :n]
    i_vec = z[:n]
    e_vec = z[n:]

    def _node_idx(net_id: str) -> int | None:
        if net_id == graph.ground_net_id:
            return None
        return node_index.get(net_id)

    for comp in active_components:
        if comp.component_type == "resistor":
            _stamp_resistor(comp, G, _node_idx)
        elif comp.component_type == "voltage_source":
            _stamp_voltage_source(comp, B, C, e_vec, vs_index, _node_idx)
        elif comp.component_type == "current_source":
            _stamp_current_source(comp, i_vec, _node_idx)
        elif comp.component_type == "inductor":
            # DC: inductor = 0V voltage source (short circuit)
            _stamp_voltage_source_value(comp, B, C, e_vec, vs_index, _node_idx, 0.0)
        elif comp.component_type == "capacitor":
            # DC: capacitor = open circuit — no stamp needed
            pass

    try:
        cond = np.linalg.cond(A)
        if cond > 1e15:
            raise SolverError(
                "Circuit matrix is near-singular (condition number too high). "
                "This usually means a voltage source loop without resistance, "
                "or nodes connected only by voltage sources."
            )
        x = np.linalg.solve(A, z)
    except np.linalg.LinAlgError:
        raise SolverError(
            "Circuit matrix is singular — cannot solve. "
            "Check for voltage source loops without resistance, "
            "or floating nodes not connected to the circuit."
        )

    node_voltages: dict[str, float] = {}
    for net_id, idx in node_index.items():
        node_voltages[net_id] = float(x[idx])
    node_voltages[graph.ground_net_id] = 0.0

    component_results: dict[str, ComponentResult] = {}
    for comp in active_components:
        cr = _compute_component_result(comp, node_voltages, x, n, vs_index)
        component_results[comp.id] = cr

    return SolverResult(
        node_voltages=node_voltages,
        component_results=component_results,
        solver_metadata={
            "matrix_size": size,
            "num_nodes": n,
            "num_voltage_sources": m,
            "condition_number": float(cond),
        },
    )


# ---------------------------------------------------------------------------
# AC Small-Signal Analysis
# ---------------------------------------------------------------------------


def solve_ac(
    graph: CircuitGraph,
    f_start: float = 1.0,
    f_stop: float = 1e6,
    points_per_decade: int = 20,
) -> ACResult:
    """AC small-signal analysis across a frequency sweep.

    Builds complex MNA matrix at each frequency:
    - Capacitor: Y_C = jωC (admittance stamped into G)
    - Inductor: Z_L = jωL (stamped as voltage source with V = jωL * I)
      Actually easier to stamp inductor admittance: Y_L = 1/(jωL)

    For AC, voltage sources contribute 1V AC excitation (small-signal).
    Current sources contribute 0A AC (they are constant in small-signal).

    Args:
        graph: Circuit topology.
        f_start: Start frequency in Hz.
        f_stop: Stop frequency in Hz.
        points_per_decade: Number of frequency points per decade.

    Returns:
        ACResult with complex node voltages at each frequency.
    """
    active_components = _validate_graph(graph)
    node_index = _build_node_index(graph)
    n = len(node_index)

    voltage_sources, vs_index = _count_voltage_sources(active_components)
    # In AC, inductors stamp as admittance (not as voltage sources)
    m = len(voltage_sources)
    size = n + m

    if size == 0:
        raise SolverError("Circuit has no nodes to solve.")

    def _node_idx(net_id: str) -> int | None:
        if net_id == graph.ground_net_id:
            return None
        return node_index.get(net_id)

    # Generate log-spaced frequencies
    if f_start <= 0:
        f_start = 0.01
    if f_stop <= f_start:
        f_stop = f_start * 10

    num_decades = math.log10(f_stop / f_start)
    num_points = max(2, int(num_decades * points_per_decade))
    frequencies = np.logspace(math.log10(f_start), math.log10(f_stop), num_points)

    points: list[ACPoint] = []

    for freq in frequencies:
        omega = 2.0 * math.pi * freq

        A = np.zeros((size, size), dtype=complex)
        z = np.zeros(size, dtype=complex)

        G = A[:n, :n]
        B = A[:n, n:]
        C = A[n:, :n]
        i_vec = z[:n]
        e_vec = z[n:]

        for comp in active_components:
            if comp.component_type == "resistor":
                _stamp_resistor_complex(comp, G, _node_idx)
            elif comp.component_type == "capacitor":
                _stamp_capacitor_ac(comp, G, _node_idx, omega)
            elif comp.component_type == "inductor":
                _stamp_inductor_ac(comp, G, _node_idx, omega)
            elif comp.component_type == "voltage_source":
                _stamp_voltage_source_complex(comp, B, C, e_vec, vs_index, _node_idx)
            elif comp.component_type == "current_source":
                # DC current sources are constant — zero AC contribution
                pass

        try:
            x = np.linalg.solve(A, z)
        except np.linalg.LinAlgError:
            raise SolverError(
                f"AC matrix singular at f={freq:.2f}Hz. "
                "Check for isolated nodes or degenerate topology."
            )

        node_voltages: dict[str, complex] = {}
        for net_id, idx in node_index.items():
            node_voltages[net_id] = complex(x[idx])
        node_voltages[graph.ground_net_id] = 0j

        points.append(ACPoint(frequency=freq, node_voltages=node_voltages))

    return ACResult(
        points=points,
        solver_metadata={
            "num_points": len(points),
            "f_start": float(frequencies[0]),
            "f_stop": float(frequencies[-1]),
            "matrix_size": size,
        },
    )


# ---------------------------------------------------------------------------
# DC Sweep
# ---------------------------------------------------------------------------


def solve_dc_sweep(
    graph: CircuitGraph,
    source_id: str,
    start: float,
    stop: float,
    steps: int = 50,
) -> SweepResult:
    """Sweep a voltage or current source value and solve DC OP at each point.

    Args:
        graph: Circuit topology.
        source_id: ID of the source component to sweep.
        start: Start value of the sweep.
        stop: Stop value of the sweep.
        steps: Number of sweep points.

    Returns:
        SweepResult with DC OP at each sweep value.
    """
    # Validate source exists
    source = None
    for comp in graph.components:
        if comp.id == source_id:
            source = comp
            break

    if source is None:
        raise SolverError(f"Source component '{source_id}' not found in circuit.")

    if source.component_type not in ("voltage_source", "current_source"):
        raise SolverError(
            f"Can only sweep voltage_source or current_source, "
            f"got '{source.component_type}'."
        )

    sweep_values = np.linspace(start, stop, steps)
    points: list[SweepPoint] = []
    original_value = source.value

    try:
        for val in sweep_values:
            source.value = float(val)
            try:
                result = solve_dc_op(graph)
                points.append(SweepPoint(
                    parameter_value=float(val),
                    node_voltages=result.node_voltages,
                    component_results=result.component_results,
                ))
            except SolverError:
                # Skip singular points in sweep
                continue
    finally:
        source.value = original_value

    if not points:
        raise SolverError("DC sweep produced no valid results.")

    return SweepResult(
        source_id=source_id,
        points=points,
        solver_metadata={
            "start": start,
            "stop": stop,
            "steps": steps,
            "valid_points": len(points),
        },
    )


# ---------------------------------------------------------------------------
# Transient Analysis
# ---------------------------------------------------------------------------


def solve_transient(
    graph: CircuitGraph,
    t_stop: float = 0.01,
    t_step: float | None = None,
    max_points: int = 1000,
) -> TransientResult:
    """Transient analysis using trapezoidal integration (companion models).

    At each time step, reactive components are replaced by companion models:
    - Capacitor → parallel conductance G_eq = 2C/h + current source I_eq
    - Inductor → series conductance G_eq = h/(2L) + voltage source V_eq

    Uses the trapezoidal rule (Gear-2 / trap) for stability and accuracy.

    Args:
        graph: Circuit topology.
        t_stop: Simulation end time in seconds.
        t_step: Time step (auto-calculated if None).
        max_points: Maximum number of output points.

    Returns:
        TransientResult with voltages at each time step.
    """
    active_components = _validate_graph(graph)

    # Determine time step
    if t_step is None:
        t_step = t_stop / min(max_points, 500)

    if t_step <= 0:
        raise SolverError("Time step must be positive.")

    # Compute total steps, limit output
    total_steps = int(t_stop / t_step)
    if total_steps > max_points * 10:
        # Too many steps — increase step size
        t_step = t_stop / (max_points * 10)
        total_steps = int(t_stop / t_step)

    output_every = max(1, total_steps // max_points)

    node_index = _build_node_index(graph)
    n = len(node_index)

    # In transient, inductors need branch current variables (like voltage sources)
    voltage_sources, vs_index = _count_voltage_sources(active_components)
    inductors = [c for c in active_components if c.component_type == "inductor"]
    inductor_vs_offset = len(voltage_sources)
    for k, ind in enumerate(inductors):
        vs_index[ind.id] = inductor_vs_offset + k

    m = len(voltage_sources) + len(inductors)
    size = n + m

    if size == 0:
        raise SolverError("Circuit has no nodes to solve.")

    def _node_idx(net_id: str) -> int | None:
        if net_id == graph.ground_net_id:
            return None
        return node_index.get(net_id)

    # Initial DC operating point (capacitors open, inductors short)
    dc_result = solve_dc_op(graph)

    # Initialize state: node voltages and inductor currents
    v_prev = np.zeros(size, dtype=float)
    for net_id, idx in node_index.items():
        v_prev[idx] = dc_result.node_voltages.get(net_id, 0.0)
    # Initial inductor currents from DC OP
    for ind in inductors:
        k = vs_index[ind.id]
        cr = dc_result.component_results.get(ind.id)
        if cr:
            v_prev[n + k] = cr.current

    # Capacitor voltage history (for trapezoidal companion)
    # Store v_p - v_n for each capacitor at previous step
    cap_voltages: dict[str, float] = {}
    cap_currents: dict[str, float] = {}
    for comp in active_components:
        if comp.component_type == "capacitor":
            v_p = dc_result.node_voltages.get(comp.pins["p"], 0.0)
            v_n = dc_result.node_voltages.get(comp.pins["n"], 0.0)
            cap_voltages[comp.id] = v_p - v_n
            cap_currents[comp.id] = 0.0  # No current at DC steady state

    # Inductor voltage history
    ind_voltages: dict[str, float] = {}
    for ind in inductors:
        v_p = dc_result.node_voltages.get(ind.pins["p"], 0.0)
        v_n = dc_result.node_voltages.get(ind.pins["n"], 0.0)
        ind_voltages[ind.id] = v_p - v_n

    points: list[TransientPoint] = []

    # Add t=0 point
    points.append(TransientPoint(
        time=0.0,
        node_voltages=dict(dc_result.node_voltages),
        component_results=dict(dc_result.component_results),
    ))

    h = t_step

    for step_num in range(1, total_steps + 1):
        t = step_num * h

        A = np.zeros((size, size), dtype=float)
        z = np.zeros(size, dtype=float)

        G = A[:n, :n]
        B = A[:n, n:]
        C = A[n:, :n]
        i_vec = z[:n]
        e_vec = z[n:]

        for comp in active_components:
            if comp.component_type == "resistor":
                _stamp_resistor(comp, G, _node_idx)
            elif comp.component_type == "voltage_source":
                _stamp_voltage_source(comp, B, C, e_vec, vs_index, _node_idx)
            elif comp.component_type == "current_source":
                _stamp_current_source(comp, i_vec, _node_idx)
            elif comp.component_type == "capacitor":
                # Trapezoidal companion: G_eq = 2C/h, I_eq = G_eq * v_prev + i_prev
                _stamp_capacitor_transient(
                    comp, G, i_vec, _node_idx, h,
                    cap_voltages[comp.id], cap_currents[comp.id],
                )
            elif comp.component_type == "inductor":
                # Trapezoidal companion: inductor as voltage source with
                # V_eq = v_prev + (h/(2L)) * i_prev ... actually use conductance form
                _stamp_inductor_transient(
                    comp, B, C, G, e_vec, vs_index, _node_idx, h,
                    v_prev, n,
                    ind_voltages[comp.id],
                )

        try:
            x = np.linalg.solve(A, z)
        except np.linalg.LinAlgError:
            raise SolverError(
                f"Transient matrix singular at t={t:.6f}s. "
                "Circuit may be degenerate."
            )

        # Extract results
        node_voltages: dict[str, float] = {}
        for net_id, idx in node_index.items():
            node_voltages[net_id] = float(x[idx])
        node_voltages[graph.ground_net_id] = 0.0

        # Update capacitor state
        for comp in active_components:
            if comp.component_type == "capacitor":
                p = _node_idx(comp.pins["p"])
                n_ = _node_idx(comp.pins["n"])
                v_p_new = float(x[p]) if p is not None else 0.0
                v_n_new = float(x[n_]) if n_ is not None else 0.0
                v_cap_new = v_p_new - v_n_new
                v_cap_old = cap_voltages[comp.id]

                # Trapezoidal: i_new = 2C/h * (v_new - v_old) - i_old
                g_eq = 2.0 * comp.value / h
                i_new = g_eq * (v_cap_new - v_cap_old) - cap_currents[comp.id]

                cap_voltages[comp.id] = v_cap_new
                cap_currents[comp.id] = i_new

        # Update inductor state
        for ind in inductors:
            v_p_new = node_voltages.get(ind.pins["p"], 0.0)
            v_n_new = node_voltages.get(ind.pins["n"], 0.0)
            ind_voltages[ind.id] = v_p_new - v_n_new

        v_prev = x.copy()

        # Compute component results and store point
        if step_num % output_every == 0 or step_num == total_steps:
            component_results: dict[str, ComponentResult] = {}
            for comp in active_components:
                cr = _compute_component_result(comp, node_voltages, x, n, vs_index)
                component_results[comp.id] = cr

            points.append(TransientPoint(
                time=t,
                node_voltages=node_voltages,
                component_results=component_results,
            ))

    return TransientResult(
        points=points,
        solver_metadata={
            "t_stop": t_stop,
            "t_step": h,
            "total_steps": total_steps,
            "output_points": len(points),
            "matrix_size": size,
        },
    )


# ---------------------------------------------------------------------------
# Stamping functions — Real (DC / Transient)
# ---------------------------------------------------------------------------


def _stamp_resistor(
    comp: ComponentInstance,
    G: np.ndarray,
    node_idx,
) -> None:
    """Stamp a resistor into the conductance matrix G."""
    if comp.value <= 0:
        raise SolverError(
            f"Resistor {comp.id} has non-positive resistance ({comp.value}). "
            f"Resistance must be greater than zero."
        )

    conductance = 1.0 / comp.value
    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    if p is not None:
        G[p, p] += conductance
    if n_ is not None:
        G[n_, n_] += conductance
    if p is not None and n_ is not None:
        G[p, n_] -= conductance
        G[n_, p] -= conductance


def _stamp_voltage_source(
    comp: ComponentInstance,
    B: np.ndarray,
    C: np.ndarray,
    e_vec: np.ndarray,
    vs_index: dict[str, int],
    node_idx,
) -> None:
    """Stamp a voltage source into B, C, and e."""
    _stamp_voltage_source_value(comp, B, C, e_vec, vs_index, node_idx, comp.value)


def _stamp_voltage_source_value(
    comp: ComponentInstance,
    B: np.ndarray,
    C: np.ndarray,
    e_vec: np.ndarray,
    vs_index: dict[str, int],
    node_idx,
    value: float,
) -> None:
    """Stamp a voltage source with a specific value into B, C, and e."""
    k = vs_index[comp.id]
    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    if p is not None:
        B[p, k] = 1.0
        C[k, p] = 1.0
    if n_ is not None:
        B[n_, k] = -1.0
        C[k, n_] = -1.0

    e_vec[k] = value


def _stamp_current_source(
    comp: ComponentInstance,
    i_vec: np.ndarray,
    node_idx,
) -> None:
    """Stamp a current source into the current injection vector."""
    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    # Current flows from n to p (into positive terminal)
    if p is not None:
        i_vec[p] += comp.value
    if n_ is not None:
        i_vec[n_] -= comp.value


def _stamp_capacitor_transient(
    comp: ComponentInstance,
    G: np.ndarray,
    i_vec: np.ndarray,
    node_idx,
    h: float,
    v_cap_prev: float,
    i_cap_prev: float,
) -> None:
    """Stamp trapezoidal companion model for a capacitor.

    Companion: parallel conductance G_eq = 2C/h with current source I_eq.
    I_eq = G_eq * v_prev + i_prev
    """
    C_val = comp.value
    if C_val <= 0:
        raise SolverError(f"Capacitor {comp.id} has non-positive capacitance.")

    g_eq = 2.0 * C_val / h
    i_eq = g_eq * v_cap_prev + i_cap_prev

    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    # Stamp conductance (like a resistor with G = g_eq)
    if p is not None:
        G[p, p] += g_eq
    if n_ is not None:
        G[n_, n_] += g_eq
    if p is not None and n_ is not None:
        G[p, n_] -= g_eq
        G[n_, p] -= g_eq

    # Stamp current source (I_eq into positive terminal)
    if p is not None:
        i_vec[p] += i_eq
    if n_ is not None:
        i_vec[n_] -= i_eq


def _stamp_inductor_transient(
    comp: ComponentInstance,
    B: np.ndarray,
    C: np.ndarray,
    G: np.ndarray,
    e_vec: np.ndarray,
    vs_index: dict[str, int],
    node_idx,
    h: float,
    x_prev: np.ndarray,
    n_nodes: int,
    v_ind_prev: float,
) -> None:
    """Stamp trapezoidal companion model for an inductor.

    The inductor branch equation is: v = L * di/dt
    Trapezoidal: i_new = i_old + (h/(2L)) * (v_new + v_old)

    Rearranged as a voltage source with series resistance:
    v_new = (2L/h) * i_new - (2L/h) * i_old - v_old

    This stamps as: voltage source equation with extra resistance term.
    The MNA row for inductor branch k:
        v_p - v_n - (2L/h) * i_k = -(2L/h) * i_old - v_old
    """
    L_val = comp.value
    if L_val <= 0:
        raise SolverError(f"Inductor {comp.id} has non-positive inductance.")

    k = vs_index[comp.id]
    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    r_eq = 2.0 * L_val / h  # equivalent resistance

    # Standard voltage source stamps (B and C)
    if p is not None:
        B[p, k] = 1.0
        C[k, p] = 1.0
    if n_ is not None:
        B[n_, k] = -1.0
        C[k, n_] = -1.0

    # D matrix: -(2L/h) on the diagonal for this branch
    # This goes into A[n_nodes + k, n_nodes + k]
    # But B and C are sub-views, so we need to use G's parent
    # The D sub-matrix position: A[n_nodes:, n_nodes:]
    # We access it through the full matrix via B's base
    # Actually, we have B = A[:n, n:] and C = A[n:, :n]
    # D = A[n:, n:] — we can compute the offset
    # D[k, k] = -r_eq
    # Since B is A[:n_nodes, n_nodes:], the D matrix is at rows n_nodes+k
    # We need to stamp into the full A matrix
    # B.base gives us A if B is a view
    A_full = B.base if B.base is not None else B
    # Actually, let's just compute the index directly
    # The inductor branch equation row is at index n_nodes + k
    # The inductor current column is at index n_nodes + k
    # We need to add -r_eq to A[n_nodes + k, n_nodes + k]
    A_full[n_nodes + k, n_nodes + k] = -r_eq

    # RHS: e_vec[k] = -r_eq * i_old - v_old
    i_old = float(x_prev[n_nodes + k])
    e_vec[k] = -r_eq * i_old - v_ind_prev


# ---------------------------------------------------------------------------
# Stamping functions — Complex (AC)
# ---------------------------------------------------------------------------


def _stamp_resistor_complex(
    comp: ComponentInstance,
    G: np.ndarray,
    node_idx,
) -> None:
    """Stamp a resistor into the complex conductance matrix."""
    if comp.value <= 0:
        raise SolverError(f"Resistor {comp.id} has non-positive resistance.")

    conductance = complex(1.0 / comp.value)
    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    if p is not None:
        G[p, p] += conductance
    if n_ is not None:
        G[n_, n_] += conductance
    if p is not None and n_ is not None:
        G[p, n_] -= conductance
        G[n_, p] -= conductance


def _stamp_capacitor_ac(
    comp: ComponentInstance,
    G: np.ndarray,
    node_idx,
    omega: float,
) -> None:
    """Stamp capacitor admittance Y = jωC into the complex conductance matrix."""
    if comp.value <= 0:
        raise SolverError(f"Capacitor {comp.id} has non-positive capacitance.")

    admittance = complex(0, omega * comp.value)  # jωC
    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    if p is not None:
        G[p, p] += admittance
    if n_ is not None:
        G[n_, n_] += admittance
    if p is not None and n_ is not None:
        G[p, n_] -= admittance
        G[n_, p] -= admittance


def _stamp_inductor_ac(
    comp: ComponentInstance,
    G: np.ndarray,
    node_idx,
    omega: float,
) -> None:
    """Stamp inductor admittance Y = 1/(jωL) into the complex conductance matrix."""
    if comp.value <= 0:
        raise SolverError(f"Inductor {comp.id} has non-positive inductance.")

    if omega == 0:
        # DC: inductor is short circuit — use very large admittance
        admittance = complex(1e12, 0)
    else:
        admittance = complex(0, -1.0 / (omega * comp.value))  # 1/(jωL) = -j/(ωL)

    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    if p is not None:
        G[p, p] += admittance
    if n_ is not None:
        G[n_, n_] += admittance
    if p is not None and n_ is not None:
        G[p, n_] -= admittance
        G[n_, p] -= admittance


def _stamp_voltage_source_complex(
    comp: ComponentInstance,
    B: np.ndarray,
    C: np.ndarray,
    e_vec: np.ndarray,
    vs_index: dict[str, int],
    node_idx,
) -> None:
    """Stamp a voltage source into complex B, C, e matrices."""
    k = vs_index[comp.id]
    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    if p is not None:
        B[p, k] = complex(1.0)
        C[k, p] = complex(1.0)
    if n_ is not None:
        B[n_, k] = complex(-1.0)
        C[k, n_] = complex(-1.0)

    e_vec[k] = complex(comp.value)


# ---------------------------------------------------------------------------
# Result computation
# ---------------------------------------------------------------------------


def _compute_component_result(
    comp: ComponentInstance,
    node_voltages: dict[str, float],
    x: np.ndarray,
    n: int,
    vs_index: dict[str, int],
) -> ComponentResult:
    """Derive current, power, and voltage drop for a component."""
    v_p = node_voltages.get(comp.pins["p"], 0.0) if comp.pins.get("p") else 0.0
    v_n = node_voltages.get(comp.pins["n"], 0.0) if comp.pins.get("n") else 0.0
    voltage_drop = v_p - v_n

    if comp.component_type == "resistor":
        current = voltage_drop / comp.value if comp.value != 0 else 0.0
        power = voltage_drop * current
    elif comp.component_type in ("voltage_source", "inductor"):
        # Branch current is in the solution vector
        k = vs_index.get(comp.id)
        if k is not None:
            current = float(x[n + k])
        else:
            current = 0.0
        power = voltage_drop * current
    elif comp.component_type == "current_source":
        current = comp.value
        power = voltage_drop * current
    elif comp.component_type == "capacitor":
        # In DC, capacitor current is 0
        current = 0.0
        power = 0.0
    else:
        current = 0.0
        power = 0.0

    return ComponentResult(
        current=current,
        power=abs(power),
        voltage_drop=voltage_drop,
    )
