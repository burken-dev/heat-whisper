import os
from components.nibe.registers import (MAX_SELECTION, DEFAULT_ENABLED, normalize_model,
    model_registers, object_id_for, entity_kind_for, validate_selection, _by_reg)

MDIR = os.path.join(os.path.dirname(__file__), "..", "components", "nibe", "models")

def _models():
    import json
    models = {}
    for f in sorted(os.listdir(MDIR)):
        if f.endswith(".json"):
            with open(os.path.join(MDIR, f)) as fh:
                models[f[:-5]] = json.load(fh)
    return models

def test_normalize_model():
    assert normalize_model("F750-42") == "F75042"
    assert normalize_model("f750") == "F750"
    assert normalize_model("") == ""

def test_model_registers_known_and_unknown():
    models = _models()
    regs = model_registers(models, "F750")
    assert 40004 in regs and len(regs) > 500
    assert model_registers(models, "NOPE-NOT-A-MODEL") == []

def test_object_id_stable():
    assert object_id_for("BT1 Outdoor") == "bt1_outdoor"
    assert object_id_for("Hot Water Top BT7") == "hot_water_top_bt7"

def test_entity_kind_hints_and_defaults():
    models = _models()
    by_reg = _by_reg(models)
    hints = {"47041": {"type": "select", "options": [[0, "Eco"]]},
             "47371": {"type": "switch"}}
    assert entity_kind_for(47041, by_reg, hints)[0] == "select"
    assert entity_kind_for(47371, by_reg, hints)[0] == "switch"
    assert entity_kind_for(40004, by_reg, hints)[0] == "sensor"
    assert entity_kind_for(43005, by_reg, hints)[0] == "number"

def test_validate_selection():
    models = _models()
    ok, err = validate_selection([40004, 40004, 43005], models)
    assert ok == [40004, 43005] and err == ""
    assert validate_selection([12345], models)[0] is None
    known = sorted({int(r["register"]) for regs in models.values() for r in regs})
    too_many = known[:MAX_SELECTION + 1]
    ok, err = validate_selection(too_many, models)
    assert ok is None and "too many" in err

def test_defaults_match_allowlist():
    from components.nibe.registers import DEFAULT_ALLOWLIST
    assert sorted(DEFAULT_ENABLED) == sorted(a for a in DEFAULT_ALLOWLIST if a != 10001) or \
        set(DEFAULT_ENABLED) <= set(DEFAULT_ALLOWLIST)
