# tests/test_transports.py
import json, os
from components.heatwhisper.registers import load_transports, generate_catalog_header

TDIR = os.path.join(os.path.dirname(__file__), "..", "components", "heatwhisper")

def _models():
    mdir = os.path.join(TDIR, "models")
    return {f[:-5]: json.load(open(os.path.join(mdir, f)))
            for f in sorted(os.listdir(mdir)) if f.endswith(".json")}

def test_modbus40_transport_defaults():
    t = load_transports(os.path.join(TDIR, "transports.json"))
    f750 = t["F750"]
    assert f750["protocol"] == "modbus_rtu"
    assert f750["baud"] == 9600 and f750["parity"] == "NONE"
    assert f750["address"] == 1 and f750["write_fc"] == 16

def test_catalog_emits_transports_and_fc():
    from components.heatwhisper.registers import load_hints
    hdr = generate_catalog_header(_models(), load_hints(os.path.join(TDIR, "entity_hints.json")),
                                  load_transports(os.path.join(TDIR, "transports.json")))
    assert "HW_TRANSPORTS" in hdr and "HW_TRANSPORTS_N" in hdr
