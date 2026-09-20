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


def _regs(name):
    return {r["register"]: r for r in json.load(open(os.path.join(MDIR, name + ".json")))}

def test_thermia_core_registers():
    # De-facto addresses per official Genesis 13 PDF (ACMBDH01UG0102, Atlas/Calibra/
    # Diplomat Inverter on Genesis platform): brief's 507/515/522 numbering is not
    # in this spec version; input-reg pos 12/13/15 -> de-facto 30013/30014/30016.
    m = _regs("Thermia_Genesis")
    assert m["30014"]["unit"] == "°C" and m["30014"]["mode"] == "R"  # outside temp
    assert m["30013"]["mode"] == "R"                                 # flow temp
    assert m["30016"]["mode"] == "R"                                 # DHW temp
    assert any(r["mb_fc"] == 1 for r in m.values())                  # coils exist

def test_dimplex_core_registers():
    # WPM software J/L/M numbering (1...207 address-range mode; extended regs
    # up to 352 for newer datapoints) per official Dimplex wiki "Modbus RTU
    # connection (EN)": outside=1, DHW=3, flow=5; operation mode=222 (R/W).
    m = _regs("Dimplex_WPM")
    assert m["1"]["unit"] == "°C" and m["1"]["mode"] == "R"  # outside temp
    assert m["5"]["mode"] == "R"                             # flow temp
    assert m["3"]["mode"] == "R"                             # DHW temp
    assert m["1"]["size"] == "s16" and m["1"]["factor"] == 10
    assert m["5"]["factor"] == 10 and m["3"]["factor"] == 10
    assert m["222"]["mode"] == "R/W"                         # operation mode
