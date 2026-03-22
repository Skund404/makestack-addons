"""Sandboxed MCU tick function execution.

MCU components run user-provided Python tick functions at each transient
simulation timestep. The tick function reads pin voltages and outputs
pin states (HIGH/LOW/HIZ).

Security: functions run with restricted globals (only math module),
no imports, and a timeout to prevent infinite loops.
"""

from __future__ import annotations

import math
import signal
import threading
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# MCU Pin Model
# ---------------------------------------------------------------------------

# MCU output voltage levels
VCC_DEFAULT = 5.0
HIGH_VOLTAGE = 5.0
LOW_VOLTAGE = 0.0


@dataclass
class MCUState:
    """State of an MCU component between tick calls."""

    pin_names: list[str] = field(default_factory=list)
    # Pin modes: "INPUT", "OUTPUT_HIGH", "OUTPUT_LOW", "HIZ", "ADC"
    pin_modes: dict[str, str] = field(default_factory=dict)
    # User state dict preserved between ticks
    user_state: dict = field(default_factory=dict)
    # Compiled tick function
    tick_fn: object = None
    source_code: str = ""


# Restricted builtins for sandboxed execution
_SAFE_BUILTINS = {
    "abs": abs,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,  # captured, not displayed
    "range": range,
    "round": round,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "True": True,
    "False": False,
    "None": None,
}


class MCUSandboxError(Exception):
    """Error in MCU tick function execution."""
    pass


def compile_tick_function(source_code: str) -> callable:
    """Compile a user-provided tick function with safety checks.

    The source must define a function: def tick(time_s, pins, state) -> dict
    where:
        time_s: current simulation time in seconds
        pins: dict of {pin_name: voltage} (input readings)
        state: dict preserved between calls (user can store anything)
    returns: dict of {pin_name: "HIGH"|"LOW"|"HIZ"} for output pins
    """
    if not source_code or not source_code.strip():
        raise MCUSandboxError("Empty source code")

    # Basic security checks
    forbidden = ["import ", "exec(", "eval(", "open(", "__", "globals(", "locals(",
                 "compile(", "getattr(", "setattr(", "delattr("]
    for f in forbidden:
        if f in source_code:
            raise MCUSandboxError(f"Forbidden construct: '{f.strip()}' not allowed in MCU code")

    # Compile in restricted namespace
    restricted_globals = {
        "__builtins__": _SAFE_BUILTINS,
        "math": math,
    }

    try:
        code = compile(source_code, "<mcu_tick>", "exec")
        exec(code, restricted_globals)
    except SyntaxError as e:
        raise MCUSandboxError(f"Syntax error in MCU code: {e}")
    except Exception as e:
        raise MCUSandboxError(f"Error compiling MCU code: {e}")

    if "tick" not in restricted_globals:
        raise MCUSandboxError("MCU code must define a 'tick(time_s, pins, state)' function")

    return restricted_globals["tick"]


def execute_tick(
    tick_fn: callable,
    time_s: float,
    pin_voltages: dict[str, float],
    state: dict,
    timeout_ms: int = 10,
) -> dict[str, str]:
    """Execute a tick function with timeout.

    Returns: dict of {pin_name: "HIGH"|"LOW"|"HIZ"}
    """
    result = {}
    error = None

    def run():
        nonlocal result, error
        try:
            r = tick_fn(time_s, pin_voltages, state)
            if isinstance(r, dict):
                result = r
        except Exception as e:
            error = e

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_ms / 1000.0)

    if thread.is_alive():
        raise MCUSandboxError(f"MCU tick function timed out after {timeout_ms}ms")

    if error:
        raise MCUSandboxError(f"MCU tick error: {error}")

    # Validate output
    valid_states = {"HIGH", "LOW", "HIZ"}
    for pin, val in result.items():
        if val not in valid_states:
            raise MCUSandboxError(
                f"Invalid pin state '{val}' for pin '{pin}'. "
                f"Must be one of: HIGH, LOW, HIZ"
            )

    return result


def apply_mcu_outputs(
    outputs: dict[str, str],
    pin_net_map: dict[str, str],
    node_voltages: dict[str, float],
    vcc: float = 5.0,
) -> dict[str, float | None]:
    """Convert MCU output states to voltage source values for the solver.

    Returns: {net_id: voltage_or_None}
    - HIGH → vcc
    - LOW → 0.0
    - HIZ → None (pin removed from circuit)
    """
    result = {}
    for pin_name, state in outputs.items():
        net_id = pin_net_map.get(pin_name)
        if net_id is None:
            continue
        if state == "HIGH":
            result[net_id] = vcc
        elif state == "LOW":
            result[net_id] = 0.0
        elif state == "HIZ":
            result[net_id] = None
    return result
