# OTA Update Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Devices self-update from their channel manifest with zero per-board JSON files.

**Architecture:** Standard ESPHome `update/http_request` reads the ESP-Web-Tools `manifest.json` (extended with per-build `ota` blocks). One manifest per channel serves both chips via `chipFamily` matching. Firmware bakes its channel manifest URL via `ota_manifest_url` substitution (stable default, CI overrides to `/beta/` on beta tags). CI stamps `version`+`ota.md5`+`ota.path` on tag deploys. `scripts/release.sh` is the only way to create tags.

**Tech Stack:** ESPHome (http_request, ota/http_request, update/http_request), GitHub Actions, GitHub Pages, bash, Python pytest.

## Global Constraints

- Stable tag regex `^v\d+\.\d+\.\d+$`, beta tag regex `^v\d+\.\d+\.\d+-beta\.\d+$`.
- Repo `manifest.json` stays `"version": "0.0.0-dev"` with no `ota` blocks; CI stamps them.
- Pages base `https://burken-dev.github.io/heat-whisper/`, beta under `beta/`.
- Never hand-tag; use `scripts/release.sh`.
- Pico W stays manual UF2 (no RP2040 build in manifest; inherits update block harmlessly with no matching chipFamily).
- `esphome.project.version` in `packages/base.yaml` left static.

---

### Task 1: Firmware OTA wiring

**Files:**
- Create: `packages/ota_update.yaml` (ESP32-only managed OTA; Pico W stays manual UF2 — RP2040 has no ESP-Web-Tools chipFamily and no HTTPS cert verification)
- Modify: `packages/base.yaml` (untouched — keeps `ota: esphome` for all boards)
- Modify: `heatwhisper_esp32.yaml:1-12`, `heatwhisper_esp32_s3_rs485.yaml:1-12` (add substitution + package include)
- Test: `tests/test_ota_manifest.py`

**Interfaces:**
- Consumes: nothing (new `ota_manifest_url` substitution, default stable URL).
- Produces: `update` entity polling `${ota_manifest_url}`; CI overrides via `esphome -s ota_manifest_url <beta-url>` on beta tags.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ota_manifest.py
import os
REPO = os.path.join(os.path.dirname(__file__), "..")

def test_base_yaml_has_managed_update():
    base = open(os.path.join(REPO, "packages", "base.yaml")).read()
    assert "http_request:" in base
    assert "platform: http_request" in base
    assert "source: ${ota_manifest_url}" in base
    assert "update_interval:" in base

def test_top_level_yamls_define_channel_url():
    for f in ("heatwhisper_esp32.yaml", "heatwhisper_esp32_s3_rs485.yaml"):
        src = open(os.path.join(REPO, f)).read()
        assert "ota_manifest_url:" in src, f
        assert "https://burken-dev.github.io/heat-whisper/manifest.json" in src, f

def test_repo_manifest_stays_dev_without_ota():
    import json
    m = json.load(open(os.path.join(REPO, "manifest.json")))
    assert m["version"] == "0.0.0-dev"
    assert {b["chipFamily"] for b in m["builds"]} == {"ESP32", "ESP32-S3"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ota_manifest.py -v`
Expected: FAIL (no `ota_manifest_url` / update block yet).

- [ ] **Step 3: Write minimal implementation**

In `packages/ota_update.yaml`, write:
```yaml
# Managed OTA only on ESP32 family (Pico W stays manual UF2 — RP2040 has no
# ESP-Web-Tools chipFamily and no HTTPS cert verification).
http_request:
ota:
  - platform: http_request
update:
  - platform: http_request
    name: "Firmware Update"
    source: ${ota_manifest_url}
    update_interval: 24h
```
(`ota: esphome` comes from `base.yaml`; package lists concatenate.)

In `heatwhisper_esp32.yaml`, prepend:
```yaml
substitutions:
  ota_manifest_url: https://burken-dev.github.io/heat-whisper/manifest.json
```
and add `ota_update: !include packages/ota_update.yaml` to `packages:`. Same for `heatwhisper_esp32_s3_rs485.yaml`. `heatwhisper_pico_w.yaml` untouched.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ota_manifest.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/base.yaml heatwhisper_esp32.yaml heatwhisper_esp32_s3_rs485.yaml tests/test_ota_manifest.py
git commit -m "feat: managed OTA via update/http_request pinned to channel manifest"
```

### Task 2: CI channel-aware compile + manifest OTA stamping

**Files:**
- Modify: `.github/workflows/build.yml:22-27` (compile)
- Modify: `.github/workflows/build.yml:74-87` (pages stamp+copy)
- Test: `tests/test_ota_manifest.py` (extend with CI assertions)

**Interfaces:**
- Consumes: Task 1 `ota_manifest_url` substitution; tag `VERSION`/`DEST` env.
- Produces: beta firmware polling `/beta/manifest.json`; `DEST/manifest.json` with `version` + per-build `ota.{md5,path}` absolute URLs.

- [ ] **Step 1: Write the failing test**

```python
def test_ci_overrides_channel_and_stamps_ota():
    yml = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "-s ota_manifest_url" in yml
    assert "beta/manifest.json" in yml
    assert "ota" in yml and "md5sum" in yml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ota_manifest.py::test_ci_overrides_channel_and_stamps_ota -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Replace the three compile lines with:
```yaml
      - run: |
          MANIFEST_URL=https://burken-dev.github.io/heat-whisper/manifest.json
          case "${GITHUB_REF:-}" in *-beta*) MANIFEST_URL=https://burken-dev.github.io/heat-whisper/beta/manifest.json;; esac
          esphome -s ota_manifest_url "$MANIFEST_URL" config heatwhisper_esp32.yaml
          esphome -s ota_manifest_url "$MANIFEST_URL" config heatwhisper_pico_w.yaml
          esphome -s ota_manifest_url "$MANIFEST_URL" config heatwhisper_esp32_s3_rs485.yaml
          esphome -s ota_manifest_url "$MANIFEST_URL" compile heatwhisper_esp32.yaml
          esphome -s ota_manifest_url "$MANIFEST_URL" compile heatwhisper_pico_w.yaml
          esphome -s ota_manifest_url "$MANIFEST_URL" compile heatwhisper_esp32_s3_rs485.yaml
```

Replace the pages stamp `run:` block (TAG/VERSION/DEST + one-line python stamp) with:
```yaml
      - run: |
          TAG=${GITHUB_REF##*/}; VERSION=${TAG#v}; DEST=public; case "$TAG" in *-beta*) DEST=public/beta;; esac
          BASE=https://burken-dev.github.io/heat-whisper
          if [ "$DEST" = "public/beta" ]; then BASE="$BASE/beta"; fi
          MD5_ESP32=$(md5sum fw/firmware.ota.bin | cut -d' ' -f1)
          MD5_S3=$(md5sum fw/heatwhisper_esp32_s3_rs485.ota.bin | cut -d' ' -f1)
          BASE="$BASE" VERSION="$VERSION" MD5_ESP32="$MD5_ESP32" MD5_S3="$MD5_S3" python3 -c "import json,os; m=json.load(open('manifest.json')); m['version']=os.environ['VERSION']; b=os.environ['BASE']; m['builds'][0]['ota']={'md5':os.environ['MD5_ESP32'],'path':b+'/heatwhisper_esp32.ota.bin'}; m['builds'][1]['ota']={'md5':os.environ['MD5_S3'],'path':b+'/heatwhisper_esp32_s3_rs485.ota.bin'}; json.dump(m,open('manifest.json','w'),indent=2)"
          echo "TAG=$TAG" >> $GITHUB_ENV
          echo "VERSION=$VERSION" >> $GITHUB_ENV
          echo "DEST=$DEST" >> $GITHUB_ENV
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ota_manifest.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/build.yml tests/test_ota_manifest.py
git commit -m "ci: channel-aware firmware + stamp manifest ota blocks"
```

### Task 3: Semver auto-tag script

**Files:**
- Create: `scripts/release.sh`
- Test: `tests/test_ota_manifest.py` (extend with script assertions)

**Interfaces:**
- Consumes: `git tag` list, Task 2 CI (does the publishing).
- Produces: validated `vX.Y.Z` / `vX.Y.Z-beta.N` tag pushed to origin.

- [ ] **Step 1: Write the failing test**

```python
def test_release_script_exists_and_validates_semver():
    import stat
    p = os.path.join(REPO, "scripts", "release.sh")
    src = open(p).read()
    assert bool(os.stat(p).st_mode & stat.S_IXUSR)
    assert "^v" in src and "-beta" in src
    assert "pytest" in src and "esphome config" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ota_manifest.py::test_release_script_exists_and_validates_semver -v`
Expected: FAIL (file missing).

- [ ] **Step 3: Write minimal implementation**

Write `scripts/release.sh` with exactly:
```bash
#!/usr/bin/env bash
# Usage: scripts/release.sh stable patch|minor|major|X.Y.Z | scripts/release.sh beta [X.Y.Z]
set -euo pipefail
CHAN=${1:-}; ARG=${2:-}
STABLE_RE='^v[0-9]+\.[0-9]+\.[0-9]+$'; BETA_RE='^v[0-9]+\.[0-9]+\.[0-9]+-beta\.[0-9]+$'
latest() { git tag --list "$1" | sort -V | tail -1; }
next_stable() {
  local cur=${1#v} part=$2
  IFS=. read -r M m p <<<"$cur"
  case "$part" in major) echo "v$((M+1)).0.0";; minor) echo "v$M.$((m+1)).0";; patch) echo "v$M.$m.$((p+1))";; esac
}
if [ "$CHAN" = stable ]; then
  case "$ARG" in patch|minor|major) TAG=$(next_stable "$(latest 'v[0-9]*' | grep -v beta || echo v0.0.0)" "$ARG");; *) TAG="v$ARG";; esac
  echo "$TAG" | grep -Eq "$STABLE_RE" || { echo "bad stable tag: $TAG"; exit 1; }
elif [ "$CHAN" = beta ]; then
  if [ -n "$ARG" ]; then BASE="v$ARG"; BASE=${BASE%-beta*}; else BASE=$(latest 'v[0-9]*' | grep -v beta || echo v0.1.0); fi
  N=1; while git rev-parse "$BASE-beta.$N" >/dev/null 2>&1; do N=$((N+1)); done
  TAG="$BASE-beta.$N"
  echo "$TAG" | grep -Eq "$BETA_RE" || { echo "bad beta tag: $TAG"; exit 1; }
else echo "usage: $0 stable patch|minor|major|X.Y.Z | $0 beta [X.Y.Z]"; exit 1; fi
git rev-parse "$TAG" >/dev/null 2>&1 && { echo "tag exists: $TAG"; exit 1; }
python -m pytest tests/ -q
esphome config heatwhisper_esp32.yaml
esphome config heatwhisper_esp32_s3_rs485.yaml
esphome config heatwhisper_pico_w.yaml
git tag "$TAG" && git push origin "$TAG"
echo "released $TAG"
```
Run: `chmod +x scripts/release.sh`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ota_manifest.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/release.sh tests/test_ota_manifest.py
git commit -m "chore: semver auto-tag script for stable/beta channels"
```

## Self-Review

1. Spec coverage: beta-polls-beta/stable-polls-stable → Task 1 substitution + Task 2 `-s` override; semver manifest+ota-json+tags structured → Task 2 stamp + Task 3 script; automatic handling → Task 2 CI + Task 3 pre-tag checks + push.
2. Placeholder scan: no TBD/TODO; every step has exact code/commands; no "similar to Task N".
3. Type consistency: `ota_manifest_url` identical in base.yaml/consumers/CI; `BASE/VERSION/MD5_*` env names match in stamp; tag regex identical to release-workflow skill; `DEST` stable=`public/`, beta=`public/beta/`.
