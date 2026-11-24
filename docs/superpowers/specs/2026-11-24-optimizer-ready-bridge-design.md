# Optimizer-Ready Bridge: Write Deduplication, Expanded Defaults & Unified Naming — Design

Date: 2026-11-24
Status: Draft (awaiting user review)

## Goal

Make HeatWhisper safe and plug-and-play out of the box with external Home Assistant energy optimizers (EnergyWizard, EffektGuard, Smart NIBE, EMHASS, Predbat) while preserving HeatWhisper's core principle: **a simple, zero-logic local bridge**.

Three tightly scoped changes:
1. **Firmware no-op write deduplication & pending-write coalescing** (EEPROM protection against minute-by-minute optimizers and rapid slider drags).
2. **Expand factory default registers from 12 to 17** by adding 5 universal read-only sensors used by heat pump optimizers.
3. **Unify board naming (`heat-whisper` / `HeatWhisper`)** across all 3 boards so HA entity IDs are identical everywhere, update CI for isolated per-board builds, and clean up documentation drift.

---

## 1. Firmware Write Deduplication & Coalescing (EEPROM Protection)

### Motivation
Energy optimizers like EnergyWizard run on 1–5 minute loops and may re-send the same setpoint (e.g., `47011` Heat Offset S1 = `+2`). Currently `HeatWhisperNumber::control`, `HeatWhisperSelect::control`, and `HeatWhisperSwitch::write_state` unconditionally call `parent_->queue_write(...)` on every call, risking unnecessary RS485 traffic and NIBE EEPROM wear.

### Architecture
Extract a small, host-compilable, ESPHome-independent header `components/heatwhisper/write_queue.h` (matching the `nibe.h` seam pattern) containing `WriteRequest`, `QueueResult`, and `WriteQueue`:

```cpp
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
```

`WriteQueue` owns:
- `std::deque<WriteRequest> pending_` with `static constexpr size_t kMaxPending = 4` (preserving the existing 4-slot queue cap).
- `std::vector<std::pair<uint16_t, int32_t>> last_raw_` storing the last known raw integer value per register address (bounded by polled/written register count, ≤ ~50 entries).

### Rules & State Transitions
1. **Unwritable guard:** `enqueue(addr, raw, dedupe, in_flight)` drops `addr < 20000` (`!nibe::is_writable(addr)`) immediately (`DROPPED_UNWRITABLE`).
2. **One-shot commands (`dedupe == false`):** Never compared against `last_raw_` or coalesced in `pending_`. Always enqueued (evicting oldest non-in-flight entry if full). Used by:
   - `setup()` startup alarm reset: `queue_write(45171, 1, false)`
   - `packages/base.yaml` `Reset Heat Pump Alarm` button: `queue_write(45171, 1, false)`
   - `HeatWhisperPickerHandler` `/heatwhisper/reset_alarm`: `queue_write(45171, 1, false)`
3. **Deduplicated entity writes (`dedupe == true`, default):**
   - Let `start = (in_flight && !pending_.empty()) ? 1 : 0`.
   - Determine the effective baseline state for `addr`:
     - If `in_flight && !pending_.empty() && pending_[0].addr == addr`: `has_base = true`, `base_raw = pending_[0].raw`, `base_is_inflight = true`.
     - Else if `last_raw_` contains `addr`: `has_base = true`, `base_raw = last_raw_[addr]`, `base_is_inflight = false`.
     - Else: `has_base = false`.
   - Look for an existing queued entry at index `i >= start` with `pending_[i].addr == addr`:
     - If `pending_[i].raw == raw` → `SKIPPED_DUPE` (no queue change).
     - Else if `has_base && base_raw == raw` → erase `pending_[i]` (`CANCELLED`; target reverted to pump's known or in-flight state).
     - Else → `pending_[i].raw = raw` (`COALESCED`; rapid slider drag `+1 → +2 → +3` becomes a single `+3` write).
   - If no queued entry at index `>= start`:
     - If `has_base && base_raw == raw` → return `base_is_inflight ? SKIPPED_DUPE : SKIPPED_NOOP`.
     - Else (cold boot with no known value yet, or genuine change) → enqueue at back (`ENQUEUED`, or `EVICTED_OLDEST` if full).
4. **Capacity eviction:** When `pending_.size() >= kMaxPending`, evict `pending_[start]` (oldest non-in-flight entry; never evict an active in-flight Modbus-RTU write).
5. **Updating `last_raw_`:**
   - **Authoritative readbacks:** In `HeatWhisperComponent::on_value(uint16_t addr, float v)`, compute `raw = (int32_t) std::lround(v * factor)` using `meta_for(addr)` (same rounding formula as `HeatWhisperNumber::control` and `HeatWhisperSelect`) and call `writes_.record_known(addr, raw)`. This covers both NIBE and Modbus-RTU readbacks uniformly.
   - **Write transmission:**
     - NIBE `0x6B` slot: call `writes_.pop_sent()` right when transmitting the write frame. If `w.dedupe` is true, `pop_sent()` updates `last_raw_[w.addr] = w.raw` so repeated identical writes during the ~20–30s poll window before the next readback are also suppressed. If the pump ignores/reverts the write, the next readback in `on_value` overwrites `last_raw_` with ground truth.
     - Modbus-RTU FC06/FC16 ACK: call `writes_.pop_sent()` upon valid write echo (updates `last_raw_` if `w.dedupe`).
     - Modbus-RTU write failure (3 timeouts or exception): call `writes_.pop_failed()` (pops without updating `last_raw_`, preserving the pump's last known state so retries still send).
6. **Logging & HA UI feedback:**
   - Entity handlers (`HeatWhisperNumber::control`, `HeatWhisperSelect::control`, `HeatWhisperSwitch::write_state`) still call `publish_state(...)` so Home Assistant sees immediate state confirmation.
   - `queue_write` logs `SKIPPED_NOOP` / `SKIPPED_DUPE` / `CANCELLED` / `COALESCED` at `DEBUG`, and `DROPPED_UNWRITABLE` / `EVICTED_OLDEST` at `WARN`.

---

## 2. Expand Default Register Set (12 → 17)

### Rationale
Checking all 16 NIBE F-series & VVM model catalogs against EnergyWizard, EffektGuard, Smart NIBE, and Predheat shows that 5 universal read-only sensors cover the remaining telemetry those optimizers expect, adding only ~5–10s to the poll cycle (still well within the 60s sensor throttle):

| Register | Factory Name | Kind | Unit / HA Metadata | Model Coverage |
|---|---|---|---|---|
| `40008` | `Supply Temp S1` | sensor | `°C` (`temperature`, `measurement`) | 14/16 (matches pre-Oct-2 name) |
| `40012` | `Return Temp` | sensor | `°C` (`temperature`, `measurement`) | 16/16 (matches pre-Oct-2 name) |
| `43009` | `Calculated Supply` | sensor | `°C` (`temperature`, `measurement`) | 16/16 (matches pre-Oct-2 name) |
| `43084` | `Electrical Addition Power` | sensor | `kW` (`power`, `measurement`, 2 dec) | 16/16 |
| `43086` | `Operating Priority` | sensor | unitless (raw NIBE prio code) | 16/16 |

### Synchronized Updates
- `components/heatwhisper/registers.py`: update `DEFAULT_ENABLED` to the 17 sorted addresses:
  `40004, 40008, 40012, 40013, 40014, 40033, 43005, 43009, 43084, 43086, 45001, 47011, 47041, 47370, 47371, 47387, 48132`.
- `components/heatwhisper/heatwhisper.cpp`: update `HW_FACTORY_NAMES[]` to the exact same 17 addresses in strictly ascending address order (required by `std::lower_bound` in `base_name_for`).
- `components/heatwhisper/catalog.h`: regenerate via `esphome config` / `generate_catalog_header` so `HW_DEFAULTS[]` and `HW_DEFAULTS_N = 17` stay in sync.
- Devices that already saved a custom selection in NVS keep their saved list untouched; fresh installs and devices still on factory defaults receive all 17 registers automatically.

---

## 3. Unified Board Naming, CI Build Isolation & Documentation Cleanup

### Unified Board Naming
Set identical `esphome.name` and `esphome.friendly_name` across all three top-level board configs:
- `heatwhisper_esp32.yaml`: `name: heat-whisper`, `friendly_name: HeatWhisper` (unchanged)
- `heatwhisper_esp32_s3_rs485.yaml`: `name: heat-whisper`, `friendly_name: HeatWhisper` (was `heat-whisper-s3` / `HeatWhisper S3`)
- `heatwhisper_pico_w.yaml`: `name: heat-whisper`, `friendly_name: HeatWhisper` (was `heat-whisper-pico` / `HeatWhisper Pico`)

This guarantees identical Home Assistant entity IDs (`sensor.heatwhisper_*`, `number.heatwhisper_*`, `select.heatwhisper_*`, `switch.heatwhisper_*`) and mDNS hostname (`heat-whisper.local`) on every supported board, with no hardcoded `build_path:` polluting `dashboard_import`.

### CI Build Isolation (`.github/workflows/build.yml`)
Because all three boards now compile into `.esphome/build/heat-whisper/`, update the `compile` job so each board is compiled, its artifacts are copied into `fw/`, and `.esphome/build/heat-whisper` is cleared before compiling the next board:
1. Compile `heatwhisper_esp32.yaml` → copy `.esphome/build/heat-whisper/build/firmware.{factory,ota}.bin` to `fw/` → `rm -rf .esphome/build/heat-whisper`
2. Compile `heatwhisper_pico_w.yaml` → copy `.esphome/build/heat-whisper/.pioenvs/heat-whisper/firmware.{bin,uf2}` to `fw/` → `rm -rf .esphome/build/heat-whisper`
3. Compile `heatwhisper_esp32_s3_rs485.yaml` → copy `.esphome/build/heat-whisper/build/firmware.{factory,ota}.bin` to `fw/heatwhisper_esp32_s3_rs485.{factory,ota}.bin`

Downstream `release` and `pages` jobs remain unchanged because the output filenames in `fw/` are identical.

### Documentation & Drift Fixes
- `index.html`: update `18 defaults` → `17 defaults`.
- `packages/base.yaml`: update `18 entities` comment → `17 entities` and pass `false` to `queue_write(45171, 1, false)` on the alarm reset button.
- `README.md`:
  - Replace prose default entity list with a full **Entity & Register Reference table** listing exact HA entity IDs, register address, kind/unit, and value meanings (including `43086` priority codes and `47041`/`48132` select options).
  - Add a short **Works with** section noting out-of-the-box compatibility with Home Assistant, EnergyWizard (`curve_offset` → `number.heatwhisper_heat_offset_s1`), EffektGuard, EMHASS, and MQTT/Node-RED.
  - Note the unified `heat-whisper.local` hostname for existing S3/Pico users upgrading from earlier versions.
  - Fix minor typos (`doens't` → `doesn't`, `forcast` → `forecast`, `Hold out` → `Wait for the fallback AP`).

---

## Testing & Verification Strategy

1. **New host C++ unit tests (`tests/test_write_queue.py`)** compiled with `g++ -std=c++17 -Wall -Werror` against `components/heatwhisper/write_queue.h` (same pattern as `tests/test_nibe.py`):
   - Cold boot write (unknown register) is enqueued.
   - Matching known readback is skipped (`SKIPPED_NOOP`).
   - Changed value is enqueued (`ENQUEUED`).
   - Duplicate pending write is skipped (`SKIPPED_DUPE`).
   - Rapid slider changes coalesce in place (`COALESCED`).
   - Pending write reverted back to known pump state cancels pending write (`CANCELLED`, queue empty).
   - Post-TX pre-readback duplicate is skipped (`SKIPPED_NOOP`), and subsequent contradictory pump readback allows retry.
   - `pop_failed()` does not update `last_raw_`, allowing retry after Modbus failure.
   - In-flight Modbus write (`in_flight=true`) is never mutated or evicted; matching write returns `SKIPPED_DUPE`; different write queues behind it and coalesces subsequent updates at index ≥ 1.
   - `dedupe=false` (e.g., `45171` Reset Alarm) always enqueues even when sent repeatedly.
   - Sub-20000 addresses return `DROPPED_UNWRITABLE`.
   - Queue cap `kMaxPending == 4` evicts oldest non-in-flight entry (`EVICTED_OLDEST`).
   - Source-level checks confirming `heatwhisper.{h,cpp}` delegates to `WriteQueue`, calls `record_known` in `on_value`, calls `pop_sent`/`pop_failed`, and passes `dedupe=false` for `45171` resets.
2. **Update `tests/test_final_fixes.py`**: update `test_write_queue_capped` to verify `kMaxPending = 4` in `write_queue.h` (or `writes_` delegation in `heatwhisper.h`).
3. **Update `tests/test_subscription.py`**: update `OLD_ENTITY_REGS` and `EXPECTED_BASE_NAMES` to the 17 factory defaults and verify strict ascending order of `HW_FACTORY_NAMES`.
4. **New config/CI test (`tests/test_board_naming.py`)**: verify all 3 top-level YAMLs set `name: heat-whisper` and `friendly_name: HeatWhisper`, that `build.yml` isolates `.esphome/build/heat-whisper` between compiles, and that `index.html`, `packages/base.yaml`, and `README.md` agree on `17` default registers.
5. **Full validation**:
   - `python3 -m pytest tests/ -v` (all tests pass)
   - `esphome config` on all three board YAMLs (`heatwhisper_esp32.yaml`, `heatwhisper_esp32_s3_rs485.yaml`, `heatwhisper_pico_w.yaml`)
   - `esphome compile` on at least ESP32 / ESP32-S3 (and check Pico W if toolchain present) to verify clean C++ compilation with zero warnings/errors.
