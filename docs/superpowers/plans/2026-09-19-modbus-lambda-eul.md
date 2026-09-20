# Lambda EU-L Modbus-RTU Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Checked-in `Lambda_EUL.json` + `transports.json` entry for Lambda EU-L heat pumps, traceable to the official Lambda Modbus protocol PDF.

**Architecture:** A tiny checked-in converter (`scripts/convert_lambda.py`) reads a transcribed TSV (`scripts/lambda_registers.tsv`, one row per PDF table line) and emits `components/heatwhisper/models/Lambda_EUL.json` in the existing schema plus `mb_fc`/`word_order`; transport defaults merged into `transports.json`; `tests/test_lambda.py` guards schema + core registers.

**Tech Stack:** Python converter, pytest, vendor PDF (linked, not vendored).

## Global Constraints

- Current-tree paths: `components/heatwhisper/`, structs `Hw*`. If the brand-agnostic rename plan lands first, map `components/heatwhisper/` → `components/heatpump/`, `Hw` → `Hp`, `heatwhisper:` → `heatpump:`; JSON/TSV/tests content unchanged.
- Schema enums: `size` in `u8/s8/u16/s16/u32/s32`; `mode` in `R/R/W`; `mb_fc` int in `1/2/3/4` (Lambda: always 3, FC03-only reads); `word_order` in `ABCD/CDAB` (Lambda: always `ABCD`); `register`/`min`/`max` stored as strings (matches `F750.json`); `factor` int, nonzero.
- Canonical Lambda numbering: `reg = index*1000 + sub*100 + no` (e.g. HP 1/0/13 COP → `1013`; buffer 3/0/6 → `3006`; heating circuit 5/0/5 → `5005`). If the PDF revision in hand numbers differently, adjust asserts to that PDF and name the version in the commit message.
- `MAX_SELECTION` 50: picker caps; the model file may hold more registers.
- Commit message carries the PDF URL + version. Every task ends with `python -m pytest tests/ -v` passing.
- Batch-C coverage map (do NOT duplicate): Nibe MODBUS40 → master plan Task 1; Thermia/Dimplex/Daikin/Mitsu → brand-models plan Tasks 2–5; this plan → Lambda only.

---

## File Structure

- Create: `scripts/convert_lambda.py` (TSV → JSON, ~30 lines), `scripts/lambda_registers.tsv` (transcription), `components/heatwhisper/models/Lambda_EUL.json`, `tests/test_lambda.py`
- Create-or-merge: `components/heatwhisper/transports.json` (Lambda entry; merge if master plan already created it)
- Modify: `README.md` (Modbus-RTU models section, Lambda row)

---

### Task 1: Lambda failing test

**Files:**
- Create: `tests/test_lambda.py`
- Test: `tests/test_lambda.py`

**Interfaces:**
- Consumes: nothing (standalone; reads JSON + transports directly).
- Produces: `test_lambda_schema` + `test_lambda_core_registers` + `test_lambda_transport` used as green-gate by Tasks 2–3.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lambda.py -v`
Expected: FAIL with `FileNotFoundError` (`Lambda_EUL.json` missing).

- [ ] **Step 3: Commit the test**

```bash
git add tests/test_lambda.py
git commit -m "test: Lambda EU-L schema + core-register guard"
```

---

### Task 2: Transcription TSV + converter + model JSON

**Files:**
- Create: `scripts/lambda_registers.tsv`, `scripts/convert_lambda.py`
- Create: `components/heatwhisper/models/Lambda_EUL.json`
- Test: `tests/test_lambda.py::test_lambda_schema`, `::test_lambda_core_registers`

**Interfaces:**
- Consumes: Task 1 (test contract).
- Produces: `Lambda_EUL.json` sorted by register; TSV as audit trail back to the PDF.

- [ ] **Step 1: Transcribe the PDF table to TSV**

Create `scripts/lambda_registers.tsv` with header:

```
register	titel	unit	size	factor	mode	min	max	info
```

One row per PDF register, `register` = canonical `index*1000+sub*100+no` as a plain number (e.g. `1013`, `3006`, `5005`); `min`/`max` raw (unscaled, as printed); `info` = PDF section/module name (e.g. `buffer`, `heat-pump-1`, `heating-circuit-0`). Must include at minimum: `1013` COP (u16, factor 100, R), the buffer demand block `3005` type + `3006`/`3007`/`3008` (+`3009` power if the PDF lists it) with `info` `demand-block: write 3006-3008 together in one FC16`, outdoor/flow/DHW temps (R), `5005` flow setpoint (R/W), error/code registers (R), energy stats `1020`/`1021` (u32, ABCD two-word pairs). Spot-check `1013`/`3006`/`5005` against the PDF before proceeding.

- [ ] **Step 2: Write the converter**

```python
# scripts/convert_lambda.py — TSV transcription -> components/heatwhisper/models/Lambda_EUL.json
import csv
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "scripts", "lambda_registers.tsv")
DST = os.path.join(BASE, "components", "heatwhisper", "models", "Lambda_EUL.json")


def main():
    regs = []
    with open(SRC, newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            regs.append({
                "register": str(int(row["register"])),
                "factor": int(row["factor"]),
                "size": row["size"],
                "mode": row["mode"],
                "titel": row["titel"],
                "info": row.get("info", ""),
                "unit": row.get("unit", ""),
                "min": str(row.get("min", "0")),
                "max": str(row.get("max", "0")),
                "mb_fc": 3,
                "word_order": "ABCD",
            })
    regs.sort(key=lambda r: int(r["register"]))
    with open(DST, "w") as fh:
        json.dump(regs, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {len(regs)} registers to {DST}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run converter, fix rows until core asserts pass**

Run: `python3 scripts/convert_lambda.py && python -m pytest tests/test_lambda.py -v -k "schema or core"`
Expected: PASS (iterate on TSV rows, never on the test, until green).

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (current codegen ignores the new `mb_fc`/`word_order` keys until the master plan lands — forward-compatible by design).

- [ ] **Step 5: Commit**

```bash
git add scripts/convert_lambda.py scripts/lambda_registers.tsv components/heatwhisper/models/Lambda_EUL.json
git commit -m "feat: Lambda EU-L model (Modbusprotokoll v1.0.0, https://www.lambda-wp.com/fileadmin/userdaten/docs/downloads/regler/1_0_0_Modbusprotokoll.pdf)"
```

---

### Task 3: Transport entry

**Files:**
- Create-or-merge: `components/heatwhisper/transports.json`
- Test: `tests/test_lambda.py::test_lambda_transport`

**Interfaces:**
- Consumes: Task 1 (`test_lambda_transport`); master plan Task 1 if already applied (merge, don't overwrite).
- Produces: `transports.json` containing the `Lambda_EUL` entry (plus any pre-existing entries untouched).

- [ ] **Step 1: Add the entry (merge-safe)**

Run (baud/parity copied from the PDF §1 serial-settings table; if the PDF lists options, take the factory default and name it in the commit):

```bash
python3 -c "
import json, os
p = 'components/heatwhisper/transports.json'
t = json.load(open(p)) if os.path.exists(p) else {'_note': 'Per-model Modbus-RTU transport defaults.'}
t['Lambda_EUL'] = {'protocol': 'modbus_rtu', 'baud': 19200, 'parity': 'EVEN', 'address': 1, 'write_fc': 16}
json.dump(t, open(p, 'w'), indent=2)
print(open(p).read())
"
```

If the PDF §1 values differ from `19200`/`EVEN` above, use the PDF values instead and state them in the commit message.

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS, including `test_lambda_transport`.

- [ ] **Step 3: Commit**

```bash
git add components/heatwhisper/transports.json
git commit -m "feat: Lambda EU-L transport (modbus_rtu, FC16-only writes, <baud/parity per PDF §1>)"
```

---

### Task 4: README row

**Files:**
- Modify: `README.md`
- Test: existing suite (no behavior change).

**Interfaces:**
- Consumes: Tasks 2–3 (model + transport facts).
- Produces: user-visible Lambda support note with accessory (= none) and demand-block warning.

- [ ] **Step 1: Document**

If `README.md` has no `Modbus-RTU` section yet (master plan Task 5 not applied), append:

```markdown
## Modbus-RTU (non-Nibe and Nibe-MODBUS40)

Bridge acts as Modbus master; each model needs the accessory listed (if any).
`protocol: modbus_rtu` + `model:` select the map; writes use FC16 where the
vendor requires it.

| Model | Accessory | Transport | Notes |
|---|---|---|---|
| Lambda EU-L (EU08/13/15/20/35L) | none (native RTU) | see `transports.json` | Buffer demand regs 3006–3008 (+3009) must be written together in one FC16 |
```

If the section already exists, add just the Lambda table row (same columns).

- [ ] **Step 2: Run full suite**

Run: `python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: Lambda EU-L Modbus-RTU support note"
```

---

## Self-Review

- Spec coverage: §1 item 3 Lambda (Tasks 2–3: converter + JSON + transport; Task 1: tests; Task 4: docs incl. demand-block note); §2 pipeline (one script, TSV audit trail, per-task pytest gate, commit cites PDF); §4 (no code change needed — `mb_fc: 3`/`ABCD` ride the master plan's columns; suite stays green). Other §1 items map to pre-existing plans, no gaps.
- Placeholders: none — TSV columns, converter, tests, merge command, README text all inline; the two PDF-dependent values (baud/parity, revision numbering) have explicit read-from-PDF procedures with fallbacks.
- Type consistency: `register`/`min`/`max` strings, `factor` int, `mb_fc: 3` int, `word_order: "ABCD"` match the committed test and `F750.json` conventions; `Lambda_EUL` key identical across JSON filename, test, and transport entry.
