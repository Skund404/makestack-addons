"""Modified Nodal Analysis (MNA) DC solver for linear circuits.

Builds the system Ax = z and solves for node voltages and voltage source
branch currents using NumPy. No external simulation engine required.

Matrix structure:
    A = | G   B |     x = | v |     z = | i |
        | C   D |         | j |         | e |

Where:
    G (n x n) = conductance matrix
    B (n x m) = voltage source incidence
    C (m x n) = transpose of B
    D (m x m) = zero (independent sources)
    v = node voltages (unknowns)
    j = voltage source branch currents (unknowns)
    i = current source injections (known)
    e = voltage source values (known)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ComponentInstance:
    """A placed component in a circuit, ready for the solver."""

    id: str
    component_type: str  # "resistor", "voltage_source", "current_source", "ground"
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


class SolverError(Exception):
    """Raised when the circuit cannot be solved."""


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


def solve_dc_op(graph: CircuitGraph) -> SolverResult:
    """Solve DC operating point using Modified Nodal Analysis.

    Args:
        graph: Circuit topology with components and net connections.

    Returns:
        SolverResult with node voltages and component currents/power.

    Raises:
        SolverError: If the circuit is invalid or the matrix is singular.
    """
    # --- Validate ---
    if graph.ground_net_id is None:
        raise SolverError(
            "No ground node defined. Every circuit needs a ground reference. "
            "Place a ground component and connect it to a net."
        )

    # Filter to components that participate in simulation (not ground symbols)
    active_components = [
        c for c in graph.components if c.component_type != "ground"
    ]

    if not active_components:
        raise SolverError(
            "Circuit has no active components. "
            "Add resistors, voltage sources, or current sources."
        )

    # Check for unconnected pins
    for comp in active_components:
        for pin_name, net_id in comp.pins.items():
            if net_id is None:
                raise SolverError(
                    f"Component {comp.id} has unconnected pin '{pin_name}'. "
                    f"Connect all pins before simulating."
                )

    # --- Build node index ---
    # Map each non-ground net to a matrix row/column index
    node_index: dict[str, int] = {}
    for i, net_id in enumerate(graph.nodes):
        if net_id != graph.ground_net_id:
            node_index[net_id] = len(node_index)

    n = len(node_index)  # number of non-ground nodes

    # Count voltage sources for the expanded MNA matrix
    voltage_sources = [
        c for c in active_components if c.component_type == "voltage_source"
    ]
    m = len(voltage_sources)
    vs_index: dict[str, int] = {}
    for k, vs in enumerate(voltage_sources):
        vs_index[vs.id] = k

    size = n + m
    if size == 0:
        raise SolverError(
            "Circuit has no nodes to solve. "
            "Connect components to form a circuit."
        )

    # --- Build matrices ---
    A = np.zeros((size, size), dtype=float)
    z = np.zeros(size, dtype=float)

    # Sub-matrix views
    G = A[:n, :n]
    B = A[:n, n:]
    C = A[n:, :n]
    # D = A[n:, n:]  # stays zero for independent sources
    i_vec = z[:n]
    e_vec = z[n:]

    def _node_idx(net_id: str) -> int | None:
        """Return matrix index for a net, or None if ground."""
        if net_id == graph.ground_net_id:
            return None
        return node_index.get(net_id)

    # --- Stamp components ---
    for comp in active_components:
        if comp.component_type == "resistor":
            _stamp_resistor(comp, G, _node_idx)
        elif comp.component_type == "voltage_source":
            _stamp_voltage_source(comp, B, C, e_vec, vs_index, _node_idx)
        elif comp.component_type == "current_source":
            _stamp_current_source(comp, i_vec, _node_idx)

    # --- Solve ---
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

    # --- Extract results ---
    node_voltages: dict[str, float] = {}
    for net_id, idx in node_index.items():
        node_voltages[net_id] = float(x[idx])
    # Ground is always 0V
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
# Stamping functions
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
    k = vs_index[comp.id]
    p = node_idx(comp.pins["p"])
    n_ = node_idx(comp.pins["n"])

    if p is not None:
        B[p, k] = 1.0
        C[k, p] = 1.0
    if n_ is not None:
        B[n_, k] = -1.0
        C[k, n_] = -1.0

    e_vec[k] = comp.value


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
    elif comp.component_type == "voltage_source":
        # Branch current is in the solution vector
        k = vs_index[comp.id]
        current = float(x[n + k])
        power = voltage_drop * current
    elif comp.component_type == "current_source":
        current = comp.value
        power = voltage_drop * current
    else:
        current = 0.0
        power = 0.0

    return ComponentResult(
        current=current,
        power=abs(power),
        voltage_drop=voltage_drop,
    )
