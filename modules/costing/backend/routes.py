"""costing module routes — record and query purchase prices."""

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


class PriceCreate(BaseModel):
    catalogue_path: str
    amount: float
    currency: str = "GBP"
    unit: str = ""
    supplier_name: str = ""
    purchased_at: str = ""
    notes: str = ""


class PriceUpdate(BaseModel):
    amount: float | None = None
    currency: str | None = None
    unit: str | None = None
    supplier_name: str | None = None
    purchased_at: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/prices")
async def list_prices(catalogue_path: str | None = None, db=Depends(get_userdb)):
    """List all price records, optionally filtered by catalogue_path."""
    if catalogue_path:
        rows = await db.fetch_all(
            "SELECT * FROM costing_prices WHERE catalogue_path = ? ORDER BY created_at DESC",
            [catalogue_path],
        )
    else:
        rows = await db.fetch_all(
            "SELECT * FROM costing_prices ORDER BY created_at DESC"
        )
    return {"prices": [dict(r) for r in rows], "total": len(rows)}


@router.get("/prices/{price_id}")
async def get_price(price_id: str, db=Depends(get_userdb)):
    """Get a single price record."""
    row = await db.fetch_one(
        "SELECT * FROM costing_prices WHERE id = ?", [price_id]
    )
    if not row:
        raise HTTPException(status_code=404, detail="Price record not found")
    return dict(row)


@router.post("/prices", status_code=201)
async def create_price(body: PriceCreate, db=Depends(get_userdb)):
    """Record a purchase price for a catalogue entry."""
    price_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO costing_prices
            (id, catalogue_path, amount, currency, unit, supplier_name, purchased_at, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            price_id,
            body.catalogue_path,
            body.amount,
            body.currency,
            body.unit,
            body.supplier_name,
            body.purchased_at or now,
            body.notes,
            now,
        ],
    )
    row = await db.fetch_one("SELECT * FROM costing_prices WHERE id = ?", [price_id])
    return dict(row)


@router.put("/prices/{price_id}")
async def update_price(price_id: str, body: PriceUpdate, db=Depends(get_userdb)):
    """Update a price record."""
    row = await db.fetch_one("SELECT * FROM costing_prices WHERE id = ?", [price_id])
    if not row:
        raise HTTPException(status_code=404, detail="Price record not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return dict(row)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [price_id]
    await db.execute(
        f"UPDATE costing_prices SET {set_clause} WHERE id = ?", values
    )
    row = await db.fetch_one("SELECT * FROM costing_prices WHERE id = ?", [price_id])
    return dict(row)


@router.delete("/prices/{price_id}", status_code=204)
async def delete_price(price_id: str, db=Depends(get_userdb)):
    """Remove a price record."""
    row = await db.fetch_one("SELECT id FROM costing_prices WHERE id = ?", [price_id])
    if not row:
        raise HTTPException(status_code=404, detail="Price record not found")
    await db.execute("DELETE FROM costing_prices WHERE id = ?", [price_id])
