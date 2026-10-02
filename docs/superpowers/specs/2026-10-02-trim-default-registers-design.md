# Trim Default Enabled Registers Set — Design

Date: 2026-10-02  
Status: Approved (Approach 1: Clean Sync)

## Problem

HeatWhisper currently enables 19 registers by default upon first boot. Several auxiliary and high-frequency/energy registers are unnecessary for minimal out-of-the-box operation and crowd Home Assistant dashboards:
- Secondary supply/return temperatures: `40008` (Supply Temp S1), `40012` (Return Temp)
- Derivative calculation: `43009` (Calculated Supply)
- High-frequency compressor telemetry: `43136` (Compressor Frequency)
- Total energy counters: `43144` (Compressor Energy Total), `43305` (Compressor Energy HW)
- Hot water niche setpoint: `47043` (Hot Water Luxury Start Temp)

Users want a leaner first-boot entity footprint while retaining the ability to enable any of these registers on demand via the runtime web picker (`/heatwhisper/registers`).

## Decisions

1. **Remove 7 registers from default enabled set**:
   - `40008` (Supply Temp S1)
   - `40012` (Return Temp)
   - `43009` (Calculated Supply)
   - `43136` (Compressor Frequency)
   - `43144` (Compressor Energy Total)
   - `43305` (Compressor Energy HW)
   - `47043` (Hot Water Luxury Start Temp)

2. **Retain 12 registers in default enabled set**:
   - **Sensors (5)**: `40004` (BT1 Outdoor), `40013` (Hot Water Top BT7), `40014` (Hot Water BT6), `40033` (Room Temp S1), `45001` (Alarm)
   - **Numbers (2)**: `43005` (Degree Minutes), `47011` (Heat Offset S1)
   - **Selects (2)**: `47041` (Hot Water Comfort Mode), `48132` (Temporary Lux)
   - **Switches (3)**: `47370` (Allow Additive Heating), `47371` (Allow Heating), `47387` (Hot Water Production)

3. **Catalog preservation**:
   - The 7 removed registers remain intact in model catalogs (`components/heatwhisper/models/*.json`).
   - The runtime web picker (`http://<node>/heatwhisper/registers`) allows users to enable any of them dynamically at runtime.

4. **1:1 Clean Sync between `DEFAULT_ENABLED` and `HW_FACTORY_NAMES`**:
   - `HW_FACTORY_NAMES` in `heatwhisper.cpp` is trimmed to match `DEFAULT_ENABLED` (12 entries), keeping factory defaults and naming table strictly synchronized.

## Architecture & Impact

- `components/heatwhisper/registers.py`:
  - `DEFAULT_ENABLED` updated from 19 to 12 registers.
  - `DEFAULT_ALLOWLIST` retains allowlisted registers (or keeps subset relationship).
- `components/heatwhisper/heatwhisper.cpp`:
  - `HW_FACTORY_NAMES[]` updated from 19 to 12 entries.
- `components/heatwhisper/catalog.h`:
  - Regenerated via `generate_catalog_header` so `HW_DEFAULTS[]` and `HW_DEFAULTS_N` reflect the 12 registers.
- `README.md`:
  - Update "Default entities" documentation from 18/19 registers to 12 registers.
- `tests/test_subscription.py`:
  - Update `OLD_ENTITY_REGS` and `EXPECTED_BASE_NAMES` test assertions to verify the 12 registers.

## Testing Strategy

- `PYTHONPATH=. pytest`: full suite test run must pass 100%.
- Verify `DEFAULT_ENABLED` length == 12.
- Verify `catalog.h` contains 12 entries in `HW_DEFAULTS[]`.
- Verify `HW_FACTORY_NAMES[]` contains 12 entries matching `DEFAULT_ENABLED`.
