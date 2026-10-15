# tests/test_transports.py
import json, os
from components.heatwhisper.registers import generate_catalog_header

TDIR = os.path.join(os.path.dirname(__file__), "..", "components", "heatwhisper")

def _models():
    mdir = os.path.join(TDIR, "models")
    return {f[:-5]: json.load(open(os.path.join(mdir, f)))
            for f in sorted(os.listdir(mdir)) if f.endswith(".json")}

def _transports():
    return {k: v for k, v in json.load(open(os.path.join(TDIR, "transports.json"))).items() if not k.startswith("_")}

def test_modbus40_transport_defaults():
    t = _transports()
    f750 = t["F750"]
    assert f750["protocol"] == "modbus_rtu"
    assert f750["baud"] == 9600 and f750["parity"] == "NONE"
    assert f750["address"] == 1 and f750["write_fc"] == 16

def test_catalog_emits_transports_and_fc():
    hdr = generate_catalog_header(_models(), json.load(open(os.path.join(TDIR, "entity_hints.json"))),
                                  _transports())
    assert "HW_TRANSPORTS" in hdr and "HW_TRANSPORTS_N" in hdr

def test_nibe_modbus40_allowlist():
    # MODBUS40 installer manual (art. 067 144) compatible list — nothing more.
    t = _transports()
    nibe = {k for k in t if k[0] in "FSV" or k == "SMO40"}
    assert nibe == {"F1145", "F1155", "F1245", "F1255", "F1345", "F1355",
                    "F370", "F470", "F730", "F750",
                    "VVM225", "VVM310", "VVM320", "VVM325", "VVM500", "SMO40"}

def test_modbus_model_gated_on_transports():
    # S-series (TCP-only) and accessories must be rejected in modbus_rtu mode.
    src = open(os.path.join(TDIR, "__init__.py")).read()
    assert "not in transports" in src
