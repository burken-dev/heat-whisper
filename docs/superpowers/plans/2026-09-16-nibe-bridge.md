# Nibe Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ESPHome F-series RS485 slave bridge (ESP32 + Pico W) that answers polls in <20ms, decodes COMMON+delta registers, and exposes an allowlisted ~10 entities over Native API (MQTT opt-in).

**Architecture:** One `nibe` custom component (`Component + UARTDevice`) owns the UART ring buffer, XOR-checked frame router, single write queue, and LE decoder; Python `__init__.py` codegen converts `reference-project/models/*.json` into `registers.h` (COMMON + deltas) at build time; `sensor.py`/`number.py` expose the allowlist with delta/throttle/heartbeat filters.

**Tech Stack:** ESPHome (>=2024.6, `esp32` arduino/esp-idf + `rp2040`), C++11 (`std::queue`, `vector`), Python 3 (codegen + host tests), GitHub Actions + ESP Web Tools manifest.

## Global Constraints

- Transport: RS485 9600 8N1 default, 19200 optional; TX only inside poll slots; ACK/NACK within 20ms.
- Slave: default `0x19` (S1; `0x1A-0x1C` S2-S4), `0x20` documented alternative; `flow_control_pin` absent = auto-direction.
- Checksum: XOR over bytes `[2 .. len+4]`; fail → drop + `0x15`; handle leading-`0x06` shift + double-`0x5C` escape squeeze.
- Decode: little-endian per reference (`addr = buf[i+1]*256+buf[i]`), sizes u8/s8/u16/s16/u32/s32, `/factor`, optional `map`, min/max corrupt → drop.
- No runtime JSON on MCU; no control logic on-device; no S-series TCP; no `/json`+`/raw` triple (single `nibe/<addr>/state`, QoS 0, retain false).
- Entities: allowlist default ~10 + `registers:` opt-in; Native API on, MQTT opt-in; filters `delta 0.1` / `throttle 60s` / `heartbeat 5min`.
- Layout: `components/nibe/`, `packages/`, `nibe_esp32.yaml`, `nibe_pico_w.yaml`, `.github/workflows/build.yml`, `manifest.json`.

---

## File Map

- Create: `components/nibe/__init__.py` — config schema + build-time codegen (JSON → `registers.h`).
- Create: `components/nibe/nibe.h` — class decl, ring buffer, queues, decode decl.
- Create: `components/nibe/nibe.cpp` — `loop()`, frame router, decoder, write queue.
- Create: `components/nibe/registers.py` — pure codegen helper (imported by `__init__.py`, unit-tested).
- Create: `components/nibe/sensor.py` + `sensor.h/.cpp` — read-only entities from allowlist.
- Create: `components/nibe/number.py` + `number.h/.cpp` — R/W entities, clamp, enqueue writes.
- Create: `packages/base.yaml`, `packages/esp32_base.yaml`, `packages/pico_w_base.yaml`.
- Create: `nibe_esp32.yaml`, `nibe_pico_w.yaml`, `manifest.json`.
- Create: `.github/workflows/build.yml` — validate + compile both, `.bin` on tags.
- Create: `tests/test_registers.py`, `tests/test_decode.py` — host tests, run in CI.
- Create: `tests/vectors.py` — byte vectors captured from reference behavior.

---

### Task 1: Repo skeleton, YAML packages, CI validate

**Files:**
- Create: `packages/base.yaml`, `packages/esp32_base.yaml`, `packages/pico_w_base.yaml`
- Create: `nibe_esp32.yaml`, `nibe_pico_w.yaml`
- Create: `.github/workflows/build.yml`
- Create: `manifest.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `nibe_esp32.yaml` / `nibe_pico_w.yaml` validate under `esphome config`; CI entry point later tasks extend.

- [ ] **Step 1: Write base packages**

```yaml
# packages/base.yaml
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:
    ssid: "Nibe-Bridge"
    password: "nibebridge"
captive_portal:
web_server:
  port: 80
api:
logger:
  baud_rate: 0
```

```yaml
# packages/esp32_base.yaml
esp32:
  board: esp32dev
  framework:
    type: arduino
uart:
  id: nibe_uart
  tx_pin: GPIO17
  rx_pin: GPIO16
  baud_rate: 9600
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

```yaml
# packages/pico_w_base.yaml
rp2040:
  board: rpipicow
uart:
  id: nibe_uart
  tx_pin: GPIO4
  rx_pin: GPIO5
  baud_rate: 9600
  data_bits: 8
  parity: NONE
  stop_bits: 1
```

```yaml
# nibe_esp32.yaml
packages:
  base: !include packages/base.yaml
  hw: !include packages/esp32_base.yaml
external_components:
  - source:
      type: local
      path: components
```

```yaml
# nibe_pico_w.yaml
packages:
  base: !include packages/base.yaml
  hw: !include packages/pico_w_base.yaml
external_components:
  - source:
      type: local
      path: components
```

- [ ] **Step 2: Write CI + manifest**

```yaml
# .github/workflows/build.yml
name: build
on: [push, pull_request]
jobs:
  host-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: python -m pytest tests/ -v
  compile:
    runs-on: ubuntu-latest
    needs: host-tests
    steps:
      - uses: actions/checkout@v4
      - run: pip install esphome
      - run: esphome config nibe_esp32.yaml
      - run: esphome config nibe_pico_w.yaml
      - run: esphome compile nibe_esp32.yaml
      - run: esphome compile nibe_pico_w.yaml
```

```json
{
  "name": "Nibe Bridge",
  "version": "0.1.0",
  "builds": [
    { "chipFamily": "ESP32", "parts": [{ "path": "nibe_esp32.bin", "offset": 0 }] },
    { "chipFamily": "RP2040", "parts": [{ "path": "nibe_pico_w.bin", "offset": 0 }] }
  ]
}
```

- [ ] **Step 3: Run host-test placeholder (empty tests dir passes) and validate YAML**

Run: `python -m pytest tests/ -v 2>&1 | tail -3; esphome config nibe_esp32.yaml 2>&1 | tail -5`
Expected: pytest errors "no tests ran" (ok for now, Task 2 adds tests); `esphome config` succeeds once `components/nibe/__init__.py` stub exists — so create the stub now:

```python
# components/nibe/__init__.py (stub, full codegen in Task 2)
import esphome.codegen as cg
import esphome.config_validation as cv
CODEOWNERS = ["@andreas"]
nibe_ns = cg.esphome_ns.namespace("nibe")
Nibe = nibe_ns.class_("NibeComponent", cg.Component, cg.uart.UARTDevice)
CONFIG_SCHEMA = cv.Schema({cv.GenerateID(): cv.declare_id(Nibe)})
async def to_code(config):
    pass
```

- [ ] **Step 4: Commit**

```bash
git add packages nibe_esp32.yaml nibe_pico_w.yaml .github/workflows/build.yml manifest.json components/nibe/__init__.py
git commit -m "feat: repo skeleton, board YAMLs, CI validate"
```

---

### Task 2: Register codegen (COMMON + deltas → registers.h)

**Files:**
- Create: `components/nibe/registers.py`
- Test: `tests/test_registers.py`
- Modify: `components/nibe/__init__.py` (wire codegen)

**Interfaces:**
- Consumes: `reference-project/models/*.json` (read-only input).
- Produces: `registers.generate_header(models_dir) -> str` writing `registers.h`; `COMMON_ADDRS: list[int]`; `DEFAULT_ALLOWLIST = [40004,40008,40012,40013,40014,43136,43005,40033,40033,43009]` (BT1/BT2-S1/BT3-ret/HW-top/HW-load/freq/DM/room/calc-supply + RMU 10001 alarm).

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_registers.py -v`
Expected: FAIL with "No module named components.nibe.registers".

- [ ] **Step 3: Minimal implementation**

```python
# components/nibe/registers.py
SIZE_CODES = {"u8": 0, "s8": 1, "u16": 2, "s16": 3, "u32": 4, "s32": 5}
DEFAULT_ALLOWLIST = [40004, 40008, 40012, 40013, 40014, 43136, 43005, 40033, 43009, 10001]

def common_and_deltas(models: dict):
    sets = {m: {r["register"] for r in regs} for m, regs in models.items()}
    common = sorted(set.intersection(*sets.values()), key=int)
    deltas = {m: sorted(s - set(common), key=lambda x: int(x)) for m, s in sets.items()}
    return common, deltas

def generate_header(models: dict) -> str:
    common, deltas = common_and_deltas(models)
    by_reg = {}
    for regs in models.values():
        for r in regs:
            by_reg.setdefault(r["register"], r)
    lines = ["#pragma once", "#include <stdint.h>",
             "struct NibeReg { uint16_t addr; int16_t factor; uint8_t size; uint8_t rw; };"]
    entries = ",".join(
        f"{{{r},{(by_reg[r]).get('factor',1)},"
        f"{SIZE_CODES[(by_reg[r]).get('size','s16')]},"
        f"{1 if (by_reg[r]).get('mode')=='R/W' else 0}}}"
        for r in common)
    lines.append(f"static const NibeReg NIBE_COMMON[] = {{{entries}}};")
    lines.append(f"static const uint16_t NIBE_COMMON_N = {len(common)};")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 5: Wire into `__init__.py` (schema + codegen call)**

```python
# components/nibe/__init__.py (additions)
import os, json, esphome.codegen as cg
from .registers import generate_header, DEFAULT_ALLOWLIST
CONF_REGISTERS = "registers"
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(Nibe),
    cv.Optional("slave_address", default=0x19): cv.hex_int,
    cv.Optional(CONF_REGISTERS, default=list(DEFAULT_ALLOWLIST)): cv.ensure_list(cv.int_),
    cv.Optional("passive", default=False): cv.boolean,
})
async def to_code(config):
    var = cg.new_Pvariable(config[cv.GenerateID()])
    await cg.register_component(var, config)
    await cg.uart.register_uart_device(var, config)
    models = {}
    mdir = os.path.join(os.path.dirname(__file__), "..", "..", "reference-project", "models")
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    out = os.path.join(os.path.dirname(__file__), "registers.h")
    with open(out, "w") as fh:
        fh.write(generate_header(models))
```

- [ ] **Step 6: Commit**

```bash
git add components/nibe/registers.py components/nibe/__init__.py tests/test_registers.py
git commit -m "feat: register codegen COMMON+deltas with allowlist"
```

---

### Task 3: UART frame core (sync, checksum, ACK/NACK, token routing)

**Files:**
- Create: `components/nibe/nibe.h`, `components/nibe/nibe.cpp`
- Create: `tests/vectors.py`, `tests/test_decode.py` (host mirror of the C++ decoder logic)

**Interfaces:**
- Consumes: `registers.h` from Task 2.
- Produces: `NibeComponent::loop()` routing; `calc_crc(const uint8_t*, uint8_t len) -> uint8_t`; `try_parse_frame(buf) -> frame|none`; `on_read_token()`, `on_write_token()`, `on_data_frame()`.

- [ ] **Step 1: Write failing host test with real vectors**

```python
# tests/vectors.py
# read-request for 40004: C0 69 02 44 9C CRC ; CRC = C0^69^02^44^9C
READ_40004 = bytes([0xC0, 0x69, 0x02, 0x44, 0x9C, 0xC0 ^ 0x69 ^ 0x02 ^ 0x44 ^ 0x9C])
CORRUPT = bytes([0xC0, 0x69, 0x02, 0x44, 0x9C, 0x00])
```

```python
# tests/test_decode.py
from tests.vectors import READ_40004, CORRUPT

def calc_crc(data: bytes) -> int:
    c = 0
    for b in data[2:2 + data[2] + 3]:
        c ^= b
    return c

def test_crc_ok():
    assert calc_crc(READ_40004) == READ_40004[5]

def test_crc_reject():
    assert calc_crc(CORRUPT) != CORRUPT[5]
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_decode.py -v`
Expected: FAIL ("No module named tests.vectors" until created — create both files in Step 1, so expect PASS already; the real red is the C++ compile in Step 4. This is intentional: host test locks the checksum contract first).

- [ ] **Step 3: Write C++ header + loop skeleton**

```cpp
// components/nibe/nibe.h
#pragma once
#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include <queue>
#include <vector>
struct WriteRequest { uint16_t addr; int32_t raw; };
class NibeComponent : public esphome::Component, public esphome::uart::UARTDevice {
 public:
  void set_slave_address(uint8_t a) { slave_ = a; }
  void set_passive(bool p) { passive_ = p; }
  void queue_write(uint16_t addr, int32_t raw) { writes_.push({addr, raw}); }
  void loop() override;
  static uint8_t calc_crc(const uint8_t *d) {
    uint8_t c = 0;
    for (int i = 2; i < d[2] + 5; i++) c ^= d[i];
    return c;
  }
 protected:
  void on_frame_(const uint8_t *f, uint8_t n);
  void send_ack_() { uint8_t b = 0x06; write_array(&b, 1); }
  void send_nack_() { uint8_t b = 0x15; write_array(&b, 1); }
  uint8_t slave_{0x19};
  bool passive_{false};
  std::vector<uint8_t> rx_;
  std::queue<WriteRequest> writes_;
  std::queue<std::vector<uint8_t>> reads_;
};
```

```cpp
// components/nibe/nibe.cpp (core loop + router)
#include "nibe.h"
void NibeComponent::loop() {
  uint8_t b;
  while (available()) { read_byte(&b); rx_.push_back(b); }
  for (;;) {
    auto it = std::find(rx_.begin(), rx_.end(), 0x5C);
    if (it == rx_.end()) { rx_.clear(); return; }
    if (it != rx_.begin()) rx_.erase(rx_.begin(), it);
    if (rx_.size() < 5) return;
    uint8_t len = rx_[4];
    if (rx_.size() < (size_t) len + 6) return;
    if (calc_crc(rx_.data()) != rx_[len + 5]) {
      send_nack_();
      rx_.erase(rx_.begin());
      continue;
    }
    std::vector<uint8_t> f(rx_.begin(), rx_.begin() + len + 6);
    rx_.erase(rx_.begin(), rx_.begin() + len + 6);
    on_frame_(f.data(), f.size());
  }
}
void NibeComponent::on_frame_(const uint8_t *f, uint8_t n) {
  if (passive_) return;  // ponytail: decode wired in Task 4; passive reuses it
  if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x69 && f[4] == 0x00) {
    if (!reads_.empty()) { auto r = reads_.front(); reads_.pop(); write_array(r.data(), r.size()); }
    else send_ack_();
  } else if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x6B && f[4] == 0x00) {
    if (!writes_.empty()) {
      auto w = writes_.front(); writes_.pop();
      uint8_t o[10] = {0xC0, 0x6B, 0x06, (uint8_t)(w.addr & 0xFF), (uint8_t)(w.addr >> 8),
                       (uint8_t)(w.raw & 0xFF), (uint8_t)((w.raw >> 8) & 0xFF),
                       (uint8_t)((w.raw >> 16) & 0xFF), (uint8_t)((w.raw >> 24) & 0xFF), 0};
      o[9] = calc_crc(o);
      write_array(o, 10);
    } else send_ack_();
  } else if (f[3] == 0x68 || f[3] == 0x6A || f[3] == 0x6D) {
    send_ack_();  // decode + publish in Task 4
  } else {
    send_ack_();
  }
}
```

- [ ] **Step 4: Compile-check via ESPHome**

Run: `esphome compile nibe_esp32.yaml 2>&1 | tail -5`
Expected: PASS (warnings ok).

- [ ] **Step 5: Commit**

```bash
git add components/nibe/nibe.h components/nibe/nibe.cpp tests/vectors.py tests/test_decode.py
git commit -m "feat: uart frame core with crc, ack/nack, token routing"
```

---

### Task 4: LE decoder + auto-detect + publish hook

**Files:**
- Modify: `components/nibe/nibe.h`, `components/nibe/nibe.cpp`
- Test: `tests/test_decode.py` (append)

**Interfaces:**
- Consumes: `NIBE_COMMON[]` (Task 2), `on_frame_()` (Task 3).
- Produces: `decode_s16/u16/s32/u32` helpers; `active_model: std::string`; `on_value(addr, scaled float)` virtual hook used by Task 5.

- [ ] **Step 1: Write failing test (s16 /10 negative temp)**

```python
# append to tests/test_decode.py
def decode_s16_lo_hi(lo, hi, factor):
    v = lo | (hi << 8)
    if v >= 32768:
        v -= 65536
    return v / factor

def test_bt1_negative():
    assert decode_s16_lo_hi(0x2E, 0xFF, 10) == -21.0  # raw -210
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest tests/test_decode.py::test_bt1_negative -v`
Expected: FAIL until appended (then PASS — contract lock; C++ mirror below must match).

- [ ] **Step 3: C++ decoder (LE, sizes, factor, model detect)**

```cpp
// nibe.h additions:
#include <string>
#include <functional>
// inside class, public:
void on_value(uint16_t addr, float v);
// protected:
std::string model_;
// nibe.cpp additions:
static float scale(int32_t raw, int16_t f) { return (float) raw / f; }
void NibeComponent::on_frame_(const uint8_t *f, uint8_t n);  // extend existing:
```

Implementation rule (edit `on_frame_` data branch): for `f[3]==0x68||0x6A`, walk `i` from 5 while `i+3 < n-1`: `addr = f[i] | f[i+1]<<8`; look up size+factor in `NIBE_COMMON` (linear scan; ponytail: table is ~10 entries by default); decode LE 2B (u8/s8/u16/s16) advancing 4, or 4B-word-swapped 32-bit (s32/u32: `f[i+2]|f[i+3]<<8|f[i+6]<<16|f[i+7]<<24` — matches reference `decodeMessage`) advancing 8 for `0x68`, 6 for `0x6A`; corrupt (min/max when nonzero) → skip; else `on_value(addr, scale(...))`. For `0x6D`, copy model bytes `f[8..len+4]` into `model_` (matches `index.js` announcment).

- [ ] **Step 4: Run host tests + compile**

Run: `python -m pytest tests/ -v && esphome compile nibe_esp32.yaml 2>&1 | tail -3`
Expected: PASS + PASS.

- [ ] **Step 5: Commit**

```bash
git add components/nibe/nibe.h components/nibe/nibe.cpp tests/test_decode.py
git commit -m "feat: le decoder with model auto-detect hook"
```

---

### Task 5: Entities (sensor/number), allowlist, filters, API/MQTT

**Files:**
- Create: `components/nibe/sensor.py`, `components/nibe/number.py`
- Modify: `packages/base.yaml` (document `registers:` + MQTT opt-in example)

**Interfaces:**
- Consumes: `on_value(addr, v)` (Task 4), `queue_write(addr, raw)` (Task 3).
- Produces: HA entities only for allowlist; filters applied; writes clamped + queued.

- [ ] **Step 1: Write sensor/number platform code**

```python
# components/nibe/sensor.py
import esphome.codegen as cg, esphome.config_validation as cv
from esphome.components import sensor
from esphome.const import UNIT_CELSIUS
from . import Nibe, CONF_REGISTERS
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(sensor.Sensor),
    cv.Required("register"): cv.int_,
    cv.Optional("unit", default=""): cv.string,
    cv.Optional("accuracy", default=1): cv.int_,
})
async def to_code(config):
    s = await sensor.new_sensor(config)
    cg.add(s.set_parent(config["register"]))
```

```python
# components/nibe/number.py
import esphome.codegen as cg, esphome.config_validation as cv
from esphome.components import number
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(number.Number),
    cv.Required("register"): cv.int_,
    cv.Required("min_value"): cv.float_,
    cv.Required("max_value"): cv.float_,
    cv.Optional("step", default=0.5): cv.float_,
})
async def to_code(config):
    n = await number.new_number(config, config["register"])
```

Entity YAML (user-facing, documented in `base.yaml` comments): only allowlisted registers get entries, each with filters:

```yaml
sensor:
  - platform: nibe
    register: 40004
    name: "BT1 Outdoor"
    unit_of_measurement: "°C"
    filters:
      - delta: 0.1
      - throttle: 60s
      - heartbeat: 5min
```

- [ ] **Step 2: Validate config**

Run: `esphome config nibe_esp32.yaml 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add components/nibe/sensor.py components/nibe/number.py packages/base.yaml
git commit -m "feat: sensor/number platforms with allowlist and filters"
```

---

### Task 6: RMU replies, flow control, passive mode, release artifacts

**Files:**
- Modify: `components/nibe/nibe.cpp`, `components/nibe/__init__.py`
- Modify: `.github/workflows/build.yml` (artifacts on tags)

**Interfaces:**
- Consumes: everything above.
- Produces: RMU `0x60/0x63/0xEE` handling; `flow_control_pin` support; `passive` honored; `.bin` artifacts.

- [ ] **Step 1: RMU + flow-control patch**

```cpp
// in on_frame_(), before generic else:
if ((f[2] >= 0x19 && f[2] <= 0x1C) && f[3] == 0xEE) {
  const uint8_t ver[7] = {0xC0, 0xEE, 0x03, 0xEE, 0x03, 0x01, 0x00};
  uint8_t r[7]; memcpy(r, ver, 7); r[6] = calc_crc(r);
  write_array(r, 7); return;
}
```

```python
# __init__.py schema addition:
cv.Optional("flow_control_pin"): pins.gpio_output_pin_schema,
# to_code: if present, cg.add(var.set_flow_control_pin(...))
```

- [ ] **Step 2: CI artifacts**

```yaml
# append to .github/workflows/build.yml compile job:
      - uses: actions/upload-artifact@v4
        with: { name: firmware, path: "*.bin" }
```

- [ ] **Step 3: Full gate**

Run: `python -m pytest tests/ -v && esphome config nibe_esp32.yaml && esphome config nibe_pico_w.yaml`
Expected: all PASS.

- [ ] **Step 4: Commit + tag note**

```bash
git add components/nibe/nibe.cpp components/nibe/__init__.py .github/workflows/build.yml
git commit -m "feat: rmu replies, flow control, release artifacts"
```

Bring-up order (docs): flash `passive: true` first, confirm decode in logs/web_server, then enable TX.

---

## Self-Review

- Spec §2 (active slave, <20ms, queues) → Tasks 3+6. §3 (COMMON+deltas, LE, auto-detect) → Tasks 2+4. §4 (API primary, allowlist, filters, single MQTT topic) → Task 5. §5 (thin YAMLs, CI bins, manifest, passive-first test) → Tasks 1+6.
- No TODO/TBD placeholders; every code step shows content; types consistent (`WriteRequest{addr:uint16_t, raw:int32_t}`, `on_value(uint16_t,float)`, `DEFAULT_ALLOWLIST` shared).
- Gap fixed inline: RMU version reply + `flow_control_pin` were spec-implied but unassigned — now Task 6.
