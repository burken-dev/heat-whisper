# tests/test_units.py — unit string -> HA device_class mapping + catalog
# string-index table (feeds App.register_* entity_fields so HA gets unit,
# device_class, display precision and state_class).
from components.heatwhisper.registers import (
    canon_unit, device_class_for_unit, state_class_for_unit,
    generate_catalog_header,
)


def test_canon_unit_fixes_masculine_ordinal():
    assert canon_unit("ºC") == "°C"
    assert canon_unit("°C") == "°C"
    assert canon_unit("%") == "%"
    assert canon_unit("") == ""
    assert canon_unit(None) == ""


def test_device_class_unambiguous_units_only():
    assert device_class_for_unit("°C") == "temperature"
    assert device_class_for_unit("ºC") == "temperature"
    assert device_class_for_unit("%RH") == "humidity"
    assert device_class_for_unit("kWh") == "energy"
    assert device_class_for_unit("Hz") == "frequency"
    assert device_class_for_unit("bar") == "pressure"
    # ambiguous / non-HA units stay classless (unit-only, no wrong conversion)
    assert device_class_for_unit("%") == ""
    assert device_class_for_unit("rpm") == ""
    assert device_class_for_unit("l/m") == ""
    assert device_class_for_unit("dagar") == ""
    assert device_class_for_unit("") == ""


def test_state_class_energy_totals_vs_measurements():
    assert state_class_for_unit("kWh") == 2  # total_increasing
    assert state_class_for_unit("Wh") == 2
    assert state_class_for_unit("°C") == 1  # measurement
    assert state_class_for_unit("%") == 0  # classless -> none
    assert state_class_for_unit("") == 0


def test_catalog_header_carries_string_indices():
    models = {"F750": [
        {"register": "40004", "factor": 10, "size": "s16", "mode": "R",
         "titel": "BT1 Outdoor", "unit": "°C", "min": "-500", "max": "500"},
        {"register": "47041", "factor": 1, "size": "u8", "mode": "R/W",
         "titel": "Comfort", "unit": "", "min": "0", "max": "4"}]}
    # codegen-time pool indices (1-based, 0 = unset)
    hdr = generate_catalog_header(models, {},
                                  str_idx={"uom": {"°C": 3}, "dc": {"temperature": 5}})
    assert "HW_STRS" in hdr and "HW_STRS_N = 2" in hdr
    assert "{40004,5,3,1}" in hdr  # dc=temperature, uom=°C, sc=measurement
    assert "{47041,0,0,0}" in hdr  # unitless -> identical to today's behavior


def test_catalog_header_without_pool_stays_zero():
    models = {"F750": [
        {"register": "40004", "factor": 10, "size": "s16", "mode": "R",
         "titel": "BT1 Outdoor", "unit": "°C", "min": "-500", "max": "500"}]}
    hdr = generate_catalog_header(models, {})
    assert "{40004,0,0,0}" in hdr
