# Value Rounding Before Transmission — Design

## Problem

Home Assistant shows numeric values with excessive decimal places (e.g., 21.56789) because raw register values divided by their factor produce floating-point noise.

## Solution

Round all decoded values to 1 decimal place at the single fan-out point `on_value()` in `heatwhisper.cpp`, before any entity (sensor, number, switch, select) receives the value.

## Change

**File:** `components/heatwhisper/heatwhisper.cpp`, line 595

Add one line at the top of `HeatWhisperComponent::on_value()`:

```cpp
v = std::round(v * 10.0f) / 10.0f;
```

## Why This Location

- `on_value()` is the single common path for both NIBE and Modbus-RTU decode paths
- All entity types (sensors, numbers, switches, selects) receive values through this function
- The web picker JSON also benefits from clean numbers
- The write path (`control()`) is unaffected — it uses `std::lround` independently

## Scope

- One line changed
- No new dependencies, no config changes, no API changes
- All value types (temperatures, currents, frequencies, etc.) rounded uniformly
