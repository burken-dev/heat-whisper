# Trim Default Enabled Registers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trim the first-boot default registers from 19 to 12 registers by removing 40008, 40012, 43009, 43136, 43144, 43305, and 47043.

**Architecture:** Update `DEFAULT_ENABLED` in `components/heatwhisper/registers.py` and `HW_FACTORY_NAMES` in `components/heatwhisper/heatwhisper.cpp` to the 12 default registers; regenerate `components/heatwhisper/catalog.h` via `esphome compile --only-generate heatwhisper_esp32.yaml`; update `tests/test_subscription.py` and `README.md` to reflect the 12 registers.

**Tech Stack:** Python 3.12, C++ (ESPHome component), pytest, ESPHome CLI.

## Global Constraints

- Retain removed registers in `components/heatwhisper/models/*.json` so runtime web picker can still enable them.
- Preserve 1:1 sync between `DEFAULT_ENABLED` and `HW_FACTORY_NAMES`.
- Ensure all tests in `PYTHONPATH=. pytest` pass.

---

### Task 1: Update Default Registers and Tests (TDD)

**Files:**
- Modify: `tests/test_subscription.py:27-68`
- Modify: `components/heatwhisper/registers.py:72-74`
- Modify: `components/heatwhisper/heatwhisper.cpp:83-91`
- Modify: `components/heatwhisper/catalog.h:46-47`

**Interfaces:**
- Consumes: Design spec `docs/superpowers/specs/2026-10-02-trim-default-registers-design.md`
- Produces: `DEFAULT_ENABLED` (12 registers), `HW_FACTORY_NAMES` (12 registers), `catalog.h` (`HW_DEFAULTS_N = 12`)

- [ ] **Step 1: Write the failing tests in `tests/test_subscription.py`**

Update `OLD_ENTITY_REGS` and `EXPECTED_BASE_NAMES` in `tests/test_subscription.py` to match the 12 default registers:

```python
OLD_ENTITY_REGS = (40004, 40013, 40014, 43005,
                   40033, 45001, 47011, 47041, 47371, 47370, 47387, 48132)
```

And in `test_factory_covers_old_entity_set`:
```python
    EXPECTED_BASE_NAMES = ["BT1 Outdoor",
        "Hot Water Top BT7", "Hot Water BT6",
        "Room Temp S1", "Degree Minutes", "Heat Offset S1",
        "Alarm", "Hot Water Comfort Mode", "Allow Heating",
        "Allow Additive Heating", "Hot Water Production", "Temporary Lux"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_subscription.py -v`  
Expected: FAIL on `test_factory_covers_old_entity_set` because `DEFAULT_ENABLED` and `HW_FACTORY_NAMES` still have 19 entries.

- [ ] **Step 3: Update `DEFAULT_ENABLED` in `components/heatwhisper/registers.py`**

Modify lines 72-74 of `components/heatwhisper/registers.py`:
```python
DEFAULT_ENABLED = [40004, 40013, 40014, 43005,
                   40033, 45001, 47011, 47041, 47371, 47370, 47387, 48132]
```

- [ ] **Step 4: Update `HW_FACTORY_NAMES` in `components/heatwhisper/heatwhisper.cpp`**

Modify `HW_FACTORY_NAMES[]` in `components/heatwhisper/heatwhisper.cpp`:
```cpp
static const struct { uint16_t addr; const char *name; } HW_FACTORY_NAMES[] = {
  {40004, "BT1 Outdoor"}, {40013, "Hot Water Top BT7"}, {40014, "Hot Water BT6"},
  {43005, "Degree Minutes"}, {40033, "Room Temp S1"}, {45001, "Alarm"},
  {47011, "Heat Offset S1"}, {47041, "Hot Water Comfort Mode"}, {47371, "Allow Heating"},
  {47370, "Allow Additive Heating"}, {47387, "Hot Water Production"}, {48132, "Temporary Lux"},
};
```

- [ ] **Step 5: Regenerate `components/heatwhisper/catalog.h`**

Run: `esphome compile --only-generate heatwhisper_esp32.yaml`  
Verify `components/heatwhisper/catalog.h` has lines 46-47 updated:
```cpp
static const uint16_t HW_DEFAULTS[] = {40004,40013,40014,43005,40033,45001,47011,47041,47371,47370,47387,48132};
static const uint8_t HW_DEFAULTS_N = 12;
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest -v`  
Expected: All tests PASS.

- [ ] **Step 7: Commit changes**

```bash
git add tests/test_subscription.py components/heatwhisper/registers.py components/heatwhisper/heatwhisper.cpp components/heatwhisper/catalog.h
git commit -m "feat: trim default enabled registers from 19 to 12"
```

---

### Task 2: Update Documentation in `README.md`

**Files:**
- Modify: `README.md:95-107`

**Interfaces:**
- Consumes: Task 1 results (12 default registers)
- Produces: Updated `README.md`

- [ ] **Step 1: Update "Default entities" in `README.md`**

Update lines 95-107 in `README.md` to reflect the 12 default registers:
```markdown
## Default entities

Created at first boot (12 registers):

Sensors: 40004 BT1 Outdoor, 40013 Hot Water Top BT7, 40014 Hot Water BT6, 40033 Room S1, 45001 Alarm.

Numbers (writable): 43005 Degree Minutes (-3000…3000), 47011 Heat Offset S1 (-10…10).

Select: 47041 HW Comfort (Eco, Normal, Luxury, Smart = raw 0, 1, 2, 4), 48132 Temporary Lux (Off, 3h, 6h, 12h, One time = raw 0, 1, 2, 3, 4).

Switches: 47371 Allow Heating, 47370 Allow Additive, 47387 HW Production (all 0/1).

Plus a diagnostic `Heat Pump Model` text sensor (empty until the pump's first announcement is heard).
```

- [ ] **Step 2: Commit README changes**

```bash
git add README.md
git commit -m "docs: update default entities list in README to 12 registers"
```

---

### Task 3: Full Verification

**Files:**
- Verification only

- [ ] **Step 1: Run pytest full test suite**

Run: `PYTHONPATH=. pytest -v`  
Expected: All tests PASS (0 failures, 0 errors).

- [ ] **Step 2: Validate ESPHome configurations**

Run:
```bash
esphome config heatwhisper_esp32.yaml
esphome config heatwhisper_esp32_s3_rs485.yaml
esphome config heatwhisper_pico_w.yaml
```
Expected: All three configurations report `INFO Configuration is valid!`.

- [ ] **Step 3: Confirm git status is clean**

Run: `git status`  
Expected: Clean working tree.
