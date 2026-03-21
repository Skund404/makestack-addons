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
    sim_type: str = "op"  # only "op" in E1
