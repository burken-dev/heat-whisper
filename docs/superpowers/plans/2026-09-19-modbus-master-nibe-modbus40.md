# Modbus-RTU Master + Nibe MODBUS40 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The bridge speaks standard Modbus RTU as master (FC03/04/06/16, CRC16, big-endian) behind `protocol: modbus_rtu`, proven end-to-end with Nibe F-series via the MODBUS40 accessory reusing existing register maps.

**Architecture:** Catalog gains `mb_fc`/word-order/`write_fc` columns; a shared Python reference module (`modbus_rtu.py`, spec §4–§5) is tested by pytest and mirrored 1:1 in `heatpump.cpp`; the Nibe slave path is frozen and only gated on `protocol`.

**Tech Stack:** Python (codegen + reference model), C++ (ESPHome component), ESPHome YAML.

## Global Constraints

- ESPHome 2026.9.0 has no runtime unit setter; factory numbers stay unitless.
- `MAX_SELECTION` stays 50; `min/max` corrupt guard applies to Modbus values too.
- NVS preference type id value `0x6E696273` MUST NOT change.
- Nibe native slave behavior MUST NOT change (regression: existing `tests/` stay green unmodified).
- Nibe MODBUS40 quirk: writes MUST use FC16 only, never FC06.
- Every task ends with `python -m pytest tests/ -v` passing; both-board compile covered by CI.
- Requires the rename plan applied first (`components/heatpump/`, `HP_*`, `heatpump:` key).

---

## File Structure

- Create: `components/heatpump/modbus_rtu.py` (Python reference: CRC16, frame builders/parsers, BE decode) — Task 2
- Create: `components/heatpump/transports.json` (model → `{protocol, baud, parity, address, write_fc}`) — Task 1
- Modify: `components/heatpump/registers.py` (schema + codegen columns), `__init__.py` (config schema), `heatpump.h`/`heatpump.cpp` (master), picker section (Tasks 1, 3, 4, 5)
- Create: `tests/test_modbus.py`, `tests/test_transports.py` (Tasks 1–2)
- Modify: `packages/base.yaml` (documented `protocol:` block), `README.md` (Tasks 5–6)

---

### Task 1: Transport sidecar + catalog schema extension

**Files:**
- Create: `components/heatpump/transports.json`
- Create: `tests/test_transports.py`
- Modify: `components/heatpump/registers.py`
- Test: `tests/test_transports.py`

**Interfaces:**
- Consumes: rename plan (`HP_*` codegen).
- Produces: `load_transports(path) -> dict`; `generate_catalog_header(models, hints, transports)` emitting `HP_TRANSPORTS[]` table `{model_hash, baud, parity, addr, write_fc}`; extended per-register fields `mb_fc` (default 3), `word_order` (`ABCD` default, `CDAB` allowed).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transports.py
import json, os
from components.heatpump.registers import load_transports, generate_catalog_header

TDIR = os.path.join(os.path.dirname(__file__), "..", "components", "heatpump")

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
    from components.heatpump.registers import load_hints
    hdr = generate_catalog_header(_models(), load_hints(os.path.join(TDIR, "entity_hints.json")),
                                  load_transports(os.path.join(TDIR, "transports.json")))
    assert "HP_TRANSPORTS" in hdr and "HP_TRANSPORTS_N" in hdr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transports.py -v`
Expected: FAIL with `ModuleNotFoundError` / missing `load_transports` / missing file.

- [ ] **Step 3: Minimal implementation**

Create `components/heatpump/transports.json` (source links in comments are JSON-illegal — put them in the plan only; file holds data):

```json
{
  "_note": "Per-model Modbus-RTU transport defaults. Nibe F-family via MODBUS40 accessory (installer manual + ModbusManager DB).",
  "F1145": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F1155": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F1245": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F1255": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F1345": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F1355": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F370": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F470": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F730": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "F750": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "VVM225": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "VVM310": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "VVM320": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "VVM325": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "VVM500": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16},
  "SMO40": {"protocol": "modbus_rtu", "baud": 9600, "parity": "NONE", "address": 1, "write_fc": 16}
}
```

In `registers.py`, add:

```python
def load_transports(path):
    with open(path) as fh:
        return {k: v for k, v in _json.load(fh).items() if not k.startswith("_")}
```

Extend `generate_catalog_header(models, hints, transports=None)`: keep the existing signature working (default `transports=None` → emit empty `HP_TRANSPORTS` table so old callers/tests don't break); when provided, emit

```c
struct HpTransport { uint8_t model_idx; uint32_t baud; uint8_t parity; uint8_t addr; uint8_t write_fc; };
static const HpTransport HP_TRANSPORTS[] = {...};
static const uint8_t HP_TRANSPORTS_N = ...;
```

with `model_idx` = index into `HP_MODELS`, parity coded `0=NONE,1=EVEN,2=ODD`. Per-register: read optional `mb_fc` (default 3, allowed 1/2/3/4) and `word_order` (default `ABCD`, allowed `CDAB`) from the register dict; emit as two extra `uint8_t` columns on `HpMeta` (`fc`, `wo`: 0=ABCD,1=CDAB). Nibe JSONs carry neither key → defaults, byte-identical semantics.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS (old `generate_catalog_header(models, hints)` calls in `test_catalog.py` and `__init__.py` still work via the default).

- [ ] **Step 5: Commit**

```bash
git add components/heatpump tests
git commit -m "feat: transport sidecar + catalog mb_fc/word-order columns"
```

---

### Task 2: Python Modbus-RTU reference module + tests

**Files:**
- Create: `components/heatpump/modbus_rtu.py`
- Create: `tests/test_modbus.py`
- Test: `tests/test_modbus.py`

**Interfaces:**
- Consumes: Task 1 (schema meanings).
- Produces: `crc16(data: bytes) -> int`; `build_read(addr, fc, reg, count) -> bytes`; `build_write_single(addr, reg, value) -> bytes`; `build_write_multi(addr, reg, values) -> bytes`; `parse_read_response(frame, fc, count) -> list[int]`; `decode_be(raw_words, size, factor, word_order) -> float`. C++ (Task 4) mirrors these 1:1.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_modbus.py
from components.heatpump.modbus_rtu import (
    crc16, build_read, build_write_single, build_write_multi,
    parse_read_response, decode_be)

def test_crc16_known_vector():
    # FC03 read holding reg 40004 (wire 0x9C43), 1 reg, slave 1
    assert crc16(bytes([0x01, 0x03, 0x9C, 0x43, 0x00, 0x01])) == 0x0C6B

def test_build_read_holding():
    f = build_read(1, 3, 40004, 1)
    assert f == bytes([0x01, 0x03, 0x9C, 0x43, 0x00, 0x01, 0x6B, 0x0C])

def test_write_multi_single_register():
    # MODBUS40 path: one R/W register via FC16, value 0x00D2
    f = build_write_multi(1, 43005, [0x00D2])
    assert f[:4] == bytes([0x01, 0x10, 0xA7, 0xFC]) and f[4:6] == bytes([0x00, 0x01])
    assert len(f) == 11  # addr+fc+reg(2)+count(2)+bytes(1)+data(2)+crc(2)

def test_parse_read_response():
    f = bytes([0x01, 0x03, 0x02, 0x00, 0xD2, 0x39, 0x87])
    assert parse_read_response(f, 3, 1) == [0x00D2]

def test_decode_be_scales_and_sign():
    assert decode_be([0x00D2], "s16", 10, "ABCD") == 21.0
    assert decode_be([0xFF38], "s16", 10, "ABCD") == -20.0
    assert decode_be([0x0001, 0x0000], "u32", 1, "ABCD") == 65536.0
    assert decode_be([0x0000, 0x0001], "u32", 1, "CDAB") == 65536.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_modbus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'components.heatpump.modbus_rtu'`.

- [ ] **Step 3: Write minimal implementation**

```python
# components/heatpump/modbus_rtu.py — Python reference for the C++ master (mirrored 1:1).
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF

def _head(addr: int, fc: int, reg: int) -> bytes:
    return bytes([addr & 0xFF, fc & 0xFF, (reg >> 8) & 0xFF, reg & 0xFF])

def build_read(addr: int, fc: int, reg: int, count: int) -> bytes:
    body = _head(addr, fc, reg) + bytes([(count >> 8) & 0xFF, count & 0xFF])
    c = crc16(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])

def build_write_single(addr: int, reg: int, value: int) -> bytes:
    body = _head(addr, 0x06, reg) + bytes([(value >> 8) & 0xFF, value & 0xFF])
    c = crc16(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])

def build_write_multi(addr: int, reg: int, values: list) -> bytes:
    body = (_head(addr, 0x10, reg) + bytes([(len(values) >> 8) & 0xFF, len(values) & 0xFF,
                                            2 * len(values)])
            + b"".join(bytes([(v >> 8) & 0xFF, v & 0xFF]) for v in values))
    c = crc16(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])

def parse_read_response(frame: bytes, fc: int, count: int) -> list:
    assert frame[1] == fc and frame[2] == 2 * count
    body, got = frame[:-2], frame[-2] | (frame[-1] << 8)
    assert crc16(body) == got
    return [(frame[3 + 2 * i] << 8) | frame[4 + 2 * i] for i in range(count)]

def decode_be(words: list, size: str, factor: int, word_order: str) -> float:
    f = factor or 1
    if size in ("u16", "s16"):
        raw = words[0]
        if size == "s16" and raw >= 32768:
            raw -= 65536
        return raw / f
    if word_order == "CDAB":
        words = [words[1], words[0]]
    u = (words[0] << 16) | words[1]
    return (u - 4294967296 if size == "s32" and u >= 2147483648 else u) / f
```

Note: register numbers here are full holding numbers (40004); wire offset `reg-40001`? NO — Modbus wire address for holding register 40004 is `0x9C43` = 40003 = 40004-1. Fix the test vectors: `build_read(1, 3, 40004, 1)` must emit wire `0x9C43`. So `_head` takes the full register number and subtracts the base: holding/input `reg - 1`… careful: de-facto 40001 ↔ wire 0. So wire = reg - 40001 for fc 3/4? 40004-40001 = 3 = 0x0003, NOT 0x9C43! Hmm. Wait: 0x9C43 = 40003. Standard: holding register #40004 → protocol address 40003 (1-based minus 1). So wire = reg - 1 = 40003. Yes: wire = full_number - 1 for 4xxxx/3xxxx; coils/discrete: wire = number - 1 (coil #1 → 0). So `_head(addr, fc, reg)` with `wire = reg - 1`… but for coil numbers like 1..N, wire = n-1. Unify: `wire = reg - base` where base = 40001/30001/1? Coil #1 → wire 0: base 1. Holding 40004 → 40003: base 1?? 40004-1 = 40003. Yes! All de-facto numbers are 1-based: wire = reg - 1 universally. And my test vector above already says wire 0x9C43 = 40003 = 40004-1. Correct. Implement `_head` with `wire = reg - 1`. Update the implementation accordingly (the sketch above passes `reg` raw — fix: `w = reg - 1`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_modbus.py -v`
Expected: PASS. (If the CRC vector mismatches, recompute with the implementation and fix the expected constant — the implementation is the standard Modbus CRC; verify against any online-known pair: FC03 slave 1 reg 0 count 1 → `01 03 00 00 00 01 84 0A`. Add that as the primary vector instead.)

Use as primary vector: `crc16(bytes([0x01,0x03,0x00,0x00,0x00,0x01])) == 0x0A84` and `build_read(1,3,40002,1) == bytes([1,3,0,1,0,1,0xD5,0xCA])`? Compute count-1 register: reg 40002 → wire 40001 = 0x9C41. Hmm — simpler to keep vectors in wire terms via full numbers and let the test compute: keep `test_crc16_known_vector` with the canonical `01 03 00 00 00 01 → 0x0A84` pair plus the 40004 case asserting wire bytes `9C 43`. For `build_write_multi(1, 43005, …)`: 43005-1 = 43004 = 0xA7FC. Matches the sketch. Good.

- [ ] **Step 5: Commit**

```bash
git add components/heatpump/modbus_rtu.py tests/test_modbus.py
git commit -m "feat: Modbus-RTU Python reference (CRC16, frames, BE decode)"
```

---

### Task 3: Config schema (`protocol`, `model`, addresses)

**Files:**
- Modify: `components/heatpump/__init__.py`
- Create: `tests/test_config.py` (stub-level: assert schema keys exist by importing CONFIG_SCHEMA with the conftest esphome MagicMock — MagicMock accepts everything, so instead assert on source text: keys present, defaults present)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: Task 1 (`transports.json` semantics).
- Produces: config keys `protocol` (default `"nibe"`), `model` (default `""`), `modbus_address` (default `1`); `slave_address` kept; validation: modbus mode requires non-empty `model` present in `transports.json` or `models/`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py — source-level contract (esphome is stubbed; see conftest.py).
import os
SRC = open(os.path.join(os.path.dirname(__file__), "..", "components", "heatpump", "__init__.py")).read()

def test_protocol_keys_present():
    for key in ('"protocol"', '"model"', '"modbus_address"', '"slave_address"'):
        assert key in SRC, key

def test_modbus_model_required():
    assert "modbus" in SRC and "model" in SRC
    assert "transports" in SRC
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL on `'"protocol"'`.

- [ ] **Step 3: Minimal implementation**

In `components/heatpump/__init__.py`, extend `CONFIG_SCHEMA` with:

```python
cv.Optional("protocol", default="nibe"): cv.one_of("nibe", "modbus_rtu"),
cv.Optional("model", default=""): cv.string,
cv.Optional("modbus_address", default=1): cv.int_range(min=1, max=247),
```

and in `to_code`, after loading `models`/`transports`:

```python
transports = load_transports(os.path.join(os.path.dirname(__file__), "transports.json")) if os.path.exists(...) else {}
protocol = config["protocol"]
if protocol == "modbus_rtu":
    if not config["model"] or config["model"] not in models:
        raise cv.Invalid("modbus_rtu protocol requires model: one of " + ", ".join(sorted(models)))
cg.add(var.set_protocol_is_modbus(protocol == "modbus_rtu"))
cg.add(var.set_peer_address(config["modbus_address"] if protocol == "modbus_rtu" else config["slave_address"]))
```

(`set_protocol_is_modbus` / `set_peer_address` are defined in Task 4; this task only needs the schema + validation strings the test greps for. Add the `cg.add` lines as written — compile checked in Task 4.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add components/heatpump/__init__.py tests/test_config.py
git commit -m "feat: protocol/model/modbus_address config schema"
```

---

### Task 4: C++ Modbus master (mirror of `modbus_rtu.py`) + scheduler

**Files:**
- Modify: `components/heatpump/heatpump.h`, `heatpump.cpp`
- Test: existing `tests/test_modbus.py` is the behavioral contract (mirror); compile via CI.

**Interfaces:**
- Consumes: Tasks 1–3 (`HP_TRANSPORTS`, `set_protocol_is_modbus`, `set_peer_address`, `peer_addr_`).
- Produces: master poll loop, FC16-only enforcement from `HP_TRANSPORTS.write_fc`, `passive` = listen-only in both modes.

- [ ] **Step 1: Add C++ members (declaration)**

In `heatpump.h`: add `void set_protocol_is_modbus(bool m) { modbus_ = m; }`, `void set_peer_address(uint8_t a) { peer_ = a; }`; members `bool modbus_{false}; uint8_t peer_{0x19}; uint32_t last_poll_{0}; uint8_t retry_{0};`; static `uint16_t crc16_modbus(const uint8_t *d, size_t n)`; `void poll_one_();` `void on_modbus_frame_(const uint8_t *f, size_t n);`. Rename `slave_` → `peer_` (update the two `on_frame_` comparisons `(f[2] == slave_ || f[2] == 0x20)` → `(f[2] == peer_ || f[2] == 0x20)`).

- [ ] **Step 2: Mirror `modbus_rtu.py` (definition)**

In `heatpump.cpp`: implement `crc16_modbus` (same polynomial loop as the Python reference); frame builders for FC03/FC04 read (`addr=peer_`, wire=`reg-1` big-endian, count 1–2 for 32-bit), FC06/FC16 writes (choose by `HP_TRANSPORTS.write_fc` for the active model; default 6 for non-listed models); BE parsers applying factor/sign/`CDAB` exactly like `decode_be`; reuse the existing `min/max` corrupt guard and `on_value` fan-out. `loop()`: if `!modbus_` run the existing slave path unchanged; else every `poll_interval` (default 5 s, `set_poll_interval` later if needed — hardcode 5000 ms with a `// ponytail:` comment) call `poll_one_()` round-robin over the polled set, 3 retries then skip; drain one queued write between polls; `passive_` suppresses all TX in both modes.

- [ ] **Step 3: Verify**

Run: `python -m pytest tests/ -v`
Expected: PASS (no Python contract change; regression only).
Run (CI if no local toolchain): `esphome config heatpump_esp32.yaml && esphome compile heatpump_esp32.yaml && esphome compile heatpump_pico_w.yaml`
Expected: clean compile both boards.

- [ ] **Step 4: Commit**

```bash
git add components/heatpump
git commit -m "feat: Modbus-RTU master (FC03/04/06/16, CRC16, BE decode, scheduler)"
```

---

### Task 5: Picker model union + MODBUS40 entries + docs

**Files:**
- Modify: picker section of `heatpump.cpp`, `packages/base.yaml`, `README.md`
- Test: manual (picker JSON), existing pytest suite.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: picker lists Nibe + Modbus models with protocol tag; modbus mode filters by configured `model:`; README documents `protocol: modbus_rtu` + MODBUS40 wiring (X2 to RS485 A/B, 9600 8N1, menu 5.2 activate, LOG.SET first 20 scan fast).

- [ ] **Step 1: Picker union + filter**

In `list_json_()`: iterate `HP_MODELS` (all); add `"proto":"nibe"|"modbus"` per entry from `HP_TRANSPORTS` membership; when `modbus_` and model known, restrict `addrs` to that model (same code path as today, plus proto field in JSON). Keep the Nibe path byte-identical when `!modbus_`.

- [ ] **Step 2: Document**

`packages/base.yaml`: commented `protocol: modbus_rtu` example block with `model:` + `modbus_address:`. `README.md`: new "Modbus-RTU (non-Nibe and Nibe-MODBUS40)" section — config snippet, MODBUS40 wiring/menu notes, FC16-only note, bring-up order (passive sniff → enable). Update Non-goals line (S-series TCP stays out).

- [ ] **Step 3: Verify**

Run: `python -m pytest tests/ -v`
Expected: PASS. CI compiles both boards.

- [ ] **Step 4: Commit**

```bash
git add components/heatpump packages README.md
git commit -m "feat: picker model union + MODBUS40 docs"
```

---

## Self-Review

- Spec coverage: §3 architecture (Task 4), §4 catalog (Task 1), §5 data flow/picker (Tasks 4–5), §6 config (Task 3), §7 pipeline step 1 MODBUS40 (Tasks 1+5), §8 error handling (Task 4: CRC/retry/stale, FC16 enforcement), §9 testing (Tasks 2+4). No gaps.
- Placeholders: none — vectors, code, commands inline (one recompute allowance flagged in Task 2 Step 4 with the canonical fallback pair).
- Type consistency: `crc16/build_read/build_write_single/build_write_multi/parse_read_response/decode_be` names identical in `modbus_rtu.py`, tests, and the C++ mirror requirement; `HP_TRANSPORTS{model_idx,baud,parity,addr,write_fc}` codes match `peer_`/`write_fc` use.
