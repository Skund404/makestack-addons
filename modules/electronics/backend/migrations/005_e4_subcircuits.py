"""Migration 005 — Subcircuit definitions and instances.

Enables reusable circuit blocks (e.g., 7400 NAND gate, 555 timer)
that can be instantiated in parent circuits and flattened at solve time.
"""

id = "005_e4_subcircuits"
description = "Add subcircuit definitions and instances tables"


async def up(db):
    """Create subcircuit tables."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_subcircuits (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            port_pins TEXT NOT NULL DEFAULT '[]',
            circuit_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_subcircuit_instances (
            id TEXT PRIMARY KEY,
            circuit_id TEXT NOT NULL,
            subcircuit_id TEXT NOT NULL,
            port_mapping TEXT NOT NULL DEFAULT '{}',
            x REAL DEFAULT 0,
            y REAL DEFAULT 0,
            rotation INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (circuit_id) REFERENCES electronics_circuits(id),
            FOREIGN KEY (subcircuit_id) REFERENCES electronics_subcircuits(id)
        )
    """)


async def down(db):
    """Drop subcircuit tables."""
    await db.execute("DROP TABLE IF EXISTS electronics_subcircuit_instances")
    await db.execute("DROP TABLE IF EXISTS electronics_subcircuits")
