# Register Subscription Design (Approach A) — 2026-09-19

## Goal
Small default poll set, user-editable in ESPHome, so we never listen to everything
and spam HA. Both moments supported: compile-time YAML (+reflash) and runtime
HA/web UI toggles (no reflash, persisted).

## Context
- Today two lists must be kept in sync: `nibe.registers:` (poll, `components/nibe/__init__.py`)
  and `sensor:`/`number:` entities (publish, `packages/base.yaml`).
- Pump cost: one register per `0x69` poll-slot round-robin (`nibe.cpp`); more regs = slower refresh.
- Wire cost: HA native API is broadcast (`ListEntities` + `SubscribeStates`, both empty requests);
  HA-registry disable does NOT stop device TX. Only `internal: true` or device-side gating saves traffic.
- Catalog: 27 vendored models, 23.5k entries; `NIBE_COMMON` holds ~10 allowlisted regs.

## Decisions (user-confirmed)
- Edit moments: both YAML defaults and runtime toggles.
- Runtime scope: toggle pre-defined entities only (ESPHome cannot create entities at runtime).
- Toggle persistence: survive reboot via stock switch `restore_mode`, no custom flash code.

## §1 — Compile-time source of truth
- `sensor:`/`number:` entries with `register:` auto-enqueue their register for polling
  in `add_sensor()`/`add_number()` (`nibe.h`). No duplicates.
- `nibe.registers:` removed; optional `extra_poll:` kept for poll-without-entity (bring-up sniffing).
- `registers.py` warns at build time if an entity's register is not decodable (not in `NIBE_COMMON`).
- `packages/base.yaml` keeps current defaults: 7 sensors
  (40004, 40008, 40012, 40013, 40014, 43009, 43136) + 1 number (43005).
  Adding e.g. 40033 = paste one `sensor:` block with the standard
  `delta/throttle/heartbeat` filters; no second list to edit.

## §2 — Runtime toggles (stock ESPHome only)
- One companion `template switch` per polled register:
  `entity_category: config`, `optimistic: true`, `restore_mode: RESTORE_DEFAULT_ON`.
  `turn_on/off_action` calls `id(nibe_bridge).set_register_enabled(REG, true/false)`.
- `NibeComponent` gains in-RAM `disabled_` set + `set_register_enabled(addr, on)`.
  Persistence is the switch's own `restore_mode`; no `ESPPreferenceObject`, no `globals` strings.
- Fresh flash (no persisted state) = all ON = today's behavior. After reboot, switches
  restore and re-assert; worst case 1–2 extra polls before restore applies.
- Rejected: custom `switch.platform: nibe` (same result, new C++ platform + restore handling).

## §3 — Poll + publish gating (only C++ change)
- `0x69` handler: rotate past disabled addrs (max one full lap); if all disabled, ACK
  (keeps pump happy, zero register TX).
- `on_value()`: first line `if (disabled_.count(addr)) return;` — stops native-API
  and MQTT sends at the source.
- Poll order/cadence unchanged; a disabled slot costs one queue rotation (µs, no UART TX).

## §4 — Edge cases
- All-disabled → ACK on `0x69`, never stall pump loop.
- Unknown register in entity → build warning, entity never fires, no poll waste.
- `number` + disabled: `control()` still queues the explicit write; readbacks stay
  suppressed until re-enabled.
- `passive: true`: toggles accepted, no TX anyway; `disabled_` still gates publishes (quiet logs).
- Downgrade/fresh flash: all enabled; no migration code.

## §5 — Testing
- Host `pytest`: entity-union→queue (no dupes); disabled addr never TX'd while others cycle;
  `on_value` drop for disabled; all-disabled→ACK.
- Manual: `esphome config` + compile both boards; toggle in `web_server`, confirm UART
  log quiets and HA stops receiving without touching HA entity registry.
- No perf test (rotation is O(N), N≈10).

## Non-goals
- Arbitrary register IDs typed at runtime; profile presets (eco/standard/full);
  per-model hand YAML; S-series Modbus-TCP.
