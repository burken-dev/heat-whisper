# tests/test_registers.py
from components.nibe.registers import common_and_deltas
def test_common_contains_bt1():
    models = {
        "F750": [{"register": "40004", "factor": 10, "size": "s16", "mode": "R"}],
        "F370": [{"register": "40004", "factor": 10, "size": "s16", "mode": "R"},
                 {"register": "40008", "factor": 10, "size": "s16", "mode": "R"}],
    }
    common, deltas = common_and_deltas(models)
    assert "40004" in common
    assert deltas["F370"] == ["40008"]
    assert deltas["F750"] == []
