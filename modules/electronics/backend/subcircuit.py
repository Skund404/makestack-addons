"""Subcircuit support — define reusable circuit blocks and flatten into parent circuits.

Subcircuits enable abstraction of complex circuit blocks (e.g., 7400 NAND gate
as a few BJTs + resistors, 555 timer internals, etc.) into single components
that can be instantiated multiple times in a parent circuit.

At solve time, subcircuit instances are flattened: their internal components
are merged into the parent circuit graph with nets remapped to avoid collisions.
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field


@dataclass
class SubcircuitDef:
    """A reusable subcircuit definition."""

    id: str
    name: str
    description: str
    port_pins: list[str]  # external interface pin names
    # Internal circuit as serialized JSON:
    # {"components": [...], "internal_nets": [...], "connections": [...]}
    circuit_json: dict = field(default_factory=dict)


@dataclass
class SubcircuitInstance:
    """A placed instance of a subcircuit in a parent circuit."""

    id: str
    subcircuit_id: str
    # Mapping: port_pin_name -> parent_net_id
    port_mapping: dict[str, str] = field(default_factory=dict)


def flatten_subcircuit(
    instance: SubcircuitInstance,
    definition: SubcircuitDef,
    solver_module,
) -> tuple[list, list[str]]:
    """Flatten a subcircuit instance into component instances + internal net IDs.

    Returns:
        (components, internal_net_ids) — components to add to the parent graph,
        and any new internal net IDs that need to be added to the node list.
    """
    ComponentInstance = solver_module.ComponentInstance

    prefix = f"_sub_{instance.id}_"
    circuit = definition.circuit_json

    internal_components = circuit.get("components", [])
    internal_nets = circuit.get("internal_nets", [])
    connections = circuit.get("connections", [])

    # Build a net remapping: internal net → parent net
    # Port pins map to parent nets; internal-only nets get prefixed unique IDs
    net_remap: dict[str, str] = {}

    # Map port nets to parent nets
    port_nets = circuit.get("port_nets", {})  # {port_pin_name: internal_net_id}
    for port_name, internal_net in port_nets.items():
        if port_name in instance.port_mapping:
            net_remap[internal_net] = instance.port_mapping[port_name]

    # Internal-only nets get unique IDs
    new_net_ids = []
    for net_id in internal_nets:
        if net_id not in net_remap:
            new_id = f"{prefix}{net_id}"
            net_remap[net_id] = new_id
            new_net_ids.append(new_id)

    # Build flattened components
    flattened = []
    for comp_data in internal_components:
        # Remap pin connections
        pins = {}
        for pin_name, net_id in comp_data.get("pins", {}).items():
            pins[pin_name] = net_remap.get(net_id, net_id)

        flattened.append(ComponentInstance(
            id=f"{prefix}{comp_data['id']}",
            component_type=comp_data["component_type"],
            value=comp_data.get("value", 0.0),
            pins=pins,
            params=comp_data.get("params", {}),
        ))

    return flattened, new_net_ids


def flatten_all_subcircuits(
    graph,
    instances: list[SubcircuitInstance],
    definitions: dict[str, SubcircuitDef],
    solver_module,
) -> object:
    """Flatten all subcircuit instances into a parent CircuitGraph.

    Returns a new CircuitGraph with subcircuit internals merged in.
    """
    CircuitGraph = solver_module.CircuitGraph

    all_components = list(graph.components)
    all_nodes = list(graph.nodes)

    for inst in instances:
        defn = definitions.get(inst.subcircuit_id)
        if defn is None:
            continue
        new_comps, new_nets = flatten_subcircuit(inst, defn, solver_module)
        all_components.extend(new_comps)
        all_nodes.extend(new_nets)

    return CircuitGraph(
        ground_net_id=graph.ground_net_id,
        nodes=all_nodes,
        components=all_components,
    )
