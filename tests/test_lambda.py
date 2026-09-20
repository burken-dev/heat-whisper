# tests/test_lambda.py
import json
import os

TDIR = os.path.join(os.path.dirname(__file__), "..", "components", "heatwhisper")
MDIR = os.path.join(TDIR, "models")


def _regs():
    with open(os.path.join(MDIR, "Lambda_EUL.json")) as fh:
        return {r["register"]: r for r in json.load(fh)}


def test_lambda_schema():
    regs = _regs()
    assert len(regs) > 20
    seen = set()
    for addr, r in regs.items():
        assert r["size"] in ("u8", "s8", "u16", "s16", "u32", "s32"), r
        assert r["mode"] in ("R", "R/W"), r
        assert r.get("mb_fc", 3) == 3, r  # Lambda reads are FC03-only
        assert r.get("word_order", "ABCD") == "ABCD", r
        assert int(r["factor"]) != 0, r
        assert r.get("titel"), r
        assert addr not in seen, r
        seen.add(addr)


def test_lambda_core_registers():
    m = _regs()
    assert m["1013"]["size"] == "u16" and m["1013"]["mode"] == "R"  # COP, [0.01]
    assert int(m["1013"]["factor"]) == 100
    for addr in ("3006", "3007", "3008"):  # buffer demand block, [0.1C], one FC16
        assert m[addr]["mode"] == "R/W", addr
        assert m[addr]["size"] == "s16", addr
        assert int(m[addr]["factor"]) == 10, addr
    assert m["5005"]["mode"] == "R/W"  # heating-circuit flow setpoint


def test_lambda_transport():
    with open(os.path.join(TDIR, "transports.json")) as fh:
        t = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
    lam = t["Lambda_EUL"]
    assert lam["protocol"] == "modbus_rtu"
    assert lam["address"] == 1 and lam["write_fc"] == 16  # PDF: writes are FC16-only
    assert lam["baud"] in (9600, 19200, 38400, 57600, 115200), lam
    assert lam["parity"] in ("NONE", "EVEN", "ODD"), lam
