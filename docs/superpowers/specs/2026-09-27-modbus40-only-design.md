# MODBUS40-only (drop RMU emulation) — design

Date: 2026-09-27. Approach B (approved): hard-code 0x20 + split the overloaded `peer_`.

## Problem

NIBE-bus mode answers two addresses: runtime-selectable RMU `peer_` (`0x19–0x1C`)
plus MODBUS40 `0x20`. Pump menu 5.2 is now Modbus ON / RMU OFF, so the RMU slot
selector does nothing (`apply_runtime_peer_` is skipped in RTU mode and the
`0x20` path works regardless of `peer_` in NIBE mode). The selector + NVS +
`slave_address` + `0x60/0x63/0xEE-for-peer` branches are dead weight, and the
picker hint wrongly tells the user to enable an RMU system. Single user: no
migration needed, stale `HW_PEER_TYPE` NVS can be orphaned.

## Goals (supported after cleanup)

1. NIBE pumps without MODBUS40 accessory: ESP emulates MODBUS40 (`0x20`) on the
   NIBE master/slave bus (5C/C0 framing). Same telemetry as today.
2. Standard Modbus-RTU pumps (incl. NIBE via real MODBUS40 accessory,
   Lambda/Thermia/Dimplex/Daikin/Mitsubishi): unchanged master/poll path driven
   by `transports.json`.

## Architecture (Approach B)

Hard-code the NIBE-bus slave address and un-overload `peer_`:

- `heatwhisper.h`: `peer_{0x1A}` → `modbus_addr_{1}` (RTU slave address only);
  add `static constexpr uint8_t kModbus40Addr = 0x20;`. `peer_seen_` →
  `modbus40_seen_` (set only on `0x20` poll in NIBE mode; never set in RTU mode
  today). Setters `set_slave_address`/`set_peer_address` → single
  `set_modbus_address(uint8_t)`; drop `get_peer()`, rename `peer_seen()` →
  `modbus40_seen()`. Delete `HeatWhisperPeer`, `load/save_peer`,
  `apply_runtime_peer_`, `HW_PEER_TYPE`.
- `__init__.py`: delete `slave_address` option; keep `modbus_address` (1–247,
  default 1); `to_code` calls `set_modbus_address` only. `setup()` drops the
  `apply_runtime_peer_()` call; `apply_runtime_mode_()` sets `modbus_addr_`
  from `HW_TRANSPORTS` in RTU mode and leaves the `0x20` constant alone in
  NIBE mode.
- `heatwhisper.cpp::on_frame_`: every `(f[2]==peer_ || f[2]==0x20)` → 
  `(f[2]==kModbus40Addr)`; `0x68`-family guard → `if (f[2] != 0x20) return;`,
  ACK only for `0x20`. Delete `0x60/0x63` RMU branches and the trailing
  `else if (f[2]==0x20 || f[2]==peer_)` (fold into the `0x20` ACK). `0x69` empty
  slot always sends `C0 69 00 A9`. Keep `0xEE→0x20` version reply byte-identical
  (Alarm-251 fix, `5bb3f28`); reword comment to MODBUS40 accessory version.
- `poll_one_/on_modbus_frame_` (RTU path): `peer_` → `modbus_addr_`, no logic
  change.
- Picker: delete RMU row + `peer=` POST (`handle_mode_save_` peer block);
  JSON replaces `"peer":N,"peer_seen":B` with `"modbus40_seen":B`; status line
  reads "Pump is polling MODBUS40 (0x20) — reads/writes live." /
  "Pump has not polled 0x20 yet — enable Modbus in 5.2, keep RMU OFF."
- Catalog: delete `models/RMU40_S1–S4.json`. Keep `nibe::is_writable`
  (`<20000` drop) — 1xxxx stays read-only on the wire. Keep pump-side
  `47365–68` (RMU System) + `48889` (MODBUS40) registers: they are pump
  settings, not emulation. Keep `build_rmu_version` bytes (used for `0x20`);
  delete `build_rmu63` (RMU-only) + its test.
- Docs: `packages/base.yaml`, `README.md`, `index.html` → "5.2: Modbus ON,
  all RMU OFF; no slot to pick".

## Error handling & edge cases

- Stale `HW_PEER_TYPE` NVS left orphaned (single user, no migration).
- `0xEE` kept byte-identical for `0x20`; `0x60/0x63` to `0x20` now get generic
  ACK (matches reference `backend.js:357-366`, which only special-cases RMU
  addresses).
- Passive mode, `0x6D` autodetect, write queue, corrupt-value guard unchanged.

## Testing & verification

- Delete `tests/test_rmu.py`, `tests/test_runtime_peer.py`.
- Rewrite `tests/test_fix_modbus_and_model.py:37,80` → 0x20-only asserts
  (`f[2] == 0x20`, no `peer_`, no `0x19–0x1C`); `tests/test_config.py`
  (`slave_address` key gone); `tests/test_nibe.py` (RMU asserts → MODBUS40
  `0x20`; drop `build_rmu63` test).
- `python3 -m pytest tests/ -v` green; `esphome config` on all three boards.

## Non-goals

- No `peer_` → dual-member split beyond `modbus_addr_` + `kModbus40Addr`
  constant; no JSON key backwards-compat; no RMU room-control coexistence.
