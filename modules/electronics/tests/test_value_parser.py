"""Tests for the engineering value parser."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Load value_parser by file path
# ---------------------------------------------------------------------------

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


vp = _load("value_parser", "backend/value_parser.py")
parse_engineering_value = vp.parse_engineering_value
format_engineering_value = vp.format_engineering_value


# ---------------------------------------------------------------------------
# parse_engineering_value
# ---------------------------------------------------------------------------


class TestParseEngineeringValue:
    """Tests for SI-prefix parsing."""

    def test_plain_integer(self):
        assert parse_engineering_value("100") == 100.0

    def test_plain_float(self):
        assert parse_engineering_value("4.7") == 4.7

    def test_scientific_notation(self):
        assert parse_engineering_value("1e3") == 1000.0

    def test_negative_scientific(self):
        assert parse_engineering_value("2.2e-6") == 2.2e-6

    def test_kilo(self):
        assert parse_engineering_value("1k") == 1000.0

    def test_kilo_uppercase(self):
        assert parse_engineering_value("1K") == 1000.0

    def test_kilo_with_decimal(self):
        assert parse_engineering_value("4.7k") == 4700.0

    def test_mega(self):
        assert parse_engineering_value("2.2M") == 2.2e6

    def test_micro_u(self):
        assert parse_engineering_value("4.7u") == 4.7e-6

    def test_micro_mu(self):
        assert parse_engineering_value("4.7µ") == 4.7e-6

    def test_nano(self):
        assert parse_engineering_value("100n") == pytest.approx(1e-7)

    def test_pico(self):
        assert parse_engineering_value("22p") == pytest.approx(22e-12)

    def test_milli(self):
        assert parse_engineering_value("1m") == 0.001

    def test_giga(self):
        assert parse_engineering_value("1G") == 1e9

    def test_tera(self):
        assert parse_engineering_value("1T") == 1e12

    def test_with_unit_suffix_ohm(self):
        assert parse_engineering_value("10kohm") == 10000.0

    def test_with_unit_suffix_farad(self):
        assert parse_engineering_value("100nF") == pytest.approx(1e-7)

    def test_with_unit_suffix_henry(self):
        assert parse_engineering_value("4.7uH") == 4.7e-6

    def test_with_unit_suffix_volt(self):
        assert parse_engineering_value("5V") == 5.0

    def test_with_unit_suffix_ampere(self):
        assert parse_engineering_value("1mA") == 0.001

    def test_with_omega_symbol(self):
        assert parse_engineering_value("10kΩ") == 10000.0

    def test_whitespace_handling(self):
        assert parse_engineering_value("  1k  ") == 1000.0

    def test_negative_value(self):
        assert parse_engineering_value("-5") == -5.0

    def test_empty_string(self):
        assert parse_engineering_value("") is None

    def test_none_input(self):
        assert parse_engineering_value(None) is None

    def test_invalid_string(self):
        assert parse_engineering_value("hello") is None

    def test_just_unit(self):
        assert parse_engineering_value("ohm") is None

    def test_zero(self):
        assert parse_engineering_value("0") == 0.0

    def test_meg_spice(self):
        """SPICE uses 'meg' for mega to avoid conflict with 'm' (milli)."""
        assert parse_engineering_value("2.2meg") == 2.2e6

    def test_femto(self):
        assert parse_engineering_value("100f") == 100e-15


# ---------------------------------------------------------------------------
# format_engineering_value
# ---------------------------------------------------------------------------


class TestFormatEngineeringValue:
    """Tests for float-to-engineering-string formatting."""

    def test_kilohm(self):
        assert format_engineering_value(1000.0, "ohm") == "1kΩ"

    def test_megohm(self):
        assert format_engineering_value(2.2e6, "ohm") == "2.2MΩ"

    def test_microfarad(self):
        assert format_engineering_value(4.7e-6, "F") == "4.7µF"

    def test_nanohenry(self):
        assert format_engineering_value(100e-9, "H") == "100nH"

    def test_volt(self):
        assert format_engineering_value(5.0, "V") == "5V"

    def test_milliamp(self):
        assert format_engineering_value(0.001, "A") == "1mA"

    def test_zero(self):
        assert format_engineering_value(0.0, "V") == "0V"

    def test_picofarad(self):
        assert format_engineering_value(22e-12, "F") == "22pF"
