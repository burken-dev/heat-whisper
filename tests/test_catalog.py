import os
from components.heatwhisper.registers import (MAX_SELECTION, DEFAULT_ENABLED, normalize_model, _by_reg)

def test_normalize_model():
    assert normalize_model("F750-42") == "F75042"
    assert normalize_model("f750") == "F750"
    assert normalize_model("") == ""

def test_generate_catalog_header_layout():
    from components.heatwhisper.registers import generate_catalog_header
    models = {"F750": [
        {"register": "40004", "factor": 10, "size": "s16", "mode": "R",
         "titel": "BT1 Outdoor Temperature", "unit": "°C", "min": "-500", "max": "500"},
        {"register": "47041", "factor": 1, "size": "u8", "mode": "R/W",
         "titel": "Comfort", "unit": "", "min": "0", "max": "4"}]}
    hints = {"47041": {"type": "select", "options": [[0, "Eco"], [1, "Normal"]]},
             "47371": {"type": "switch"}}
    hdr = generate_catalog_header(models, hints)
    assert "HW_META" in hdr and "HW_TITLES" in hdr
    assert "HW_MODEL_F750" in hdr and "HW_MODELS" in hdr
    assert "HW_DEFAULTS" in hdr and "HW_HINTS" in hdr
    assert "HW_MAX_SELECTION = 50" in hdr
    assert "{40004,10,3,0,-500,500,3,0}" in hdr
    assert "BT1 Outdoor Temperature" in hdr
    assert "0:Eco;1:Normal" in hdr

def test_generate_catalog_header_unknown_size_falls_back_to_s16():
    from components.heatwhisper.registers import generate_catalog_header
    models = {"VVMS320": [
        {"register": "31561", "factor": "1", "size": "", "mode": "R",
         "titel": "Datum periodisk varmvatten", "unit": "", "min": "", "max": ""}]}
    hdr = generate_catalog_header(models, {})
    assert "{31561,1,3,0,0,0,3,0}" in hdr
