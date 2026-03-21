"""Tests for electronics module migrations."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest
import pytest_asyncio

from makestack_sdk.testing import MockUserDB

_MODULE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _load(name: str, relpath: str):
    key = f"_electronics_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(_MODULE_ROOT, relpath)
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


migration_001 = _load("mig001", "backend/migrations/001_create_tables.py")


@pytest_asyncio.fixture
async def db():
    userdb = MockUserDB()
    await userdb.setup()
    yield userdb
    await userdb.teardown()


@pytest.mark.asyncio
async def test_migration_up_creates_tables(db):
    await migration_001.up(db)
    tables = [
        "electronics_circuits",
        "electronics_components",
        "electronics_nets",
        "electronics_pins",
        "electronics_sim_results",
        "electronics_sim_node_results",
        "electronics_sim_component_results",
    ]
    for table in tables:
        count = await db.count(table)
        assert count == 0, f"Table {table} should exist and be empty"


@pytest.mark.asyncio
async def test_migration_down_drops_tables(db):
    await migration_001.up(db)
    await migration_001.down(db)
    # After down, tables should not exist
    for table in ["electronics_circuits", "electronics_components", "electronics_nets",
                   "electronics_pins", "electronics_sim_results",
                   "electronics_sim_node_results", "electronics_sim_component_results"]:
        with pytest.raises(Exception):
            await db.count(table)


@pytest.mark.asyncio
async def test_migration_up_idempotent(db):
    await migration_001.up(db)
    await migration_001.up(db)  # should not raise
    count = await db.count("electronics_circuits")
    assert count == 0
