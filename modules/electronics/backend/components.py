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
    # --- Nonlinear components (E3) ---
    "diode": {
        "label": "Diode",
        "pins": ["anode", "cathode"],
        "value_unit": "",
        "value_label": "Model",
        "default_value": "0",
        "prefix": "D",
        "symbol": "diode",
        "description": "PN junction diode. Current flows from anode to cathode when forward biased (V > ~0.7V). Blocks reverse current.",
        "model_params": {"Is": 1e-14, "N": 1.0, "Bv": 100.0, "Ibv": 1e-3, "Rs": 0.0},
        "presets": ["1N4148", "1N4001", "1N4002", "1N4007", "1N5817", "1N5819"],
    },
    "zener": {
        "label": "Zener Diode",
        "pins": ["anode", "cathode"],
        "value_unit": "V",
        "value_label": "Zener Voltage",
        "default_value": "5.1",
        "prefix": "DZ",
        "symbol": "zener",
        "description": "Zener diode. Conducts in reverse at the breakdown voltage (Vz), used for voltage regulation.",
        "model_params": {"Is": 1e-13, "N": 1.0, "Bv": 5.1, "Ibv": 1e-3},
        "presets": ["1N4733A", "1N4734A", "1N4742A", "1N4744A", "BZX55C3V3"],
    },
    "led": {
        "label": "LED",
        "pins": ["anode", "cathode"],
        "value_unit": "",
        "value_label": "Color",
        "default_value": "0",
        "prefix": "LED",
        "symbol": "led",
        "description": "Light-emitting diode. Higher forward voltage than standard diodes (~1.8-3.3V depending on color).",
        "model_params": {"Is": 1e-20, "N": 2.0, "Bv": 5.0},
        "presets": ["red", "green", "blue", "white"],
    },
    "npn_bjt": {
        "label": "NPN BJT",
        "pins": ["collector", "base", "emitter"],
        "value_unit": "",
        "value_label": "Model",
        "default_value": "0",
        "prefix": "Q",
        "symbol": "npn_bjt",
        "description": "NPN bipolar junction transistor. Current flows collector→emitter when base-emitter is forward biased. Ic ≈ β × Ib.",
        "model_params": {"Bf": 100.0, "Br": 1.0, "Is": 1e-15, "Nf": 1.0, "Nr": 1.0, "Vaf": 100.0},
        "presets": ["2N3904", "2N2222", "BC547"],
    },
    "pnp_bjt": {
        "label": "PNP BJT",
        "pins": ["collector", "base", "emitter"],
        "value_unit": "",
        "value_label": "Model",
        "default_value": "0",
        "prefix": "Q",
        "symbol": "pnp_bjt",
        "description": "PNP bipolar junction transistor. Complementary to NPN — current flows emitter→collector when base-emitter is reverse biased.",
        "model_params": {"Bf": 100.0, "Br": 1.0, "Is": 1e-15, "Nf": 1.0, "Nr": 1.0, "Vaf": 100.0},
        "presets": ["2N3906", "BC557"],
    },
    "nmos": {
        "label": "NMOS FET",
        "pins": ["gate", "drain", "source"],
        "value_unit": "",
        "value_label": "Model",
        "default_value": "0",
        "prefix": "M",
        "symbol": "nmos",
        "description": "N-channel MOSFET. Conducts drain→source when Vgs > Vth. Gate draws no DC current.",
        "model_params": {"Kp": 110e-6, "Vth": 0.7, "Lambda": 0.04, "W": 10e-6, "L": 1e-6},
        "presets": ["2N7000", "BS170", "IRF510"],
    },
    "pmos": {
        "label": "PMOS FET",
        "pins": ["gate", "drain", "source"],
        "value_unit": "",
        "value_label": "Model",
        "default_value": "0",
        "prefix": "M",
        "symbol": "pmos",
        "description": "P-channel MOSFET. Complementary to NMOS — conducts when Vgs < Vth (negative threshold).",
        "model_params": {"Kp": 110e-6, "Vth": -0.7, "Lambda": 0.04, "W": 10e-6, "L": 1e-6},
        "presets": ["IRF9510"],
    },
    "opamp": {
        "label": "Op-Amp",
        "pins": ["non_inv", "inv", "output"],
        "value_unit": "",
        "value_label": "",
        "default_value": "0",
        "prefix": "U",
        "symbol": "opamp",
        "description": "Ideal operational amplifier. Infinite open-loop gain forces V+ = V-. Zero input current, zero output impedance.",
        "model_params": {},
        "presets": [],
    },
    "mcu": {
        "label": "Microcontroller",
        "pins": ["GPIO0", "GPIO1", "GPIO2", "GPIO3", "GPIO4", "GPIO5", "GPIO6", "GPIO7"],
        "value_unit": "",
        "value_label": "Pins",
        "default_value": "0",
        "prefix": "MCU",
        "symbol": "mcu",
        "description": "Microcontroller with configurable GPIO pins. Runs a Python tick function at each simulation timestep for co-simulation.",
        "model_params": {"num_pins": 8, "vcc": 5.0},
        "presets": [],
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
