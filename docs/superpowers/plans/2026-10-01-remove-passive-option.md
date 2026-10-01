# Remove Passive Mode Option Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the "passive" (listen-only) option, NVS persistence, web picker controls, YAML schema, and code paths so HeatWhisper always operates actively (answering polls/queries and transmitting ACKs).

**Architecture:** Purge `passive_` member, `HeatWhisperPassive` NVS struct, and passive bypass branches from `HeatWhisperComponent` (`heatwhisper.h`, `heatwhisper.cpp`). In NIBE mode, always transmit ACKs and accessory responses (`0xEE`, `0x69`, `0x6B`). Remove UI controls from the picker and `passive` parameter from `CONFIG_SCHEMA` in `__init__.py`. Replace `test_passive_toggle.py` with tests asserting no passive concepts remain.

**Tech Stack:** C++ (ESPHome component), Python (ESPHome schema & pytest), HTML/JS (picker).

## Global Constraints

- Do not alter NVS keys other than orphaning `HW_PASSIVE_TYPE`.
- `send_ack_()` must always execute on eligible NIBE frames (`0x68`, `0x6A`, `0x62`, `0x6D`, and unhandled `0x20` frames).
- `on_frame_` must always respond to `0xEE` accessory inquiries with `nibe::build_rmu_version`.
- All pytest tests and `esphome config` checks must pass.

---

### Task 1: Update Tests for Complete Removal of Passive Mode

**Files:**
- Modify: `tests/test_passive_toggle.py` -> rename/replace to test absence of passive mode

- [x] **Step 1: Replace test_passive_toggle.py with test_no_passive assertions**

Verify that:
- `passive` does not exist in `components/heatwhisper/__init__.py` schema.
- `passive_` and `HeatWhisperPassive` do not exist in `heatwhisper.h`.
- `apply_runtime_passive_` does not exist in `heatwhisper.cpp`.
- `"passive"` key is not in `list_json_` or picker HTML.
- `on_frame_` has no `passive_` guards.

- [x] **Step 2: Run test to verify it fails (RED)**

Run: `python3 -m pytest tests/test_passive_toggle.py -v`
Expected: FAIL

---

### Task 2: Remove Passive Logic from C++ Component

**Files:**
- Modify: `components/heatwhisper/heatwhisper.h`
- Modify: `components/heatwhisper/heatwhisper.cpp`

- [x] **Step 1: Remove passive definitions from heatwhisper.h**

Delete:
- `struct HeatWhisperPassive` and its `static_assert`
- `set_passive(bool)`
- `load_passive`, `save_passive`, `is_passive`, `apply_runtime_passive_`
- `bool passive_{false};` member

- [x] **Step 2: Remove passive code paths and picker controls from heatwhisper.cpp**

Remove:
- `HW_PASSIVE_TYPE`, `load_passive`, `save_passive`, `apply_runtime_passive_`
- `apply_runtime_passive_()` call in `setup()`
- `if (passive_) return;` in `poll_one_()`
- `passive_` guards in `on_frame_()`:
  - `0x69 0x00`: remove `if (passive_) return;`
  - `0x6B 0x00`: remove `if (passive_) return;`
  - `0x68/0x6A/0x62/0x6D`: replace `if (!passive_) send_ack_();` with `send_ack_();`
  - `0xEE`: remove `if (passive_) return;`
  - trailing `f[2] == kModbus40Addr`: replace `if (!passive_) send_ack_();` with `send_ack_();`
- Picker HTML: remove `<input type="checkbox" id="psv">` and its JS event listener / value setting
- `list_json_()`: remove `,"passive":` output
- `handle_mode_save_`: remove `passive` argument parsing and saving

- [x] **Step 3: Run tests to verify Task 1 & 2 pass**

Run: `python3 -m pytest tests/test_passive_toggle.py -v`
Expected: PASS

---

### Task 3: Clean up Python Schema, YAML Packages, and Documentation

**Files:**
- Modify: `components/heatwhisper/__init__.py`
- Modify: `packages/base.yaml`
- Modify: `README.md`

- [x] **Step 1: Remove passive option from __init__.py**

Remove `cv.Optional("passive", default=False): cv.boolean,` and `cg.add(var.set_passive(config["passive"]))`.

- [x] **Step 2: Clean up base.yaml and README.md**

Remove commented `# passive: true` in `packages/base.yaml` and remove references to passive/listen-only mode from `README.md`.

- [x] **Step 3: Run full verification suite**

Run:
- `python3 -m pytest tests/ -v`
- `esphome config heatwhisper_esp32.yaml`
- `esphome config heatwhisper_esp32_s3_rs485.yaml`
- `esphome config heatwhisper_pico_w.yaml`
Expected: All PASS
