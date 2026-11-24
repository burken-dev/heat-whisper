# Optimizer-Ready Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add EEPROM-safe write deduplication & coalescing, expand factory defaults from 12 to 17 optimizer-ready registers, unify board naming to `heat-whisper` / `HeatWhisper` across all 3 boards with isolated CI builds, and fix documentation drift.

**Architecture:** Extract a host-compilable, ESPHome-independent `WriteQueue` helper in `components/heatwhisper/write_queue.h` (matching the `nibe.h` seam) and wire it into `HeatWhisperComponent` (`heatwhisper.{h,cpp}`). Update `DEFAULT_ENABLED`, `HW_FACTORY_NAMES`, and regenerated `catalog.h` in lockstep to 17 registers, unify all board YAML names with sequential artifact isolation in `.github/workflows/build.yml`, and document exact Home Assistant entity IDs in `README.md`.

**Tech Stack:** C++17 (ESPHome component), Python 3.12, pytest, `g++`, ESPHome CLI (`2026.9.0`), GitHub Actions YAML.

## Global Constraints

- HeatWhisper must remain a zero-logic bridge (no built-in optimization policies or write cooldown timers).
- Preserve the 4-slot pending write queue cap (`kMaxPending = 4`) and `< 20000` unwritable address drop guard.
- One-shot commands (`45171` Reset Pump Alarm) must pass `dedupe = false` so repeated resets are never suppressed.
- Preserve 1:1 sync between `DEFAULT_ENABLED` (17 registers) and `HW_FACTORY_NAMES` (strictly ascending by address for `std::lower_bound`).
- Unify all three top-level board YAMLs to `name: heat-whisper` and `friendly_name: HeatWhisper` without hardcoding `build_path:` in user-facing YAMLs.
- All host tests (`python3 -m pytest tests/ -v`) and `esphome config` checks on all 3 board YAMLs must pass.

---

### File Structure

- **Create:** `components/heatwhisper/write_queue.h` — Host-compilable `WriteRequest`, `QueueResult`, and `WriteQueue` with no-op deduplication, pending coalescing, revert cancellation, in-flight Modbus protection, and 4-slot eviction.
- **Create:** `tests/test_write_queue.py` — `g++` host C++ unit harness for `WriteQueue` + source-level wiring contract assertions.
- **Create:** `tests/test_board_naming.py` — Contract tests for unified board YAML naming, CI sequential build isolation, and doc/HTML/YAML 17-default sync.
- **Modify:** `components/heatwhisper/heatwhisper.h` — Include `write_queue.h`, replace `std::queue<WriteRequest> writes_` with `WriteQueue writes_`, update `queue_write(..., bool dedupe = true)`, add `is_modbus_write_in_flight_()`.
- **Modify:** `components/heatwhisper/heatwhisper.cpp` — Wire `writes_.record_known(...)` in `on_value`, `pop_sent()` / `pop_failed()` in NIBE & Modbus paths, `dedupe = false` for `45171` resets, and expand `HW_FACTORY_NAMES[]` to 17 sorted entries.
- **Modify:** `components/heatwhisper/registers.py` — Expand `DEFAULT_ENABLED` to 17 sorted registers.
- **Modify:** `components/heatwhisper/catalog.h` — Regenerate via `esphome compile --only-generate heatwhisper_esp32.yaml`.
- **Modify:** `packages/base.yaml` — Pass `false` for `queue_write(45171, 1, false)` and update `18 entities` comment to `17 entities`.
- **Modify:** `tests/test_final_fixes.py` — Update `test_write_queue_capped` to verify `kMaxPending = 4` in `write_queue.h` and `WriteQueue writes_` in `heatwhisper.h`.
- **Modify:** `tests/test_subscription.py` — Update `OLD_ENTITY_REGS` and `EXPECTED_BASE_NAMES` to 17 entries and assert ascending order of `HW_FACTORY_NAMES`.
- **Modify:** `heatwhisper_esp32_s3_rs485.yaml`, `heatwhisper_pico_w.yaml` — Unify `name: heat-whisper` and `friendly_name: HeatWhisper`.
- **Modify:** `.github/workflows/build.yml` — Compile each board sequentially, copy binaries to `fw/`, and clear `.esphome/build/heat-whisper` between boards (updating Pico W `.pioenvs/heat-whisper/`).
- **Modify:** `index.html`, `README.md` — Sync `17 defaults`, add Entity & Register Reference table, add "Works with" section, add upgrade hostname note, and fix typos.

---

### Task 1: EEPROM-Safe `WriteQueue` (`components/heatwhisper/write_queue.h`)

**Files:**
- Create: `tests/test_write_queue.py`
- Create: `components/heatwhisper/write_queue.h`

**Interfaces:**
- Consumes: `nibe::is_writable(uint16_t addr)` from `components/heatwhisper/nibe.h`
- Produces: `esphome::heatwhisper::WriteRequest`, `esphome::heatwhisper::QueueResult`, and `esphome::heatwhisper::WriteQueue` (`kMaxPending = 4`, `enqueue(uint16_t addr, int32_t raw, bool dedupe = true, bool in_flight = false)`, `record_known(uint16_t addr, int32_t raw)`, `lookup_known(uint16_t addr, int32_t *out) const`, `empty()`, `size()`, `front()`, `pop_sent()`, `pop_failed()`)

- [ ] **Step 1: Write the failing host C++ unit tests in `tests/test_write_queue.py`**

Create `tests/test_write_queue.py`:

```python
# tests/test_write_queue.py — host C++ unit tests for EEPROM-safe WriteQueue
# (deduplication, coalescing, cancellation, in-flight safety, cap eviction).
import os
import subprocess
import tempfile

REPO = os.path.join(os.path.dirname(__file__), "..")
WQ_H = os.path.join(REPO, "components", "heatwhisper", "write_queue.h")

HARNESS = r"""
#include "write_queue.h"
#include <cassert>
#include <cstdio>
using namespace esphome::heatwhisper;

int main() {
  // 1. Sub-20000 addresses dropped regardless of dedupe flag
  {
    WriteQueue q;
    assert(q.enqueue(19999, 1, true) == QueueResult::DROPPED_UNWRITABLE);
    assert(q.enqueue(10001, 1, false) == QueueResult::DROPPED_UNWRITABLE);
    assert(q.empty());
  }

  // 2. Cold boot (unknown register) always enqueues
  {
    WriteQueue q;
    assert(q.enqueue(47011, 0) == QueueResult::ENQUEUED);
    assert(q.size() == 1);
    assert(q.front().addr == 47011 && q.front().raw == 0);
  }

  // 3. Matching known pump readback is skipped as no-op; changed value enqueues
  {
    WriteQueue q;
    q.record_known(47011, 2);
    assert(q.enqueue(47011, 2) == QueueResult::SKIPPED_NOOP);
    assert(q.empty());
    assert(q.enqueue(47011, 3) == QueueResult::ENQUEUED);
    assert(q.size() == 1 && q.front().raw == 3);
  }

  // 4. Duplicate pending write skipped; rapid slider changes coalesce in place
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 1) == QueueResult::ENQUEUED);
    assert(q.enqueue(47011, 1) == QueueResult::SKIPPED_DUPE);
    assert(q.enqueue(47011, 2) == QueueResult::COALESCED);
    assert(q.enqueue(47011, 3) == QueueResult::COALESCED);
    assert(q.size() == 1 && q.front().raw == 3);
  }

  // 5. Pending write reverted back to known pump state cancels the queued write
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    assert(q.enqueue(47011, 0) == QueueResult::CANCELLED);
    assert(q.empty());
  }

  // 6. Post-TX pre-readback duplicate skipped; contradictory readback re-enables write
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    q.pop_sent();
    assert(q.empty());
    assert(q.enqueue(47011, 2) == QueueResult::SKIPPED_NOOP);
    // Pump readback reveals pump stayed at 0
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    assert(q.size() == 1);
  }

  // 7. pop_failed() does NOT update last_raw_, allowing retry
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    q.pop_failed();
    assert(q.empty());
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    assert(q.size() == 1);
  }

  // 8. In-flight Modbus write is never mutated; matching value skipped, change queues behind & coalesces
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    // Now pending_[0] = {47011, 2} is in-flight
    assert(q.enqueue(47011, 2, true, true) == QueueResult::SKIPPED_DUPE);
    assert(q.size() == 1 && q.front().raw == 2);
    // New value queues at index 1 without touching in-flight index 0
    assert(q.enqueue(47011, 3, true, true) == QueueResult::ENQUEUED);
    assert(q.size() == 2 && q.front().raw == 2);
    // Further slider change coalesces index 1
    assert(q.enqueue(47011, 4, true, true) == QueueResult::COALESCED);
    assert(q.size() == 2 && q.front().raw == 2);
    // Reverting to in-flight value cancels index 1
    assert(q.enqueue(47011, 2, true, true) == QueueResult::CANCELLED);
    assert(q.size() == 1 && q.front().raw == 2);
    // Queue another value behind in-flight, finish in-flight, confirm next is sent
    assert(q.enqueue(47011, 5, true, true) == QueueResult::ENQUEUED);
    q.pop_sent();
    assert(q.size() == 1 && q.front().raw == 5);
  }

  // 9. Non-deduped one-shot command (45171 Reset Alarm) always enqueues and does not pollute last_raw_
  {
    WriteQueue q;
    assert(q.enqueue(45171, 1, false) == QueueResult::ENQUEUED);
    assert(q.enqueue(45171, 1, false) == QueueResult::ENQUEUED);
    assert(q.size() == 2);
    q.pop_sent();
    q.pop_sent();
    int32_t out = 0;
    assert(!q.lookup_known(45171, &out));
    assert(q.enqueue(45171, 1, false) == QueueResult::ENQUEUED);
  }

  // 10. Cap kMaxPending == 4: evicts oldest when full, never evicts in-flight index 0
  {
    WriteQueue q;
    static_assert(WriteQueue::kMaxPending == 4, "cap must stay 4");
    assert(q.enqueue(47011, 1) == QueueResult::ENQUEUED);
    assert(q.enqueue(47041, 2) == QueueResult::ENQUEUED);
    assert(q.enqueue(47370, 1) == QueueResult::ENQUEUED);
    assert(q.enqueue(47371, 1) == QueueResult::ENQUEUED);
    // Not in-flight: evicts 47011
    assert(q.enqueue(47387, 1, true, false) == QueueResult::EVICTED_OLDEST);
    assert(q.size() == 4 && q.front().addr == 47041);
    // Now 47041 is in-flight: evicts 47370 (index 1), keeps 47041 at index 0
    assert(q.enqueue(48132, 1, true, true) == QueueResult::EVICTED_OLDEST);
    assert(q.size() == 4 && q.front().addr == 47041);
    q.pop_sent();
    assert(q.front().addr == 47371);
  }

  printf("write_queue harness ok\n");
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
        assert "write_queue harness ok" in p.stdout


def test_write_queue_header_compiles_and_passes_vectors():
    assert os.path.exists(WQ_H), "components/heatwhisper/write_queue.h missing"
    _compile_and_run()


def test_write_queue_header_has_no_esphome_deps():
    src = open(WQ_H).read()
    for bad in ("UARTDevice", "ESP_LOG", "App.", "Component.h", "uart/uart.h"):
        assert bad not in src, f"write_queue.h must stay host-compilable, found {bad}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_write_queue.py -v`
Expected: FAIL with `components/heatwhisper/write_queue.h missing`.

- [ ] **Step 3: Implement `components/heatwhisper/write_queue.h`**

Create `components/heatwhisper/write_queue.h`:

```cpp
// components/heatwhisper/write_queue.h — EEPROM-safe write queue with
// no-op deduplication and pending-write coalescing, no ESPHome deps.
#pragma once
#include "nibe.h"
#include <stddef.h>
#include <stdint.h>
#include <deque>
#include <utility>
#include <vector>
namespace esphome {
namespace heatwhisper {
struct WriteRequest {
  uint16_t addr;
  int32_t raw;
  bool dedupe{true};
};
enum class QueueResult : uint8_t {
  ENQUEUED = 0,
  COALESCED,
  CANCELLED,
  SKIPPED_NOOP,
  SKIPPED_DUPE,
  DROPPED_UNWRITABLE,
  EVICTED_OLDEST,
};
class WriteQueue {
 public:
  static constexpr size_t kMaxPending = 4;

  void record_known(uint16_t addr, int32_t raw) {
    for (auto &kv : last_raw_) {
      if (kv.first == addr) {
        kv.second = raw;
        return;
      }
    }
    last_raw_.push_back({addr, raw});
  }

  bool lookup_known(uint16_t addr, int32_t *out) const {
    for (const auto &kv : last_raw_) {
      if (kv.first == addr) {
        if (out != nullptr) *out = kv.second;
        return true;
      }
    }
    return false;
  }

  QueueResult enqueue(uint16_t addr, int32_t raw, bool dedupe = true, bool in_flight = false) {
    if (!nibe::is_writable(addr)) return QueueResult::DROPPED_UNWRITABLE;
    const size_t start = (in_flight && !pending_.empty()) ? 1 : 0;
    if (dedupe) {
      bool has_base = false;
      int32_t base_raw = 0;
      bool base_is_inflight = false;
      if (start == 1 && pending_[0].addr == addr) {
        has_base = true;
        base_raw = pending_[0].raw;
        base_is_inflight = true;
      } else {
        has_base = lookup_known(addr, &base_raw);
      }
      for (size_t i = start; i < pending_.size(); i++) {
        if (pending_[i].addr != addr) continue;
        if (pending_[i].raw == raw) return QueueResult::SKIPPED_DUPE;
        if (has_base && base_raw == raw) {
          pending_.erase(pending_.begin() + (ptrdiff_t) i);
          return QueueResult::CANCELLED;
        }
        pending_[i].raw = raw;
        return QueueResult::COALESCED;
      }
      if (has_base && base_raw == raw) {
        return base_is_inflight ? QueueResult::SKIPPED_DUPE : QueueResult::SKIPPED_NOOP;
      }
    }
    bool evicted = false;
    if (pending_.size() >= kMaxPending) {
      pending_.erase(pending_.begin() + (ptrdiff_t) start);
      evicted = true;
    }
    pending_.push_back({addr, raw, dedupe});
    return evicted ? QueueResult::EVICTED_OLDEST : QueueResult::ENQUEUED;
  }

  bool empty() const { return pending_.empty(); }
  size_t size() const { return pending_.size(); }
  const WriteRequest &front() const { return pending_.front(); }

  void pop_sent() {
    if (pending_.empty()) return;
    WriteRequest w = pending_.front();
    pending_.pop_front();
    if (w.dedupe) record_known(w.addr, w.raw);
  }

  void pop_failed() {
    if (!pending_.empty()) pending_.pop_front();
  }

 private:
  std::deque<WriteRequest> pending_;
  std::vector<std::pair<uint16_t, int32_t>> last_raw_;
};
}  // namespace heatwhisper
}  // namespace esphome
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_write_queue.py -v`
Expected: PASS (`2 passed`).

- [ ] **Step 5: Commit**

```bash
git add components/heatwhisper/write_queue.h tests/test_write_queue.py
git commit -m "feat: add host-tested WriteQueue with EEPROM no-op dedupe and coalescing"
```

---

### Task 2: Wire `WriteQueue` into `HeatWhisperComponent` & Alarm Reset Calls

**Files:**
- Modify: `tests/test_write_queue.py`
- Modify: `tests/test_final_fixes.py:83-85`
- Modify: `components/heatwhisper/heatwhisper.h:12-27,101-106,120-150`
- Modify: `components/heatwhisper/heatwhisper.cpp:221-226,368-378,434-448,468-496,568-581,704-712`
- Modify: `packages/base.yaml:49-52`

**Interfaces:**
- Consumes: `WriteQueue`, `WriteRequest`, `QueueResult` from Task 1 (`components/heatwhisper/write_queue.h`)
- Produces: `HeatWhisperComponent::queue_write(uint16_t addr, int32_t raw, bool dedupe = true)` backed by `WriteQueue writes_`, recording readbacks in `on_value` and calling `pop_sent()` / `pop_failed()` in NIBE & Modbus paths

- [ ] **Step 1: Add failing wiring contract tests to `tests/test_write_queue.py` and update `tests/test_final_fixes.py`**

Append to `tests/test_write_queue.py`:

```python
def test_heatwhisper_wires_write_queue():
    h = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")).read()
    cpp = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")).read()
    base = open(os.path.join(REPO, "packages", "base.yaml")).read()
    assert '#include "write_queue.h"' in h
    assert "WriteQueue writes_;" in h
    assert "bool dedupe = true" in h
    assert "writes_.enqueue(" in h
    # on_value records pump readbacks for no-op dedupe
    on_val = cpp.split("void HeatWhisperComponent::on_value")[1].split("void HeatWhisperSelect::set_labels")[0]
    assert "writes_.record_known(" in on_val
    # TX paths use pop_sent on success and pop_failed on retry exhaustion
    assert "writes_.pop_sent()" in cpp
    assert "writes_.pop_failed()" in cpp
    assert "writes_.pop()" not in cpp
    # One-shot alarm reset (45171) bypasses dedupe everywhere
    assert "queue_write(45171, 1, false)" in cpp
    assert "queue_write(45171, 1)" not in cpp
    assert "queue_write(45171, 1, false)" in base
```

Update `test_write_queue_capped` in `tests/test_final_fixes.py`:

```python
def test_write_queue_capped():
    wq = open(os.path.join(REPO, "components", "heatwhisper", "write_queue.h")).read()
    assert "kMaxPending = 4" in wq and "WriteQueue writes_" in HDR  # I5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_write_queue.py tests/test_final_fixes.py -v`
Expected: FAIL on `test_heatwhisper_wires_write_queue` and `test_write_queue_capped`.

- [ ] **Step 3: Wire `WriteQueue` into `components/heatwhisper/heatwhisper.h`**

In `components/heatwhisper/heatwhisper.h`:
1. Add `#include "write_queue.h"` right after `#include "nibe.h"`.
2. Remove the duplicate `struct WriteRequest { uint16_t addr; int32_t raw; };` line (now defined in `write_queue.h`).
3. Replace `queue_write(...)` with:

```cpp
  void queue_write(uint16_t addr, int32_t raw, bool dedupe = true) {
    auto res = writes_.enqueue(addr, raw, dedupe, is_modbus_write_in_flight_());
    if (res == QueueResult::DROPPED_UNWRITABLE) {
      ESP_LOGW("heatwhisper", "Dropping sub-20000 write addr %u", addr);
    } else if (res == QueueResult::EVICTED_OLDEST) {
      ESP_LOGW("heatwhisper", "Write queue full, dropping oldest");
    } else if (res == QueueResult::SKIPPED_NOOP || res == QueueResult::SKIPPED_DUPE) {
      ESP_LOGD("heatwhisper", "Skipping no-op write addr %u (already %d)", addr, (int) raw);
    } else if (res == QueueResult::CANCELLED) {
      ESP_LOGD("heatwhisper", "Cancelled pending write addr %u (reverted to %d)", addr, (int) raw);
    } else if (res == QueueResult::COALESCED) {
      ESP_LOGD("heatwhisper", "Coalesced pending write addr %u -> %d", addr, (int) raw);
    }
  }
```

4. In `protected:`, add:

```cpp
  bool is_modbus_write_in_flight_() const {
    return modbus_ && pending_ && (pending_fc_ == 6 || pending_fc_ == 16);
  }
```

5. Replace `std::queue<WriteRequest> writes_;` with `WriteQueue writes_;`.

- [ ] **Step 4: Wire `WriteQueue` into `components/heatwhisper/heatwhisper.cpp` and `packages/base.yaml`**

In `components/heatwhisper/heatwhisper.cpp`:
1. In `setup()` (line 224): change `queue_write(45171, 1);` → `queue_write(45171, 1, false);`
2. In `poll_one_()` (line 373): change `if (!writes_.empty()) writes_.pop();` → `if (!writes_.empty()) writes_.pop_failed();`
3. In `on_modbus_frame_()` `fail_` lambda (line 439): change `if (!writes_.empty()) writes_.pop();` → `if (!writes_.empty()) writes_.pop_failed();`
4. In `on_modbus_frame_()` FC06/FC16 ACK (line 473): change `if (!writes_.empty()) writes_.pop();` → `if (!writes_.empty()) writes_.pop_sent();`
5. In `on_frame_()` NIBE `0x6B` slot (line 491): change `auto w = writes_.front(); writes_.pop();` → `auto w = writes_.front(); writes_.pop_sent();`
6. In `on_value()` (line 568): record decoded raw value at top of `on_value`:

```cpp
void HeatWhisperComponent::on_value(uint16_t addr, float v) {
  const HwMeta *meta = meta_for(addr);
  float f = (meta != nullptr && meta->factor) ? (float) meta->factor : 1.0f;
  writes_.record_known(addr, (int32_t) std::lround(v * f));
  for (auto *s : sensors_)
    if (s->get_register() == addr) s->publish_state(v);
  for (auto *n : numbers_)
    if (n->get_register() == addr) n->publish_state(v);
  for (auto *sw : switches_)
    if (sw->get_register() == addr) sw->publish_state(v != 0);
  for (auto *sel : selects_)
    if (sel->get_register() == addr) sel->publish_raw((int32_t) std::lround(v * f));
}
```

7. In `HeatWhisperPickerHandler::handleRequest()` (line 707): change `this->parent_->queue_write(45171, 1);` → `this->parent_->queue_write(45171, 1, false);`

In `packages/base.yaml` (line 51):
Change `- lambda: 'id(heatwhisper_bridge).queue_write(45171, 1);'` → `- lambda: 'id(heatwhisper_bridge).queue_write(45171, 1, false);'`

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add components/heatwhisper/heatwhisper.h components/heatwhisper/heatwhisper.cpp packages/base.yaml tests/test_write_queue.py tests/test_final_fixes.py
git commit -m "feat: wire EEPROM-safe WriteQueue deduplication into HeatWhisperComponent"
```

---

### Task 3: Expand Default Registers (12 → 17) & Regenerate `catalog.h`

**Files:**
- Modify: `tests/test_subscription.py:27-65`
- Modify: `components/heatwhisper/registers.py:4-5`
- Modify: `components/heatwhisper/heatwhisper.cpp:80-89`
- Modify: `components/heatwhisper/catalog.h` (regenerated via ESPHome)

**Interfaces:**
- Consumes: Model catalogs in `components/heatwhisper/models/*.json`
- Produces: 17-entry `DEFAULT_ENABLED`, 17-entry strictly ascending `HW_FACTORY_NAMES`, and regenerated `catalog.h` (`HW_DEFAULTS_N = 17`)

- [ ] **Step 1: Update `tests/test_subscription.py` with the 17-register expectations (TDD RED)**

In `tests/test_subscription.py`, update `OLD_ENTITY_REGS` and `test_factory_covers_old_entity_set`:

```python
OLD_ENTITY_REGS = (40004, 40008, 40012, 40013, 40014, 40033,
                   43005, 43009, 43084, 43086, 45001,
                   47011, 47041, 47370, 47371, 47387, 48132)
```

And in `test_factory_covers_old_entity_set`:

```python
def test_factory_covers_old_entity_set():
    # Factory defaults must cover the optimizer-ready 17-register set in
    # ascending address order (required by std::lower_bound in base_name_for).
    from components.heatwhisper.registers import DEFAULT_ENABLED
    table = _base_names_table()
    assert list(table.keys()) == sorted(table.keys())
    assert sorted(table) == sorted(OLD_ENTITY_REGS)
    assert sorted(table) == sorted(DEFAULT_ENABLED)
    assert len(set(table.values())) == len(table)
    # ponytail: hardcoded snapshot of the 17 factory names; catches silent renames.
    EXPECTED_BASE_NAMES = [
        "BT1 Outdoor", "Supply Temp S1", "Return Temp",
        "Hot Water Top BT7", "Hot Water BT6", "Room Temp S1",
        "Degree Minutes", "Calculated Supply",
        "Electrical Addition Power", "Operating Priority", "Alarm",
        "Heat Offset S1", "Hot Water Comfort Mode",
        "Allow Additive Heating", "Allow Heating",
        "Hot Water Production", "Temporary Lux",
    ]
    assert sorted(table.values()) == sorted(EXPECTED_BASE_NAMES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_subscription.py -v`
Expected: FAIL on `test_factory_covers_old_entity_set` (still 12 entries).

- [ ] **Step 3: Update `DEFAULT_ENABLED` in `components/heatwhisper/registers.py` and `HW_FACTORY_NAMES` in `components/heatwhisper/heatwhisper.cpp`**

In `components/heatwhisper/registers.py`:

```python
DEFAULT_ENABLED = [40004, 40008, 40012, 40013, 40014, 40033,
                   43005, 43009, 43084, 43086, 45001,
                   47011, 47041, 47370, 47371, 47387, 48132]
```

In `components/heatwhisper/heatwhisper.cpp`:

```cpp
// Post-Task-5 name authority: factory names for the 17 HW_DEFAULTS addrs,
// sorted ascending by addr for std::lower_bound in base_name_for().
static const struct { uint16_t addr; const char *name; } HW_FACTORY_NAMES[] = {
  {40004, "BT1 Outdoor"}, {40008, "Supply Temp S1"}, {40012, "Return Temp"},
  {40013, "Hot Water Top BT7"}, {40014, "Hot Water BT6"}, {40033, "Room Temp S1"},
  {43005, "Degree Minutes"}, {43009, "Calculated Supply"}, {43084, "Electrical Addition Power"},
  {43086, "Operating Priority"}, {45001, "Alarm"}, {47011, "Heat Offset S1"},
  {47041, "Hot Water Comfort Mode"}, {47370, "Allow Additive Heating"}, {47371, "Allow Heating"},
  {47387, "Hot Water Production"}, {48132, "Temporary Lux"},
};
```

- [ ] **Step 4: Regenerate `components/heatwhisper/catalog.h`**

Run: `esphome compile --only-generate heatwhisper_esp32.yaml`
Verify `HW_DEFAULTS_N = 17` in `components/heatwhisper/catalog.h`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add components/heatwhisper/registers.py components/heatwhisper/heatwhisper.cpp components/heatwhisper/catalog.h tests/test_subscription.py
git commit -m "feat: expand default enabled registers from 12 to 17 for energy optimizers"
```

---

### Task 4: Unified Board Naming, CI Build Isolation & Docs/Drift Cleanup

**Files:**
- Create: `tests/test_board_naming.py`
- Modify: `heatwhisper_esp32_s3_rs485.yaml:3-5`
- Modify: `heatwhisper_pico_w.yaml:1-3`
- Modify: `.github/workflows/build.yml:36-48`
- Modify: `index.html:19`
- Modify: `packages/base.yaml:59-60`
- Modify: `README.md:1-179`

**Interfaces:**
- Consumes: 17 default factory names from Task 3 (`HW_FACTORY_NAMES`)
- Produces: Unified `name: heat-whisper` / `friendly_name: HeatWhisper` across all 3 boards, isolated sequential CI build steps, synced `17` default counts across docs/HTML/YAML, and complete Entity & Register Reference + "Works with" documentation in `README.md`

- [ ] **Step 1: Write failing tests in `tests/test_board_naming.py`**

Create `tests/test_board_naming.py`:

```python
# tests/test_board_naming.py — unified board naming, CI build isolation, doc count sync.
import os

REPO = os.path.join(os.path.dirname(__file__), "..")


def test_all_boards_share_unified_name_and_friendly_name():
    for fname in ("heatwhisper_esp32.yaml", "heatwhisper_esp32_s3_rs485.yaml", "heatwhisper_pico_w.yaml"):
        src = open(os.path.join(REPO, fname)).read()
        assert "name: heat-whisper\n" in src, fname
        assert "friendly_name: HeatWhisper\n" in src, fname


def test_ci_isolates_shared_build_dir_between_boards():
    yml = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "heat-whisper-s3" not in yml
    assert "heat-whisper-pico" not in yml
    assert ".esphome/build/heat-whisper/.pioenvs/heat-whisper/firmware.uf2" in yml
    # Each board must copy its outputs before the next compile overwrites .esphome/build/heat-whisper
    esp32_compile = yml.index("compile heatwhisper_esp32.yaml")
    esp32_copy = yml.index("cp .esphome/build/heat-whisper/build/firmware.factory.bin fw/")
    pico_compile = yml.index("compile heatwhisper_pico_w.yaml")
    pico_copy = yml.index("cp .esphome/build/heat-whisper/.pioenvs/heat-whisper/firmware.uf2 fw/")
    s3_compile = yml.index("compile heatwhisper_esp32_s3_rs485.yaml")
    s3_copy = yml.index("cp .esphome/build/heat-whisper/build/firmware.factory.bin fw/heatwhisper_esp32_s3_rs485.factory.bin")
    assert esp32_compile < esp32_copy < pico_compile < pico_copy < s3_compile < s3_copy
    assert yml.count("rm -rf .esphome/build/heat-whisper") >= 2


def test_default_register_count_synced_across_docs_and_config():
    readme = open(os.path.join(REPO, "README.md")).read()
    html = open(os.path.join(REPO, "index.html")).read()
    base = open(os.path.join(REPO, "packages", "base.yaml")).read()
    assert "17 registers" in readme
    assert "17 defaults" in html and "18 defaults" not in html
    assert "17 entities" in base and "18 entities" not in base
    # Exact HA entity IDs documented in README for key optimizer entities
    for eid in (
        "sensor.heatwhisper_bt1_outdoor",
        "sensor.heatwhisper_supply_temp_s1",
        "sensor.heatwhisper_return_temp",
        "sensor.heatwhisper_calculated_supply",
        "sensor.heatwhisper_electrical_addition_power",
        "sensor.heatwhisper_operating_priority",
        "number.heatwhisper_degree_minutes",
        "number.heatwhisper_heat_offset_s1",
        "select.heatwhisper_hot_water_comfort_mode",
        "select.heatwhisper_temporary_lux",
        "switch.heatwhisper_allow_additive_heating",
        "switch.heatwhisper_allow_heating",
        "switch.heatwhisper_hot_water_production",
    ):
        assert eid in readme, f"missing {eid} in README.md"
    assert "doens't" not in readme and "forcast" not in readme
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_board_naming.py -v`
Expected: FAIL on all 3 tests.

- [ ] **Step 3: Update board YAMLs (`heatwhisper_esp32_s3_rs485.yaml`, `heatwhisper_pico_w.yaml`)**

In `heatwhisper_esp32_s3_rs485.yaml`:

```yaml
esphome:
  name: heat-whisper
  friendly_name: HeatWhisper
```

In `heatwhisper_pico_w.yaml`:

```yaml
esphome:
  name: heat-whisper
  friendly_name: HeatWhisper
```

- [ ] **Step 4: Update `.github/workflows/build.yml` for sequential per-board build isolation**

Replace lines 36-47 in `.github/workflows/build.yml`:

```yaml
          mkdir -p fw
          esphome "${ARGS[@]}" compile heatwhisper_esp32.yaml
          cp .esphome/build/heat-whisper/build/firmware.factory.bin fw/
          cp .esphome/build/heat-whisper/build/firmware.ota.bin fw/
          rm -rf .esphome/build/heat-whisper

          esphome "${ARGS[@]}" compile heatwhisper_pico_w.yaml
          cp .esphome/build/heat-whisper/.pioenvs/heat-whisper/firmware.bin fw/
          cp .esphome/build/heat-whisper/.pioenvs/heat-whisper/firmware.uf2 fw/
          rm -rf .esphome/build/heat-whisper

          esphome "${ARGS[@]}" compile heatwhisper_esp32_s3_rs485.yaml
          cp .esphome/build/heat-whisper/build/firmware.factory.bin fw/heatwhisper_esp32_s3_rs485.factory.bin
          cp .esphome/build/heat-whisper/build/firmware.ota.bin fw/heatwhisper_esp32_s3_rs485.ota.bin
```

- [ ] **Step 5: Update `index.html`, `packages/base.yaml`, and `README.md`**

1. In `index.html` line 19: change `(18 defaults, max 50)` → `(17 defaults, max 50)`.
2. In `packages/base.yaml` line 60: change `18 entities; stored in flash, survives OTA.` → `17 entities; stored in flash, survives OTA.`.
3. In `README.md`:
   - Fix typos: `doens't` → `doesn't`, `forcast` → `forecast`, `Hold out, or press` → `Wait for the fallback AP, press`.
   - Add a **Works with** section highlighting out-of-the-box integration with Home Assistant, EnergyWizard (`curve_offset: number.heatwhisper_heat_offset_s1`), EffektGuard, EMHASS, and MQTT/Node-RED (plus note that HeatWhisper deduplicates no-op writes to protect the NIBE EEPROM).
   - Replace the prose "Default entities" section with a full **Entity & Register Reference** table covering all 17 default entities (exact HA entity ID, register, type/unit, values/notes) plus built-in device entities (`Heat Pump Model`, `HeatWhisper version`, `Reset Heat Pump Alarm`, etc.), and note that all three boards now use `heat-whisper` / `HeatWhisper` (upgrading S3/Pico users: mDNS hostname unifies to `heat-whisper.local`; existing Home Assistant entity IDs in HA's registry remain intact).

- [ ] **Step 6: Run full test suite and ESPHome config + compile verification**

Run:
```bash
python3 -m pytest tests/ -v
esphome config heatwhisper_esp32.yaml
esphome config heatwhisper_esp32_s3_rs485.yaml
esphome config heatwhisper_pico_w.yaml
esphome compile heatwhisper_esp32.yaml
```
Expected: All pytest tests PASS, all 3 `esphome config` commands report valid configuration, and `esphome compile` succeeds cleanly with zero errors.

- [ ] **Step 7: Commit**

```bash
git add heatwhisper_esp32_s3_rs485.yaml heatwhisper_pico_w.yaml .github/workflows/build.yml index.html packages/base.yaml README.md tests/test_board_naming.py
git commit -m "chore: unify board names, isolate CI builds, and sync optimizer docs"
```
