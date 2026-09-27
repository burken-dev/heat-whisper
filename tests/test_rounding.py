# tests/test_rounding.py — host mirror of on_value() rounding behavior
import math


def round_to_1_decimal(v: float) -> float:
    """Mirror of the C++ rounding: std::round(v * 10.0f) / 10.0f"""
    return round(v * 10.0) / 10.0


def test_rounds_to_1_decimal():
    assert round_to_1_decimal(21.56789) == 21.6
    assert round_to_1_decimal(21.54999) == 21.5
    assert round_to_1_decimal(-3.14159) == -3.1
    assert round_to_1_decimal(0.0) == 0.0
    assert round_to_1_decimal(100.0) == 100.0


def test_typical_sensor_values():
    # raw 215 / factor 10 = 21.5 (already clean)
    assert round_to_1_decimal(215 / 10) == 21.5
    # raw 2157 / factor 100 = 21.57 -> 21.6
    assert round_to_1_decimal(2157 / 100) == 21.6
    # raw -210 / factor 10 = -21.0
    assert round_to_1_decimal(-210 / 10) == -21.0
