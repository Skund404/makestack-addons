"""Migration 002 — E1b wire segments, junctions, regions.

Adds geometric wire storage (display layer), junction points,
and circuit region annotations. The solver is unaffected — it
reads nets/pins only. Wire segments are for frontend rendering.
"""

id = "002_e1b_wire_catalogue"
description = "Add wire segments, junctions, and region tables for E1b"


async def up(db) -> None:
    """Create E1b tables."""

    # Wire segments — geometric display layer for wire routing
    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_wire_segments (
            id              TEXT PRIMARY KEY,
            circuit_id      TEXT NOT NULL REFERENCES electronics_circuits(id) ON DELETE CASCADE,
            net_id          TEXT NOT NULL REFERENCES electronics_nets(id) ON DELETE CASCADE,
            x1              REAL NOT NULL,
            y1              REAL NOT NULL,
            x2              REAL NOT NULL,
            y2              REAL NOT NULL,
            sort_order      INTEGER NOT NULL DEFAULT 0
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_wire_seg_circuit
        ON electronics_wire_segments (circuit_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_wire_seg_net
        ON electronics_wire_segments (net_id)
    """)

    # Junctions — points where 3+ wire segments meet
    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_junctions (
            id              TEXT PRIMARY KEY,
            circuit_id      TEXT NOT NULL REFERENCES electronics_circuits(id) ON DELETE CASCADE,
            net_id          TEXT NOT NULL REFERENCES electronics_nets(id) ON DELETE CASCADE,
            x               REAL NOT NULL,
            y               REAL NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_junctions_circuit
        ON electronics_junctions (circuit_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_junctions_net
        ON electronics_junctions (net_id)
    """)

    # Regions — named colored groupings of components/nets for annotation
    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_regions (
            id              TEXT PRIMARY KEY,
            circuit_id      TEXT NOT NULL REFERENCES electronics_circuits(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            color           TEXT NOT NULL DEFAULT '#3b82f6',
            description     TEXT NOT NULL DEFAULT '',
            created_by      TEXT NOT NULL DEFAULT 'user'
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_regions_circuit
        ON electronics_regions (circuit_id)
    """)

    # Region members — component or net membership in a region
    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_region_members (
            id              TEXT PRIMARY KEY,
            region_id       TEXT NOT NULL REFERENCES electronics_regions(id) ON DELETE CASCADE,
            member_type     TEXT NOT NULL,
            member_id       TEXT NOT NULL,
            UNIQUE(region_id, member_type, member_id)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_region_members_region
        ON electronics_region_members (region_id)
    """)


async def down(db) -> None:
    """Drop E1b tables in reverse dependency order."""
    await db.execute("DROP TABLE IF EXISTS electronics_region_members")
    await db.execute("DROP TABLE IF EXISTS electronics_regions")
    await db.execute("DROP TABLE IF EXISTS electronics_junctions")
    await db.execute("DROP TABLE IF EXISTS electronics_wire_segments")
