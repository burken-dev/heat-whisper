# Passive toggle in picker UI — design

Date: 2026-09-26. Approach A (approved): new 1-byte flash slot, reboot to apply.

## Problem

`passive:` is YAML-only. Every TX on/off test needs a recompile + reflash.
Goal: flip listen-only bring-up from `http://<node>/heatwhisper/registers`, reboot,
no rebuild. Persists in flash like register selection + Modbus mode.

## Architecture

`components/heatwhisper/{heatwhisper.h,heatwhisper.cpp,picker.h}` only. No YAML
schema change; YAML `passive:` stays as first-boot default when no NVS entry.

- New NVS key `HW_PASSIVE_TYPE` (1-byte struct `{version:1, passive:0/1}`),
  `load_passive()` / `save_passive()` mirroring `load/save_mode()`.
- `setup()`: after `apply_runtime_mode_()`, call `apply_runtime_passive_()`
  which overrides `passive_` when an NVS entry exists.
- Picker `list_json_()` gains `"passive":0/1` (effective value: NVS or YAML).
- Existing `POST /heatwhisper/registers/mode` also accepts `passive=0/1`,
  alone or together with `mode=`/`model=`. New checkbox + save wiring in
  `HW_PICKER_HTML`. Response stays `saved,reboot`.

## Data flow

1. Page `GET ?format=json` → `{..., passive: 0|1, runtime:{...}}`.
2. Checkbox renders state; save POSTs `passive=` (+ optional mode fields).
3. Device replies `saved,reboot`; user hits ESPHome Restart.
4. Boot applies NVS passive over YAML default. TX disabled when 1
   (decode + entity publish continue, `queue_write` still queues but nothing
   is sent — same semantics as YAML `passive: true` today).

## Error handling

- Missing/corrupt NVS → fall back to YAML value, page shows it. Never fails boot.
- `passive` present but not `0`/`1` → 400, nothing saved (same as bad mode).
- Mode validation unchanged; passive-only POST must not touch mode slot.
- No live toggle: avoids half-applied TX state mid-poll.

## Testing

- Host pytest: passive save/load round-trip, NVS-absent falls back to YAML,
  `list_json` exposes effective passive, bad value → 400, passive-only POST
  leaves mode untouched.
- `esphome config` on esp32 / esp32-s3-rs485 / pico_w (picker is
  `USE_NETWORK && !USE_ZEPHYR` gated).

## Non-goals

Live no-reboot toggle (needs TX drain + loop safety). Folding passive into
`HeatWhisperMode` (migration churn, no UX gain). Changing YAML semantics.
