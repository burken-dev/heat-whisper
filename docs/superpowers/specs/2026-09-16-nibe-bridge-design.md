# Nibe-to-MQTT/REST Bridge — Design

Date: 2026-09-16 | Status: approved (verbal, 4 sections) | Scope: ESPHome bare-metal F-series RS485 slave for ESP32 + Pico W

## 1. Objective
Bare-metal bridge between Nibe F-series heat pump (RS485 master) and MQTT / HA Native API. No control logic on-device (no price/weather/curve algorithms). Reliable bi-directional telemetry only: answer polls in <20ms (else Alarm 163), decode registers, queue writes into poll slots.

Reference (`reference-project/`, NibePi Node.js) used only for protocol + `models/*.json` register maps. Not ported.

## 2. Architecture (approach A: active slave)
- ESPHome custom component `nibe`: `Component + UARTDevice`, 9600 8N1 default (19200 optional).
- `loop()` drains UART into ring buffer (non-blocking). Scan for `0x5C`, need ≥5B for len byte `msg[4]`, wait for full `len+6` frame.
- Checksum: XOR over bytes `[2 .. len+4]`; on fail drop + send NACK `0x15` (cf. `backend.js:211-228,199`). Handle leading-`0x06`+`0x5C` shift and `0x5C`-escape (double-`0x5C` squeeze + recompute, cf. `backend.js:169-184`).
- Routing (cf. `backend.js:229-369`):
  - `0x19-0x1C` + `0x60` → RMU slot: send queued RMU write or ACK.
  - `0x19-0x1C` + `0x62/0x63/0xEE` → ACK (+ fixed version reply for `0xEE`).
  - Read token `0x69 len 0` → send next read-request `[C0 69 02 lo hi CRC]` (priority queue first, then round-robin) or ACK `0x06`.
  - Write token `0x6B len 0` → send one queued `[C0 6B 06 lo hi 4B-LE CRC]` or ACK.
  - Data `0x68/0x6A/0x62` (+ announcement `0x6D`) → decode + publish; always ACK.
- Queues: `std::queue<WriteRequest>` (one per eligible window), read round-robin list, priority on-demand list.
- Options: `flow_control_pin` (absent = auto-direction transceiver), `passive: true` (decode only, reuses same path; debug harness), `slave_address` default `0x19` (RMU S1; `0x1A-0x1C` = S2-S4) with `0x20` (Modbus40) as documented alternative.
- Never transmit outside a poll slot. Never block `loop()`.

## 3. Register map & codegen
- Source: `models/*.json` fields `register/factor/size(R:u8/s8/u16/s16/u32/s32)/mode(R/R-W)/titel/unit/min/max/map`.
- Build-time (`__init__.py`): compute intersection → `COMMON[]`; per-model add/remove deltas. Emit `registers.h` as packed struct array. No runtime JSON parsing on MCU.
- Auto-detect: announcement frame (`data[3]==0x6D`, model string slice, cf. `index.js:385-398`) selects overlay at runtime; unknown model → COMMON only; unknown addr → skip.
- Decode LE per reference (`addr = buf[i+1]*256+buf[i]`, value LE per size, signed adjust, `/factor`, optional `map` lookup, min/max corrupt guard → drop + fault log). Key MVP registers: 40004 BT1, 40008 BT2 S1, 40012 BT3 ret, 40013/40014 HW top/load, 43136 compressor actual, 43005 degree-minutes R/W, RMU 1xxxx (10001 alarm, 10020 lux R/W).
- `sensor.py` ← `mode R`; `number.py` ← `R/W` with clamp (`value*factor` vs min/max).

## 4. Entities & network (anti-spam defaults)
- HA Native API primary (`api:` on). MQTT opt-in only (configured → enabled); HA users generate zero broker traffic.
- Allowlist: COMMON table defines *available* registers; entities generated only for curated default (~10: BT1/BT2/BT3, HW top/load, compressor freq, DM, setpoint/offset/mode) + user `registers: [...]` opt-ins. No entity = no messages on either transport.
- Publish on change: `filters:` per sensor (`delta: 0.1` temps, `throttle: 60s`, `heartbeat: 5min`). Pump polls every seconds; HA/broker see updates only on movement or heartbeat.
- If MQTT on: single state topic per entity (`nibe/<addr>/state`), QoS 0, `retain: false`; discovery only for allowlisted entities. No `/json`+`/raw` triple (reference `index.js:1141-1143` pattern explicitly rejected); `debug_mqtt: true` re-enables them.
- `packages/base.yaml`: Wi-Fi fallback AP + captive portal, `web_server` diagnostics, logger kept off UART pins.
- Writes: number/set → clamp → `WriteRequest` → next `0x6B` slot; ACK surfaced as state.

## 5. Builds, safety, testing
- `nibe_esp32.yaml` / `nibe_pico_w.yaml` thin wrappers over `packages/{base,esp32_base,pico_w_base}.yaml` (pins/baud only). Layout per spec §4.
- CI `build.yml`: validate + compile both, `.bin` on tags, `manifest.json` for ESP Web Tools.
- Safety: malformed → drop/NACK; R/W clamp; TX only in slots.
- Test: host `test_decode.py` with vectors (valid/corrupt/escape) in CI; on-device bring-up = `passive: true` first, enable TX after decode confirmed.

## 6. Non-goals (MVP)
S-series Modbus-TCP (runs as docker elsewhere), price/weather/curve logic, runtime JSON, per-model hand YAML.
