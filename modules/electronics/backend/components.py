"""Component type registry for the electronics simulator.

Defines the behavior, pin layout, and defaults for each component type
that the solver and frontend know about. This is the built-in library —
catalogue entries extend it with SPICE models and educational content.
"""

from __future__ import annotations

COMPONENT_TYPES: dict[str, dict] = {
    "resistor": {
        "label": "Resistor",
        "pins": ["p", "n"],
        "value_unit": "ohm",
        "value_label": "Resistance",
        "default_value": "1000",
        "prefix": "R",
        "symbol": "resistor",
        "description": "Two-terminal passive component that opposes current flow. Voltage = Current x Resistance (Ohm's law).",
    },
    "capacitor": {
        "label": "Capacitor",
        "pins": ["p", "n"],
        "value_unit": "F",
        "value_label": "Capacitance",
        "default_value": "100n",
        "prefix": "C",
        "symbol": "capacitor",
        "description": "Stores energy in an electric field. Opposes changes in voltage. Impedance decreases with frequency: Z = 1/(jωC).",
    },
    "inductor": {
        "label": "Inductor",
        "pins": ["p", "n"],
        "value_unit": "H",
        "value_label": "Inductance",
        "default_value": "1m",
        "prefix": "L",
        "symbol": "inductor",
        "description": "Stores energy in a magnetic field. Opposes changes in current. Impedance increases with frequency: Z = jωL.",
    },
    "voltage_source": {
        "label": "Voltage Source",
        "pins": ["p", "n"],
        "value_unit": "V",
        "value_label": "Voltage",
        "default_value": "5",
        "prefix": "V",
        "symbol": "voltage_source",
        "description": "Maintains a constant voltage difference between its terminals regardless of current.",
    },
    "current_source": {
        "label": "Current Source",
        "pins": ["p", "n"],
        "value_unit": "A",
        "value_label": "Current",
        "default_value": "0.001",
        "prefix": "I",
        "symbol": "current_source",
        "description": "Maintains a constant current through its terminals regardless of voltage.",
    },
    "ground": {
        "label": "Ground",
        "pins": ["gnd"],
        "value_unit": "",
        "value_label": "",
        "default_value": "0",
        "prefix": "GND",
        "symbol": "ground",
        "description": "Reference node. All voltages are measured relative to ground (0V).",
    },
}


def get_component_type(component_type: str) -> dict | None:
    """Return component type definition or None if unknown."""
    return COMPONENT_TYPES.get(component_type)


def get_ref_prefix(component_type: str) -> str:
    """Return the ref designator prefix for a component type."""
    ct = COMPONENT_TYPES.get(component_type)
    return ct["prefix"] if ct else component_type.upper()[:3]


def get_pins(component_type: str) -> list[str]:
    """Return the pin names for a component type."""
    ct = COMPONENT_TYPES.get(component_type)
    return ct["pins"] if ct else []


def validate_component_type(component_type: str) -> bool:
    """Check if a component type is known."""
    return component_type in COMPONENT_TYPES
