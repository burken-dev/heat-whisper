# Nibe Bridge — Runtime Register Picker (design)

Date: 2026-09-19. Status: approved (approach + sections confirmed by user).

## Problem

Exposed registers are fixed at compile time: `DEFAULT_ALLOWLIST` (19 entries)
in `components/nibe/registers.py` plus hand-written `sensor:`/`number:` and
`Enable …` switch blocks in `packages/base.yaml`. Adding a register means
editing YAML, recompiling, reflashing — too hostile for webflasher users.

## Decisions (from brainstorming Q&A)

- Picker lists **only the detected pump's model registers** (~600, filtered via
  the existing 0x6D auto-detect `model_` string).
- Entity types are **smart**: curated hints map known addresses to
  switch/select; everything else defaults to R→sensor, R/W→number.
- Max **~50** simultaneously enabled registers (poll cycle + RAM bound).
- Reboot-to-apply is acceptable; persistence must survive reboot/OTA without HA.

## Rejected alternatives

- **Browser-side YAML generator** (picker emits YAML, user compiles): zero MCU
  risk but keeps the compile step — fails the webflasher goal. Fallback only.
- **All ~600 registers as disabled-by-default compiled entities**: blows ESP32
  RAM, spams HA discovery, still needs recompile per model. Rejected.

## Architecture (chosen)

1. **Catalog in flash.** Extend `registers.py` codegen to emit a full catalog
   (replacing the 19-entry `NIBE_COMMON`): one row per unique register (addr,
   factor, size, R/W, min/max ≈ 14 B × 3221 ≈ 45 KB) plus title/unit strings,
   organized per model for picker filtering. Single generic binary for all pumps.
2. **`entity_hints.json` overlay.** Small hand-maintained file: addr →
   `{type: switch|select|number|sensor, options/labels, step}`. Covers known
   flags (e.g. 47371/47370/47387 → switch) and enums (e.g. 47041 comfort →
   select Eco/Normal/Luxury/Smart). Default: mode R→sensor, R/W→number with
   min/max/step from catalog factor/range.
3. **NVS selection.** Enabled set (≤50 addrs + version) stored via ESPHome
   `Preferences`; survives reboot/OTA, no HA needed. Empty/corrupt NVS seeds
   the current 19 defaults (factory set = today's entities).
4. **Boot-time entities.** `NibeComponent::setup()` reads NVS, drops unknown
   addrs with a warning, creates only enabled entities (new `NibeSelect` /
   switch classes alongside existing `NibeSensor`/`NibeNumber`), registers them
   with `App`, seeds the poll queue via existing `ensure_polled`. Decode,
   publish, write-queue, and RMU-drop paths unchanged.
5. **Picker page.** Dependency-free page on `web_server` :80 at
   `/nibe/registers` (inherits existing admin auth): GET returns detected
   model's registers with enabled flags (text filter + "enabled only" toggle);
   POST validates (known addr, ≤50, dedupe) → NVS commit → reboot-button to
   apply. Model unknown → show 19 defaults with "waiting for pump announcement".
   The 0x6D `model_` string is normalized (uppercase alphanumeric prefix) to
   match a `models/<NAME>.json` basename; no match → defaults list + notice.
6. **Migration.** Delete static sensor/number/Enable-switch blocks from
   `packages/base.yaml`; keep entity titles so HA names stay stable. Breaking
   change (Enable switches removed) goes in release notes. MQTT, `extra_poll`,
   `passive`, pins untouched.

## Data flow

- Boot: NVS → validate → create entities by hint type → `ensure_polled` each.
- Picker: 0x6D `model_` filters list; POST → validate → NVS → reboot → entities.
- Writes: select/switch/number control → catalog range clamp → existing
  `queue_write` → `0x6B` slot; addr < 20000 dropped as today.

## Error handling

| Case | Behavior |
|---|---|
| Model not announced | Picker shows defaults + notice |
| NVS corrupt/version mismatch | Fall back to 19 defaults + log warning |
| Saved addr gone from maps | Skipped at boot + warning |
| POST >50 / unknown addr | 400 rejected, nothing written |
| Pico W flash overflow | CI compile catches; per-model binary split is out-of-scope fallback |
| Slow poll cycle at 50 regs | Documented; the cap is the control |

## Testing & rollout

- Host pytest: codegen union map, per-model filter, hints merge, POST/boot
  validator, one-model picker-JSON golden test.
- CI: existing `esphome config` + compile both boards, watch binary size.
- Manual: flash → model detected → toggle 3 regs → reboot → entities appear →
  writes clamp → disable → reboot → gone.
- Non-goals: no-reboot apply, per-entity filter tuning in picker (firmware
  delta/throttle/heartbeat defaults apply to all dynamic entities).
