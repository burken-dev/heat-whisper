# Value Rounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Round all decoded sensor values to 1 decimal place before transmission to Home Assistant.

**Architecture:** Add a single rounding line at the top of `HeatWhisperComponent::on_value()` — the single fan-out point where all decoded values pass through before reaching any entity. Both NIBE and Modbus decode paths call this function.

**Tech Stack:** C++ (ESPHome component), Python (host mirror tests)

## Global Constraints

- Rounding: 1 decimal place via `std::round(v * 10.0f) / 10.0f`
- Location: `components/heatwhisper/heatwhisper.cpp`, `on_value()` method
- No changes to write path, config, or API

---

### Task 1: Add rounding in on_value()

**Files:**
- Modify: `components/heatwhisper/heatwhisper.cpp:595`
- Test: `tests/test_rounding.py`

**Interfaces:**
- Consumes: `float v` parameter from decode paths
- Produces: rounded `float v` passed to all entity `publish_value()` / `publish_state()` calls

- [ ] **Step 1: Write the failing test**

Create `tests/test_rounding.py`:

```python
# tests/test_rounding.py — host mirror of on_value() rounding behavior
import math


def round_to_1_decimal(v: float) -> float:
    """Mirror of the C++ rounding: std::round(v * 10.0f) / 10.0f"""
    return round(v * 10.0) / 10.0


def test_rounds_to_1_decimal():
    assert round_to_1_decimal(21.56789) == 21.6
    assert round_to_1_decimal(21.54999) == 21.5
    assert round_to_1_decimal(-3.14159) == -3.1
    assert round_to_1_decimal(0.0) == 0.0
    assert round_to_1_decimal(100.0) == 100.0


def test_typical_sensor_values():
    # raw 215 / factor 10 = 21.5 (already clean)
    assert round_to_1_decimal(215 / 10) == 21.5
    # raw 2157 / factor 100 = 21.57 -> 21.6
    assert round_to_1_decimal(2157 / 100) == 21.6
    # raw -210 / factor 10 = -21.0
    assert round_to_1_decimal(-210 / 10) == -21.0
```

- [ ] **Step 2: Run test to verify it passes (mirror logic is correct)**

Run: `pytest tests/test_rounding.py -v`
Expected: PASS (validates the rounding formula)

- [ ] **Step 3: Add rounding to on_value() in heatwhisper.cpp**

At line 595 of `components/heatwhisper/heatwhisper.cpp`, add as the first line of `on_value()`:

```cpp
void HeatWhisperComponent::on_value(uint16_t addr, float v) {
  v = std::round(v * 10.0f) / 10.0f;
  for (auto *s : sensors_)
```

- [ ] **Step 4: Verify the change compiles (if ESPHome build env available)**

Run: `esphome compile heatwhisper_esp32s3.yaml` (or closest board config)
Expected: Compiles without errors

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add components/heatwhisper/heatwhisper.cpp tests/test_rounding.py
git commit -m "feat: round sensor values to 1 decimal before transmission"
```
