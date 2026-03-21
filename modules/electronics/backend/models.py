"""Pydantic request/response models for the electronics module."""

from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Circuit
# ---------------------------------------------------------------------------


class CircuitCreate(BaseModel):
    name: str
    description: str = ""
    canvas_width: int = 1200
    canvas_height: int = 800


class CircuitUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    canvas_width: int | None = None
    canvas_height: int | None = None


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class ComponentCreate(BaseModel):
    component_type: str  # "resistor", "voltage_source", "current_source", "ground"
    value: str = ""
    unit: str = ""
    x: float = 0
    y: float = 0
    rotation: int = 0
    catalogue_path: str | None = None


class ComponentUpdate(BaseModel):
    value: str | None = None
    unit: str | None = None
    x: float | None = None
    y: float | None = None
    rotation: int | None = None


# ---------------------------------------------------------------------------
# Net
# ---------------------------------------------------------------------------


class NetCreate(BaseModel):
    name: str
    net_type: str = "signal"  # "power", "ground", "signal"
    color: str = ""


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


class ConnectPinsRequest(BaseModel):
    component_id: str
    pin_name: str
    net_name: str  # auto-creates net if it doesn't exist


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


class SimulateRequest(BaseModel):
    sim_type: str = "op"  # "op", "ac", "dc_sweep", "transient"

    # AC analysis parameters
    f_start: float = 1.0
    f_stop: float = 1e6
    points_per_decade: int = 20

    # DC sweep parameters
    sweep_source_id: str | None = None
    sweep_start: float = 0.0
    sweep_stop: float = 10.0
    sweep_steps: int = 50

    # Transient analysis parameters
    t_stop: float = 0.01
    t_step: float | None = None


# ---------------------------------------------------------------------------
# Wire Segments (E1b)
# ---------------------------------------------------------------------------


class WireSegmentCreate(BaseModel):
    net_id: str | None = None  # auto-creates net if None
    net_name: str | None = None  # used when net_id is None
    x1: float
    y1: float
    x2: float
    y2: float


class WireSplitRequest(BaseModel):
    wire_id: str
    x: float
    y: float


class AutoRouteRequest(BaseModel):
    """Generate Manhattan wire segments between two points."""
    net_id: str | None = None
    net_name: str | None = None
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    route_style: str = "horizontal_first"  # or "vertical_first"


# ---------------------------------------------------------------------------
# Regions (E1b)
# ---------------------------------------------------------------------------


class RegionCreate(BaseModel):
    name: str
    color: str = "#3b82f6"
    description: str = ""
    created_by: str = "user"  # "user" or "ai"


class RegionUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    description: str | None = None


class RegionMemberAdd(BaseModel):
    member_type: str  # "component" or "net"
    member_id: str
