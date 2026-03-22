"""Migration 006 — MCU programs table for co-simulation.

Stores user-provided Python tick functions for MCU components.
"""

id = "006_e7_mcu"
description = "Add MCU programs table for co-simulation tick functions"


async def up(db):
    """Create MCU programs table."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_mcu_programs (
            id TEXT PRIMARY KEY,
            circuit_id TEXT NOT NULL,
            component_id TEXT NOT NULL,
            source_code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (circuit_id) REFERENCES electronics_circuits(id) ON DELETE CASCADE
        )
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mcu_prog_comp
        ON electronics_mcu_programs (circuit_id, component_id)
    """)


async def down(db):
    """Drop MCU programs table."""
    await db.execute("DROP TABLE IF EXISTS electronics_mcu_programs")
