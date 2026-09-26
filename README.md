# HeatWhisper

ESPHome bridge between a NIBE heat pump (RS485) and Home Assistant. It acts as a room-unit slave: answers pump polls, decodes registers, and sends writes back in poll slots. No control logic on-device — telemetry and writes only.

Native HA API is primary. MQTT is opt-in only.

Boards: ESP32 (`heatwhisper_esp32.yaml`), ESP32-S3 RS485-CAN (`heatwhisper_esp32_s3_rs485.yaml`), and Raspberry Pi Pico W (`heatwhisper_pico_w.yaml`).

## Supported heat pumps

Brand: **NIBE** (RS485 / NIBE Modbus, not S-series Modbus-TCP).

Auto-detected from the pump's announcement frame — no model setting needed. If your model is not listed, the bridge still runs with a generic register set.

| Family | Models |
|---|---|
| F ground-source | F1145, F1155, F1245, F1255, F1345, F1355 |
| F exhaust-air | F370, F470, F730, F750 |
| Indoor modules | VVM225, VVM310, VVM320, VVM325, VVM500 |
| Control / accessories | SMO40, SHK200S, HMA60, VPK8R, STAR12, TehowattiAir |
| Room units | RMU40 S1–S4 |

Register maps live in `components/heatwhisper/models/*.json` (32 files: the NIBE models above, plus RMU S1–S4 variants, S-series maps, and native Modbus-RTU maps for Lambda/Thermia/Dimplex/Daikin/Mitsubishi — see Modbus-RTU section).

Nibe MODBUS40 (RTU accessory 067 144) covers 16 NIBE models: F1145, F1155, F1245, F1255, F1345, F1355, F370, F470, F730, F750, VVM225, VVM310, VVM320, VVM325, VVM500, SMO40. Five more native Modbus-RTU maps ship in `transports.json` (21 entries total): Lambda_EUL, Thermia_Genesis, Dimplex_WPM, Daikin_Altherma3, Mitsubishi_Ecodan. `model:` in modbus mode must be one of the `transports.json` entries. S-series (S1255, VVMS320, …) is Modbus-TCP only — no bridge needed; their JSON maps are vendored but not usable over this RS485 bridge (the picker lists every catalog file, so ignore the S-series entries).

## What you need

- ESP32, ESP32-S3 RS485-CAN, or Raspberry Pi Pico W
- RS485-to-TTL transceiver (pump RS485 A/B → transceiver → MCU UART, 9600 8N1)
- NIBE pump with a free RS485 port
- Home Assistant with the ESPHome integration

| Board | TX | RX | Flashing |
|---|---|---|---|
| ESP32 (`esp32dev`) | GPIO17 | GPIO16 | `esphome run` or web flasher (`index.html`) |
| ESP32-S3 RS485-CAN (`esp32-s3-devkitc-1`) | GPIO17 | GPIO18 (EN GPIO21) | `esphome run` or web flasher (`index.html`) |
| Pico W (`rpipicow`) | GPIO4 | GPIO5 | `firmware.uf2` via USB mass-storage (BOOTSEL) |

Optional `flow_control_pin` under `heatwhisper:` (e.g. GPIO18) for DIY transceivers needing manual direction control. Without it, an auto-direction transceiver is assumed. This is separate from the ESP32-S3 RS485-CAN package, which sets UART-level `flow_control_pin: GPIO21` in `packages/esp32_s3_rs485.yaml` (onboard transceiver needs manual DE — not auto-direction).

## Getting started (single flash, no secrets file)

### 1. Flash from the browser

Go to the GitHub Pages flasher, plug the board in over USB, click Install. The manifest picks ESP32 vs ESP32-S3 automatically. After flashing, click **Configure Wi-Fi** (Improv over USB). Skipped it? Join the fallback AP `HeatWhisper` (password `heatwhisper01`) and pick your network in the captive portal.

Local build instead: `esphome run heatwhisper_esp32_s3_rs485.yaml` (or `heatwhisper_esp32.yaml`). No `secrets.yaml` needed — the factory image ships open (no API key, no OTA/web passwords) so HA can discover it. Add passwords after adoption (see Hardening).

### 2. Wire it up

Pump RS485 A/B → transceiver → MCU UART pins from the table above. Power the transceiver from the MCU (3.3 V or 5 V per module). Waveshare S3 RS485-CAN: onboard screw terminals, 120Ω jumper ON for a single-drop bus.

### 3. Add it to Home Assistant

Settings → Devices & Services → ESPHome — the node appears automatically (no API key on factory image). Click Add. The pump model is autodetected from its announcement (`Heat Pump Model` sensor, empty until first heard) — no model setting, no Modbus vs NIBE choice for NIBE pumps.

Service menu (hold `Back` 7s) → `5.2 System settings`: enable `Modbus` (required for F-series telemetry & auto-detection). If using RMU room control, enable matching RMU system (e.g. `RMU S2`, leave `RMU S1 OFF` so BT50 stays the S1 room unit). Open `http://<node>/heatwhisper/registers` — `Model: F... (nibe|modbus)` confirms communication is live (`Waiting for pump announcement` = nothing heard yet).

### 4. Pick registers

1. Open `http://<node>/heatwhisper/registers`, check what to expose (max 50), save, reboot (via the ESPHome restart button).
2. The selection is stored in flash and survives OTA. Fewer registers = faster poll cycle, so enable only what you need.

The page also holds the other runtime settings (all saved to flash, reboot to apply): NIBE model pin / Autodetect (pins the catalog filter until the next pump announcement overwrites it), Modbus-RTU setup (see below), listen-only (passive) toggle, RMU slot S1–S4, and a `Reset pump alarm` button (writes 1 to 45171 — NIBE models only).

Done — sensors appear in Home Assistant and writable registers appear as numbers/switches/selects.

### Hardening (optional, after adoption)

Adopt in the ESPHome dashboard (`dashboard_import` is built in), then add `api` encryption, `ota` password, and `web_server` auth and reflash OTA. `secrets.yaml.example` documents the optional extras (MQTT).

### Troubleshooting

- No values? Check A/B wiring (try swapping), confirm decoded temps at `http://<node>`, then re-check the pump port.
- Advanced listen-only bring-up: tick `listen-only (passive, no TX)` at `http://<node>/heatwhisper/registers`, save, reboot — decode first, untick to enable TX. (`passive: true` under `heatwhisper:` in YAML does the same but needs a recompile.)

## Default entities

Created at first boot (18 registers):

Sensors: 40004 BT1 Outdoor, 40008 Supply S1, 40012 Return, 40013 Hot Water Top BT7, 40014 Hot Water BT6, 43009 Calculated Supply, 43136 Compressor Frequency, 40033 Room S1, 43144 Compressor Energy Total, 43305 Compressor Energy HW.

Numbers (writable): 43005 Degree Minutes (-3000…3000), 47011 Heat Offset S1 (-10…10), 47007 Heat Curve S1 (0…15), 47043 HW Luxury Start Temp (5…70 °C).

Select: 47041 HW Comfort (Eco, Normal, Luxury, Smart = raw 0, 1, 2, 4).

Switches: 47371 Allow Heating, 47370 Allow Additive, 47387 HW Production (all 0/1).

Plus a diagnostic `Heat Pump Model` text sensor (empty until the pump's first announcement is heard).

Smart-control recipe: cheap/solar surplus → raise 47011 (+2…+3) and set 47041=2, ensure 47371/47370=1; expensive → lower 47011, set 47041=0, set 47370=0. Prefer 47011 over raw 43005 writes.

## Configuration

```yaml
heatwhisper:
  id: heatwhisper_bridge
  uart_id: heatwhisper_uart
  # passive: true          # decode-only bring-up (or tick listen-only in the picker — no recompile)
  # slave_address: 0x1A    # default RMU S2 (S1=0x19, S2=0x1A, S3=0x1B, S4=0x1C); S2 keeps BT50 on S1
  # No recompile needed: RMU slot is switchable at http://<node>/heatwhisper/registers.
  # (0x20 is the MODBUS40 accessory address — the bridge auto-answers it, but it is not selectable as slave_address.)
  # flow_control_pin: GPIO18  # heatwhisper-level DE pin for DIY transceivers (S3 package uses UART-level GPIO21 instead)
  # extra_poll: [10001]    # poll-without-entity (sniffing)
```

Writes to addresses below 20000 (RMU range) are dropped by design.

MQTT (off by default — uncomment block at bottom of `packages/base.yaml`): each entity publishes to its native state topic automatically. Optional `topic_prefix: "heatwhisper"`; HA discovery is automatic, `discovery: false` disables it.

## Modbus-RTU (advanced: non-Nibe and Nibe MODBUS40)

Default is NIBE slave with autodetect — most users stop here. Only for MODBUS40 accessory or non-NIBE pumps (Lambda/Thermia/…), open `http://<node>/heatwhisper/registers`, pick the model under Modbus-RTU setup, Detect & save, reboot. No recompile; the section is emphasized while no NIBE model is heard. YAML alternative (recompile):

```yaml
heatwhisper:
  protocol: modbus_rtu
  model: F750        # required in modbus mode
  modbus_address: 1  # peer address
```

Nibe MODBUS40 wiring: MODBUS40 accessory X2 terminals → RS485 A/B transceiver, 9600 8N1; enable MODBUS40 in the pump installer menu. Writes to MODBUS40 models use FC16 only, never FC06 (enforced from `transports.json` `write_fc`). The picker (`/heatwhisper/registers`) tags each model with `"proto": "nibe"|"modbus"` and, in modbus mode, lists the configured model's registers.

Lambda EU-L (EU08/13/15/20/35L) needs no accessory (native RTU); bridge default is 19200 EVEN (see `transports.json`). Writes use FC16 only. Note: the pump requires buffer-demand regs 3006–3008 (+3009) to be written together in one FC16 frame, but the bridge sends one single-register FC16 per write — so don't expose 3006–3009 as separate number entities and expect block semantics.

## Build / test / release

```bash
python -m pytest tests/ -v
esphome config heatwhisper_esp32.yaml
esphome config heatwhisper_esp32_s3_rs485.yaml
esphome compile heatwhisper_esp32.yaml
esphome compile heatwhisper_esp32_s3_rs485.yaml
esphome compile heatwhisper_pico_w.yaml
```

CI (`.github/workflows/build.yml`): pytest → `esphome config` + `compile` all three boards → artifacts on tags attached to the GitHub release + deployed to GitHub Pages (web flasher).

## Troubleshooting

- No values? Check wiring (try swapping A/B), check logs / `web_server` :80 (switch Log Level to DEBUG), confirm the pump port is enabled.
- Writes ignored for addr < 20000: dropped by design, never sent.
- `Heat Pump Model` empty: pump hasn't sent its announcement yet — wait a minute.
- Wi-Fi wrong? Hold out, or press Factory Reset Wi-Fi (`button`), or re-run Improv; fallback AP is `HeatWhisper` / `heatwhisper01`.

## Non-goals

S-series Modbus-TCP, price/weather/curve logic, runtime JSON, per-model hand YAML.

License: MIT. Register maps vendored under their own MIT license (`components/heatwhisper/models/LICENSE`).
