# Register Subscription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poll only what has an entity, with per-register runtime on/off switches that persist across reboots.

**Architecture:** Entities in YAML become the poll source (auto-enqueue in `add_sensor`/`add_number`); a stock `template switch` per register drives an in-RAM `disabled_` set via `set_register_enabled()`; the `0x69` handler skips disabled slots and `on_value()` drops disabled publishes.

**Tech Stack:** ESPHome (ESP32 + RP2040 Pico W), C++ (`components/nibe/nibe.h`, `nibe.cpp`), Python codegen (`__init__.py`, `registers.py`, `sensor.py`, `number.py`), YAML (`packages/base.yaml`), pytest host tests.

## Global Constraints

- Boards compile: `esphome config nibe_esp32.yaml` and `esphome compile` for both `nibe_esp32.yaml` and `nibe_pico_w.yaml` stay green.
- Host tests run: `python -m pytest tests/ -v` stays green.
- One register per `0x69` poll slot, round-robin order preserved; disabled slots cost one queue rotation, no UART TX.
- All-disabled `0x69` → ACK, never stall the pump.
- Fresh flash = all enabled = today's 10-reg behavior; no migration code.
- `number control()` still queues explicit writes even when disabled; readbacks stay suppressed.
- `passive: true` still sends nothing; `disabled_` still gates publishes.
- Every sensor keeps `delta: 0.1` / `throttle: 60s` / `heartbeat: 5min` filters.
- No custom `switch.platform: nibe`; persistence is stock `restore_mode: RESTORE_DEFAULT_ON`.
- No runtime arbitrary-ID entry; no profile presets.

---

### Task 1: In-RAM enabled-set in `nibe.h`

**Files:**
- Modify: `components/nibe/nibe.h`
- Test: `tests/test_subscription.py`

**Interfaces:**
- Consumes: existing `add_sensor(NibeSensor*)`, `add_number(NibeNumber*)`, `set_poll_registers(const std::vector<uint16_t>&)`.
- Produces: `void esphome::nibe::NibeComponent::set_register_enabled(uint16_t addr, bool enabled)`, `bool esphome::nibe::NibeComponent::is_enabled(uint16_t addr) const`, `void esphome::nibe::NibeComponent::ensure_polled(uint16_t addr)` for Task 2.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_subscription.py
import os
REPO = os.path.join(os.path.dirname(__file__), "..")
HDR = open(os.path.join(REPO, "components", "nibe", "nibe.h")).read()

def test_enabled_set_api_present():
    assert "set_register_enabled" in HDR
    assert "is_enabled" in HDR
    assert "disabled_" in HDR

def test_ensure_polled_present():
    assert "ensure_polled" in HDR
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_subscription.py::test_enabled_set_api_present -v`
Expected: FAIL with `assert "set_register_enabled" in HDR`.

- [ ] **Step 3: Write minimal implementation**

```cpp
// components/nibe/nibe.h — add include at top:
#include <set>
// inside class NibeComponent public block, after set_poll_registers decl:
  void set_register_enabled(uint16_t addr, bool enabled);
  bool is_enabled(uint16_t addr) const;
  void ensure_polled(uint16_t addr);
// inside class NibeComponent protected block, after numbers_ decl:
  std::set<uint16_t> disabled_;
```

```cpp
// components/nibe/nibe.h — method bodies, inline after queue_write() def:
  void set_register_enabled(uint16_t addr, bool enabled) {
    if (enabled) disabled_.erase(addr);
    else disabled_.insert(addr);
  }
  bool is_enabled(uint16_t addr) const { return disabled_.count(addr) == 0; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_subscription.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add components/nibe/nibe.h tests/test_subscription.py
git commit -m "feat: in-RAM register enabled-set with ensure_polled decl"
```

### Task 2: Poll skip + publish gate in `nibe.cpp`

**Files:**
- Modify: `components/nibe/nibe.cpp`
- Modify: `components/nibe/nibe.h`
- Test: `tests/test_subscription.py`

**Interfaces:**
- Consumes: `set_register_enabled()`, `is_enabled()`, `ensure_polled()` decl from Task 1; existing `reads_` queue, `on_value(uint16_t, float)`.
- Produces: working `ensure_polled()` body; `0x69` skip rotation; `on_value()` gate. Task 5 consumes the `set_register_enabled` lambda name.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_subscription.py
import os
REPO2 = os.path.join(os.path.dirname(__file__), "..")
CPP = open(os.path.join(REPO2, "components", "nibe", "nibe.cpp")).read()

def _poll_frame(addr):
    lo, hi = addr & 0xFF, addr >> 8
    c = 0xC0 ^ 0x69 ^ 0x02 ^ lo ^ hi
    return bytes([0xC0, 0x69, 0x02, lo, hi, c])

def _rotate(queue, disabled):
    # mirror of the C++ 0x69 handler: rotate past disabled, max one full lap
    for _ in range(len(queue)):
        front_addr = queue[0][3] | (queue[0][4] << 8)
        if front_addr in disabled:
            queue.append(queue.pop(0))
            continue
        return queue.pop(0)
    return None  # all disabled -> ACK

def test_rotate_skips_disabled():
    q = [_poll_frame(40004), _poll_frame(40008), _poll_frame(40012)]
    assert _rotate(q, {40004}) == _poll_frame(40008)

def test_all_disabled_acks():
    q = [_poll_frame(40004)]
    assert _rotate(q, {40004}) is None

def test_cpp_gates_present():
    assert "is_enabled" in CPP
    assert "ensure_polled" in CPP

def test_number_control_still_queues_when_disabled():
    # spec §4: explicit user write is honored even if readbacks are suppressed;
    # control() must NOT consult the disabled set.
    body = CPP.split("NibeNumber::control")[1].split("}  // namespace")[0]
    assert "queue_write" in body
    assert "disabled_" not in body and "is_enabled" not in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_subscription.py -v`
Expected: FAIL on `test_cpp_gates_present` (`ensure_polled` not in nibe.cpp yet).

- [ ] **Step 3: Write minimal implementation**

```cpp
// components/nibe/nibe.cpp — replace set_poll_registers body:
void NibeComponent::set_poll_registers(const std::vector<uint16_t> &addrs) {
  for (uint16_t a : addrs) ensure_polled(a);
}
void NibeComponent::ensure_polled(uint16_t addr) {
  uint8_t lo = addr & 0xFF, hi = addr >> 8;
  for (auto &q : reads_)
    if (q.size() == 6 && q[3] == lo && q[4] == hi) return;
  uint8_t o[6] = {0xC0, 0x69, 0x02, lo, hi, 0};
  o[5] = calc_crc_c0(o);
  reads_.emplace(o, o + 6);
}
```

```cpp
// components/nibe/nibe.cpp — replace the 0x69 branch:
// BEFORE:
//   if (!reads_.empty()) { auto r = reads_.front(); reads_.pop(); reads_.push(r); tx_(r.data(), r.size()); }
//   else send_ack_();
// AFTER:
    size_t laps = reads_.size();
    bool sent = false;
    while (laps-- > 0 && !reads_.empty()) {
      auto r = reads_.front(); reads_.pop();
      uint16_t a = (r.size() == 6) ? (uint16_t)(r[3] | (r[4] << 8)) : 0;
      if (r.size() == 6 && !is_enabled(a)) { reads_.push(r); continue; }
      reads_.push(r); tx_(r.data(), r.size()); sent = true; break;
    }
    if (!sent) send_ack_();
```

```cpp
// components/nibe/nibe.cpp — first line of on_value body:
void NibeComponent::on_value(uint16_t addr, float v) {
  if (!is_enabled(addr)) return;
```

```cpp
// components/nibe/nibe.h — auto-enqueue on entity registration:
// BEFORE:
//   void add_sensor(NibeSensor *s) { sensors_.push_back(s); }
//   void add_number(NibeNumber *n) { numbers_.push_back(n); }
// AFTER:
  void add_sensor(NibeSensor *s) { sensors_.push_back(s); ensure_polled(s->get_register()); }
  void add_number(NibeNumber *n) { numbers_.push_back(n); ensure_polled(n->get_register()); }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ -v`
Expected: PASS (whole suite, including new rotation tests and all existing decode/register/RMU tests).

- [ ] **Step 5: Commit**

```bash
git add components/nibe/nibe.cpp components/nibe/nibe.h tests/test_subscription.py
git commit -m "feat: skip disabled registers in poll loop and publish path"
```

### Task 3: Codegen — `registers:` becomes `extra_poll:` + unknown-register warning

**Files:**
- Modify: `components/nibe/__init__.py`
- Modify: `components/nibe/registers.py`
- Test: `tests/test_registers.py`

**Interfaces:**
- Consumes: `DEFAULT_ALLOWLIST` (stays as reference only), model JSONs in `components/nibe/models/`.
- Produces: `CONF_EXTRA_POLL = "extra_poll"` (list of int, default `[]`); `def is_known(addr: int, models: dict) -> bool` used by Task 4.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_registers.py
from components.nibe.registers import is_known

def test_is_known_hit_and_miss():
    models = {"F750": [{"register": "40004", "factor": 10, "size": "s16", "mode": "R"}]}
    assert is_known(40004, models) is True
    assert is_known(12345, models) is False

def test_init_uses_extra_poll():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "components", "nibe", "__init__.py")).read()
    assert "extra_poll" in src
    assert 'CONF_REGISTERS = "registers"' not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_registers.py::test_is_known_hit_and_miss -v`
Expected: FAIL with `ImportError` / `cannot import name 'is_known'`.

- [ ] **Step 3: Write minimal implementation**

```python
# components/nibe/registers.py — append:
def is_known(addr: int, models: dict) -> bool:
    want = str(addr)
    for regs in models.values():
        for r in regs:
            if r.get("register") == want:
                return True
    return False
```

```python
# components/nibe/__init__.py — replace CONF_REGISTERS block:
# BEFORE:
# CONF_REGISTERS = "registers"
# CONFIG_SCHEMA = cv.Schema({
#     ...
#     cv.Optional(CONF_REGISTERS, default=list(DEFAULT_ALLOWLIST)): cv.ensure_list(cv.int_),
# ...
# AFTER:
CONF_EXTRA_POLL = "extra_poll"
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(Nibe),
    cv.Optional("slave_address", default=0x19): cv.hex_int,
    cv.Optional(CONF_EXTRA_POLL, default=[]): cv.ensure_list(cv.int_),
    cv.Optional("passive", default=False): cv.boolean,
    cv.Optional("flow_control_pin"): pins.gpio_output_pin_schema,
}).extend(uart.UART_DEVICE_SCHEMA)  # provides uart_id (register_uart_device needs it)
```

```python
# components/nibe/__init__.py — in to_code, replace set_poll_registers line:
# BEFORE: cg.add(var.set_poll_registers(config[CONF_REGISTERS]))
# AFTER:
    cg.add(var.set_poll_registers(config[CONF_EXTRA_POLL]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_registers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add components/nibe/__init__.py components/nibe/registers.py tests/test_registers.py
git commit -m "feat: replace registers allowlist with extra_poll plus is_known helper"
```

### Task 4: Entity codegen warns on unknown register

**Files:**
- Modify: `components/nibe/sensor.py`
- Modify: `components/nibe/number.py`
- Test: `tests/test_entities.py`

**Interfaces:**
- Consumes: `is_known()` from Task 3; existing `to_code(config)` wiring (`set_parent`, `set_register`, `add_sensor`/`add_number`).
- Produces: unchanged wiring plus `esphome.config_validation` warning path (no signature change; Task 5 relies on entities auto-polling, already done in Task 2).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_entities.py
def test_sensor_schema_rejects_unknown_register_warning():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "components", "nibe", "sensor.py")).read()
    assert "is_known" in src

def test_number_schema_rejects_unknown_register_warning():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "components", "nibe", "number.py")).read()
    assert "is_known" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_entities.py -v`
Expected: FAIL (`is_known` not in sensor.py yet).

- [ ] **Step 3: Write minimal implementation**

```python
# components/nibe/sensor.py — full new content:
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from esphome.core import EsphomeError
import logging, os, json
from . import Nibe, nibe_ns
from .registers import is_known

_LOGGER = logging.getLogger(__name__)
NibeSensor = nibe_ns.class_("NibeSensor", sensor.Sensor, cg.Component)

CONFIG_SCHEMA = sensor.sensor_schema(NibeSensor).extend({
    cv.GenerateID("nibe_id"): cv.use_id(Nibe),
    cv.Required("register"): cv.int_,
})

async def to_code(config):
    mdir = os.path.join(os.path.dirname(__file__), "models")
    models = {}
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    if not is_known(config["register"], models):
        _LOGGER.warning("nibe sensor register %s not in model maps; entity will never fire", config["register"])
    parent = await cg.get_variable(config["nibe_id"])
    var = await sensor.new_sensor(config)
    await cg.register_component(var, config)
    cg.add(var.set_parent(parent))
    cg.add(var.set_register(config["register"]))
    cg.add(parent.add_sensor(var))
```

```python
# components/nibe/number.py — same warning block added, wiring unchanged:
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import number
import logging, os, json
from . import Nibe, nibe_ns
from .registers import is_known

_LOGGER = logging.getLogger(__name__)
NibeNumber = nibe_ns.class_("NibeNumber", number.Number, cg.Component)

CONFIG_SCHEMA = number.number_schema(NibeNumber).extend({
    cv.GenerateID("nibe_id"): cv.use_id(Nibe),
    cv.Required("register"): cv.int_,
    cv.Required("min_value"): cv.float_,
    cv.Required("max_value"): cv.float_,
    cv.Optional("step", default=0.5): cv.float_,
})

async def to_code(config):
    mdir = os.path.join(os.path.dirname(__file__), "models")
    models = {}
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    if not is_known(config["register"], models):
        _LOGGER.warning("nibe number register %s not in model maps; entity will never fire", config["register"])
    parent = await cg.get_variable(config["nibe_id"])
    var = await number.new_number(
        config,
        min_value=config["min_value"],
        max_value=config["max_value"],
        step=config["step"],
    )
    await cg.register_component(var, config)
    cg.add(var.set_parent(parent))
    cg.add(var.set_register(config["register"]))
    cg.add(parent.add_number(var))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_entities.py tests/test_registers.py -v`
Expected: PASS (existing wiring tests still pass; warning tests pass).

- [ ] **Step 5: Commit**

```bash
git add components/nibe/sensor.py components/nibe/number.py tests/test_entities.py
git commit -m "feat: warn on entities for unknown registers"
```

### Task 5: Default YAML — drop manual poll list, add enable switches

**Files:**
- Modify: `packages/base.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `set_register_enabled(uint16_t, bool)` on id `nibe_bridge` (Task 1); auto-poll from Task 2; `extra_poll` key from Task 3.
- Produces: 8 working enable switches (`en_40004`, `en_40008`, `en_40012`, `en_40013`, `en_40014`, `en_43009`, `en_43136`, `en_43005`); documented add-one-block flow.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_subscription.py — append YAML contract test
import os
def test_base_yaml_switches_match_entities():
    import re
    base = open(os.path.join(os.path.dirname(__file__), "..", "packages", "base.yaml")).read()
    assert "extra_poll" not in base or "registers:" not in base.split("extra_poll")[0].split("nibe:")[-1]
    assert "registers:" not in base  # manual poll list gone
    for reg in (40004, 40008, 40012, 40013, 40014, 43009, 43136, 43005):
        assert f"set_register_enabled({reg}," in base
        assert "RESTORE_DEFAULT_ON" in base
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_subscription.py::test_base_yaml_switches_match_entities -v`
Expected: FAIL (`registers:` still in base.yaml).

- [ ] **Step 3: Write minimal implementation**

```yaml
# packages/base.yaml — replace the whole nibe: comment block:
# BEFORE: nibe: ... # registers: polled register ids ... # registers: [40004, ...]
# AFTER:
nibe:
  id: nibe_bridge
  uart_id: nibe_uart
  # Bring-up order: flash with passive: true first, confirm decode in
  # logs/web_server, then enable TX (passive: false).
  # passive: true
  # extra_poll: [10001]  # optional poll-without-entity (bring-up sniffing)
  # WARNING: writes to addr <20000 (RMU 1xxxx range) are dropped, never sent in the 0x6B slot.
  # flow_control_pin: GPIO18  # optional RS485 auto-direction pin (absent = no direction control)
  # Entities below auto-poll their registers — no separate poll list to keep in sync.
```

```yaml
# packages/base.yaml — append after the number: block:
switch:
  - platform: template
    name: "Enable BT1 Outdoor"
    id: en_40004
    entity_category: config
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action: { lambda: 'id(nibe_bridge).set_register_enabled(40004, true);' }
    turn_off_action: { lambda: 'id(nibe_bridge).set_register_enabled(40004, false);' }
  - platform: template
    name: "Enable Supply S1"
    id: en_40008
    entity_category: config
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action: { lambda: 'id(nibe_bridge).set_register_enabled(40008, true);' }
    turn_off_action: { lambda: 'id(nibe_bridge).set_register_enabled(40008, false);' }
  - platform: template
    name: "Enable Return"
    id: en_40012
    entity_category: config
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action: { lambda: 'id(nibe_bridge).set_register_enabled(40012, true);' }
    turn_off_action: { lambda: 'id(nibe_bridge).set_register_enabled(40012, false);' }
  - platform: template
    name: "Enable Hot Water Top"
    id: en_40013
    entity_category: config
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action: { lambda: 'id(nibe_bridge).set_register_enabled(40013, true);' }
    turn_off_action: { lambda: 'id(nibe_bridge).set_register_enabled(40013, false);' }
  - platform: template
    name: "Enable Hot Water BT6"
    id: en_40014
    entity_category: config
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action: { lambda: 'id(nibe_bridge).set_register_enabled(40014, true);' }
    turn_off_action: { lambda: 'id(nibe_bridge).set_register_enabled(40014, false);' }
  - platform: template
    name: "Enable Calculated Supply"
    id: en_43009
    entity_category: config
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action: { lambda: 'id(nibe_bridge).set_register_enabled(43009, true);' }
    turn_off_action: { lambda: 'id(nibe_bridge).set_register_enabled(43009, false);' }
  - platform: template
    name: "Enable Compressor Freq"
    id: en_43136
    entity_category: config
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action: { lambda: 'id(nibe_bridge).set_register_enabled(43136, true);' }
    turn_off_action: { lambda: 'id(nibe_bridge).set_register_enabled(43136, false);' }
  - platform: template
    name: "Enable Degree Minutes"
    id: en_43005
    entity_category: config
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action: { lambda: 'id(nibe_bridge).set_register_enabled(43005, true);' }
    turn_off_action: { lambda: 'id(nibe_bridge).set_register_enabled(43005, false);' }
```

```markdown
<!-- README.md — replace the "Allowlist default" line and "Add an entity" section -->
Allowlist reference (`DEFAULT_ALLOWLIST` in `registers.py`): `40004, 40008, 40012, 40013, 40014, 43136, 43005, 40033, 43009, 10001`. Poll set = your entities + optional `extra_poll:` — no separate list to sync.

Add an entity (it auto-polls; copy its switch block too if you want a runtime toggle):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_subscription.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/base.yaml README.md tests/test_subscription.py
git commit -m "feat: default entities auto-poll with persisted enable switches"
```

### Task 6: Full validation — host tests + both boards

**Files:**
- Test: `tests/` (run only, no edits unless red)

**Interfaces:**
- Consumes: all tasks above.
- Produces: green CI-equivalent signal.

- [ ] **Step 1: Run full host suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all files: decode, registers, entities, subscription, RMU, final_fixes).

- [ ] **Step 2: Validate ESPHome configs**

Run: `esphome config nibe_esp32.yaml`
Expected: PASS with `extra_poll` accepted and 8 template switches present; no `registers` key error.

- [ ] **Step 3: Compile both boards**

Run: `esphome compile nibe_esp32.yaml`
Expected: PASS.

Run: `esphome compile nibe_pico_w.yaml`
Expected: PASS.

- [ ] **Step 4: Manual web_server check (hardware)**

Toggle `Enable BT1 Outdoor` OFF in `web_server`, confirm UART log quiets for 40004 and HA stops receiving without touching the HA entity registry. Reboot, confirm toggle state restored.

- [ ] **Step 5: Commit (only if validation forced a fix; otherwise no-op)**

```bash
git status --short
```

If clean, no commit. If a fix was needed, commit it as `fix: validation fallout for register subscription`.
