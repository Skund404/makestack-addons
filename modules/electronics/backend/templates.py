"""Built-in circuit templates for quick-start and education.

Each template is a circuit JSON bundle that can be imported to create
a fully-wired circuit ready for simulation.
"""

from __future__ import annotations

TEMPLATES: dict[str, dict] = {
    "voltage_divider": {
        "name": "Voltage Divider",
        "description": "Simple resistive voltage divider (Vout = Vin × R2/(R1+R2))",
        "category": "basic",
        "circuit": {
            "name": "Voltage Divider",
            "description": "Vin=10V, R1=R2=1kΩ → Vout=5V",
        },
        "components": [
            {"ref": "V1", "type": "voltage_source", "value": "10", "pins": {"p": "VCC", "n": "GND"}},
            {"ref": "R1", "type": "resistor", "value": "1000", "pins": {"p": "VCC", "n": "OUT"}},
            {"ref": "R2", "type": "resistor", "value": "1000", "pins": {"p": "OUT", "n": "GND"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "led_driver": {
        "name": "LED with Current Limiting Resistor",
        "description": "LED driven from 5V with 330Ω resistor (~10mA)",
        "category": "basic",
        "circuit": {
            "name": "LED Driver",
            "description": "5V supply, 330Ω series resistor, red LED",
        },
        "components": [
            {"ref": "V1", "type": "voltage_source", "value": "5", "pins": {"p": "VCC", "n": "GND"}},
            {"ref": "R1", "type": "resistor", "value": "330", "pins": {"p": "VCC", "n": "LED_A"}},
            {"ref": "D1", "type": "led", "value": "0", "pins": {"anode": "LED_A", "cathode": "GND"},
             "params": {"model": "red"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "common_emitter_amp": {
        "name": "Common Emitter Amplifier",
        "description": "NPN BJT (2N3904) common-emitter with bias resistors",
        "category": "amplifier",
        "circuit": {
            "name": "Common Emitter Amplifier",
            "description": "Vcc=12V, Rc=1kΩ, Rb=100kΩ, 2N3904",
        },
        "components": [
            {"ref": "Vcc", "type": "voltage_source", "value": "12", "pins": {"p": "VCC", "n": "GND"}},
            {"ref": "Rc", "type": "resistor", "value": "1000", "pins": {"p": "VCC", "n": "COLLECTOR"}},
            {"ref": "Rb", "type": "resistor", "value": "100000", "pins": {"p": "VCC", "n": "BASE"}},
            {"ref": "Q1", "type": "npn_bjt", "value": "0",
             "pins": {"collector": "COLLECTOR", "base": "BASE", "emitter": "GND"},
             "params": {"model": "2N3904"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "cmos_inverter": {
        "name": "CMOS Inverter",
        "description": "Complementary NMOS/PMOS inverter",
        "category": "digital",
        "circuit": {
            "name": "CMOS Inverter",
            "description": "Vdd=5V, NMOS+PMOS complementary pair",
        },
        "components": [
            {"ref": "Vdd", "type": "voltage_source", "value": "5", "pins": {"p": "VDD", "n": "GND"}},
            {"ref": "Vin", "type": "voltage_source", "value": "5", "pins": {"p": "INPUT", "n": "GND"}},
            {"ref": "Mp", "type": "pmos", "value": "0",
             "pins": {"gate": "INPUT", "drain": "OUTPUT", "source": "VDD"},
             "params": {"Vth": -0.7}},
            {"ref": "Mn", "type": "nmos", "value": "0",
             "pins": {"gate": "INPUT", "drain": "OUTPUT", "source": "GND"},
             "params": {"Vth": 0.7}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "zener_regulator": {
        "name": "Zener Voltage Regulator",
        "description": "5.1V zener regulator from 12V supply",
        "category": "power",
        "circuit": {
            "name": "Zener Regulator",
            "description": "12V in, 5.1V regulated output via 1N4733A",
        },
        "components": [
            {"ref": "Vin", "type": "voltage_source", "value": "12", "pins": {"p": "VIN", "n": "GND"}},
            {"ref": "Rs", "type": "resistor", "value": "680", "pins": {"p": "VIN", "n": "VOUT"}},
            {"ref": "Dz", "type": "zener", "value": "0",
             "pins": {"anode": "GND", "cathode": "VOUT"},
             "params": {"model": "1N4733A"}},
            {"ref": "Rload", "type": "resistor", "value": "1000", "pins": {"p": "VOUT", "n": "GND"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "opamp_inverting": {
        "name": "Inverting Op-Amp Amplifier",
        "description": "Op-amp inverting amplifier with gain = -10",
        "category": "amplifier",
        "circuit": {
            "name": "Inverting Amplifier",
            "description": "Vin=1V, Rin=1kΩ, Rf=10kΩ → Vout=-10V",
        },
        "components": [
            {"ref": "Vin", "type": "voltage_source", "value": "1", "pins": {"p": "VIN", "n": "GND"}},
            {"ref": "Rin", "type": "resistor", "value": "1000", "pins": {"p": "VIN", "n": "INV"}},
            {"ref": "Rf", "type": "resistor", "value": "10000", "pins": {"p": "INV", "n": "VOUT"}},
            {"ref": "U1", "type": "opamp", "value": "0",
             "pins": {"non_inv": "GND", "inv": "INV", "output": "VOUT"}},
            {"ref": "Rload", "type": "resistor", "value": "10000", "pins": {"p": "VOUT", "n": "GND"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "apple1_clock": {
        "name": "Apple 1 Clock Generator",
        "description": "BJT astable multivibrator for clock signal generation",
        "category": "apple1",
        "circuit": {
            "name": "Apple 1 Clock Generator",
            "description": "2N3904 astable multivibrator with timing capacitors",
        },
        "components": [
            {"ref": "Vcc", "type": "voltage_source", "value": "5", "pins": {"p": "VCC", "n": "GND"}},
            {"ref": "Rc1", "type": "resistor", "value": "1000", "pins": {"p": "VCC", "n": "C1"}},
            {"ref": "Rc2", "type": "resistor", "value": "1000", "pins": {"p": "VCC", "n": "C2"}},
            {"ref": "Rb1", "type": "resistor", "value": "10000", "pins": {"p": "VCC", "n": "B1"}},
            {"ref": "Rb2", "type": "resistor", "value": "10000", "pins": {"p": "VCC", "n": "B2"}},
            {"ref": "C1", "type": "capacitor", "value": "0.0000001", "pins": {"p": "C1", "n": "B2"}},
            {"ref": "C2", "type": "capacitor", "value": "0.0000001", "pins": {"p": "C2", "n": "B1"}},
            {"ref": "Q1", "type": "npn_bjt", "value": "0",
             "pins": {"collector": "C1", "base": "B1", "emitter": "GND"},
             "params": {"model": "2N3904"}},
            {"ref": "Q2", "type": "npn_bjt", "value": "0",
             "pins": {"collector": "C2", "base": "B2", "emitter": "GND"},
             "params": {"model": "2N3904"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "apple1_power_supply": {
        "name": "Apple 1 Power Supply (Simplified)",
        "description": "Rectifier + zener regulation for Apple 1 power",
        "category": "apple1",
        "circuit": {
            "name": "Apple 1 Power Supply",
            "description": "Bridge rectifier (4x 1N4001) + filter cap + zener regulation",
        },
        "components": [
            {"ref": "Vac", "type": "voltage_source", "value": "9", "pins": {"p": "AC_IN", "n": "GND"}},
            {"ref": "D1", "type": "diode", "value": "0",
             "pins": {"anode": "AC_IN", "cathode": "RECT_OUT"},
             "params": {"model": "1N4001"}},
            {"ref": "D2", "type": "diode", "value": "0",
             "pins": {"anode": "GND", "cathode": "AC_IN"},
             "params": {"model": "1N4001"}},
            {"ref": "Cfilt", "type": "capacitor", "value": "0.001", "pins": {"p": "RECT_OUT", "n": "GND"}},
            {"ref": "Rs", "type": "resistor", "value": "100", "pins": {"p": "RECT_OUT", "n": "V5"}},
            {"ref": "Dz", "type": "zener", "value": "0",
             "pins": {"anode": "GND", "cathode": "V5"},
             "params": {"model": "1N4733A"}},
            {"ref": "Cout", "type": "capacitor", "value": "0.0001", "pins": {"p": "V5", "n": "GND"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "apple1_reset": {
        "name": "Apple 1 Reset Circuit",
        "description": "RC power-on reset with Schmitt trigger for clean startup",
        "category": "apple1",
        "circuit": {
            "name": "Apple 1 Reset Circuit",
            "description": "RC delay + BJT Schmitt trigger for power-on reset",
        },
        "components": [
            {"ref": "Vcc", "type": "voltage_source", "value": "5", "pins": {"p": "VCC", "n": "GND"}},
            {"ref": "R1", "type": "resistor", "value": "100000", "pins": {"p": "VCC", "n": "RC_NODE"}},
            {"ref": "C1", "type": "capacitor", "value": "0.00001", "pins": {"p": "RC_NODE", "n": "GND"}},
            {"ref": "R2", "type": "resistor", "value": "10000", "pins": {"p": "VCC", "n": "RESET_OUT"}},
            {"ref": "Q1", "type": "npn_bjt", "value": "0",
             "pins": {"collector": "RESET_OUT", "base": "RC_NODE", "emitter": "GND"},
             "params": {"model": "2N3904"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "half_wave_rectifier": {
        "name": "Half-Wave Rectifier",
        "description": "Single diode rectifier with filter capacitor",
        "category": "power",
        "circuit": {
            "name": "Half-Wave Rectifier",
            "description": "1N4001 diode + 100µF filter cap",
        },
        "components": [
            {"ref": "Vac", "type": "voltage_source", "value": "12", "pins": {"p": "AC_IN", "n": "GND"}},
            {"ref": "D1", "type": "diode", "value": "0",
             "pins": {"anode": "AC_IN", "cathode": "DC_OUT"},
             "params": {"model": "1N4001"}},
            {"ref": "C1", "type": "capacitor", "value": "0.0001", "pins": {"p": "DC_OUT", "n": "GND"}},
            {"ref": "Rload", "type": "resistor", "value": "1000", "pins": {"p": "DC_OUT", "n": "GND"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "emitter_follower": {
        "name": "Emitter Follower (Buffer)",
        "description": "NPN emitter follower with unity voltage gain and low output impedance",
        "category": "amplifier",
        "circuit": {
            "name": "Emitter Follower",
            "description": "Vcc=12V, 2N3904 buffer, Vout ≈ Vin - 0.7V",
        },
        "components": [
            {"ref": "Vcc", "type": "voltage_source", "value": "12", "pins": {"p": "VCC", "n": "GND"}},
            {"ref": "Vin", "type": "voltage_source", "value": "5", "pins": {"p": "INPUT", "n": "GND"}},
            {"ref": "Rb", "type": "resistor", "value": "10000", "pins": {"p": "INPUT", "n": "BASE"}},
            {"ref": "Q1", "type": "npn_bjt", "value": "0",
             "pins": {"collector": "VCC", "base": "BASE", "emitter": "VOUT"},
             "params": {"model": "2N3904"}},
            {"ref": "Re", "type": "resistor", "value": "1000", "pins": {"p": "VOUT", "n": "GND"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
    "current_mirror": {
        "name": "BJT Current Mirror",
        "description": "Matched NPN pair current mirror for precise current copying",
        "category": "analog",
        "circuit": {
            "name": "BJT Current Mirror",
            "description": "Two 2N3904, Iref set by 10kΩ, Iout mirrors Iref",
        },
        "components": [
            {"ref": "Vcc", "type": "voltage_source", "value": "10", "pins": {"p": "VCC", "n": "GND"}},
            {"ref": "Rref", "type": "resistor", "value": "10000", "pins": {"p": "VCC", "n": "MIRROR"}},
            {"ref": "Rload", "type": "resistor", "value": "10000", "pins": {"p": "VCC", "n": "IOUT"}},
            {"ref": "Q1", "type": "npn_bjt", "value": "0",
             "pins": {"collector": "MIRROR", "base": "MIRROR", "emitter": "GND"},
             "params": {"model": "2N3904"}},
            {"ref": "Q2", "type": "npn_bjt", "value": "0",
             "pins": {"collector": "IOUT", "base": "MIRROR", "emitter": "GND"},
             "params": {"model": "2N3904"}},
            {"ref": "GND1", "type": "ground", "value": "", "pins": {"gnd": "GND"}},
        ],
    },
}


def list_templates() -> list[dict]:
    """Return list of available templates (summary only)."""
    return [
        {
            "id": tid,
            "name": t["name"],
            "description": t["description"],
            "category": t["category"],
            "component_count": len(t.get("components", [])),
        }
        for tid, t in TEMPLATES.items()
    ]


def get_template(template_id: str) -> dict | None:
    """Get a specific template definition."""
    return TEMPLATES.get(template_id)
