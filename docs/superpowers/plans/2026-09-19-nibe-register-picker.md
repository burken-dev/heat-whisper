# Runtime Register Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let webflasher users enable/disable pump registers from a checkbox page on `web_server` :80, with entity types auto-inferred, applied on reboot, no recompile.

**Architecture:** Build-time Python merges all `models/*.json` plus a curated `entity_hints.json` into a full flash catalog (metadata + titles/units + per-model index). At boot the component loads the enabled set (max 50) from NVS `Preferences`, creates only those entities via `App.register_*`, and seeds the poll queue. A `web_server_base` `AsyncWebHandler` serves the picker page + GET/POST endpoints.

**Tech Stack:** ESPHome 2026.9.0 (verified APIs: `WebServerBase::add_handler`, `App.register_<entity>` 1-arg/4-arg overloads, `global_preferences->make_preference<T>`, `Select::traits.set_options`, `NumberTraits::set_min/max/step`), Python stdlib codegen, pytest host tests.

## Global Constraints

- Single generic binary must compile for both ESP32 (`nibe_esp32.yaml`) and Pico W (`nibe_pico_w.yaml`); CI compiles both.
- No new dependencies: Python stdlib only; no new Arduino/ESPHome libraries.
- Max 50 enabled registers, enforced identically in Python validator and C++ (`NIBE_MAX_SELECTION`).
- HA entity names stay identical to today's `packages/base.yaml` titles (same title strings → same names).
- Reboot-to-apply; NVS survives reboot and OTA.
- Picker endpoints inherit `web_server` admin auth via `add_handler` (never `add_handler_without_auth`).
- RMU write drop (addr < 20000) and corrupt-value filter behavior unchanged.

---

## File structure

- Create `components/nibe/entity_hints.json` — curated smart-type overlay (Task 1).
- Modify `components/nibe/registers.py` — catalog union, model filter, hints merge, validator, object-id helper, header emitter (Tasks 1–2).
- Create `tests/test_catalog.py` — host tests for all of the above (Tasks 1–2).
- Modify `components/nibe/__init__.py` — emit catalog header, optional picker-handler wiring (Tasks 2, 4).
- Modify `components/nibe/nibe.h`, `components/nibe/nibe.cpp` — `NibeSelect`/`NibeSwitch`, NVS selection, boot factory, `on_value` fan-out (Task 3).
- Create `components/nibe/picker.h` — `NibePickerHandler` + embedded page (Task 4).
- Modify `packages/base.yaml` — delete static entity/switch blocks, keep model text sensor (Task 5).
- Modify `README.md` — picker docs + breaking-change note (Task 5).

---

### Task 1: Hints overlay + catalog Python + validator

**Files:**
- Create: `components/nibe/entity_hints.json`
- Modify: `components/nibe/registers.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: existing `_by_reg`, `SIZE_CODES` in `registers.py`; `models/*.json` schema (`register`, `factor`, `size`, `mode`, `titel`, `unit`, `min`, `max`).
- Produces: `load_hints`, `normalize_model`, `model_registers`, `object_id_for`, `entity_kind_for`, `validate_selection`, `MAX_SELECTION` for Tasks 2–4.

- [ ] **Step 1: Write `entity_hints.json`**

```json
{
  "47041": {"type": "select", "options": [[0, "Eco"], [1, "Normal"], [2, "Luxury"], [4, "Smart"]]},
  "47371": {"type": "switch"},
  "47370": {"type": "switch"},
  "47387": {"type": "switch"}
}
```

- [ ] **Step 2: Append catalog helpers to `components/nibe/registers.py`**

```python
import json as _json
MAX_SELECTION = 50
DEFAULT_ENABLED = [40004, 40008, 40012, 40013, 40014, 43009, 43136, 43005,
                   40033, 43144, 43305, 47011, 47007, 47041, 47371, 47370, 47387, 47043]

def load_hints(path):
    with open(path) as fh:
        return _json.load(fh)

def normalize_model(name):
    out = "".join(c for c in (name or "").upper() if c.isalnum())
    return out

def model_registers(models, model_name):
    want = normalize_model(model_name)
    for key in sorted(models):
        if normalize_model(key) == want:
            return sorted({int(r["register"]) for r in models[key]})
    return []

def object_id_for(title):
    out = []
    for c in title.lower().replace(" ", "_"):
        if c.isalnum() or c == "_":
            out.append(c)
    return "".join(out).strip("_")

def entity_kind_for(addr, by_reg, hints):
    h = hints.get(str(addr))
    if h is not None:
        return h["type"], h.get("options", [])
    rw = (by_reg.get(str(addr)) or {}).get("mode") == "R/W"
    return ("number" if rw else "sensor"), []

def validate_selection(addrs, models):
    seen, clean = set(), []
    for a in addrs:
        a = int(a)
        if a in seen:
            continue
        if not is_known(a, models):
            return None, f"unknown register {a}"
        seen.add(a)
        clean.append(a)
    if len(clean) > MAX_SELECTION:
        return None, f"too many registers ({len(clean)} > {MAX_SELECTION})"
    return clean, ""
```

- [ ] **Step 3: Write failing tests in `tests/test_catalog.py`**

```python
import os
from components.nibe.registers import (MAX_SELECTION, DEFAULT_ENABLED, normalize_model,
    model_registers, object_id_for, entity_kind_for, validate_selection, _by_reg)

MDIR = os.path.join(os.path.dirname(__file__), "..", "components", "nibe", "models")

def _models():
    import json
    models = {}
    for f in sorted(os.listdir(MDIR)):
        if f.endswith(".json"):
            with open(os.path.join(MDIR, f)) as fh:
                models[f[:-5]] = json.load(fh)
    return models

def test_normalize_model():
    assert normalize_model("F750-42") == "F75042"
    assert normalize_model("f750") == "F750"
    assert normalize_model("") == ""

def test_model_registers_known_and_unknown():
    models = _models()
    regs = model_registers(models, "F750")
    assert 40004 in regs and len(regs) > 500
    assert model_registers(models, "NOPE-NOT-A-MODEL") == []

def test_object_id_stable():
    assert object_id_for("BT1 Outdoor") == "bt1_outdoor"
    assert object_id_for("Hot Water Top BT7") == "hot_water_top_bt7"

def test_entity_kind_hints_and_defaults():
    models = _models()
    by_reg = _by_reg(models)
    hints = {"47041": {"type": "select", "options": [[0, "Eco"]]},
             "47371": {"type": "switch"}}
    assert entity_kind_for(47041, by_reg, hints)[0] == "select"
    assert entity_kind_for(47371, by_reg, hints)[0] == "switch"
    assert entity_kind_for(40004, by_reg, hints)[0] == "sensor"
    assert entity_kind_for(43005, by_reg, hints)[0] == "number"

def test_validate_selection():
    models = _models()
    ok, err = validate_selection([40004, 40004, 43005], models)
    assert ok == [40004, 43005] and err == ""
    assert validate_selection([12345], models)[0] is None
    too_many = list(range(40000, 40000 + MAX_SELECTION + 1))
    ok, err = validate_selection(too_many, models)
    assert ok is None and "too many" in err

def test_defaults_match_allowlist():
    from components.nibe.registers import DEFAULT_ALLOWLIST
    assert sorted(DEFAULT_ENABLED) == sorted(a for a in DEFAULT_ALLOWLIST if a != 10001) or \
        set(DEFAULT_ENABLED) <= set(DEFAULT_ALLOWLIST)
```

- [ ] **Step 4: Run tests, expect failures on missing functions**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL (functions not defined yet).

- [ ] **Step 5: Implement Step 2 code, rerun**

Run: `python -m pytest tests/test_catalog.py tests/test_registers.py -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add components/nibe/entity_hints.json components/nibe/registers.py tests/test_catalog.py
git commit -m "feat: register catalog python (hints, model filter, validator)"
```

### Task 2: Catalog header codegen

**Files:**
- Modify: `components/nibe/registers.py`, `components/nibe/__init__.py`
- Test: `tests/test_catalog.py` (append)

**Interfaces:**
- Consumes: Task 1 helpers (`_by_reg`, `load_hints`, `DEFAULT_ENABLED`, `MAX_SELECTION`).
- Produces: generated `components/nibe/catalog.h` with `NIBE_META`/`NIBE_META_N`, `NIBE_TITLES`, per-model arrays, `NIBE_MODELS`, `NIBE_DEFAULTS`, `NIBE_HINTS`, `NIBE_MAX_SELECTION` for Tasks 3–4.

- [ ] **Step 1: Add failing golden test**

```python
def test_generate_catalog_header_layout():
    from components.nibe.registers import generate_catalog_header
    models = {"F750": [
        {"register": "40004", "factor": 10, "size": "s16", "mode": "R",
         "titel": "BT1 Outdoor Temperature", "unit": "°C", "min": "-500", "max": "500"},
        {"register": "47041", "factor": 1, "size": "u8", "mode": "R/W",
         "titel": "Comfort", "unit": "", "min": "0", "max": "4"}]}
    hints = {"47041": {"type": "select", "options": [[0, "Eco"], [1, "Normal"]]},
             "47371": {"type": "switch"}}
    hdr = generate_catalog_header(models, hints)
    assert "NIBE_META" in hdr and "NIBE_TITLES" in hdr
    assert "NIBE_MODEL_F750" in hdr and "NIBE_MODELS" in hdr
    assert "NIBE_DEFAULTS" in hdr and "NIBE_HINTS" in hdr
    assert "NIBE_MAX_SELECTION 50" in hdr
    assert "{40004,10,3,0,-500,500}" in hdr
    assert "BT1 Outdoor Temperature" in hdr
    assert "0:Eco;1:Normal" in hdr
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_catalog.py::test_generate_catalog_header_layout -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement `generate_catalog_header` in `registers.py`**

```python
def _esc(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')

def generate_catalog_header(models, hints):
    by_reg = _by_reg(models)
    addrs = sorted({int(r["register"]) for regs in models.values() for r in regs})
    titles = {}
    for regs in models.values():
        for r in regs:
            titles.setdefault(r["register"], (r.get("titel") or f"Register {r['register']}",
                                              (r.get("unit") or "").replace("�", "°")))
    lines = ["#pragma once", '#include <stdint.h>',
             "struct NibeMeta { uint16_t addr; int16_t factor; uint8_t size; uint8_t rw; int32_t min; int32_t max; };",
             "struct NibeTitle { uint16_t addr; const char *title; const char *unit; };",
             "struct NibeModel { const char *name; const uint16_t *addrs; uint16_t n; };",
             "struct NibeHint { uint16_t addr; uint8_t kind; const char *opts; };"]
    entries = ",".join(
        f"{{{a},{_num(by_reg[str(a)].get('factor', 1))},"
        f"{SIZE_CODES[by_reg[str(a)].get('size', 's16')]},"
        f"{1 if by_reg[str(a)].get('mode') == 'R/W' else 0},"
        f"{_num(by_reg[str(a)].get('min', 0))},{_num(by_reg[str(a)].get('max', 0))}}}"
        for a in addrs)
    lines.append(f"static const NibeMeta NIBE_META[] = {{{entries}}};")
    lines.append(f"static const uint16_t NIBE_META_N = {len(addrs)};")
    trows = ",".join(f'{{{a},"{_esc(titles[str(a)][0])}","{_esc(titles[str(a)][1])}"}}' for a in addrs)
    lines.append(f"static const NibeTitle NIBE_TITLES[] = {{{trows}}};")
    for m, regs in sorted(models.items()):
        want = normalize_model(m)
        lst = sorted({int(r["register"]) for r in regs})
        lines.append(f"static const uint16_t NIBE_MODEL_{want}[] = {{{','.join(map(str, lst))}}};")
    mrows = []
    for m, regs in sorted(models.items()):
        want = normalize_model(m)
        n = len({int(r["register"]) for r in regs})
        mrows.append(f'{{"{m}",NIBE_MODEL_{want},{n}}}')
    lines.append(f"static const NibeModel NIBE_MODELS[] = {{{','.join(mrows)}}};")
    lines.append(f"static const uint8_t NIBE_MODELS_N = {len(models)};")
    kinds = {"sensor": 0, "number": 1, "switch": 2, "select": 3}
    hrows = []
    for a_str, h in sorted(hints.items(), key=lambda kv: int(kv[0])):
        opts = ";".join(f"{v}:{_esc(l)}" for v, l in h.get("options", []))
        hrows.append(f'{{{a_str},{kinds[h["type"]]},"{opts}"}}')
    lines.append(f"static const NibeHint NIBE_HINTS[] = {{{','.join(hrows)}}};")
    lines.append(f"static const uint8_t NIBE_HINTS_N = {len(hrows)};")
    lines.append(f"static const uint16_t NIBE_DEFAULTS[] = {{{','.join(map(str, DEFAULT_ENABLED))}}};")
    lines.append(f"static const uint8_t NIBE_DEFAULTS_N = {len(DEFAULT_ENABLED)};")
    lines.append(f"static const uint8_t NIBE_MAX_SELECTION = {MAX_SELECTION};")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Wire into `components/nibe/__init__.py` `to_code`**

After the existing `registers.h` write, add:

```python
from .registers import generate_catalog_header, load_hints
hints_path = os.path.join(os.path.dirname(__file__), "entity_hints.json")
hints = load_hints(hints_path) if os.path.exists(hints_path) else {}
catalog_out = os.path.join(os.path.dirname(__file__), "catalog.h")
with open(catalog_out, "w") as fh:
    fh.write(generate_catalog_header(models, hints))
```

- [ ] **Step 5: Run tests + validate codegen output**

Run: `python -m pytest tests/ -v`
Expected: PASS.
Run: `python3 -c "import json,os; m={f[:-5]:json.load(open(os.path.join('components/nibe/models',f))) for f in sorted(os.listdir('components/nibe/models')) if f.endswith('.json')}; from components.nibe.registers import generate_catalog_header,load_hints; open('/tmp/catalog.h','w').write(generate_catalog_header(m,load_hints('components/nibe/entity_hints.json')))" && wc -c /tmp/catalog.h`
Expected: file written, ~300–500 KB (titles dominate; size gate re-checked at compile in Task 6).

- [ ] **Step 6: Commit**

```bash
git add components/nibe/registers.py components/nibe/__init__.py tests/test_catalog.py
git commit -m "feat: full register catalog codegen (meta, titles, per-model index)"
```

### Task 3: NVS selection + boot-time entity factory (C++)

**Files:**
- Modify: `components/nibe/nibe.h`, `components/nibe/nibe.cpp`
- Test: `esphome compile nibe_esp32.yaml` (host pytest cannot run C++; Python validator from Task 1 is the mirrored logic)

**Interfaces:**
- Consumes: `catalog.h` tables from Task 2; existing `NibeSensor`/`NibeNumber`, `ensure_polled`, `queue_write`, `model_`.
- Produces: `NibeSelect`, `NibeSwitch`, `load_selection`/`save_selection`, `create_entities()`, extended `on_value` fan-out for Task 4.

- [ ] **Step 1: Extend `nibe.h`**

Add includes `esphome/components/select/select.h`, `esphome/components/switch/switch.h`, `esphome/core/preferences.h`, `esphome/core/application.h`, and `"catalog.h"`. Add after `NibeNumber`:

```cpp
class NibeSelect : public esphome::select::Select, public esphome::Component {
 public:
  void set_parent(NibeComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void set_mapping(const std::vector<int32_t> &raws) { raws_ = raws; }
  void control(const std::string &value) override;
 protected:
  NibeComponent *parent_{nullptr};
  uint16_t addr_{0};
  std::vector<int32_t> raws_;
};
class NibeSwitch : public esphome::switch_::Switch, public esphome::Component {
 public:
  void set_parent(NibeComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void write_state(bool state) override;
 protected:
  NibeComponent *parent_{nullptr};
  uint16_t addr_{0};
};
struct NibeSelection {
  uint32_t version{1};
  uint16_t count{0};
  uint16_t addrs[50];
};
static_assert(sizeof(NibeSelection{}) == 4 + 2 + 2 * 50, "NibeSelection layout");
static_assert(50 == NIBE_MAX_SELECTION, "selection slots match catalog cap");
```

Add to `NibeComponent` public: `bool load_selection(NibeSelection *out); bool save_selection(const uint16_t *addrs, uint16_t n); void create_entities();` plus vectors `std::vector<NibeSelect*> selects_; std::vector<NibeSwitch*> switches_;` and `void add_select(NibeSelect *s); void add_switch(NibeSwitch *s);`.

- [ ] **Step 2: Implement in `nibe.cpp`**

```cpp
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
static const uint32_t NIBE_SEL_TYPE = 0x6E696273UL;  // 'nibs'
bool NibeComponent::load_selection(NibeSelection *out) {
  ESPPreferenceObject pref = global_preferences->make_preference<NibeSelection>(NIBE_SEL_TYPE, true);
  if (!pref.load(out) || out->version != 1 || out->count > NIBE_MAX_SELECTION) return false;
  return true;
}
bool NibeComponent::save_selection(const uint16_t *addrs, uint16_t n) {
  if (n > NIBE_MAX_SELECTION) return false;
  NibeSelection s{};
  s.version = 1;
  s.count = n;
  memcpy(s.addrs, addrs, n * sizeof(uint16_t));
  ESPPreferenceObject pref = global_preferences->make_preference<NibeSelection>(NIBE_SEL_TYPE, true);
  return pref.save(&s);
}
```

`setup()` becomes: try `load_selection`; on failure copy `NIBE_DEFAULTS`/`NIBE_DEFAULTS_N`; then `create_entities()` which for each addr first checks it against `NIBE_META` (linear scan like the decode loop) and skips unknown addrs with `ESP_LOGW` (covers maps updated after save), then looks up meta/title/hint and news the right entity (`NibeSensor` + `set_unit_of_measurement`/`set_accuracy_decimals(1)`; `NibeNumber` + `traits.set_min_value/max/step`; `NibeSwitch`; `NibeSelect` + `traits.set_options` from parsed `opts` + `set_mapping`), names it from the catalog title, registers via the 4-arg `App.register_sensor(s, name, fnv1_hash(object_id), 0)` family (object id = `object_id_for` equivalent computed inline: lowercase, spaces→`_`, keep alnum/`_`), calls existing `add_sensor`/`add_number`/new `add_select`/`add_switch` (which `ensure_poll`).

Reference for exact setter sequence: run `esphome config nibe_esp32.yaml` on the current tree and copy the generated `sensor->set_...` / `number->traits...` lines for one sensor and one number. If the generated reference shows a unit setter on Number, apply the catalog unit to numbers too; otherwise numbers expose traits only (no unit) — record whichever outcome in the commit message.

`on_value` gains loops over `selects_` (publish option label by raw→index; skip unknown raws) and `switches_` (publish `v != 0`).

`NibeSelect::control` maps option index→raw via `raws_` and calls `parent_->queue_write(addr_, raw)` then `publish_state(value)`. `NibeSwitch::write_state` calls `parent_->queue_write(addr_, state ? 1 : 0)` then `publish_state(state)`.

- [ ] **Step 3: Compile**

Run: `esphome compile nibe_esp32.yaml`
Expected: success. Fix setter/API mismatches against ESPHome 2026.9.0 headers (`sensor.h`, `number_traits.h`, `select_traits.h`, `switch.h`) until it passes.

- [ ] **Step 4: Commit**

```bash
git add components/nibe/nibe.h components/nibe/nibe.cpp
git commit -m "feat: NVS register selection with boot-time entity factory"
```

### Task 4: Picker web handler + page

**Files:**
- Create: `components/nibe/picker.h`
- Modify: `components/nibe/__init__.py`, `components/nibe/nibe.h` (handler pointer + accessor for catalog/model/selection)
- Test: `esphome compile` both boards + `curl` checks against a running node (manual, Task 6)

**Interfaces:**
- Consumes: Task 3 (`load_selection`/`save_selection`, `get_model`, catalog tables), Task 1 `validate_selection` rules (re-implemented in C++: known-addr check against `NIBE_META`, count cap).
- Produces: `GET /nibe/registers` JSON, `POST /nibe/registers/save`, reboot hint for Task 6.

- [ ] **Step 1: Create `components/nibe/picker.h`** modeled on the verified `prometheus_handler.h` pattern (`AsyncWebHandler` + `Component`, constructor takes `WebServerBase*`, `setup()` calls `base_->init()` then `base_->add_handler(this)`):

```cpp
#pragma once
#include "esphome/components/web_server_base/web_server_base.h"
#include "esphome/core/component.h"
namespace esphome {
namespace nibe {
class NibeComponent;
class NibePickerHandler final : public AsyncWebHandler, public Component {
 public:
  NibePickerHandler(web_server_base::WebServerBase *base, NibeComponent *parent)
      : base_(base), parent_(parent) {}
  bool canHandle(AsyncWebServerRequest *request) const override;
  void handleRequest(AsyncWebServerRequest *request) override;
  void setup() override {
    this->base_->init();
    this->base_->add_handler(this);
  }
  float get_setup_priority() const override { return esphome::setup_priority::AFTER_WIFI; }
 protected:
  std::string list_json_() const;
  web_server_base::WebServerBase *base_;
  NibeComponent *parent_;
};
}  // namespace nibe
}  // namespace esphome
```

Implement `canHandle` for `GET /nibe/registers` and `POST /nibe/registers/save` (same URL-span style as prometheus: `request->method()` check + path compare). Implement `handleRequest` + `list_json_()` in `nibe.cpp`: GET serves the embedded HTML page (query `?format=json` serves the JSON list: `{model, addrs:[{a,t,u,kind,en}]}` with `"`/`\` escaping on titles); when `model_` is empty or matches no `NIBE_MODELS` entry, serve the `NIBE_DEFAULTS` set with `"model":null` and let the page render the "waiting for pump announcement" notice. POST reads the `addrs` form param (comma-separated, collected by page JS), validates each against `NIBE_META` + cap, calls `save_selection`, replies 200 `saved,reboot` or 400 with reason. Page HTML (dependency-free, ~60 lines): filter input, "enabled only" checkbox, per-register checkboxes grouped in one list, save button, reboot button calling `fetch('/nibe/registers/save',{method:'POST'...})` then showing "Reboot via ESPHome restart to apply".

- [ ] **Step 2: Wire optionally in `components/nibe/__init__.py`**

Declare the handler class next to `Nibe`:

```python
NibePickerHandler = nibe_ns.class_("NibePickerHandler", cg.Component)
CONF_PICKER_ID = "picker_id"
```

Extend the schema (additive — existing keys untouched). This follows the
verified `prometheus/__init__.py` pattern exactly (`GenerateID` + `use_id`
auto-binds to the single `WebServerBase` instance; no YAML key needed):

```python
from esphome.components import web_server_base
from esphome.components.web_server_base import CONF_WEB_SERVER_BASE_ID
AUTO_LOAD = ["web_server_base"]
CONFIG_SCHEMA = CONFIG_SCHEMA.extend({
    cv.GenerateID(CONF_PICKER_ID): cv.declare_id(NibePickerHandler),
    cv.GenerateID(CONF_WEB_SERVER_BASE_ID): cv.use_id(web_server_base.WebServerBase),
})
```

In `to_code`, after creating the component var:

```python
base = await cg.get_variable(config[CONF_WEB_SERVER_BASE_ID])
picker = cg.new_Pvariable(config[CONF_PICKER_ID], base, var)
await cg.register_component(picker, config)
```

Deliberate constraint (fail-fast over silent): the picker is only meaningful
with `web_server:` (it serves the page). If a custom config drops
`web_server:`, validation errors clearly at `esphome config` time instead of
silently shipping a dead picker. `packages/base.yaml` keeps `web_server:`.

- [ ] **Step 3: Compile both boards**

Run: `esphome compile nibe_esp32.yaml` and `esphome compile nibe_pico_w.yaml`
Expected: both succeed.

- [ ] **Step 4: Commit**

```bash
git add components/nibe/picker.h components/nibe/nibe.cpp components/nibe/nibe.h components/nibe/__init__.py
git commit -m "feat: register picker web UI (list json + save to NVS)"
```

### Task 5: base.yaml migration + docs

**Files:**
- Modify: `packages/base.yaml`, `README.md`
- Test: `esphome config nibe_esp32.yaml`

- [ ] **Step 1: Strip static blocks from `packages/base.yaml`**

Delete the `esphome.on_boot` lambda list, the entire `sensor:` block (10 entries), the entire `number:` block (8 entries), and the entire `switch:` block (18 `Enable …` entries). Keep `nibe:`, `text_sensor` (Heat Pump Model), wifi/api/ota/web_server. Add under `nibe:`:

```yaml
  # Registers are now picked at runtime: open http://<node>/nibe/registers,
  # check what to expose (max 50), save, reboot. Entity types auto-inferred
  # (R→sensor, R/W→number, curated switches/selects). Factory defaults =
  # previous 19 entities; stored in flash, survives OTA.
```

- [ ] **Step 2: Update `README.md`**

Replace the "Add an entity" + `add_register.py` section with picker flow docs (URL, max 50, reboot to apply, poll cycle slows ~linearly with enabled count); note breaking change (Enable switches removed); note the number-unit outcome from Task 3; note `scripts/add_register.py` is now only for extending `entity_hints.json` titles reference (or delete the script — delete it and its mention if nothing references it; check with grep first).

- [ ] **Step 3: Validate**

Run: `esphome config nibe_esp32.yaml`
Expected: validates with no `sensor:`/`number:`/`switch:` nibe entities.
Run: `python -m pytest tests/ -v`
Expected: PASS (update any test grepping `base.yaml` content if it breaks).

- [ ] **Step 4: Commit**

```bash
git add packages/base.yaml README.md
git commit -m "feat!: runtime register picker replaces static entities"
```

### Task 6: Verification + size gate

- [ ] **Step 1: Binary size gate**

Run: `esphome compile nibe_esp32.yaml && esphome compile nibe_pico_w.yaml` and record `.bin`/`.uf2` sizes vs `main` branch builds. If Pico W overflows flash, stop and re-plan (approved fallback: per-model binary split — out of scope for this plan).

- [ ] **Step 2: Device pass (passive bring-up per README)**

Flash with `passive: true`, open `/nibe/registers`, confirm list shows the detected model's registers (~600 for F750-class), filter box works, 19 defaults pre-checked.

- [ ] **Step 3: Enable/disable round-trip**

Check 3 new registers, save, reboot via device restart, confirm 3 new HA entities appear with values; uncheck one, save, reboot, confirm it disappears; confirm a writable (e.g. 47011) accepts a write and the pump responds; confirm 47041 select shows Eco/Normal/Luxury/Smart.

- [ ] **Step 4: Edge cases**

POST >50 addrs → 400; model unknown (fresh boot before announcement) → defaults + notice; NVS reset (esphome `reset`) → defaults restored.

- [ ] **Step 5: Commit any fixes with `fix:` prefix; update todos to completed.**
