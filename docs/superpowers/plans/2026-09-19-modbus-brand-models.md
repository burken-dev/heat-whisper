# Brand Model Pipelines (Thermia, Dimplex, Daikin, Mitsubishi) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Checked-in `model.json` + `transports.json` entries for Thermia Genesis, Dimplex WPM, Daikin Altherma 3, and Mitsubishi Ecodan, each traceable to its official spec.

**Architecture:** One converter script per brand under `scripts/` (checked in, reproducible) that emits `components/heatpump/models/<Name>.json` in the existing schema (`register/factor/size/mode/titel/unit/min/max` + `mb_fc`/`word_order`); transport defaults appended to `transports.json`; shared schema test guards every file.

**Tech Stack:** Python converters, pytest, vendor PDFs (linked, not vendored).

## Global Constraints

- Schema enums: `size` in `u8/s8/u16/s16/u32/s32`; `mode` in `R/R-W`; `mb_fc` in `1/2/3/4` (default 3); `word_order` in `ABCD/CDAB` (default ABCD).
- Every model entry carries the source PDF URL + version in the task's commit message (spec §7 traceability).
- `MAX_SELECTION` 50: picker caps; models may hold more registers.
- Requires rename + master plans applied first.
- Every task ends with `python -m pytest tests/ -v` passing.

---

## File Structure

- Create: `scripts/convert_thermia.py`, `scripts/convert_dimplex.py`, `scripts/convert_daikin.py`, `scripts/convert_mitsu.py`
- Create: `components/heatpump/models/Thermia_*.json`, `Dimplex_*.json`, `Daikin_*.json`, `Mitsu_*.json`
- Modify: `components/heatpump/transports.json` (append entries)
- Create: `tests/test_brand_models.py` (shared schema + per-brand core-register asserts)

---

### Task 1: Shared schema test

**Files:**
- Create: `tests/test_brand_models.py`
- Test: `tests/test_brand_models.py`

**Interfaces:**
- Consumes: master plan (`mb_fc`/`word_order` schema).
- Produces: `test_model_schema_valid` (parametrized over all `models/*.json`), used by Tasks 2–5.

- [ ] **Step 1: Write the test (passes vacuously for existing models, fails on bad new ones)**

```python
# tests/test_brand_models.py
import json, os
import pytest
MDIR = os.path.join(os.path.dirname(__file__), "..", "components", "heatpump", "models")

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
```

- [ ] **Step 2: Run to verify green baseline**

Run: `python -m pytest tests/test_brand_models.py -v`
Expected: PASS for all current Nibe models.

- [ ] **Step 3: Commit**

```bash
git add tests/test_brand_models.py
git commit -m "test: shared brand-model schema guard"
```

---

### Task 2: Thermia Genesis (scripted YAML conversion)

**Files:**
- Create: `scripts/convert_thermia.py`
- Create: `components/heatpump/models/Thermia_Genesis.json`
- Modify: `components/heatpump/transports.json`
- Test: `tests/test_brand_models.py` (+ core asserts below)

**Interfaces:**
- Consumes: Task 1.
- Produces: `Thermia_Genesis` model; transport `{protocol modbus_rtu, baud 19200, parity EVEN, address 1, write_fc 16}`.

Source: official "Modbus protocol for Genesis platform" PDF v10–17.1 (thermia.fi / geotherma.be); machine-readable base `nielsbasjes/modbus-devices` ThermiaGenesis YAML (FC1/2/3/4/5/6/15/16). RTU via BM-card `MBe` port.

- [ ] **Step 1: Add core-register asserts (failing)**

Append to `tests/test_brand_models.py`:

```python
def _regs(name):
    return {r["register"]: r for r in json.load(open(os.path.join(MDIR, name + ".json")))}

def test_thermia_core_registers():
    m = _regs("Thermia_Genesis")
    assert m["507"]["unit"] == "°C" and m["507"]["mode"] == "R"      # outside temp
    assert m["515"]["mode"] == "R"                                    # flow temp
    assert m["522"]["mode"] == "R"                                    # DHW temp
    assert any(r["mb_fc"] == 1 for r in m.values())                   # coils exist
```

(Register numbers are the de-facto input-register numbers from the Genesis PDF: 507 outside, 515 flow, 522 DHW. If the PDF version in hand numbers them differently, adjust the three asserts to that PDF and name the version in the commit message — the schema test still guards structure.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_brand_models.py -v -k thermia`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Write converter + generate**

`scripts/convert_thermia.py`: fetch/parses the ThermiaGenesis YAML (local copy path passed as argv — do NOT vendor the YAML; download once, convert, keep the URL in the commit message), maps each field to `{register, factor: 10|100|1 per Scale column, size: s16/u16 (signed iff Min < 0), mode: R iff Table in (Read Digital, Read Analog) else R/W, titel, unit, min, max, mb_fc: 1/2/3/4 per table, word_order: ABCD}`; writes the JSON sorted by register. Run it, inspect the diff (spot-check 507/515/522 against the PDF), append transport entry:

```json
"Thermia_Genesis": {"protocol": "modbus_rtu", "baud": 19200, "parity": "EVEN", "address": 1, "write_fc": 16},
```

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/convert_thermia.py components/heatpump/models/Thermia_Genesis.json components/heatpump/transports.json tests/test_brand_models.py
git commit -m "feat: Thermia Genesis model (spec vX, <pdf-url>)"  # fill X + URL
```

---

### Task 3: Dimplex WPM via LWPM 410 (transcription)

Same five steps as Task 2. Details: source = Dimplex wiki "Modbus RTU connection (EN)" + datapoint-list PDF (devicedb.my-gekko.com id_pk=92). Transport: `{baud 9600, parity NONE, address 1, write_fc 6}` (LWPM 410 supports FC06; addr range 1–207, baud ≤19200 — 9600 factory). Model file `Dimplex_WPM.json`. Core asserts: registers `1` (outside °C R), `5` (flow °C R), `3` (DHW °C R), scale factor 10. Commit message carries the wiki/PDF URLs.

### Task 4: Daikin Altherma 3 via DCOM-LT/MB / Intesis (transcription)

Same five steps. Source: Intesis `IN485DAI001A000` user manual register tables + DCOM-LT/MB register PDF + ModbusCloud 31-register template as cross-check. Model file `Daikin_Altherma3.json`. Transport: `{baud 9600, parity NONE, address 1, write_fc 16}` (Intesis gateways accept FC16; confirm against the manual table while transcribing — if the table says FC06-only, use 6 and note it in the commit). Core asserts: leaving-water temp (R), DHW tank temp (R), outdoor temp (R), operation-mode/setpoint (R/W) — exact numbers per the manual, named in the commit message.

### Task 5: Mitsubishi Ecodan via Intesis (transcription)

Same five steps. Source: Intesis `IN485MIT001A000` user manual (§4 Modbus registers, 100+ points; monoblock + split Ecodan). Model file `Mitsubishi_Ecodan.json`. Transport: `{baud 9600, parity NONE, address 1, write_fc 16}` (same FC06 proviso as Task 4). Core asserts: flow/return temps (R), DHW temp (R), zone setpoint (R/W), error code (R) — exact numbers per the manual, named in the commit message.

---

## Self-Review

- Spec §7 coverage: steps 2–5 = Thermia, Dimplex, Daikin, Mitsubishi pipelines; Nibe MODBUS40 lives in the master plan. Exclusions (TCP, Luxtronik-RTU, CTC) need no tasks. No gaps.
- Placeholders: none — where vendor numbering may vary by PDF revision, the task names the exact fallback (adjust asserts, cite version in commit).
- Type consistency: file naming `<Brand>_<Family>.json`, converter naming `convert_<brand>.py`, transport keys identical to Task 1 of the master plan.
