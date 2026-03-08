"""suppliers module routes — vendor management and catalogue linking."""

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


class VendorCreate(BaseModel):
    name: str
    url: str = ""
    contact: str = ""
    notes: str = ""


class VendorUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    contact: str | None = None
    notes: str | None = None


class LinkCreate(BaseModel):
    catalogue_path: str
    product_url: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/vendors")
async def list_vendors(db=Depends(get_userdb)):
    """List all vendor records."""
    rows = await db.fetch_all(
        "SELECT * FROM suppliers_vendors ORDER BY name ASC"
    )
    return {"vendors": [dict(r) for r in rows], "total": len(rows)}


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: str, db=Depends(get_userdb)):
    """Get a vendor with its catalogue links."""
    row = await db.fetch_one(
        "SELECT * FROM suppliers_vendors WHERE id = ?", [vendor_id]
    )
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")

    links = await db.fetch_all(
        "SELECT * FROM suppliers_catalog_links WHERE vendor_id = ?", [vendor_id]
    )
    vendor = dict(row)
    vendor["links"] = [dict(l) for l in links]
    return vendor


@router.post("/vendors", status_code=201)
async def create_vendor(body: VendorCreate, db=Depends(get_userdb)):
    """Create a new vendor."""
    vendor_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO suppliers_vendors (id, name, url, contact, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [vendor_id, body.name, body.url, body.contact, body.notes, now],
    )
    row = await db.fetch_one("SELECT * FROM suppliers_vendors WHERE id = ?", [vendor_id])
    return dict(row)


@router.put("/vendors/{vendor_id}")
async def update_vendor(vendor_id: str, body: VendorUpdate, db=Depends(get_userdb)):
    """Update vendor details."""
    row = await db.fetch_one("SELECT * FROM suppliers_vendors WHERE id = ?", [vendor_id])
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return dict(row)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [vendor_id]
    await db.execute(f"UPDATE suppliers_vendors SET {set_clause} WHERE id = ?", values)
    row = await db.fetch_one("SELECT * FROM suppliers_vendors WHERE id = ?", [vendor_id])
    return dict(row)


@router.delete("/vendors/{vendor_id}", status_code=204)
async def delete_vendor(vendor_id: str, db=Depends(get_userdb)):
    """Remove a vendor and all its catalogue links."""
    row = await db.fetch_one("SELECT id FROM suppliers_vendors WHERE id = ?", [vendor_id])
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")
    await db.execute("DELETE FROM suppliers_catalog_links WHERE vendor_id = ?", [vendor_id])
    await db.execute("DELETE FROM suppliers_vendors WHERE id = ?", [vendor_id])


@router.post("/vendors/{vendor_id}/links", status_code=201)
async def add_link(vendor_id: str, body: LinkCreate, db=Depends(get_userdb)):
    """Link a vendor to a catalogue entry."""
    row = await db.fetch_one("SELECT id FROM suppliers_vendors WHERE id = ?", [vendor_id])
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")

    link_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO suppliers_catalog_links (id, vendor_id, catalogue_path, product_url, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [link_id, vendor_id, body.catalogue_path, body.product_url, body.notes, now],
    )
    link = await db.fetch_one(
        "SELECT * FROM suppliers_catalog_links WHERE id = ?", [link_id]
    )
    return dict(link)


@router.delete("/links/{link_id}", status_code=204)
async def remove_link(link_id: str, db=Depends(get_userdb)):
    """Remove a catalogue link."""
    row = await db.fetch_one(
        "SELECT id FROM suppliers_catalog_links WHERE id = ?", [link_id]
    )
    if not row:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.execute("DELETE FROM suppliers_catalog_links WHERE id = ?", [link_id])
