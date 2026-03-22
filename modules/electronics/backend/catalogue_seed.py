"""Catalogue seed data — pushes built-in component presets to Core as Material primitives.

Each preset (1N4148, 2N3904, etc.) becomes a Material primitive in the catalogue
with SPICE parameters stored in properties.spice_params. The catalogue_path
convention is: materials/electronics-{type}-{slug} (e.g., materials/electronics-diode-1n4148).

This module is pure functions — no side effects until seed_catalogue() is called.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import asdict


def _load_device_models():
    """Load device_models.py from the same directory."""
    key = "_electronics_backend_device_models"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_models.py")
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


# Component type metadata for catalogue entries
_TYPE_INFO = {
    "diode": {
        "description": "Silicon PN junction diode",
        "tags": ["electronics", "diode", "semiconductor"],
    },
    "zener": {
        "description": "Zener voltage regulator diode",
        "tags": ["electronics", "zener", "diode", "semiconductor", "regulator"],
    },
    "led": {
        "description": "Light-emitting diode",
        "tags": ["electronics", "led", "diode", "semiconductor"],
    },
    "npn_bjt": {
        "description": "NPN bipolar junction transistor",
        "tags": ["electronics", "bjt", "npn", "transistor"],
    },
    "pnp_bjt": {
        "description": "PNP bipolar junction transistor",
        "tags": ["electronics", "bjt", "pnp", "transistor"],
    },
    "nmos": {
        "description": "N-channel MOSFET",
        "tags": ["electronics", "mosfet", "nmos", "transistor"],
    },
    "pmos": {
        "description": "P-channel MOSFET",
        "tags": ["electronics", "mosfet", "pmos", "transistor"],
    },
}


def build_seed_entries() -> list[dict]:
    """Build a list of catalogue entry payloads from built-in presets.

    Returns a list of dicts with keys: name, component_type, spice_params, description, tags.
    """
    dm = _load_device_models()
    entries = []

    # Diodes
    for name, model in dm.DIODE_PRESETS.items():
        if name == "default":
            continue
        entries.append({
            "name": name,
            "component_type": "diode",
            "spice_params": asdict(model),
            **_TYPE_INFO["diode"],
        })

    # Zeners
    for name, model in dm.ZENER_PRESETS.items():
        if name == "default":
            continue
        entries.append({
            "name": name,
            "component_type": "zener",
            "spice_params": asdict(model),
            **_TYPE_INFO["zener"],
        })

    # LEDs
    for name, model in dm.LED_PRESETS.items():
        if name == "default":
            continue
        entries.append({
            "name": name,
            "component_type": "led",
            "spice_params": asdict(model),
            **_TYPE_INFO["led"],
        })

    # BJTs
    for name, (model, is_pnp) in dm.BJT_PRESETS.items():
        if name.startswith("default"):
            continue
        comp_type = "pnp_bjt" if is_pnp else "npn_bjt"
        entries.append({
            "name": name,
            "component_type": comp_type,
            "spice_params": asdict(model),
            **_TYPE_INFO[comp_type],
        })

    # MOSFETs
    for name, (model, is_pmos) in dm.MOSFET_PRESETS.items():
        if name.startswith("default"):
            continue
        comp_type = "pmos" if is_pmos else "nmos"
        entries.append({
            "name": name,
            "component_type": comp_type,
            "spice_params": asdict(model),
            **_TYPE_INFO[comp_type],
        })

    return entries


def catalogue_path_for(component_type: str, name: str) -> str:
    """Generate the expected catalogue path for a component model.

    Convention: materials/electronics-{type}-{slug}
    where slug is the lowercased name with unsafe chars replaced.
    """
    slug = name.lower().replace(" ", "-").replace("/", "-")
    type_slug = component_type.replace("_", "-")
    return f"materials/electronics-{type_slug}-{slug}"


async def seed_catalogue(catalogue) -> dict:
    """Push all built-in presets to the catalogue.

    Skips entries that already exist (create_primitive raises on duplicate path).
    Returns {seeded: int, skipped: int, errors: list[str]}.
    """
    from backend.app.models import PrimitiveCreate

    entries = build_seed_entries()
    seeded = 0
    skipped = 0
    errors = []

    for entry in entries:
        try:
            await catalogue.create_primitive(PrimitiveCreate(
                type="material",
                name=entry["name"],
                description=f'{entry["description"]}: {entry["name"]}',
                tags=entry["tags"],
                domain="electronics",
                properties={
                    "component_type": entry["component_type"],
                    "spice_params": entry["spice_params"],
                },
            ))
            seeded += 1
        except Exception as exc:
            exc_str = str(exc)
            # Skip duplicates (already exists)
            if "already exists" in exc_str.lower() or "409" in exc_str or "conflict" in exc_str.lower():
                skipped += 1
            else:
                errors.append(f'{entry["name"]}: {exc_str}')

    return {"seeded": seeded, "skipped": skipped, "errors": errors}
