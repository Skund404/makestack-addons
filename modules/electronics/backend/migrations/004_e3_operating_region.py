"""Migration 004 — Add operating region and extra data to sim component results.

Supports E3 nonlinear device simulation results with operating region
(cutoff/active/saturation/forward/reverse/breakdown/linear) and device-specific
extra data (Vbe, Ic, gm, etc.).
"""

id = "004_e3_operating_region"
description = "Add operating_region and extra_data columns to sim component results"


async def up(db):
    """Add columns for nonlinear device result data."""
    await db.execute(
        "ALTER TABLE electronics_sim_component_results ADD COLUMN operating_region TEXT"
    )
    await db.execute(
        "ALTER TABLE electronics_sim_component_results ADD COLUMN extra_data TEXT DEFAULT '{}'"
    )


async def down(db):
    """Remove operating_region and extra_data columns.

    SQLite does not support DROP COLUMN before 3.35.0, so we recreate the table.
    """
    await db.execute("""
        CREATE TABLE electronics_sim_component_results_backup (
            id TEXT PRIMARY KEY,
            sim_result_id TEXT NOT NULL,
            component_id TEXT NOT NULL,
            current REAL NOT NULL,
            power REAL NOT NULL,
            voltage_drop REAL NOT NULL,
            FOREIGN KEY (sim_result_id) REFERENCES electronics_sim_results(id)
        )
    """)
    await db.execute("""
        INSERT INTO electronics_sim_component_results_backup
        SELECT id, sim_result_id, component_id, current, power, voltage_drop
        FROM electronics_sim_component_results
    """)
    await db.execute("DROP TABLE electronics_sim_component_results")
    await db.execute(
        "ALTER TABLE electronics_sim_component_results_backup RENAME TO electronics_sim_component_results"
    )
