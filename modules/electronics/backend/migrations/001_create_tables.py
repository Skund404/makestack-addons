"""Migration 001 — Create all electronics_ UserDB tables."""

id = "001_create_tables"
description = "Create electronics module tables: circuits, components, nets, pins, simulation results"


async def up(db) -> None:
    """Create all electronics_ tables."""

    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_circuits (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            description     TEXT NOT NULL DEFAULT '',
            canvas_width    INTEGER NOT NULL DEFAULT 1200,
            canvas_height   INTEGER NOT NULL DEFAULT 800,
            sim_settings    TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_components (
            id              TEXT PRIMARY KEY,
            circuit_id      TEXT NOT NULL REFERENCES electronics_circuits(id) ON DELETE CASCADE,
            catalogue_path  TEXT,
            ref_designator  TEXT NOT NULL,
            component_type  TEXT NOT NULL,
            value           TEXT NOT NULL DEFAULT '',
            unit            TEXT NOT NULL DEFAULT '',
            x               REAL NOT NULL DEFAULT 0,
            y               REAL NOT NULL DEFAULT 0,
            rotation        INTEGER NOT NULL DEFAULT 0,
            properties      TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_comp_circuit
        ON electronics_components (circuit_id)
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_nets (
            id              TEXT PRIMARY KEY,
            circuit_id      TEXT NOT NULL REFERENCES electronics_circuits(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            net_type        TEXT NOT NULL DEFAULT 'signal',
            color           TEXT NOT NULL DEFAULT '',
            UNIQUE(circuit_id, name)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_nets_circuit
        ON electronics_nets (circuit_id)
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_pins (
            id              TEXT PRIMARY KEY,
            component_id    TEXT NOT NULL REFERENCES electronics_components(id) ON DELETE CASCADE,
            pin_name        TEXT NOT NULL,
            net_id          TEXT REFERENCES electronics_nets(id) ON DELETE SET NULL,
            UNIQUE(component_id, pin_name)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_pins_comp
        ON electronics_pins (component_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_pins_net
        ON electronics_pins (net_id)
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_sim_results (
            id              TEXT PRIMARY KEY,
            circuit_id      TEXT NOT NULL REFERENCES electronics_circuits(id) ON DELETE CASCADE,
            sim_type        TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            error_message   TEXT,
            result_data     TEXT NOT NULL DEFAULT '{}',
            ran_at          TEXT NOT NULL,
            duration_ms     INTEGER
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_elec_sim_circuit
        ON electronics_sim_results (circuit_id)
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_sim_node_results (
            id              TEXT PRIMARY KEY,
            sim_result_id   TEXT NOT NULL REFERENCES electronics_sim_results(id) ON DELETE CASCADE,
            net_id          TEXT NOT NULL REFERENCES electronics_nets(id) ON DELETE CASCADE,
            voltage         REAL,
            UNIQUE(sim_result_id, net_id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS electronics_sim_component_results (
            id              TEXT PRIMARY KEY,
            sim_result_id   TEXT NOT NULL REFERENCES electronics_sim_results(id) ON DELETE CASCADE,
            component_id    TEXT NOT NULL REFERENCES electronics_components(id) ON DELETE CASCADE,
            current         REAL,
            power           REAL,
            voltage_drop    REAL,
            UNIQUE(sim_result_id, component_id)
        )
    """)


async def down(db) -> None:
    """Drop all electronics_ tables in reverse dependency order."""
    await db.execute("DROP TABLE IF EXISTS electronics_sim_component_results")
    await db.execute("DROP TABLE IF EXISTS electronics_sim_node_results")
    await db.execute("DROP TABLE IF EXISTS electronics_sim_results")
    await db.execute("DROP TABLE IF EXISTS electronics_pins")
    await db.execute("DROP TABLE IF EXISTS electronics_nets")
    await db.execute("DROP TABLE IF EXISTS electronics_components")
    await db.execute("DROP TABLE IF EXISTS electronics_circuits")
