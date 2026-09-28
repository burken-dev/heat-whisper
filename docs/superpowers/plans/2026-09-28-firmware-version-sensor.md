# Firmware Version Sensor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the HeatWhisper build identity (git tag) on `http://<node>/` and in HA via a template text_sensor named "HeatWhisper version".

**Architecture:** Codegen bakes `git describe --tags --dirty --always` into a `-DHW_FW_VERSION="..."` compile define (fallback `"dev"`); a 6-line template sensor in `base.yaml` publishes it. No C++ entity code, no picker changes.

**Tech Stack:** ESPHome codegen (`esphome.codegen`), YAML template text_sensor, GitHub Actions checkout, pytest (source-grep + helper unit tests).

## Global Constraints

- Version source is the git tag only; never hand-bump a version string.
- Sensor name is exactly `HeatWhisper version`, `entity_category: diagnostic`, `update_interval: 60s` (mirrors the existing "Heat Pump Model" sensor).
- `manifest.json` stays `0.0.0-dev` in repo; CI stamps it (untouched by this plan).
- Dirty tree keeps the `-dirty` suffix; git missing / empty output → `"dev"`.
- Define value is sanitized to `[A-Za-z0-9._-+]` so the `-D` quote can't break.

---

## File Structure

- Modify: `components/heatwhisper/__init__.py` — new `resolve_fw_version()` helper + one `cg.add_define` line in `to_code`. Owns: tag → string → define.
- Modify: `components/heatwhisper/heatwhisper.h` — `#ifndef HW_FW_VERSION` fallback guard. Owns: safe default when the define is absent.
- Modify: `packages/base.yaml` — template text_sensor block after "Heat Pump Model". Owns: publishing the baked string to `/` + HA.
- Modify: `.github/workflows/build.yml` — `fetch-depth: 0` on the compile job checkout. Owns: tags reach `git describe` in CI.
- Create: `tests/test_fw_version.py` — helper unit tests (monkeypatched subprocess) + source-grep contract tests. Owns: proving the wiring without the ESPHome toolchain.

---

### Task 1: Bake git tag into a compile define

**Files:**
- Modify: `components/heatwhisper/__init__.py` (top import + helper + one line in `to_code`)
- Test: `tests/test_fw_version.py` (new)

**Interfaces:**
- Consumes: stdlib `subprocess` only.
- Produces: `components.heatwhisper.resolve_fw_version() -> str` (used by `to_code` in the same file; tested directly in this task).

- [ ] **Step 1: Write the failing test**

Create `tests/test_fw_version.py` with the full contract (helper tests fail now with ImportError; grep tests fail until later tasks — run only the helper tests in this task):

```python
# tests/test_fw_version.py — firmware identity baked from git tag.
import os
REPO = os.path.join(os.path.dirname(__file__), "..")


def test_resolve_fw_version_live_matches_git():
    # Smoke: in a real checkout this equals git describe output (sanitized).
    import subprocess
    from components.heatwhisper import resolve_fw_version
    try:
        raw = subprocess.run(
            ["git", "describe", "--tags", "--dirty", "--always"],
            capture_output=True, text=True, timeout=10, cwd=REPO,
        ).stdout.strip()
    except Exception:
        raw = ""
    expected = "".join(c for c in raw if c.isalnum() or c in "._-+") or "dev"
    assert resolve_fw_version() == expected


def test_resolve_fw_version_falls_back_to_dev(monkeypatch):
    from components.heatwhisper import subprocess as hw_subprocess
    def boom(*a, **k):
        raise FileNotFoundError("no git")
    monkeypatch.setattr(hw_subprocess, "run", boom)
    from components.heatwhisper import resolve_fw_version
    assert resolve_fw_version() == "dev"


def test_resolve_fw_version_strips_dangerous_chars(monkeypatch):
    from components.heatwhisper import subprocess as hw_subprocess
    class R:
        stdout = 'v1.0"; rm -rf /; echo "'
    monkeypatch.setattr(hw_subprocess, "run", lambda *a, **k: R())
    from components.heatwhisper import resolve_fw_version
    v = resolve_fw_version()
    assert '"' not in v and " " not in v and ";" not in v
    assert v.startswith("v1.0")


def test_resolve_fw_version_empty_output_is_dev(monkeypatch):
    from components.heatwhisper import subprocess as hw_subprocess
    class R:
        stdout = "\n"
    monkeypatch.setattr(hw_subprocess, "run", lambda *a, **k: R())
    from components.heatwhisper import resolve_fw_version
    assert resolve_fw_version() == "dev"


def test_codegen_bakes_fw_define():
    src = open(os.path.join(REPO, "components", "heatwhisper", "__init__.py")).read()
    assert "git describe" in src
    assert 'cg.add_define("HW_FW_VERSION"' in src


def test_header_has_fw_fallback():
    hdr = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")).read()
    assert "#ifndef HW_FW_VERSION" in hdr
    assert '#define HW_FW_VERSION "dev"' in hdr


def test_base_yaml_has_version_sensor():
    base = open(os.path.join(REPO, "packages", "base.yaml")).read()
    assert 'name: "HeatWhisper version"' in base
    assert "return HW_FW_VERSION;" in base


def test_build_yml_fetches_tags():
    yml = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "fetch-depth: 0" in yml
```

- [ ] **Step 2: Run helper tests to verify they fail**

Run: `python -m pytest tests/test_fw_version.py::test_resolve_fw_version_live_matches_git tests/test_fw_version.py::test_resolve_fw_version_falls_back_to_dev -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_fw_version'` (conftest stubs `esphome`, so the package imports; only the helper is missing).

- [ ] **Step 3: Write minimal implementation**

In `components/heatwhisper/__init__.py`, extend the import line 2 and add the helper + define. Exact edits:

Old (line 2):
```python
import os, json, esphome.codegen as cg
```

New:
```python
import os, json, subprocess, esphome.codegen as cg
```

Add after line 15 (`CONF_WEB_SERVER_BASE_ID = ...` line), before `CONFIG_SCHEMA`:
```python
def resolve_fw_version():
    # ponytail: git tag is the single source of truth; never hand-bump.
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--dirty", "--always"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."),
            check=True,
        ).stdout.strip()
    except Exception:
        return "dev"
    if not out:
        return "dev"
    # ponytail: tag-safe by construction; allow-list so the -D quote can't break.
    safe = "".join(c for c in out if c.isalnum() or c in "._-+")
    return safe or "dev"
```

In `to_code`, after line 34 (`cg.add(var.set_passive(config["passive"]))`), insert:
```python
    cg.add_define("HW_FW_VERSION", f'"{resolve_fw_version()}"')
```

So the block reads:
```python
    cg.add(var.set_passive(config["passive"]))
    cg.add_define("HW_FW_VERSION", f'"{resolve_fw_version()}"')
    if "flow_control_pin" in config:
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run: `python -m pytest tests/test_fw_version.py::test_resolve_fw_version_live_matches_git tests/test_fw_version.py::test_resolve_fw_version_falls_back_to_dev tests/test_fw_version.py::test_resolve_fw_version_strips_dangerous_chars tests/test_fw_version.py::test_resolve_fw_version_empty_output_is_dev tests/test_fw_version.py::test_codegen_bakes_fw_define -v`
Expected: PASS (the header/yaml/yml grep tests still fail — covered in their tasks).

- [ ] **Step 5: Commit**

```bash
git add components/heatwhisper/__init__.py tests/test_fw_version.py
git commit -m "feat: bake git tag into HW_FW_VERSION define"
```

### Task 2: Header fallback guard

**Files:**
- Modify: `components/heatwhisper/heatwhisper.h` (4-line guard after includes)
- Test: `tests/test_fw_version.py::test_header_has_fw_fallback` (already written in Task 1)

**Interfaces:**
- Consumes: `HW_FW_VERSION` define from Task 1 (may be absent on exotic build paths).
- Produces: guaranteed `HW_FW_VERSION` string literal for any TU including this header.

- [ ] **Step 1: Test already written (Task 1)** — no new test code.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fw_version.py::test_header_has_fw_fallback -v`
Expected: FAIL with `assert "#ifndef HW_FW_VERSION" in hdr`.

- [ ] **Step 3: Write minimal implementation**

In `components/heatwhisper/heatwhisper.h`, insert after line 16 (`#include <vector>`) and before line 17 (`// ponytail: must match SIZE_CODES in registers.py`):

```cpp
// Firmware identity baked by codegen (git describe); "dev" when unknown.
#ifndef HW_FW_VERSION
#define HW_FW_VERSION "dev"
#endif
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_fw_version.py::test_header_has_fw_fallback -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add components/heatwhisper/heatwhisper.h tests/test_fw_version.py
git commit -m "feat: HW_FW_VERSION dev fallback in header"
```

### Task 3: Publish via template text_sensor

**Files:**
- Modify: `packages/base.yaml` (one sensor block after "Heat Pump Model")
- Test: `tests/test_fw_version.py::test_base_yaml_has_version_sensor` (already written in Task 1)

**Interfaces:**
- Consumes: `HW_FW_VERSION` macro from Task 1 (command-line define; header fallback from Task 2 as belt-and-braces).
- Produces: entity `HeatWhisper version` on `http://<node>/` + HA via native API.

- [ ] **Step 1: Test already written (Task 1)** — no new test code.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fw_version.py::test_base_yaml_has_version_sensor -v`
Expected: FAIL with `assert 'name: "HeatWhisper version"' in base`.

- [ ] **Step 3: Write minimal implementation**

In `packages/base.yaml`, after the "Heat Pump Model" block (lines 77–83), insert:

```yaml
  # Firmware build identity (git tag baked at compile time, "dev" when unknown).
  - platform: template
    name: "HeatWhisper version"
    lambda: 'return HW_FW_VERSION;'
    update_interval: 60s
    entity_category: diagnostic
```

So the file reads:
```yaml
text_sensor:
  # Autodetected from the pump's 0x6D announcement (empty = not heard yet).
  - platform: template
    name: "Heat Pump Model"
    lambda: 'return id(heatwhisper_bridge).get_model();'
    update_interval: 60s
    entity_category: diagnostic
  # Firmware build identity (git tag baked at compile time, "dev" when unknown).
  - platform: template
    name: "HeatWhisper version"
    lambda: 'return HW_FW_VERSION;'
    update_interval: 60s
    entity_category: diagnostic
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_fw_version.py::test_base_yaml_has_version_sensor -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/base.yaml tests/test_fw_version.py
git commit -m "feat: HeatWhisper version text_sensor in base"
```

### Task 4: Fetch tags in CI compile job

**Files:**
- Modify: `.github/workflows/build.yml` (one `with:` block on the compile checkout)
- Test: `tests/test_fw_version.py::test_build_yml_fetches_tags` (already written in Task 1)

**Interfaces:**
- Consumes: nothing from earlier tasks (CI plumbing for Task 1's `git describe`).
- Produces: full tag history in the compile job so the baked version is a real tag, not a bare SHA.

- [ ] **Step 1: Test already written (Task 1)** — no new test code.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fw_version.py::test_build_yml_fetches_tags -v`
Expected: FAIL with `assert "fetch-depth: 0" in yml`.

- [ ] **Step 3: Write minimal implementation**

In `.github/workflows/build.yml`, the compile job checkout (lines 15–16):

Old:
```yaml
    steps:
      - uses: actions/checkout@v4
      # ponytail: factory image is zero-config (no secrets); keep a dummy file
```

New:
```yaml
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }  # tags must reach git describe for HW_FW_VERSION
      # ponytail: factory image is zero-config (no secrets); keep a dummy file
```

Host-tests and pages checkouts stay shallow — only the compile job runs codegen.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_fw_version.py::test_build_yml_fetches_tags -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/build.yml tests/test_fw_version.py
git commit -m "ci: fetch tags for firmware version bake"
```

### Task 5: Full verification

**Files:**
- No changes; runs the whole suite plus ESPHome validation.

**Interfaces:**
- Consumes: all tasks above.
- Produces: green suite + validated configs; plan file committed.

- [ ] **Step 1: Run the full host suite**

Run: `python -m pytest tests/ -q`
Expected: all PASS, including the 8 new `test_fw_version.py` tests.

- [ ] **Step 2: Validate all three board configs (requires ESPHome toolchain)**

Run:
```bash
esphome config heatwhisper_esp32.yaml
esphome config heatwhisper_esp32_s3_rs485.yaml
esphome config heatwhisper_pico_w.yaml
```
Expected: all three validate clean (proves the codegen define path + YAML lambda parse). If the toolchain is unavailable in this environment, note it and rely on CI's compile job.

- [ ] **Step 3: Sanity-check the baked value**

Run: `git describe --tags --dirty --always`
Expected: output matches what `resolve_fw_version()` returns:
```bash
python -c "from components.heatwhisper import resolve_fw_version; print(resolve_fw_version())"
```

- [ ] **Step 4: Commit the plan**

```bash
git add docs/superpowers/plans/2026-09-28-firmware-version-sensor.md
git commit -m "docs: firmware version sensor implementation plan"
```
