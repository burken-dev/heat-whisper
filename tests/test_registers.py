# tests/test_registers.py
import json, os
from components.nibe.registers import common_and_deltas
def test_common_contains_bt1():
    models = {
        "F750": [{"register": "40004", "factor": 10, "size": "s16", "mode": "R"}],
        "F370": [{"register": "40004", "factor": 10, "size": "s16", "mode": "R"},
                 {"register": "49999", "factor": 1, "size": "u16", "mode": "R"}],
    }
    common, deltas = common_and_deltas(models)
    assert "40004" in common
    assert deltas["F370"] == ["49999"]
    assert deltas["F750"] == []


def test_common_allowlist_seeded_real_models():
    mdir = os.path.join(os.path.dirname(__file__), "..", "reference-project", "models")
    models = {}
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    common, _ = common_and_deltas(models)
    assert "40004" in common
    assert len(common) >= 5
