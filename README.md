# HeatWhisper

ESPHome bridge between a NIBE heat pump (RS485) and Home Assistant. It acts as a room-unit slave: answers pump polls, decodes registers, and sends writes back in poll slots. No control logic on-device — telemetry and writes only.

Native HA API is primary. MQTT is opt-in only.

Boards: ESP32 (`heatwhisper_esp32.yaml`) and Raspberry Pi Pico W (`heatwhisper_pico_w.yaml`).

## Supported heat pumps

Brand: **NIBE** (RS485 / NIBE Modbus, not S-series Modbus-TCP).

Auto-detected from the pump's announcement frame — no model setting needed. If your model is not listed, the bridge still runs with a generic register set.

| Family | Models |
|---|---|
| F ground-source | F1145, F1155, F1245, F1255, F1345, F1355 |
| F exhaust-air | F370, F470, F730, F750 |
| S ground-source | S1255 |
| Indoor modules | VVM225, VVM310, VVM320, VVM325, VVM500, VVMS320 |
| Control / accessories | SMO40, SHK200S, HMA60, VPK8R, STAR12, TehowattiAir |
| Room units | RMU40 S1–S4 |

Register maps live in `components/heatwhisper/models/*.json` (one file per model above).

## What you need

- ESP32 or Raspberry Pi Pico W
- RS485-to-TTL transceiver (pump RS485 A/B → transceiver → MCU UART, 9600 8N1)
- NIBE pump with a free RS485 port
- Home Assistant with the ESPHome integration

| Board | TX | RX | Flashing |
|---|---|---|---|
| ESP32 (`esp32dev`) | GPIO17 | GPIO16 | `esphome run` or web flasher (`index.html`) |
| Pico W (`rpipicow`) | GPIO4 | GPIO5 | `firmware.uf2` via USB mass-storage (BOOTSEL) |

Optional `flow_control_pin` (e.g. GPIO18) for transceivers needing manual direction control. Without it, an auto-direction transceiver is assumed.

## Getting started

### 1. Wire it up

Pump RS485 A/B → transceiver → MCU UART pins from the table above. Power the transceiver from the MCU (3.3 V or 5 V per module).

### 2. Add Wi-Fi credentials

```bash
cp secrets.yaml.example secrets.yaml
# edit secrets.yaml
```

```yaml
# secrets.yaml
wifi_ssid: "YOUR_WIFI"
wifi_password: "YOUR_PASSWORD"
ap_password: "heatwhisper01"   # fallback AP, min 8 chars — change it
ota_password: "CHANGE_ME_OTA"
web_password: "CHANGE_ME_WEB"  # web_server :80, user admin
api_key: "BASE64_32_BYTES"     # generate: python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### 3. First flash: listen-only

Flash with listen-only mode so you can verify decoding before the bridge transmits anything:

1. Set `passive: true` under `heatwhisper:` in `packages/base.yaml`.
2. Flash: `esphome run heatwhisper_esp32.yaml` (or `heatwhisper_pico_w.yaml`).
3. Open logs or `http://<node>` (user `admin`) and confirm you see decoded temperatures. If Wi-Fi fails, connect to the `HeatWhisper` fallback AP.

### 4. Enable the bridge and add it to Home Assistant

1. Set `passive: false` (or remove the line), re-flash.
2. In Home Assistant: Settings → Devices & Services → Add → ESPHome, enter the node address. Use the `api_key` from `secrets.yaml` when asked.

### 5. Pick registers

1. Open `http://<node>/heatwhisper/registers`, check what to expose (max 50), save, reboot.
2. The selection is stored in flash and survives OTA. Fewer registers = faster poll cycle, so enable only what you need.

Done — sensors appear in Home Assistant and writable registers appear as numbers/switches/selects.

## Default entities

Created at first boot (18 registers):

Sensors: 40004 BT1 Outdoor, 40008 Supply S1, 40012 Return, 40013 Hot Water Top BT7, 40014 Hot Water BT6, 43009 Calculated Supply, 43136 Compressor Frequency, 40033 Room S1, 43144 Compressor Energy Total, 43305 Compressor Energy HW.

Numbers (writable): 43005 Degree Minutes (-3000…3000), 47011 Heat Offset S1 (-10…10), 47007 Heat Curve S1 (0…15), 47041 HW Comfort (0=Eco, 1=Normal, 2=Luxury, 4=Smart), 47371 Allow Heating, 47370 Allow Additive, 47387 HW Production (all 0/1), 47043 HW Luxury Start Temp (5…70 °C).

Plus a diagnostic `Heat Pump Model` text sensor (empty until the pump's first announcement is heard).

Smart-control recipe: cheap/solar surplus → raise 47011 (+2…+3) and set 47041=2, ensure 47371/47370=1; expensive → lower 47011, set 47041=0, set 47370=0. Prefer 47011 over raw 43005 writes.

## Configuration

```yaml
heatwhisper:
  id: heatwhisper_bridge
  uart_id: heatwhisper_uart
  # passive: true          # decode-only bring-up
  # slave_address: 0x19    # default RMU S1 (0x1A-0x1C = S2-S4, 0x20 = Modbus40 alt)
  # flow_control_pin: GPIO18
  # extra_poll: [10001]    # poll-without-entity (sniffing)
```

Writes to addresses below 20000 (RMU range) are dropped by design.

MQTT (off by default — uncomment block at bottom of `packages/base.yaml`): each entity publishes to its native state topic automatically. Optional `topic_prefix: "heatwhisper"`; HA discovery is automatic, `discovery: false` disables it.

## Modbus-RTU (non-Nibe and Nibe MODBUS40)

Nibe F-family maps double as MODBUS40 maps (same register numbers). The bridge polls as Modbus master behind `protocol: modbus_rtu`:

```yaml
heatwhisper:
  protocol: modbus_rtu
  model: F750        # required in modbus mode
  modbus_address: 1  # peer address
```

Nibe MODBUS40 wiring: MODBUS40 accessory X2 terminals → RS485 A/B transceiver, 9600 8N1; enable MODBUS40 in the pump installer menu. Writes to MODBUS40 models use FC16 only, never FC06 (enforced from `transports.json` `write_fc`). Bring-up order: flash with `passive: true` first to sniff/decode bus traffic, confirm values in logs/`web_server`, then enable TX (`passive: false`). The picker (`/heatwhisper/registers`) tags each model with `"proto": "nibe"|"modbus"` and, in modbus mode, lists the configured model's registers.

## Build / test

```bash
python -m pytest tests/ -v
esphome config heatwhisper_esp32.yaml
esphome compile heatwhisper_esp32.yaml
esphome compile heatwhisper_pico_w.yaml
```

CI (`.github/workflows/build.yml`): pytest → `esphome config` + `compile` both boards → artifacts on tags attached to the GitHub release + deployed to GitHub Pages (web flasher).

## Troubleshooting

- No values? Flash with `passive: true` first, check logs / `web_server` :80 (user `admin`), then re-enable TX.
- Writes ignored for addr < 20000: dropped by design, never sent.
- `Heat Pump Model` empty: pump hasn't sent its announcement yet — wait a minute.
- API "invalid key": regenerate `api_key` as 32 random bytes base64 (see step 2).

## Non-goals

S-series Modbus-TCP, price/weather/curve logic, runtime JSON, per-model hand YAML.

License: MIT. Register maps vendored under their own MIT license (`components/heatwhisper/models/LICENSE`).
