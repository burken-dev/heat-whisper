# Brand-Agnostic Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename every generic `nibe` identifier to brand-agnostic `heatpump`/`Hp`/`HP_` names with zero behavior change.

**Architecture:** Pure mechanical rename in dependency order (Python → C++ → YAML/CI/docs); Nibe-vendor data, NVS value, history untouched per spec §10.

**Tech Stack:** Python (ESPHome codegen), C++ (ESPHome component), ESPHome YAML, GitHub Actions.

## Global Constraints

- ESPHome 2026.9.0 has no runtime unit setter; factory numbers stay unitless (spec §1 context).
- `MAX_SELECTION` stays 50.
- NVS preference type id value `0x6E696273` MUST NOT change (saved selections survive OTA); only the symbol is renamed.
- Factory entity titles MUST stay verbatim (HA entity-id continuity).
- Every task ends with `python -m pytest tests/ -v` passing; firmware compile is covered by CI (`esphome config` + `compile` both boards).
- Frequent commits; one commit per task minimum.

---

## File Structure

- Modify: `components/nibe/registers.py`, `__init__.py`, `sensor.py`, `number.py` (Python layer, Task 1)
- Rename (git mv): `components/nibe/` → `components/heatpump/`; inside, `nibe.h` → `heatpump.h`, `nibe.cpp` → `heatpump.cpp` (Task 2)
- Modify: `tests/*.py` (Task 1–2), `packages/*.yaml`, `heatpump_*.yaml` (renamed via git mv from `nibe_*.yaml`), `.github/workflows/build.yml`, `manifest.json`, `index.html`, `secrets.yaml.example`, `README.md` (Task 3)
- Regenerate + commit: `components/heatpump/catalog.h` via the snippet in Task 2 Step 6.

---

### Task 1: Python layer rename + tests

**Files:**
- Modify: `components/nibe/registers.py`, `components/nibe/__init__.py`, `components/nibe/sensor.py`, `components/nibe/number.py`
- Modify: `tests/test_catalog.py`, `tests/test_registers.py`, `tests/test_entities.py`, `tests/test_rmu.py`, `tests/test_subscription.py`, `tests/test_fixwave.py`, `tests/test_final_fixes.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `components.heatpump.registers.generate_catalog_header(models, hints)` emitting `HpMeta`/`HP_META`/`HP_MODEL_<X>`/`HP_DEFAULTS`/`HP_MAX_SELECTION`; config key `heatpump:` with `heatpump_id`; namespace `heatpump`.

- [ ] **Step 1: Update tests to expect new names (failing)**

In `tests/test_catalog.py`, replace the import and path:

```python
from components.heatpump.registers import (MAX_SELECTION, DEFAULT_ENABLED, normalize_model,
    model_registers, object_id_for, entity_kind_for, validate_selection, _by_reg)

MDIR = os.path.join(os.path.dirname(__file__), "..", "components", "heatpump", "models")
```

and the header asserts:

```python
assert "HP_META" in hdr and "HP_TITLES" in hdr
assert "HP_MODEL_F750" in hdr and "HP_MODELS" in hdr
assert "HP_DEFAULTS" in hdr and "HP_HINTS" in hdr
assert "HP_MAX_SELECTION = 50" in hdr
```

In `tests/test_entities.py`: `from components.heatpump import sensor as hp_sensor`, `from components.heatpump import number as hp_number`, config dicts use `{"heatpump_id": "heatpump_bridge", ...}`, source paths `components/heatpump/sensor.py` and `components/heatpump/number.py`. In `tests/test_rmu.py`, `tests/test_subscription.py`, `tests/test_fixwave.py`, `tests/test_final_fixes.py`: replace every `components/nibe/` path with `components/heatpump/`, `NibeNumber::control` with `HeatpumpNumber::control`, `NIBE_BASE_NAMES` with `HP_FACTORY_NAMES`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'components.heatpump'` (collection error).

- [ ] **Step 3: Rename Python symbols (still under `components/nibe/`; dir moves in Task 2)**

In `components/nibe/registers.py`: `struct NibeMeta` → `struct HpMeta`, `NibeTitle` → `HpTitle`, `NibeModel` → `HpModel`, `NibeHint` → `HpHint`; `NIBE_META` → `HP_META`, `NIBE_META_N` → `HP_META_N`, `NIBE_TITLES` → `HP_TITLES`, `NIBE_MODEL_` → `HP_MODEL_`, `NIBE_MODELS` → `HP_MODELS`, `NIBE_MODELS_N` → `HP_MODELS_N`, `NIBE_HINTS` → `HP_HINTS`, `NIBE_HINTS_N` → `HP_HINTS_N`, `NIBE_DEFAULTS` → `HP_DEFAULTS`, `NIBE_DEFAULTS_N` → `HP_DEFAULTS_N`, `NIBE_MAX_SELECTION` → `HP_MAX_SELECTION`. File header comment `# components/nibe/registers.py` → `# components/heatpump/registers.py`.

In `components/nibe/__init__.py`: `nibe_ns = cg.esphome_ns.namespace("heatpump")`, `Heatpump = heatpump_ns.class_("HeatpumpComponent", ...)`, `HeatpumpPickerHandler = heatpump_ns.class_("HeatpumpPickerHandler", ...)`, header comment path update. (Config-key rename `nibe:` → `heatpump:` is Task 3 YAML-side; the Python `CONFIG_SCHEMA` key follows the component dir name automatically in ESPHome — no code change needed beyond the move.)

In `components/nibe/sensor.py` and `number.py`: `from . import Heatpump, heatpump_ns`; class registrations on `heatpump_ns`; `cv.GenerateID("heatpump_id")`; `config["heatpump_id"]`; warning strings `"heatpump sensor register …"` / `"heatpump number register …"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS (dir still `components/nibe/`; module path `components.nibe` still resolves — the failing asserts from Step 1 now pass because symbol names changed; path asserts for `components/heatpump/` will fail until Task 2, so keep those path edits staged for Task 2 — see note below).

NOTE: to keep every commit green, do NOT edit the `components/heatpump` path strings in tests until Task 2. In this task only change symbol-level expects (`HP_*`, `heatpump_id`, `HeatpumpNumber::control`, `HP_FACTORY_NAMES`). Path-string edits (`components/nibe/` → `components/heatpump/`, `from components.heatpump…` imports) belong to Task 2 Step 1.

- [ ] **Step 5: Commit**

```bash
git add components/nibe tests
git commit -m "refactor: brand-agnostic Python symbols (Hp/HP_/heatpump_id)"
```

---

### Task 2: C++ layer + directory rename

**Files:**
- Rename: `components/nibe/` → `components/heatpump/` (git mv), `nibe.h` → `heatpump.h`, `nibe.cpp` → `heatpump.cpp`
- Modify: `components/heatpump/heatpump.h`, `heatpump.cpp`, `picker.h`
- Modify: path strings in `tests/*.py`; regenerate `components/heatpump/catalog.h`

**Interfaces:**
- Consumes: Task 1 (`HP_*` codegen).
- Produces: namespace `esphome::heatpump`; classes `HeatpumpComponent`, `HeatpumpSensor/Number/Select/Switch`, `HeatpumpPickerHandler`; struct `HeatpumpSelection`; enum `HpSize { HP_U8, HP_S8, HP_U16, HP_S16, HP_U32, HP_S32 }`; `calc_crc_nibe` / `calc_crc_c0_nibe`; log tag `"heatpump"`; picker URL `/heatpump/registers`; NVS symbol `HP_SEL_TYPE` with value unchanged.

- [ ] **Step 1: Update test path strings to the new dir (failing)**

Replace in `tests/*.py`: `from components.nibe` → `from components.heatpump`, `"components", "nibe"` → `"components", "heatpump"`, `components/nibe/` → `components/heatpump/`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ -v`
Expected: FAIL with `ModuleNotFoundError` / missing path.

- [ ] **Step 3: git mv the directory and files**

```bash
git mv components/nibe components/heatpump
git mv components/heatpump/nibe.h components/heatpump/heatpump.h
git mv components/heatpump/nibe.cpp components/heatpump/heatpump.cpp
```

- [ ] **Step 4: Rename C++ symbols**

In `heatpump.h`, `heatpump.cpp`, `picker.h`: `namespace nibe` → `namespace heatpump`; `NibeComponent` → `HeatpumpComponent`; `NibeSensor` → `HeatpumpSensor`; `NibeNumber` → `HeatpumpNumber`; `NibeSelect` → `HeatpumpSelect`; `NibeSwitch` → `HeatpumpSwitch`; `NibePickerHandler` → `HeatpumpPickerHandler`; `NibeSelection` → `HeatpumpSelection`; `NibeSize` → `HpSize`, `NIBE_U8` → `HP_U8` (same for S8/U16/S16/U32/S32); `NIBE_BASE_NAMES` → `HP_FACTORY_NAMES`; `NIBE_SEL_TYPE` → `HP_SEL_TYPE` (keep value `0x6E696273UL` and add comment `// keep: saved selections survive OTA`); every `ESP_LOGx("nibe", …)` → `ESP_LOGx("heatpump", …)`; `#include "nibe.h"` → `#include "heatpump.h"`; file header comments → new paths; `calc_crc` → `calc_crc_nibe`, `calc_crc_c0` → `calc_crc_c0_nibe` (update the two call sites in `loop()`/`on_frame_` and the tests' comments referencing them — `tests/test_decode.py` header comment only, logic untouched).
Picker: `NIBE_PICKER_HTML` → `HP_PICKER_HTML`; `<title>Nibe registers</title>` → `<title>Heat pump registers</title>`; `<h1>Nibe register picker</h1>` → `<h1>Heat pump register picker</h1>`; `fetch('/nibe/registers/save'…)` → `fetch('/heatpump/registers/save'…)`; `canHandle` URLs `/nibe/registers` → `/heatpump/registers`, `/nibe/registers/save` → `/heatpump/registers/save`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Regenerate the checked-in catalog.h and verify it**

Run:

```bash
python3 - <<'EOF'
import json, os
from components.heatpump.registers import generate_catalog_header, load_hints
mdir = "components/heatpump/models"
models = {f[:-5]: json.load(open(os.path.join(mdir, f))) for f in sorted(os.listdir(mdir)) if f.endswith(".json")}
hints = load_hints("components/heatpump/entity_hints.json")
open("components/heatpump/catalog.h", "w").write(generate_catalog_header(models, hints))
EOF
git diff --stat components/heatpump/catalog.h
```

Expected: only symbol renames (`NIBE_` → `HP_`, `Nibe` → `Hp`), identical register contents. Verify with `git diff components/heatpump/catalog.h | grep '^[+-]' | grep -v '^[+-][+-]' | grep -vc 'NIBE\|Nibe\|HP_\|Hp'` → `0` content lines outside the rename.

- [ ] **Step 7: Commit**

```bash
git add components tests
git commit -m "refactor: rename component to heatpump (C++ + dir, NVS value kept)"
```

---

### Task 3: YAML, CI, user-facing strings

**Files:**
- Modify: `packages/base.yaml`, `packages/esp32_base.yaml`, `packages/pico_w_base.yaml`, `.github/workflows/build.yml`, `manifest.json`, `index.html`, `secrets.yaml.example`, `README.md`
- Rename: `nibe_esp32.yaml` → `heatpump_esp32.yaml`, `nibe_pico_w.yaml` → `heatpump_pico_w.yaml` (git mv)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: config key `heatpump:` with ids `heatpump_bridge`/`heatpump_uart`; node names `heatpump-bridge(-pico)`; artifacts `heatpump_esp32.factory/ota.bin`, `heatpump_pico_w.bin/uf2`.

- [ ] **Step 1: Rename board YAMLs and packages**

```bash
git mv nibe_esp32.yaml heatpump_esp32.yaml
git mv nibe_pico_w.yaml heatpump_pico_w.yaml
```

`heatpump_esp32.yaml`: `name: heatpump-bridge`, `friendly_name: Heat Pump Bridge`. `heatpump_pico_w.yaml`: `name: heatpump-bridge-pico`, `friendly_name: Heat Pump Bridge Pico`.
`packages/base.yaml`: ssid `"Heatpump-Bridge"`; comment `# Heat-pump bridge. …`; block `heatpump:` with `id: heatpump_bridge`, `uart_id: heatpump_uart`; picker URL comment `http://<node>/heatpump/registers`; lambda `id(heatpump_bridge).get_model()`; topic_prefix comments `"heatpump"`. Keep the `passive:` bring-up comments verbatim otherwise.
`packages/esp32_base.yaml` + `pico_w_base.yaml`: `id: heatpump_uart` (baud/parity lines untouched).

- [ ] **Step 2: CI workflow + flasher + secrets example**

`.github/workflows/build.yml`: `esphome config/compile heatpump_esp32.yaml`, `heatpump_pico_w.yaml`; artifact aliases `heatpump_esp32.factory.bin`, `heatpump_esp32.ota.bin`, `heatpump_pico_w.bin`, `heatpump_pico_w.uf2` (both release `cp` and pages `cp` lines); build-input paths (`.esphome/build/heatpump-bridge/…`, `.esphome/build/heatpump-bridge-pico/…`) follow the new node names.
`manifest.json`: `"name": "Heat Pump Bridge"`, path `heatpump_esp32.factory.bin`.
`index.html`: title/heading `Heat Pump Bridge — Flash`; `https://<user>.github.io/heatpump-bridge/`; `heatpump_pico_w.uf2`; fallback AP `Heatpump-Bridge`.
`secrets.yaml.example`: `ap_password: "heatpumpbridge01"`.

- [ ] **Step 3: README strings (generic mentions only)**

Replace `Nibe Bridge` → `Heat Pump Bridge`, `nibe-bridge` → `heatpump-bridge` (URLs, node names), `nibe_esp32.yaml` → `heatpump_esp32.yaml` (same for pico), `nibe:` block → `heatpump:`, `nibe_bridge`/`nibe_uart` ids, `/nibe/registers` URL, `components/nibe/` paths. Keep vendor-specific sentences (F-series heat pump, NibePi reference, `models/*.json` MIT note, MODBUS 40 as Nibe accessory). Add one migration note paragraph under Configuration:

```markdown
Migration from `nibe:`: replace the `nibe:` block with `heatpump:` (`id: heatpump_bridge`, `uart_id: heatpump_uart`), delete the old key, re-flash. Entity names are unchanged; the MQTT topic prefix, fallback AP (`Heatpump-Bridge`), picker URL (`/heatpump/registers`) and release filenames change. Saved register selections survive (NVS key unchanged).
```

- [ ] **Step 4: Verify**

Run: `python -m pytest tests/ -v`
Expected: PASS.
Run (CI if no local ESPHome toolchain): `esphome config heatpump_esp32.yaml && esphome config heatpump_pico_w.yaml`
Expected: `INFO Configuration is valid!` for both. If the toolchain is unavailable locally, note it in the commit message and let CI compile.

- [ ] **Step 5: Commit**

```bash
git add packages heatpump_esp32.yaml heatpump_pico_w.yaml .github manifest.json index.html secrets.yaml.example README.md
git commit -m "refactor: brand-agnostic YAML, CI artifacts and user-facing strings"
```

---

## Self-Review

- Spec §10 coverage: dir/files/classes/enum/catalog symbols/factory table/helpers/config/address/log/picker/nodes/artifacts/tests — each in Tasks 1–3. Keeps (model JSON data, NVS value, history, `protocol: nibe` value) explicitly untouched. No gaps.
- Placeholders: none — every step names exact strings/commands.
- Type consistency: `Heatpump*` classes, `Hp*` structs, `HP_*` macros, `heatpump*` ids/keys used uniformly across tasks.
