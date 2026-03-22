"""Export functions — SPICE netlist, BOM, waveform CSV, circuit JSON bundle.

These are pure functions that operate on solver data structures and/or
raw database rows, with no side effects.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# SPICE Netlist Export
# ---------------------------------------------------------------------------

# Map component types to SPICE element letters
_SPICE_PREFIX = {
    "resistor": "R",
    "capacitor": "C",
    "inductor": "L",
    "voltage_source": "V",
    "current_source": "I",
    "diode": "D",
    "zener": "D",
    "led": "D",
    "npn_bjt": "Q",
    "pnp_bjt": "Q",
    "nmos": "M",
    "pmos": "M",
    "opamp": "X",
}

# Map component types to SPICE value units
_SPICE_UNIT = {
    "resistor": "",
    "capacitor": "",
    "inductor": "",
    "voltage_source": "",
    "current_source": "",
}


def export_spice(components: list[dict], nets: list[dict], pins: list[dict],
                 circuit_name: str = "circuit") -> str:
    """Generate a SPICE .cir netlist from circuit data.

    Args:
        components: list of component dicts from DB
        nets: list of net dicts from DB
        pins: list of pin dicts from DB (with net_id)
        circuit_name: title line
    Returns:
        SPICE netlist as string
    """
    lines = [f"* {circuit_name}", "*"]

    # Build net name map: net_id -> net_name (use "0" for ground)
    net_names: dict[str, str] = {}
    for net in nets:
        if net["net_type"] == "ground":
            net_names[net["id"]] = "0"
        else:
            net_names[net["id"]] = net["name"]

    # Build pin lookup: component_id -> {pin_name: net_name}
    pin_map: dict[str, dict[str, str]] = {}
    for pin in pins:
        cid = pin["component_id"]
        if cid not in pin_map:
            pin_map[cid] = {}
        net_id = pin.get("net_id")
        if net_id and net_id in net_names:
            pin_map[cid][pin["pin_name"]] = net_names[net_id]
        else:
            pin_map[cid][pin["pin_name"]] = "NC"

    # Track which .model cards we need
    model_cards: list[str] = []
    model_names_seen: set[str] = set()

    for comp in components:
        ctype = comp["component_type"]
        prefix = _SPICE_PREFIX.get(ctype)
        if not prefix or ctype == "ground":
            continue

        ref = comp.get("ref_designator", comp["id"])
        comp_pins = pin_map.get(comp["id"], {})

        props = {}
        props_str = comp.get("properties", "{}")
        if props_str:
            try:
                props = json.loads(props_str)
            except (ValueError, TypeError):
                pass

        if ctype == "resistor":
            p = comp_pins.get("p", "NC")
            n = comp_pins.get("n", "NC")
            lines.append(f"R{ref} {p} {n} {comp['value'] or '0'}")

        elif ctype == "capacitor":
            p = comp_pins.get("p", "NC")
            n = comp_pins.get("n", "NC")
            lines.append(f"C{ref} {p} {n} {comp['value'] or '0'}")

        elif ctype == "inductor":
            p = comp_pins.get("p", "NC")
            n = comp_pins.get("n", "NC")
            lines.append(f"L{ref} {p} {n} {comp['value'] or '0'}")

        elif ctype == "voltage_source":
            p = comp_pins.get("p", "NC")
            n = comp_pins.get("n", "NC")
            lines.append(f"V{ref} {p} {n} DC {comp['value'] or '0'}")

        elif ctype == "current_source":
            p = comp_pins.get("p", "NC")
            n = comp_pins.get("n", "NC")
            lines.append(f"I{ref} {p} {n} DC {comp['value'] or '0'}")

        elif ctype in ("diode", "zener", "led"):
            a = comp_pins.get("anode", "NC")
            c = comp_pins.get("cathode", "NC")
            model_name = props.get("model", f"D_{ctype}")
            lines.append(f"D{ref} {a} {c} {model_name}")
            if model_name not in model_names_seen:
                model_names_seen.add(model_name)
                model_cards.append(f".model {model_name} D")

        elif ctype in ("npn_bjt", "pnp_bjt"):
            c = comp_pins.get("collector", "NC")
            b = comp_pins.get("base", "NC")
            e = comp_pins.get("emitter", "NC")
            model_name = props.get("model", f"Q_{ctype}")
            polarity = "NPN" if ctype == "npn_bjt" else "PNP"
            lines.append(f"Q{ref} {c} {b} {e} {model_name}")
            if model_name not in model_names_seen:
                model_names_seen.add(model_name)
                model_cards.append(f".model {model_name} {polarity}")

        elif ctype in ("nmos", "pmos"):
            d = comp_pins.get("drain", "NC")
            g = comp_pins.get("gate", "NC")
            s = comp_pins.get("source", "NC")
            model_name = props.get("model", f"M_{ctype}")
            polarity = "NMOS" if ctype == "nmos" else "PMOS"
            lines.append(f"M{ref} {d} {g} {s} {s} {model_name}")
            if model_name not in model_names_seen:
                model_names_seen.add(model_name)
                model_cards.append(f".model {model_name} {polarity}")

        elif ctype == "opamp":
            ni = comp_pins.get("non_inv", "NC")
            inv = comp_pins.get("inv", "NC")
            out = comp_pins.get("output", "NC")
            lines.append(f"X{ref} {ni} {inv} {out} OPAMP")

    if model_cards:
        lines.append("*")
        lines.extend(model_cards)

    lines.append("*")
    lines.append(".op")
    lines.append(".end")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BOM Export
# ---------------------------------------------------------------------------


def export_bom(components: list[dict]) -> list[dict]:
    """Generate a Bill of Materials from component data.

    Groups identical components (same type + value) and counts quantities.
    Returns list of BOM entries sorted by ref designator.
    """
    groups: dict[str, dict] = {}

    for comp in components:
        ctype = comp["component_type"]
        if ctype == "ground":
            continue

        value = comp.get("value", "")
        unit = comp.get("unit", "")
        key = f"{ctype}:{value}:{unit}"

        if key not in groups:
            props = {}
            props_str = comp.get("properties", "{}")
            if props_str:
                try:
                    props = json.loads(props_str)
                except (ValueError, TypeError):
                    pass

            groups[key] = {
                "component_type": ctype,
                "value": value,
                "unit": unit,
                "model": props.get("model", ""),
                "quantity": 0,
                "ref_designators": [],
            }

        groups[key]["quantity"] += 1
        ref = comp.get("ref_designator", comp["id"])
        groups[key]["ref_designators"].append(ref)

    items = sorted(groups.values(), key=lambda x: (x["component_type"], x["value"]))
    return items


def export_bom_csv(bom: list[dict]) -> str:
    """Convert BOM entries to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ref", "Type", "Value", "Unit", "Model", "Qty"])
    for entry in bom:
        writer.writerow([
            ", ".join(entry["ref_designators"]),
            entry["component_type"],
            entry["value"],
            entry["unit"],
            entry["model"],
            entry["quantity"],
        ])
    return output.getvalue()


# ---------------------------------------------------------------------------
# Waveform CSV Export
# ---------------------------------------------------------------------------


def export_waveform_csv(sweep_data: list[dict]) -> str:
    """Export sweep/transient data as CSV.

    Each row is a sweep point with parameter_value and node voltages.
    """
    if not sweep_data:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)

    # Collect all node IDs from first point
    first = sweep_data[0]
    node_ids = sorted(first.get("node_voltages", {}).keys())
    comp_ids = sorted(first.get("component_results", {}).keys())

    header = ["parameter_value"]
    header.extend([f"V({nid})" for nid in node_ids])
    header.extend([f"I({cid})" for cid in comp_ids])
    writer.writerow(header)

    for point in sweep_data:
        row = [point.get("parameter_value", "")]
        for nid in node_ids:
            v = point.get("node_voltages", {}).get(nid, "")
            if isinstance(v, dict):
                v = v.get("magnitude", v.get("real", ""))
            row.append(v)
        for cid in comp_ids:
            cr = point.get("component_results", {}).get(cid, {})
            row.append(cr.get("current", "") if isinstance(cr, dict) else "")
        writer.writerow(row)

    return output.getvalue()


# ---------------------------------------------------------------------------
# Circuit JSON Bundle (import/export)
# ---------------------------------------------------------------------------


def export_circuit_bundle(circuit: dict, components: list[dict],
                         nets: list[dict], pins: list[dict],
                         wire_segments: list[dict] = None,
                         subcircuit_instances: list[dict] = None) -> dict:
    """Create a JSON bundle for circuit export/import."""
    return {
        "format": "electronics_circuit_v1",
        "circuit": {
            "name": circuit.get("name", ""),
            "description": circuit.get("description", ""),
            "canvas_width": circuit.get("canvas_width", 1200),
            "canvas_height": circuit.get("canvas_height", 800),
        },
        "components": [
            {
                "ref_designator": c.get("ref_designator", ""),
                "component_type": c["component_type"],
                "value": c.get("value", ""),
                "unit": c.get("unit", ""),
                "x": c.get("x", 0),
                "y": c.get("y", 0),
                "rotation": c.get("rotation", 0),
                "properties": c.get("properties", "{}"),
            }
            for c in components
        ],
        "nets": [
            {
                "name": n["name"],
                "net_type": n.get("net_type", "signal"),
            }
            for n in nets
        ],
        "connections": [
            {
                "component_ref": _find_ref(p["component_id"], components),
                "pin_name": p["pin_name"],
                "net_name": _find_net_name(p.get("net_id"), nets),
            }
            for p in pins
            if p.get("net_id")
        ],
        "wire_segments": [
            {
                "net_name": _find_net_name(w.get("net_id"), nets),
                "x1": w["x1"], "y1": w["y1"],
                "x2": w["x2"], "y2": w["y2"],
            }
            for w in (wire_segments or [])
        ],
    }


def _find_ref(comp_id: str, components: list[dict]) -> str:
    for c in components:
        if c["id"] == comp_id:
            return c.get("ref_designator", c["id"])
    return comp_id


def _find_net_name(net_id: str | None, nets: list[dict]) -> str:
    if not net_id:
        return ""
    for n in nets:
        if n["id"] == net_id:
            return n["name"]
    return ""
