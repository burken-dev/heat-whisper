# tests/test_brand_models.py
import json, os
import pytest
MDIR = os.path.join(os.path.dirname(__file__), "..", "components", "heatwhisper", "models")

def _all():
    return [f[:-5] for f in sorted(os.listdir(MDIR)) if f.endswith(".json")]

@pytest.mark.parametrize("name", _all())
def test_model_schema_valid(name):
    regs = json.load(open(os.path.join(MDIR, name + ".json")))
    assert isinstance(regs, list) and regs
    seen = set()
    for r in regs:
        assert r["size"] in ("u8", "s8", "u16", "s16", "u32", "s32"), r
        assert r["mode"] in ("R", "R/W"), r
        assert r.get("mb_fc", 3) in (1, 2, 3, 4), r
        assert r.get("word_order", "ABCD") in ("ABCD", "CDAB"), r
        assert int(r["factor"]) != 0, r
        assert r["register"] not in seen, r
        seen.add(r["register"])
        assert r.get("titel"), r
