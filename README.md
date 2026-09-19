# Nibe Bridge

ESPHome bridge between a Nibe F-series heat pump (RS485 master) and Home Assistant. Active slave: answers pump polls, decodes registers, queues writes into poll slots. No control logic on-device — telemetry only.

Native HA API is primary. MQTT is opt-in only.

Boards: ESP32 (`nibe_esp32.yaml`) and Raspberry Pi Pico W (`nibe_pico_w.yaml`). Thin wrappers over `packages/{base,esp32_base,pico_w_base}.yaml` (pins/baud only). Protocol + register maps (`components/nibe/models/*.json`, MIT, see `models/LICENSE`) come from `reference-project/` (NibePi Node.js) — used as reference only, not ported.

## How it works

- `loop()` drains UART non-blocking, scans for `0x5C` frames, XOR checksum, NACK (`0x15`) on fail. Handles `0x5C`-escape (double-`0x5C` squeeze).
- Routing: read token `0x69` → send next queued `C0 69 02 lo hi CRC` or ACK; write token `0x6B` → send one queued `C0 6B 06 …` or ACK; data `0x68/0x6A/0x62` → decode + publish + ACK; `0x6D` announcement → model auto-detect; RMU `0x19–0x1C` slots (`0x60/0x63/0xEE`) → ACK / fixed version reply. Never transmits outside a poll slot.
- Codegen (`components/nibe/__init__.py` + `registers.py`): at build time merges model JSONs into `registers.h` (`NIBE_COMMON` struct array). No runtime JSON on MCU. Unknown model → common table only; unknown addr → skip; corrupt values (outside min/max) → drop.
- Writes: `number` → clamp raw to merged R/W min/max → `queue_write` → next `0x6B` slot. RMU-range writes (addr < 20000) are dropped.
- Anti-spam: every sensor carries `delta / throttle / heartbeat` filters. Polling alone creates no entity — only `sensor:`/`number:` entries publish.

## Hardware

Pump RS485 (A/B) → RS485-to-TTL transceiver → MCU UART, 9600 8N1.

| Board | TX | RX | Notes |
|---|---|---|---|
| ESP32 (`esp32dev`) | GPIO17 | GPIO16 | Flash via ESP Web Tools (`manifest.json`) or `esphome` |
| Pico W (`rpipicow`) | GPIO4 | GPIO5 | Flash `firmware.uf2` manually via USB mass-storage |

- `flow_control_pin` (e.g. GPIO18): optional RS485 auto-direction pin. Absent = auto-direction transceiver.
- `logger: baud_rate: 0` — logger kept off UART pins (see `packages/base.yaml`).

## Default entities

From `packages/base.yaml`:

Sensors: 40004 BT1 Outdoor, 40008 Supply S1, 40012 Return, 40013 Hot Water Top BT7, 40014 Hot Water BT6, 43009 Calculated Supply, 43136 Compressor Frequency. Number (writable): 43005 Degree Minutes (-3000…3000, step 10).

Allowlist reference (`DEFAULT_ALLOWLIST` in `registers.py`): `40004, 40008, 40012, 40013, 40014, 43136, 43005, 40033, 43009, 10001`. Poll set = your entities + optional `extra_poll:` — no separate list to sync.

## Quick start

```bash
cp secrets.yaml.example secrets.yaml
# edit secrets.yaml with wifi (mqtt optional)
```

```yaml
# secrets.yaml
wifi_ssid: "YOUR_WIFI"
wifi_password: "YOUR_PASSWORD"
# mqtt_broker: "YOUR_MQTT_BROKER"
# mqtt_user: "YOUR_MQTT_USER"
# mqtt_password: "YOUR_MQTT_PASSWORD"
```

Bring-up (recommended — verify decode before transmitting):

1. Set `passive: true` under `nibe:` in `packages/base.yaml`.
2. Flash: `esphome run nibe_esp32.yaml` (or `nibe_pico_w.yaml`).
3. Confirm decoded values in logs / `web_server` (port 80). Fallback AP `Nibe-Bridge` + captive portal if Wi-Fi fails.
4. Set `passive: false` (or remove), re-flash. Bridge now ACKs and answers poll slots.

## Configuration

```yaml
nibe:
  id: nibe_bridge
  uart_id: nibe_uart
  # passive: true          # decode-only bring-up
  # slave_address: 0x19    # default RMU S1 (0x1A-0x1C = S2-S4, 0x20 = Modbus40 alt)
  # flow_control_pin: GPIO18
  # extra_poll: [10001]  # optional poll-without-entity (bring-up sniffing)
```

Migration: delete any existing `nibe: registers: [...]` key — entities auto-poll now; use `extra_poll:` only for entity-less sniffing.

Add an entity (it auto-polls; copy its switch block too if you want a runtime toggle):

```yaml
sensor:
  - platform: nibe
    nibe_id: nibe_bridge
    register: 40033   # example opt-in
    name: "My Register"
    unit_of_measurement: "°C"
    accuracy_decimals: 1
    filters:
      - delta: 0.1
      - throttle: 60s
      - heartbeat: 5min
```

MQTT (off by default — uncomment block at bottom of `packages/base.yaml`): each entity publishes to its single native state topic automatically. No `/json`+`/raw` triple spam.

## Build / test / release

```bash
python -m pytest tests/ -v          # host tests (decode, registers, entities, RMU)
esphome config nibe_esp32.yaml      # validate
esphome compile nibe_esp32.yaml
esphome compile nibe_pico_w.yaml
```

CI (`.github/workflows/build.yml`): pytest → `esphome config` + `compile` both boards → artifacts on tags (`firmware.factory/ota.bin`, Pico `firmware.bin/uf2`) attached to GitHub release.

## Non-goals

S-series Modbus-TCP, price/weather/curve logic, runtime JSON, per-model hand YAML.

License: MIT. Register maps vendored under their own MIT license (`components/nibe/models/LICENSE`).
