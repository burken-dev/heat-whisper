# Generic Modbus-RTU Support — Design

Date: 2026-09-19 | Status: approved (scope: full multi-brand) | Scope: bridge becomes Modbus-RTU master alongside the existing Nibe native slave

## 1. Objective

Support heat pumps other than Nibe over standard Modbus RTU (RS485) with the
same bridge hardware and the same UX (runtime register picker, NVS selection,
HA native API primary, MQTT opt-in). No Modbus-TCP models: they need no
hardware bridge and are out of scope.

## 2. Key insight: the roles flip

Today the pump is master and the bridge is a reactive slave (answers `0x69` /
`0x6B` poll tokens, never transmits unsolicited). Every standard-Modbus heat
pump (or its gateway) is a Modbus *slave*, so the bridge must become a Modbus
RTU *master* that polls on a timer. Everything downstream of decode is reuse.

| Aspect | Nibe native (today, frozen) | Standard Modbus RTU (new) |
|---|---|---|
| Role | Slave, TX only in poll slots | Master, polls on interval |
| Framing | `0x5C` … XOR, `5C 5C` escape | addr + FC + data + CRC16 |
| Byte order | Little-endian | Big-endian (+ word-order variants for u32) |
| Read | `0x69` token → `C0 69` request | FC01 / FC02 / FC03 / FC04 |
| Write | `0x6B` slot | FC05 / FC06 / FC15 / FC16 (Nibe MODBUS40 is FC16-only, no FC06) |
| Model detect | `0x6D` announcement | Explicit `model:` config (Nibe MODBUS40 FC `0x2B` device-ID is the exception) |
| Serial | Fixed 9600 8N1 | Per brand, e.g. 9600 8N1 … 19200 Even |

Approaches considered: (A) custom master in the existing component (chosen —
one UX, handles quirks); (B) reuse ESPHome `modbus_controller` (rejected —
bypasses picker/factory, FC16-only quirk not cleanly supported, splits UX);
(C) static per-brand YAML, no firmware change (rejected — no picker,
duplicated entity logic).

## 3. Architecture

- New `protocol: nibe | modbus_rtu` option on the `nibe:` block (default
  `nibe`). Slave path (`on_frame_` tokens, RMU slots, announcement) is frozen
  and gated on `protocol == nibe`.
- New master scheduler in `heatpump.cpp` (see §10 rename), active only in
  over the enabled NVS selection + `extra_poll`, with response timeout, 3 retries
  then stale marking, and a write queue drained between polls.
- Same UART/RS485 wiring; `flow_control_pin` reused for direction control.
  Baud/parity/stop bits become parameters passed through to the `uart:` block
  (per-brand defaults, user-overridable).
- `passive: true` keeps its bring-up meaning in both modes (decode/log, no TX;
  in master mode: listen only, no polls/writes).

## 4. Catalog schema extension (`registers.py` → `catalog.h`)

Per-register additions, all optional with Nibe-native defaults:

- `mb_fc`: 1 (coil) / 2 (discrete) / 3 (holding) / 4 (input). Default 3.
- Wire address (defaults to the Nibe `register` number; de-facto vs 0-based
  offset normalized at conversion time).
- Word order flag for 32-bit types (default ABCD; CDAB where the vendor spec
  says so).
- Per-model `write_fc` quirk flag (`6` vs `16`; Nibe MODBUS40 forces `16`).

`catalog.h` gains `fc`/`endian` columns on `NibeMeta` (or a parallel
small table if struct churn threatens flash — implementation plan decides).
Validator, `MAX_SELECTION` (50), hints (`entity_hints.json`), and the
`min/max` corrupt guard are unchanged. Nibe `models/*.json` normalize to
`fc=3, BE` with identical register numbers.

## 5. Data flow, entities, picker

- Master poll → BE decode (factor scale, signed adjust, `map` lookup) →
  existing `on_value` fan-out → existing entity factory (sensor / number /
  switch / select), filters (`delta / throttle / heartbeat`), NVS selection.
- Writes: `number`/`switch`/`select` control → clamp to catalog min/max →
  master write queue → FC06 or FC16 per model flag. RMU-range drop rule stays
  Nibe-mode-only.
- Picker (`/heatpump/registers`, see §10 rename): model list becomes the union
  models; in modbus mode the list is filtered by the configured `model:` (no
  auto-detect) with a protocol tag per entry. Save/validate path unchanged.

## 6. Config

```yaml
heatpump:
  protocol: modbus_rtu        # default: nibe
  model: Thermia_Calibra      # required in modbus_rtu mode
  modbus_address: 1           # Modbus slave id
  # baud_rate / parity / stop_bits default from the model's spec, overridable
```

## 7. Model pipeline (Tier 1 — RTU spec in hand)

1. **Nibe F-series via MODBUS40 accessory** — copy existing `models/*.json`
   verbatim (same register numbers: F1145/1155/1245/1255/1345/1355/370/470/
   730/750, VVM225/310/320/325/500, SMO40). FC03/FC16, 9600 8N1, addr 1
   (configurable on v10+). First target; proves the abstraction with zero new
   maps. Source: MODBUS40 installer manual + ModbusManager database.
2. **Thermia Genesis** (Calibra, Diplomat, Atlas, Mega/Eco, Athena…) — convert
   the machine-readable YAML (`nielsbasjes/modbus-devices`) to `model.json`.
   RTU via BM-card `MBe` port, 19200 Even addr 1, FC1/2/3/4/5/6/15/16.
   Source: official Modbus protocol PDF v10–17.1.
3. **Glen Dimplex** (LI/LA/SI/LS, WPM 2006/2007/EconPlus) via **LWPM 410** —
   transcribe the official wiki datapoint list + PDF. FC01–06, ≤19200 baud,
   addr 1–207.
4. **Daikin Altherma 3** via **DCOM-LT/MB** or **Intesis IN485DAI001A000** —
   transcribe Intesis manual tables + DCOM register PDF (~31 core regs).
5. **Mitsubishi Ecodan** (monoblock/split, FTC) via **Intesis IN485MIT001A000**
   / PAC-IF062B-E — transcribe Intesis manual (100+ points).

Each model ships with a comment/link to its source PDF and the accessory (if
any) required for RTU. Excluded (Modbus-TCP, no bridge needed): Nibe S-series,
Stiebel ISG, Luxtronik 2.x (RTU is service-only). Tier 2, PDFs not yet pulled:
Vaillant VR71/72, Viessmann Vitogate, Bosch/Buderus MB LAN2, Samsung MIM-B19N,
LG PI485, Panasonic PAW-AW-MBS, Lambda, Midea. CTC: no public Modbus map found.

## 8. Error handling

- CRC16 fail → drop frame, retry up to 3, then mark entities stale (same
  unavailable semantics as today, no cached-value lies).
- Unknown addr → skip; corrupt value outside min/max → drop (existing guard).
- Write-queue full → drop oldest with log (existing semantics).
- `write_fc` mismatch guarded at codegen: MODBUS40-family models can never
  emit FC06.

## 9. Testing

- Host vectors (extend `tests/`): CRC16 pass/fail, BE decode incl. u32 word
  orders, FC16-only enforcement, Thermia/Dimplex sample registers.
- `esphome config` + `compile` both boards in CI (unchanged); passive
  bring-up procedure per brand (poll first, enable writes after decode
  confirmed).

## 10. Brand-agnostic renaming (lands first, own commit)

Rule: `nibe` stays if and only if it means Nibe-the-vendor, Nibe's proprietary
protocol, or a Nibe model. Everything that means "arbitrary heat pump /
bridge / register catalog" is renamed. The `protocol: nibe` value itself keeps
its name — it *is* Nibe's proprietary protocol.

| Area | Old | New |
|---|---|---|
| Component dir / files | `components/nibe/nibe.{h,cpp}` | `components/heatpump/heatpump.{h,cpp}` (`picker.h`, `sensor.py`, `number.py`, `registers.py`, `entity_hints.json`, `models/` move along) |
| C++ namespace / classes | `esphome::nibe`, `NibeComponent`, `NibeSensor/Number/Select/Switch`, `NibePickerHandler`, `NibeSelection` | `esphome::heatpump`, `HeatpumpComponent`, `HeatpumpSensor/…`, `HeatpumpPickerHandler`, `HeatpumpSelection` |
| Size enum / catalog structs | `NibeSize`/`NIBE_U8…`, `NibeMeta/Title/Model/Hint`, `NIBE_META…`, `NIBE_MODEL_<X>`, `NIBE_DEFAULTS…`, `NIBE_MAX_SELECTION` | `HpSize`/`HP_U8…`, `HpMeta/Title/Model/Hint`, `HP_META…`, `HP_MODEL_<X>`, `HP_DEFAULTS…`, `HP_MAX_SELECTION` |
| Factory name table | `NIBE_BASE_NAMES` | `HP_FACTORY_NAMES` (contents kept verbatim for HA name continuity) |
| Protocol helpers | `calc_crc`, `calc_crc_c0` | `calc_crc_nibe`, `calc_crc_c0_nibe` (new: `crc16_modbus`) |
| Config key / ids | `nibe:`, `nibe_id`, `nibe_bridge`, `nibe_uart` | `heatpump:`, `heatpump_id`, `heatpump_bridge`, `heatpump_uart` |
| Address config | `slave_address` (RMU slave meaning) | kept for nibe mode; modbus mode uses `modbus_address`; both map to one member `peer_addr_` |
| Log tag | `"nibe"` | `"heatpump"` |
| Picker | `/nibe/registers`, `NIBE_PICKER_HTML`, "Nibe register picker" | `/heatpump/registers`, `HP_PICKER_HTML`, "Heat pump register picker" |
| Nodes / firmware | `nibe_esp32.yaml`, `nibe-bridge(-pico)`, "Nibe Bridge", AP `Nibe-Bridge` | `heatpump_esp32.yaml`, `heatpump-bridge(-pico)`, "Heat Pump Bridge", AP `Heatpump-Bridge` |
| CI artifacts / flasher | `nibe_esp32.factory/ota.bin`, `manifest.json`, `index.html` strings | `heatpump_esp32.factory/ota.bin`, same files, renamed strings |
| Tests | `components.nibe.*` imports, `components/nibe/…` paths, `NIBE_*` asserts, `nibe_id` cfgs, `NibeNumber::control` split anchor | same, renamed (`HP_*`, `HeatpumpNumber::control`, …) |

Deliberately kept:

- `models/*.json` filenames, contents, and vendor title strings (`"NIBE
  Inverter …"`) — vendor data, not code naming.
- NVS preference type id value `0x6E696273` (`'nibs'`): unchanged so saved
  register selections survive OTA (symbol becomes `HP_SEL_TYPE` + comment).
- `reference-project/`, old specs/plans under `docs/superpowers/`, git
  history — historical, untouched. Repo rename (GitHub-level) out of scope.
- Already-generic names (`queue_write`, `ensure_polled`, `on_value`,
  `MAX_SELECTION`, `DEFAULT_ENABLED`) — no change.

Migration (breaking, same pattern as the earlier `registers:` removal): users
replace the `nibe:` block with `heatpump:` and re-flash; node rename changes
the MQTT topic prefix, AP SSID, and picker URL but HA entity ids are stable
(titles unchanged) and NVS selections carry over.
