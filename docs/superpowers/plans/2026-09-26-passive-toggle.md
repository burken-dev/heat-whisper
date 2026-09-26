# Passive Toggle in Picker UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip listen-only (`passive`) mode from the `/heatwhisper/registers` web UI with flash persistence and reboot-to-apply, ending the recompile cycle for TX testing.

**Architecture:** New 1-byte NVS slot (`HeatWhisperPassive`) mirroring the existing mode persistence; picker JSON exposes effective state and the existing mode-save endpoint accepts `passive=`; YAML stays as first-boot default.

**Tech Stack:** ESPHome C++ component (`heatwhisper.h/.cpp`), embedded HTML/JS picker, host pytest (source-grep contract tests).

## Global Constraints

- YAML `passive:` remains the first-boot default; NVS overrides it only when an entry exists.
- Reboot-to-apply semantics; no live toggle.
- Missing/corrupt NVS falls back to YAML and never fails boot.
- Bad `passive` value returns 400 and saves nothing.
- Passive-only POST must not touch the mode slot.
- Picker code stays inside `USE_NETWORK && !USE_ZEPHYR` gate.

---

### Task 1: Flash persistence + boot override

**Files:**
- Modify: `components/heatwhisper/heatwhisper.h`
- Modify: `components/heatwhisper/heatwhisper.cpp:31-50,189-202`
- Test: `tests/test_passive_toggle.py` (new)

**Interfaces:**
- Consumes: existing `HeatWhisperMode` load/save pattern (`HW_MODE_TYPE = 0x68776D6FUL`), `setup()` calling `apply_runtime_mode_()` then `create_entities()`.
- Produces: `struct HeatWhisperPassive { uint32_t version; uint8_t passive; }`, `bool load_passive(HeatWhisperPassive *out)`, `bool save_passive(bool passive)`, `void apply_runtime_passive_()`, `bool is_passive() const` — consumed by Task 2 (JSON + save handler).

- [ ] **Step 1: Write the failing test**

Create `tests/test_passive_toggle.py`:

```python
# tests/test_passive_toggle.py — passive toggle in picker UI (no recompile).
import os

REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")
HDR = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")
PICKER = os.path.join(REPO, "components", "heatwhisper", "picker.h")


def _read(p):
    with open(p) as fh:
        return fh.read()


def test_passive_persisted_in_flash():
    src = _read(HDR)
    assert "HeatWhisperPassive" in src
    assert "load_passive" in src and "save_passive" in src


def test_setup_applies_runtime_passive_before_entities():
    src = _read(CPP)
    setup = src.split("void HeatWhisperComponent::setup")[1].split("void HeatWhisperComponent::tx_")[0]
    assert "apply_runtime_passive_" in setup
    assert setup.index("apply_runtime_mode_") < setup.index("apply_runtime_passive_")
    assert setup.index("apply_runtime_passive_") < setup.index("create_entities")


def test_picker_json_exposes_passive():
    src = _read(CPP)
    body = src.split("HeatWhisperPickerHandler::list_json_")[1].split("HeatWhisperPickerHandler::handle_save_")[0]
    assert '"passive"' in body or "'passive'" in body or "passive" in body


def test_mode_save_accepts_passive():
    src = _read(CPP)
    body = src.split("HeatWhisperPickerHandler::handle_mode_save_")[1].split("#endif")[0]
    assert "passive" in body
    assert "400" in body


def test_picker_ui_has_passive_checkbox():
    src = _read(CPP)
    assert "psv" in src and "passive" in src.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_passive_toggle.py -v`
Expected: FAIL on `test_passive_persisted_in_flash` with `HeatWhisperPassive` not found.

- [ ] **Step 3: Write minimal persistence implementation**

In `components/heatwhisper/heatwhisper.h`, after the `HeatWhisperMode` struct (lines 77-82), add:

```cpp
struct HeatWhisperPassive {
  uint32_t version{1};
  uint8_t passive{0};
};
static_assert(sizeof(HeatWhisperPassive{}) == 8, "HeatWhisperPassive layout");
```

In the `HeatWhisperComponent` public block next to `load_mode`/`save_mode` (lines 110-111), add:

```cpp
  bool load_passive(HeatWhisperPassive *out);
  bool save_passive(bool passive);
  bool is_passive() const { return passive_; }
```

In the protected block next to `apply_runtime_mode_()` (line 123), add:

```cpp
  void apply_runtime_passive_();
```

In `components/heatwhisper/heatwhisper.cpp`, after `save_mode` (line 46, before the `apply_runtime_mode_` comment at line 47), add:

```cpp
static const uint32_t HW_PASSIVE_TYPE = 0x68777073UL;  // keep: passive override survives OTA
bool HeatWhisperComponent::load_passive(HeatWhisperPassive *out) {
  ESPPreferenceObject pref = global_preferences->make_preference<HeatWhisperPassive>(HW_PASSIVE_TYPE, true);
  if (!pref.load(out) || out->version != 1 || out->passive > 1) return false;
  return true;
}
bool HeatWhisperComponent::save_passive(bool passive) {
  HeatWhisperPassive m{};
  m.version = 1;
  m.passive = passive ? 1 : 0;
  ESPPreferenceObject pref = global_preferences->make_preference<HeatWhisperPassive>(HW_PASSIVE_TYPE, true);
  return pref.save(&m);
}
// apply_runtime_passive_: NVS override wins over YAML; absent/corrupt NVS
// keeps the YAML default so first boot is unchanged.
void HeatWhisperComponent::apply_runtime_passive_() {
  HeatWhisperPassive m{};
  if (!load_passive(&m)) return;
  passive_ = (m.passive != 0);
}
```

In `HeatWhisperComponent::setup()` (lines 189-196), add the override between mode and entities:

```cpp
  apply_runtime_mode_();
  apply_runtime_passive_();
  create_entities();
```

- [ ] **Step 4: Run test to verify persistence passes**

Run: `python -m pytest tests/test_passive_toggle.py::test_passive_persisted_in_flash tests/test_passive_toggle.py::test_setup_applies_runtime_passive_before_entities -v`
Expected: PASS (remaining three tests still FAIL — implemented in Task 2/3).

- [ ] **Step 5: Commit**

```bash
git add components/heatwhisper/heatwhisper.h components/heatwhisper/heatwhisper.cpp tests/test_passive_toggle.py
git commit -m "feat: passive flash persistence with boot override"
```

---

### Task 2: Picker JSON state + save handler

**Files:**
- Modify: `components/heatwhisper/heatwhisper.cpp:779-873` (`list_json_` tail + `handle_mode_save_`)
- Test: `tests/test_passive_toggle.py`

**Interfaces:**
- Consumes: `is_passive()`, `save_passive(bool)` from Task 1.
- Produces: `GET /heatwhisper/registers?format=json` field `"passive":0/1`; `POST /heatwhisper/registers/mode` accepting `passive=0/1` standalone or combined — consumed by Task 3 (HTML checkbox).

- [ ] **Step 1: Run the JSON/save tests to verify they fail**

Run: `python -m pytest tests/test_passive_toggle.py::test_picker_json_exposes_passive tests/test_passive_toggle.py::test_mode_save_accepts_passive -v`
Expected: FAIL (no `"passive"` in `list_json_`, no `passive` in `handle_mode_save_`).

- [ ] **Step 2: Write minimal JSON + handler implementation**

In `list_json_()`, after the `suggest_modbus` line (line 787-788, `o += rmodel.empty() ? '1' : '0';`), add:

```cpp
  o += ",\"passive\":";
  o += this->parent_->is_passive() ? '1' : '0';
```

At the top of `handle_mode_save_()` (line 843, before reading `mode`), insert the passive branch so a passive-only POST never touches the mode slot:

```cpp
  std::string passive = request->hasArg("passive") ? request->arg("passive").c_str() : std::string();
  if (!passive.empty()) {
    if (passive != "0" && passive != "1") {
      request->send(400, "text/plain", "need passive=0|1");
      return;
    }
    if (!this->parent_->save_passive(passive == "1")) {
      request->send(500, "text/plain", "save failed");
      return;
    }
    if (mode.empty() && model.empty()) {
      request->send(200, "text/plain", "saved,reboot");
      return;
    }
  }
```

Note: `mode`/`model` locals must be read before this branch — move the two existing `std::string mode/model` lines above it. The rest of the existing mode logic (nibe early-return, modbus validation, 400/500 paths) stays byte-identical. Combined POST (`passive=1&mode=nibe`) saves passive first, then falls through to the mode logic.

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/test_passive_toggle.py::test_picker_json_exposes_passive tests/test_passive_toggle.py::test_mode_save_accepts_passive -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add components/heatwhisper/heatwhisper.cpp tests/test_passive_toggle.py
git commit -m "feat: picker reports and saves passive flag"
```

---

### Task 3: Web checkbox + full verification

**Files:**
- Modify: `components/heatwhisper/heatwhisper.cpp:612-653` (`HW_PICKER_HTML` + script)
- Test: `tests/test_passive_toggle.py`

**Interfaces:**
- Consumes: `"passive"` JSON field and `passive=` POST param from Task 2.
- Produces: visible checkbox on `/heatwhisper/registers`; nothing downstream (terminal task).

- [ ] **Step 1: Run the UI test to verify it fails**

Run: `python -m pytest tests/test_passive_toggle.py::test_picker_ui_has_passive_checkbox -v`
Expected: FAIL (`psv` not in picker HTML).

- [ ] **Step 2: Write minimal UI implementation**

In `HW_PICKER_HTML`, after the Modbus `<details>` block (line 619, after `</details>`), add:

```html
<p><label><input type="checkbox" id="psv"> listen-only (passive, no TX)</label> <button id="psvgo">Save</button> <span id="pmsg"></span></p>
```

In the script, extend the element lookup line (line 627-629) with:

```js
const PV=document.getElementById('psv'),PG=document.getElementById('psvgo'),PM=document.getElementById('pmsg');
```

In the JSON-load callback (line 635-640, after the `suggest_modbus` banner lines), add:

```js
PV.checked=j.passive==1||j.passive=='1';
```

After the `MN.onclick` line (line 652), add:

```js
PG.onclick=()=>{const v=PV.checked?'1':'0';fetch('/heatwhisper/registers/mode',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'passive='+v}).then(async r=>{PM.textContent=r.ok?'Saved. Reboot via ESPHome restart to apply.':'Save failed: '+await r.text()}).catch(e=>PM.textContent='Save failed: '+e);};
```

- [ ] **Step 3: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS, including all five `test_passive_toggle.py` tests and no regressions in `test_runtime_modbus.py`.

- [ ] **Step 4: Run static config check on all boards**

Run: `esphome config heatwhisper_esp32.yaml && esphome config heatwhisper_esp32_s3_rs485.yaml && esphome config heatwhisper_pico_w.yaml`
Expected: all three validate (picker is network-gated; Pico W skips it).

- [ ] **Step 5: Commit**

```bash
git add components/heatwhisper/heatwhisper.cpp
git commit -m "feat: passive checkbox in register picker"
```
