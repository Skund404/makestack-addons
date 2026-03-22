"""Engineering value parser for electronics component values.

Converts human-readable SI-prefixed strings to canonical floats:
    "1k"   → 1000.0
    "4.7µ" → 4.7e-6
    "100n" → 1e-7
    "2.2M" → 2.2e6
    "10"   → 10.0
    "1e3"  → 1000.0
"""

from __future__ import annotations

import re

# SI prefix multipliers
_SI_PREFIXES: dict[str, float] = {
    "T": 1e12,
    "G": 1e9,
    "M": 1e6,
    "meg": 1e6,   # SPICE convention
    "k": 1e3,
    "K": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,
    "\u03bc": 1e-6,  # Greek mu
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}

# Pattern: optional sign, digits (with optional decimal), optional SI prefix, optional unit suffix
_PATTERN = re.compile(
    r"^\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*"  # numeric part
    r"(meg|[TGMkKmuµnpf])?"                        # optional SI prefix
    r"\s*[A-Za-zΩ]*\s*$"                            # optional unit suffix (ohm, V, A, F, H, etc.)
)


def parse_engineering_value(s: str) -> float | None:
    """Parse an engineering notation string to a float.

    Returns None if the string cannot be parsed.

    Examples:
        >>> parse_engineering_value("1k")
        1000.0
        >>> parse_engineering_value("4.7µF")
        4.7e-06
        >>> parse_engineering_value("100nH")
        1e-07
        >>> parse_engineering_value("2.2M")
        2200000.0
        >>> parse_engineering_value("hello")
        None
    """
    if not s or not isinstance(s, str):
        return None

    s = s.strip()
    if not s:
        return None

    # Try plain float first (handles "10", "1e3", "3.14", etc.)
    try:
        return float(s)
    except ValueError:
        pass

    # Try SI prefix pattern
    match = _PATTERN.match(s)
    if not match:
        return None

    number_str = match.group(1)
    prefix = match.group(2)

    try:
        value = float(number_str)
    except ValueError:
        return None

    if prefix and prefix in _SI_PREFIXES:
        value *= _SI_PREFIXES[prefix]

    return value


def format_engineering_value(value: float, unit: str = "") -> str:
    """Format a float as a human-readable engineering string.

    Examples:
        >>> format_engineering_value(1000.0, "ohm")
        '1kΩ'
        >>> format_engineering_value(0.0000047, "F")
        '4.7µF'
    """
    unit_display = "Ω" if unit == "ohm" else unit

    abs_val = abs(value)
    sign = "-" if value < 0 else ""

    if abs_val == 0:
        return f"0{unit_display}"
    elif abs_val >= 1e12:
        return f"{sign}{abs_val / 1e12:.3g}T{unit_display}"
    elif abs_val >= 1e9:
        return f"{sign}{abs_val / 1e9:.3g}G{unit_display}"
    elif abs_val >= 1e6:
        return f"{sign}{abs_val / 1e6:.3g}M{unit_display}"
    elif abs_val >= 1e3:
        return f"{sign}{abs_val / 1e3:.3g}k{unit_display}"
    elif abs_val >= 1:
        return f"{sign}{abs_val:.3g}{unit_display}"
    elif abs_val >= 1e-3:
        return f"{sign}{abs_val * 1e3:.3g}m{unit_display}"
    elif abs_val >= 1e-6:
        return f"{sign}{abs_val * 1e6:.3g}µ{unit_display}"
    elif abs_val >= 1e-9:
        return f"{sign}{abs_val * 1e9:.3g}n{unit_display}"
    elif abs_val >= 1e-12:
        return f"{sign}{abs_val * 1e12:.3g}p{unit_display}"
    else:
        return f"{sign}{abs_val:.3g}{unit_display}"
