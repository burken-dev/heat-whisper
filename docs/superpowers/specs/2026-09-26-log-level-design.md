# Runtime Log Level via ESPHome select.logger — design

Date: 2026-09-26. Approach 1 (approved): native `select.logger` with `initial_level: INFO`.

## Problem

ESPHome defaults `logger:` to `level: DEBUG`. Because HeatWhisper continuously decodes and publishes 18–50 registers from the heat pump RS485 bus, ESPHome's internal core logs every sensor state update over Server-Sent Events (SSE `/events`) to the web UI (`:80`):
```text
[D][sensor:094]: 'Outdoor temp (BT1)': Sending state 12.40000 °C with 1 decimals of accuracy
```
This floods the web UI log console with continuous debug messages, drowning out real diagnostic logs (pump announcements, RMU slot polling, CRC errors, dropped writes) and creating unnecessary Wi-Fi and browser overhead during normal operation.

## Architecture

Leverage ESPHome's native logging capabilities in `packages/base.yaml` without custom C++ or NVS boilerplate:

- Set `level: DEBUG` in `logger:` to retain the compile-time ability to output debug messages on demand.
- Set `initial_level: INFO` in `logger:` so the node boots in quiet mode. State pushes (`[D][sensor:...]`) are suppressed; only Wi-Fi connections, pump announcements, OTA events, warnings, and errors are logged.
- Add ESPHome's built-in `select.logger` entity:
  ```yaml
  select:
    - platform: logger
      name: "Log Level"
      entity_category: config
  ```
  This automatically exposes a dropdown entity (`NONE`, `ERROR`, `WARN`, `INFO`, `DEBUG`) on both the ESPHome Web UI (`http://<node>/`) and in Home Assistant under device Configuration.

## User Experience & Data Flow

1. **Normal Operation / First Boot**:
   - Device boots at `initial_level: INFO`.
   - Web UI logs console is quiet and clean.
   - Sensor state updates are published to Home Assistant and web server entity cards as usual without emitting debug log messages.

2. **Troubleshooting / Diagnostics**:
   - User opens `http://<node>/` or Home Assistant device settings.
   - User changes "Log Level" dropdown from `INFO` to `DEBUG`.
   - ESPHome immediately switches logging verbosity in memory to `DEBUG` without rebooting or recompiling.
   - Debug logs immediately stream to the web UI console and serial terminal.
   - User can switch back to `INFO` once troubleshooting is complete.

## Error Handling & Edge Cases

- **Compile ceiling**: Setting `level: DEBUG` ensures all debug strings are preserved in the compiled binary so runtime elevation to `DEBUG` succeeds.
- **Power cycle / Reboot**: Device restarts cleanly at `initial_level: INFO`.
- **Entity namespace**: The `select` entity uses `entity_category: config` to keep it organized with device maintenance controls (Restart, Factory Reset).

## Testing & Verification

- `esphome config heatwhisper_esp32.yaml`
- `esphome config heatwhisper_pico_w.yaml`
- `esphome config heatwhisper_esp32_s3_rs485.yaml`
- Add host pytest test in `tests/test_config.py` verifying that:
  - `packages/base.yaml` sets `initial_level: INFO` under `logger:`.
  - `packages/base.yaml` configures `platform: logger` under `select:`.
- Run full pytest test suite (`python3 -m pytest tests/ -v`).

## Non-goals

- Adding custom log level controls to the `/heatwhisper/registers` HTML picker page (the register picker is dedicated to pump register allowlisting and protocol bring-up; ESPHome's native web dashboard already provides `select.logger`).
- Custom C++ log filtering or NVS persistence for log level across reboots.
