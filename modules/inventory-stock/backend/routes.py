"""inventory-stock module routes — track material/tool quantities and locations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from makestack_sdk import get_userdb

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StockCreate(BaseModel):
    inventory_id: str
    quantity: float
    unit: str = ""
    location: str = ""
    reorder_threshold: float = 0.0
    notes: str = ""


class StockUpdate(BaseModel):
    quantity: float | None = None
    unit: str | None = None
    location: str | None = None
    reorder_threshold: float | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/stock")
async def list_stock(db=Depends(get_userdb)):
    """List all stock entries with low-stock flag."""
    rows = await db.fetch_all(
        "SELECT * FROM inventory_stock_items ORDER BY updated_at DESC"
    )
    items = []
    for row in rows:
        d = dict(row)
        d["low_stock"] = (
            d["reorder_threshold"] > 0
            and d["quantity"] <= d["reorder_threshold"]
        )
        items.append(d)
    return {"items": items, "total": len(items)}


@router.get("/stock/{entry_id}")
async def get_stock(entry_id: str, db=Depends(get_userdb)):
    """Get a single stock entry."""
    row = await db.fetch_one(
        "SELECT * FROM inventory_stock_items WHERE id = ?", [entry_id]
    )
    if not row:
        raise HTTPException(status_code=404, detail="Stock entry not found")
    d = dict(row)
    d["low_stock"] = (
        d["reorder_threshold"] > 0
        and d["quantity"] <= d["reorder_threshold"]
    )
    return d


@router.post("/stock", status_code=201)
async def create_stock(body: StockCreate, db=Depends(get_userdb)):
    """Create a stock entry for an inventory item."""
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO inventory_stock_items
            (id, inventory_id, quantity, unit, location, reorder_threshold, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            entry_id,
            body.inventory_id,
            body.quantity,
            body.unit,
            body.location,
            body.reorder_threshold,
            body.notes,
            now,
        ],
    )
    row = await db.fetch_one(
        "SELECT * FROM inventory_stock_items WHERE id = ?", [entry_id]
    )
    return dict(row)


@router.put("/stock/{entry_id}")
async def update_stock(entry_id: str, body: StockUpdate, db=Depends(get_userdb)):
    """Update quantity, unit, location, or threshold."""
    row = await db.fetch_one(
        "SELECT * FROM inventory_stock_items WHERE id = ?", [entry_id]
    )
    if not row:
        raise HTTPException(status_code=404, detail="Stock entry not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return dict(row)

    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [entry_id]
    await db.execute(
        f"UPDATE inventory_stock_items SET {set_clause} WHERE id = ?", values
    )

    row = await db.fetch_one(
        "SELECT * FROM inventory_stock_items WHERE id = ?", [entry_id]
    )
    d = dict(row)
    d["low_stock"] = (
        d["reorder_threshold"] > 0
        and d["quantity"] <= d["reorder_threshold"]
    )
    return d


@router.delete("/stock/{entry_id}", status_code=204)
async def delete_stock(entry_id: str, db=Depends(get_userdb)):
    """Remove a stock entry."""
    row = await db.fetch_one(
        "SELECT id FROM inventory_stock_items WHERE id = ?", [entry_id]
    )
    if not row:
        raise HTTPException(status_code=404, detail="Stock entry not found")
    await db.execute("DELETE FROM inventory_stock_items WHERE id = ?", [entry_id])
