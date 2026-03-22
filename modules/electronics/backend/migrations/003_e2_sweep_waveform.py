"""Migration 003 — Add tables for AC/transient/sweep results (E2).

Stores multi-point simulation results: frequency sweeps, DC sweeps,
and transient waveforms. Each result links back to electronics_sim_results
for the top-level metadata.
"""

id = "003_e2_sweep_waveform"
description = "Add sweep and waveform data tables for AC/transient/DC sweep analysis"


async def up(db) -> None:
    """Create sweep/waveform tables."""

    # Sweep data points — used by DC sweep, AC sweep, transient
    # Each row is one (parameter, node, value) triple
    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_sweep_points (
            id              TEXT PRIMARY KEY,
            sim_result_id   TEXT NOT NULL REFERENCES electronics_sim_results(id) ON DELETE CASCADE,
            point_index     INTEGER NOT NULL,
            parameter_value REAL NOT NULL,
            net_id          TEXT REFERENCES electronics_nets(id) ON DELETE CASCADE,
            voltage_real    REAL,
            voltage_imag    REAL,
            component_id    TEXT REFERENCES electronics_components(id) ON DELETE CASCADE,
            current         REAL,
            power           REAL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_sweep_sim
        ON electronics_sweep_points (sim_result_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_sweep_sim_net
        ON electronics_sweep_points (sim_result_id, net_id)
    """)


async def down(db) -> None:
    """Drop sweep/waveform tables."""
    await db.execute("DROP TABLE IF EXISTS electronics_sweep_points")
