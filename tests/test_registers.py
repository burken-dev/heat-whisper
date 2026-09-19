# tests/test_registers.py
import json, os
from components.heatwhisper.registers import DEFAULT_ALLOWLIST, is_known


def test_merge_prefers_nonzero_minmax():
    # first-wins would lock in 0/0 (corrupt filter off, number clamp open);
    # _by_reg is shared with the catalog, so cover it via generate_catalog_header.
    from components.heatwhisper.registers import generate_catalog_header
    models = {
        "A": [{"register": "43005", "factor": 10, "size": "s16",
               "mode": "R/W", "min": "0", "max": "0"}],
        "B": [{"register": "43005", "factor": 10, "size": "s16",
               "mode": "R/W", "min": "-30000", "max": "30000"}],
    }
    hdr = generate_catalog_header(models, {})
    entry = hdr[hdr.index("{43005,"):hdr.index("{43005,") + 80]
    assert "-30000" in entry and "30000" in entry


def test_real_43005_resolves_nonzero_minmax():
    from components.heatwhisper.registers import generate_catalog_header
    mdir = os.path.join(os.path.dirname(__file__), "..", "components", "heatwhisper", "models")
    models = {}
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    hdr = generate_catalog_header(models, {})
    entry = hdr[hdr.index("{43005,"):hdr.index("{43005,") + 80]
    assert "-30000" in entry and "30000" in entry


def test_is_known_hit_and_miss():
    models = {"F750": [{"register": "40004", "factor": 10, "size": "s16", "mode": "R"}]}
    assert is_known(40004, models) is True
    assert is_known(12345, models) is False

def test_init_uses_extra_poll():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "components", "heatwhisper", "__init__.py")).read()
    assert "extra_poll" in src
    assert 'CONF_REGISTERS = "registers"' not in src


def test_smart_allowlist_present():
    for a in [40033, 43144, 43305, 47011, 47007, 47041, 47371, 47370, 47387, 47043]:
        assert a in DEFAULT_ALLOWLIST


def test_smart_catalog_decodable_real_models():
    from components.heatwhisper.registers import generate_catalog_header
    import json, os
    mdir = os.path.join(os.path.dirname(__file__), "..", "components", "heatwhisper", "models")
    models = {}
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    hdr = generate_catalog_header(models, {})
    for a in ["40033", "43144", "43305", "47007", "47011", "47041", "47370", "47371", "47387", "47043"]:
        assert "{" + a + "," in hdr
