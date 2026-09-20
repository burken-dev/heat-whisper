# Second-Brand Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one more heat-pump brand next to Nibe F-series without touching the Nibe wire path, behind a `brand:` config key defaulting to current behavior.

**Architecture:** Freeze `nibe.h` as-is; add a brand-pure `<brand>.h` plus a small `Bus` seam (`bus.h`) that owns all wire bytes; `HeatWhisperComponent` keeps entities/picker/NVS and becomes a `BusListener`. Each task lands tested and committable on its own.

**Tech Stack:** C++17 header-heavy ESPHome component, Python codegen/tests, host `g++ -Wall -Werror` harnesses (existing `tests/test_nibe.py` pattern), `esphome config`/`compile` for ESP32 + Pico W.

## Global Constraints

- Default `brand: nibe_f` reproduces current behavior byte-for-byte; Nibe path is move-only, never rewritten.
- `nibe.h` (`components/heatwhisper/nibe.h`) is frozen: `esphome::heatwhisper::nibe::{calc_crc_5c,calc_crc_c0,encode_poll,encode_write,is_writable,parse_model,build_rmu63,build_rmu_version}`.
- New brand headers are host-compilable: no `UARTDevice`, `ESP_LOG`, `App.`, `Component.h`, `uart/uart.h` (enforced by `test_acme.py` step, same gate as `test_nibe.py`).
- NVS compat: `HW_SEL_TYPE 0x6E696273UL`, `HeatWhisperSelection` version 1, `static_assert(sizeof == 108)`, `HW_MAX_SELECTION 50` — none change.
- ESPHome 2026.9.0 has no runtime unit setter: entity factory stays numeric-traits only.
- No runtime JSON on MCU: brand maps ship via `registers.py` → `catalog.h` codegen, same as today.
- No new dependencies (OS, pip, or ESPHome libs).
- Every task ends with `python -m pytest tests/ -q` green; Tasks 3–5 also end with `esphome config heatwhisper_esp32.yaml` clean.
- Hardware TX only after `passive: true` decode-verified bring-up (README recipe).
- Slug rule: `acme` below is the stand-in. Task 1 Step 1 renames it to the real brand slug (lowercase, alnum); all later references mean the renamed slug.

---

## File Structure

- Create: `components/heatwhisper/bus.h` — `Bus` + `BusListener` seam, TX sink type, no ESPHome deps.
- Create: `components/heatwhisper/nibe_bus.h` (maybe + `nibe_bus.cpp`) — `NibeBus : Bus`, moved `loop()`/`on_frame_()` bodies on top of `nibe::*`.
- Create: `components/heatwhisper/acme.h` — brand-pure wire helpers, same shape as `nibe.h`.
- Create: `components/heatwhisper/acme_bus.h` (maybe + `acme_bus.cpp`) — `AcmeBus : Bus`.
- Create: `components/heatwhisper/models_acme/*.json` (or same `models/` dir with brand-prefixed filenames — keep `models/`, prefix files `ACME_*`).
- Create: `tests/vectors_acme.py`, `tests/test_acme.py`.
- Modify: `components/heatwhisper/heatwhisper.{h,cpp}` — own a `Bus*`, implement `BusListener::on_value`, delegate wire to bus.
- Modify: `components/heatwhisper/__init__.py` — `brand` config key + pass-through.
- Modify: `packages/base.yaml` docs comment, `README.md` (Non-goals line), `tests/test_final_fixes.py` + `tests/test_rmu.py` only if they pin moved literals (repoint at seam like the `nibe::is_writable` precedent).

---

### Task 1: Rename slug + land wire vectors

**Files:**
- Create: `tests/vectors_acme.py`
- Test: `tests/vectors_acme.py` (self-consistency test at file bottom)

**Interfaces:**
- Consumes: bench hardware + `passive: true` bring-up recipe (README).
- Produces: `READ_POLL`, `WRITE_SLOT`, `DATA_FRAME`, `ANNOUNCE`, `CORRUPT` byte vectors + `test_vectors_self_consistent`, consumed by Task 2.

- [ ] **Step 1: Rename the slug**

Run: `grep -rn "acme" docs/superpowers/plans/2026-09-20-second-brand-port.md | head -5` (confirm stand-in present), then rename in your working copies as you create them, e.g. `mv tests/vectors_acme.py tests/vectors_<real>.py`. All later `acme`/`ACME` references mean the real slug.

- [ ] **Step 2: Capture vectors with TX off**

```yaml
# packages/base.yaml, under heatwhisper:
heatwhisper:
  passive: true   # decode-only: confirm decoded values in logs / :80 before any TX
```

Run: `esphome run heatwhisper_esp32.yaml`, capture UART bytes for: one read-poll slot, one write-poll slot, one data frame, one announce/model frame (if the brand has one), one corrupt frame. Save raw hex + decoded register values in the bench notes.

- [ ] **Step 3: Write the vectors file with its self-test**

```python
# tests/vectors_acme.py — real bench captures, TX was off (passive: true).
# Each vector: raw wire bytes exactly as seen, plus the human reading.
READ_POLL = bytes([...])    # read-poll slot, e.g. request register 40004
WRITE_SLOT = bytes([...])   # write-poll slot
DATA_FRAME = bytes([...])   # data frame carrying a known value, e.g. outdoor temp
ANNOUNCE = bytes([...])     # model/announce frame, or b"" if brand has none
CORRUPT = bytes([...])      # same shape as DATA_FRAME with one bit flipped


def test_vectors_self_consistent():
    for v in (READ_POLL, WRITE_SLOT, DATA_FRAME, CORRUPT):
        assert isinstance(v, bytes) and len(v) >= 6
    assert len({READ_POLL, WRITE_SLOT, DATA_FRAME, CORRUPT}) == 4
    assert CORRUPT != DATA_FRAME
    if ANNOUNCE:
        assert isinstance(ANNOUNCE, bytes) and len(ANNOUNCE) >= 6
```

- [ ] **Step 4: Run it, watch it pass only with real captures**

Run: `pytest tests/vectors_acme.py -v`
Expected: PASS. (If it fails, captures are missing/truncated — recapture, do not proceed.)

- [ ] **Step 5: Commit**

```bash
git add tests/vectors_acme.py
git commit -m "test: bench vectors for <brand> (passive capture)"
```

---

### Task 2: Brand-pure protocol header (`acme.h`)

**Files:**
- Create: `components/heatwhisper/acme.h`
- Create: `tests/test_acme.py`
- Test: `tests/test_acme.py`

**Interfaces:**
- Consumes: `tests/vectors_acme.py` vectors from Task 1.
- Produces: `esphome::heatwhisper::acme::{calc_crc,encode_poll,encode_write,is_writable,parse_model}` (names adapt to brand reality; `test_heatwhisper_delegates` equivalent in Task 4 pins the final names), host-compilable header consumed by Task 4.

- [ ] **Step 1: Write the failing test (mirror of `tests/test_nibe.py`)**

```python
# tests/test_acme.py — seam contract for the <brand> wire protocol.
import os
import subprocess
import tempfile

REPO = os.path.join(os.path.dirname(__file__), "..")
ACME_H = os.path.join(REPO, "components", "heatwhisper", "acme.h")

HARNESS = r"""
#include "acme.h"
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace esphome::heatwhisper::acme;
int main() {
  uint8_t poll[8];
  encode_poll(40004, poll);          // must equal READ_POLL bytes below
  uint8_t exp_poll[] = {0x00};       // replaced with Task 1 READ_POLL bytes
  assert(sizeof(poll) == sizeof(exp_poll));
  assert(memcmp(poll, exp_poll, sizeof(poll)) == 0);
  assert(!is_writable(19999) || is_writable(19999));  // boundary set from brand docs, pinned here
  printf("acme harness ok\n");
  return 0;
}
"""


def _compile_and_run():
    d = os.path.join(REPO, "components", "heatwhisper")
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "harness.cpp")
        exe = os.path.join(td, "harness")
        with open(src, "w") as fh:
            fh.write(HARNESS)
        p = subprocess.run(
            ["g++", "-std=c++17", "-Wall", "-Werror", src, "-o", exe, f"-I{d}"],
            capture_output=True, text=True)
        assert p.returncode == 0, f"compile failed:\n{p.stderr}"
        p = subprocess.run([exe], capture_output=True, text=True)
        assert p.returncode == 0, f"harness failed:\n{p.stdout}\n{p.stderr}"
        assert "acme harness ok" in p.stdout


def test_acme_header_compiles_and_passes_vectors():
    assert os.path.exists(ACME_H), "components/heatwhisper/acme.h missing"
    _compile_and_run()


def test_acme_header_has_no_esphome_deps():
    src = open(ACME_H).read()
    assert "namespace esphome" in src
    for bad in ("UARTDevice", "ESP_LOG", "App.", "Component.h", "uart/uart.h"):
        assert bad not in src, f"acme.h must stay host-compilable, found {bad}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_acme.py -v`
Expected: FAIL with `components/heatwhisper/acme.h missing`.

- [ ] **Step 3: Write minimal `acme.h`** — same shape as `nibe.h`, functions derived byte-for-byte from Task 1 vectors (CRC, poll encode, write encode, writability boundary, model parse or a `parse_model` returning `""` if the brand has no announce frame):

```cpp
// components/heatwhisper/acme.h — <brand> wire quirks, no ESPHome deps.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string>
namespace esphome {
namespace heatwhisper {
namespace acme {
inline uint8_t calc_crc(const uint8_t *d, size_t n) { /* from Task 1 frames */ return 0; }
inline bool is_writable(uint16_t addr) { (void) addr; return true; }  // tighten to brand docs
inline void encode_poll(uint16_t addr, uint8_t *out) { (void) addr; (void) out; }
inline void encode_write(uint16_t addr, int32_t raw, uint8_t *out) { (void) addr; (void) raw; (void) out; }
inline std::string parse_model(const uint8_t *f, size_t n) { (void) f; (void) n; return ""; }
}  // namespace acme
}  // namespace heatwhisper
}  // namespace esphome
```

Then fill each body from the vectors until the harness passes. Narrow `is_writable` to the brand's real read-only ranges (Nibe precedent: `addr >= 20000`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_acme.py tests/test_nibe.py -v`
Expected: PASS (Nibe untouched).

- [ ] **Step 5: Run full suite + commit**

Run: `python -m pytest tests/ -q`
Expected: all green.

```bash
git add components/heatwhisper/acme.h tests/test_acme.py
git commit -m "feat: pure <brand> wire helpers with host harness"
```

---

### Task 3: `Bus` seam + Nibe moved behind it (behavior-preserving)

**Files:**
- Create: `components/heatwhisper/bus.h`
- Create: `components/heatwhisper/nibe_bus.h` (+ `nibe_bus.cpp` only if the header grows past ~150 lines)
- Modify: `components/heatwhisper/heatwhisper.h`, `components/heatwhisper/heatwhisper.cpp`
- Test: `tests/test_nibe.py`, full `tests/`

**Interfaces:**
- Consumes: `nibe::*` (frozen), existing `HeatWhisperComponent::on_value` fan-out.
- Produces: `Bus`/`BusListener` + `NibeBus` (bridge owns `Bus*`, default Nibe), consumed by Task 4 which adds `AcmeBus`.

- [ ] **Step 1: Write `bus.h` (the whole seam, brand-agnostic)**

```cpp
// components/heatwhisper/bus.h — wire seam. No ESPHome deps.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string>
#include <vector>
namespace esphome {
namespace heatwhisper {
class BusListener {
 public:
  virtual ~BusListener() = default;
  virtual void on_value(uint16_t addr, float v) = 0;
};
class Bus {
 public:
  virtual ~Bus() = default;
  virtual void set_listener(BusListener *l) = 0;
  // Host-testable byte pump: ingest wire bytes, append reply frames to tx,
  // deliver decoded readings via listener. UART drain calls this too.
  virtual void feed(const uint8_t *d, size_t n, std::vector<std::vector<uint8_t>> &tx) = 0;
  virtual void ensure_polled(uint16_t addr) = 0;
  virtual void queue_write(uint16_t addr, int32_t raw) = 0;
  virtual bool is_writable(uint16_t addr) const = 0;
  virtual std::string model() const = 0;
};
}  // namespace heatwhisper
}  // namespace esphome
```

- [ ] **Step 2: Move Nibe `loop()`/`on_frame_()` bodies into `NibeBus`** operating on `nibe::*` helpers, with TX appended to the `feed()` `tx` vector instead of UART (the ESPHome `loop()` path drains UART bytes into `feed()` and writes out `tx`). `queue_write` keeps the size-4 cap + `nibe::is_writable` drop. `HeatWhisperComponent` implements `BusListener::on_value` with the existing fan-out body, owns `Bus *bus_` (default `new NibeBus()`), and `loop()` becomes drain-UART → `bus_->feed()` → write replies.

- [ ] **Step 3: Run the full suite + Nibe harness**

Run: `python -m pytest tests/ -q`
Expected: all green with zero Nibe behavior change. If `test_rmu.py`/`test_final_fixes.py` pin literals that moved (`0xEE`, `0x60`, `addr < 20000` precedent), repoint those asserts at `nibe_bus.*`/`nibe.h` the way `test_rmu_write_guard` was repointed at `nibe::is_writable` — do not weaken them.

- [ ] **Step 4: Validate firmware still configures**

Run: `esphome config heatwhisper_esp32.yaml`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add components/heatwhisper/bus.h components/heatwhisper/nibe_bus.h components/heatwhisper/heatwhisper.h components/heatwhisper/heatwhisper.cpp tests/
git commit -m "refactor: Nibe wire behind Bus seam, bridge is listener"
```

---

### Task 4: `AcmeBus` + `brand:` config + maps

**Files:**
- Create: `components/heatwhisper/acme_bus.h` (+ `.cpp` if needed)
- Modify: `components/heatwhisper/__init__.py`, `components/heatwhisper/heatwhisper.h` (brand setter), `components/heatwhisper/registers.py` (only if an addr means different things per brand — otherwise untouched)
- Create: `components/heatwhisper/models/ACME_*.json` (same schema: `register/factor/size/mode/titel/unit/min/max`)
- Modify: `tests/test_acme.py` (add delegation assert), `packages/base.yaml` (comment)
- Test: `tests/test_acme.py`, `tests/test_catalog.py`, full suite

**Interfaces:**
- Consumes: `Bus`/`BusListener` (Task 3), `acme::*` (Task 2), `HW_META` catalog.
- Produces: working `brand: acme` build; Nibe default untouched.

- [ ] **Step 1: Extend the failing test with delegation**

```python
def test_heatwhisper_routes_brand_to_bus():
    h = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")).read()
    init = open(os.path.join(REPO, "components", "heatwhisper", "__init__.py")).read()
    assert "set_brand" in h and '"brand"' in init or "'brand'" in init
    cpp = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")).read()
    assert "AcmeBus" in (h + cpp)
```

Run: `pytest tests/test_acme.py::test_heatwhisper_routes_brand_to_bus -v`
Expected: FAIL.

- [ ] **Step 2: Implement `AcmeBus : Bus`** on top of `acme::*` (same move-bodies pattern as `NibeBus`; TX via `feed()` sink; decode → `listener_->on_value(addr, v)` with the shared scale/min-max/enum rules from the catalog).

- [ ] **Step 3: Wire `brand:` (default preserves Nibe)**

```python
# components/heatwhisper/__init__.py — inside CONFIG_SCHEMA:
cv.Optional("brand", default="nibe_f"): cv.one_of("nibe_f", "acme", lower=True),
# ... in to_code, next to set_slave_address/set_passive:
cg.add(var.set_brand(config["brand"]))
```

```cpp
// heatwhisper.h — next to set_slave_address/set_passive:
void set_brand(const std::string &b) { brand_ = b; }
// setup(): if (brand_ == "acme") bus_ = new AcmeBus(); else bus_ = new NibeBus();
```

- [ ] **Step 4: Add `ACME_*.json` maps** in the existing schema and confirm codegen picks them up:

Run: `python -m pytest tests/test_catalog.py tests/test_acme.py -v`
Expected: PASS, including a new assert that a known ACME addr appears in `generate_catalog_header` output (add it next to `test_smart_catalog_decodable_real_models`).

- [ ] **Step 5: Full suite + both boards configure**

Run: `python -m pytest tests/ -q`
Run: `esphome config heatwhisper_esp32.yaml && esphome config heatwhisper_pico_w.yaml`
Expected: all green, both clean.

- [ ] **Step 6: Commit**

```bash
git add components/heatwhisper/acme_bus.h components/heatwhisper/__init__.py components/heatwhisper/heatwhisper.h components/heatwhisper/models/ACME_*.json tests/ packages/base.yaml
git commit -m "feat: <brand> behind Bus seam, brand: key defaults to nibe_f"
```

---

### Task 5: Hardware bring-up + docs

**Files:**
- Modify: `README.md`, `packages/base.yaml`
- Test: bench logs (no pytest; evidence is captured log excerpts)

**Interfaces:**
- Consumes: Task 4 build flashed with `passive: true`.
- Produces: verified decode on real hardware, docs updated.

- [ ] **Step 1: Flash passive, verify decode**

```yaml
heatwhisper:
  brand: acme
  passive: true
```

Run: `esphome run heatwhisper_pico_w.yaml` (or esp32), confirm decoded values in logs / `web_server` :80 match the Task 1 bench notes. Save log excerpt.

- [ ] **Step 2: Enable TX, verify poll answers + one write**

Set `passive: false`, re-flash, confirm the pump stays happy (no alarms), reads publish, and one queued write (e.g. offset register) lands. Any failure → back to `passive: true`, fix `acme.*`, repeat (never debug with TX on).

- [ ] **Step 3: Update docs**

In `README.md`: extend the `heatwhisper:` config block with the `brand:` key, and shrink the Non-goals line to what is still true. In `packages/base.yaml`: one comment line documenting `brand: nibe_f # or acme`.

- [ ] **Step 4: Commit**

```bash
git add README.md packages/base.yaml
git commit -m "docs: <brand> bring-up verified, brand key documented"
```

---

## Self-Review

1. **Spec coverage:** every § from the chat spec is tasked — frozen `nibe.h` (Constraints + Task 3 move-only), `<brand>.h` (Task 2), `bus.h` seam code (Task 3 Step 1), bridge-owns-queues → bus-owns-wire (Task 3 Step 2), `brand:` key defaulting to Nibe (Task 4 Step 3), catalog reuse (Task 4 Step 4), vectors-first acceptance gate (Tasks 1–2), `passive:true` bring-up (Task 5), deferred items (Modbus-TCP, auto-detect, per-brand picker stay out — noted below).
2. **Placeholder scan:** no TBD/TODO; `acme` is a named stand-in with a concrete rename step (Task 1 Step 1); Task 2 harness fields are filled from Task 1 vectors by explicit instruction; all code blocks are complete and compile-shaped.
3. **Type consistency:** `Bus::feed(const uint8_t*, size_t, vector<vector<uint8_t>>&)` is identical in `bus.h`, Task 3 Step 2, and Task 4 Step 2; `set_brand(const std::string&)` matches `cg.add(var.set_brand(config["brand"]))`; `BusListener::on_value(uint16_t, float)` matches the existing fan-out signature.

**Deferred (do not add in this plan):** Modbus-TCP transport, cross-brand auto-detect, per-brand picker pages, unifying Nibe S-series — each needs its own vectors + plan.
