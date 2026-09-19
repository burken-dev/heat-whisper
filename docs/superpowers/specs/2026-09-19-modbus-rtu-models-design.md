# Modbus-RTU Models — Design

Date: 2026-09-19 | Status: approved (batch C, 6 families) | Scope: which models get `model.json` + `transports.json` entries, in what order

Depends on: generic Modbus-RTU spec (`2026-09-19-generic-modbus-rtu-design.md` §7),
master plan (`plans/2026-09-19-modbus-master-nibe-modbus40.md`), brand pipeline
plan (`plans/2026-09-19-modbus-brand-models.md`). Requires rename + master
applied first. Selection criteria (agreed): spec-ready + easy wins first, then
as many as openly spec'd allows.

## 1. Approved batch (ordered easiest-first)

1. **Nibe F-series via MODBUS40** — copy existing `models/*.json` verbatim
   (F1145/1155/1245/1255/1345/1355/370/470/730/750, VVM225/310/320/325/500,
   SMO40). FC03/FC16 (FC16-only writes), 9600 8N1, addr 1. Zero new maps;
   proves the master abstraction. Source: MODBUS40 installer manual +
   ModbusManager DB (already in repo history).
2. **Thermia Genesis** (Calibra, Diplomat, Atlas, Mega/Eco, Athena…) —
   scripted conversion of machine-readable YAML to `Thermia_Genesis.json`.
   19200 Even, addr 1, FC1/2/3/4/5/6/15/16. RTU via BM-card `MBe` port.
   Sources: official "Modbus protocol for Genesis platform" PDF v10–17.1;
   base `https://github.com/nielsbasjes/modbus-devices/tree/main/modbus-device-thermia-genesis`
   (schemas v10/12/13, Apache-2.0, do NOT vendor — download once, convert,
   cite URL+version in commit); overview `https://modbus.basjes.nl/devices/thermia/`.
3. **Lambda EU-L** (EU08L/13L/15L/20L/35L, incl. Zewotherm rebrand) — NEW
   promotion (was not in Tier 1). Official PDF `1_0_0_Modbusprotokoll.pdf`
   (v1.0.0, 2026): native RTU + TCP, controller is server/slave, all reads
   FC03, all writes FC16 (even single register). No accessory required —
   cheapest BOM of the batch. One register map shared across all EU-L sizes
   (only capacity differs). Transport serial params (baud/parity) read from
   PDF §1 at conversion time and recorded in `transports.json` + commit
   message. Sources: `https://www.lambda-wp.com/fileadmin/userdaten/docs/downloads/regler/1_0_0_Modbusprotokoll.pdf`
   via `https://www.lambda-wp.com/en/services/downloads/`;
   cross-checks `https://github.com/TRON4R/ha-lambda-heatpump-modbus`
   (spec 2025-02-13) and `https://www.openhab.org/addons/bindings/modbus.lambda/`.
   Note: registers 06–08 (buffer demand block) must be written together —
   converter marks them; master sends one FC16 covering the block.
4. **Dimplex WPM** (LI/LA/SI/LS, WPM 2006/2007/EconPlus) via **LWPM 410** —
   transcribe open wiki to `Dimplex_WPM.json` (~100 vars, int16 tenths °C).
   9600 8N1 factory (≤19200, addr 1–207), FC01–06 (`write_fc: 6`).
   Source: `https://dimplex.atlassian.net/wiki/spaces/DW/pages/2900787230/Modbus+RTU+connection+EN`
   (+ Systemstatus/Betriebsmodus subpages for alarms/modes).
5. **Daikin Altherma 3** via **Intesis IN485DAI001A000** — transcribe manual
   §8.2 to `Daikin_Altherma3.json` (~60 regs, base0/base1 both printed).
   9600 NONE addr 1, `write_fc: 16` (confirm against manual table while
   transcribing; if FC06-only use 6 and note in commit).
   Source: `https://www.hms-networks.com/docs/default-source/products/intesis/manuals-and-guides---manuals/user-manual-in485dai001a000.pdf`.
6. **Mitsubishi Ecodan** (monoblock/split) via **Intesis IN485MIT001A000** —
   transcribe manual §8.2 to `Mitsubishi_Ecodan.json` (100+ regs incl. zones,
   DHW, error codes). Same transport + same converter pattern as #5, so the
   second transcription is cheap. Source: `https://www.hms-networks.com/docs/default-source/products/intesis/manuals-and-guides---manuals/user-manual-in485mit001a000.pdf`.

## 2. Pipeline (per model)

One converter script per brand under `scripts/` (checked in, reproducible):
`convert_thermia.py` (YAML parse), `convert_lambda.py` (PDF-table/CSV parse
or structured transcription with source-line refs), `convert_dimplex.py`,
`convert_daikin.py` + `convert_mitsu.py` (shared Intesis table parser —
write once for Daikin, reuse for Mitsu). Each emits the existing schema
(`register/factor/size/mode/titel/unit/min/max` + `mb_fc`/`word_order`) sorted
by register, appends one `transports.json` entry, cites PDF URL + version in
the commit message. Every model: core-register asserts in
`tests/test_brand_models.py` (3–5 regs checked against the PDF), full
`python -m pytest tests/ -v` green before commit.

## 3. Explicitly deferred

- Samsung / LG / Panasonic Intesis clones (IN485SAM/LGA/PAN): same doc
  pattern as #5/#6 — add once the shared Intesis parser is proven.
- Vaillant VR71/72, Viessmann Vitogate, Bosch/Buderus MB LAN2: no open PDF
  found 2026-09-19 — add when a public register table surfaces.
- CTC: no public Modbus map found. Luxtronik RTU (service-only),
  Nibe S-series / Stiebel ISG (Modbus-TCP, no bridge needed): out of scope
  per generic spec §7.

## 4. Error handling / testing

Unchanged from master plan: CRC16 fail → 3 retries → stale; corrupt
(min/max) → drop; FC16-only enforcement at codegen for MODBUS40 + Lambda;
`MAX_SELECTION` 50. Host vectors extended per model (BE decode, word orders,
FC enforcement, sample regs).
