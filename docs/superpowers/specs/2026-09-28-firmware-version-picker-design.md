# Firmware build number as text_sensor — design

Date: 2026-09-28. Approved: codegen-baked `git describe` published via a
template text_sensor named "HeatWhisper version". (Rev 2: supersedes the
picker-page `"fw"` approach — the sensor auto-appears on `http://<node>/`
via `web_server`'s entity list plus HA, so no custom HTML/JSON is needed.)

## Problem

Firmware carries no build identity. `base.yaml` project version is a stale
hardcoded `"1.0"`, `manifest.json` stays `0.0.0-dev` until Pages stamps it —
neither reaches the device. Debugging ("which build is this node running?")
needs the git tag visible on the node itself.

## Decisions

- Source: git tag at compile time (`git describe --tags --dirty --always`).
  No hand-maintained version string; tag stays the single source of truth.
- Surface: one template `text_sensor` ("HeatWhisper version", diagnostic)
  publishing the baked string. Visible on `/` (entity list), in HA, and in
  logs. Picker page untouched.
- ESPHome's stock `platform: version` sensor deliberately NOT used: it
  reports the ESPHome framework version (e.g. `2026.9.0`), identical across
  HeatWhisper releases built with the same toolchain — answers the wrong
  question.

## Architecture

`components/heatwhisper/__init__.py` + `packages/base.yaml` + `build.yml`
only. No C++ entity code, no picker changes.

- Codegen (`to_code`): subprocess `git describe --tags --dirty --always`,
  fallback `"dev"` (git missing / not-a-repo / describe fails). Bakes
  `-DHW_FW_VERSION="<ver>"` via `cg.add_define`. ~5 lines.
- YAML (`base.yaml`, next to "Heat Pump Model"): template text_sensor with
  `lambda: 'return HW_FW_VERSION;'`, `entity_category: diagnostic`. Define
  defaults to `"dev"` when absent (host tests, stale builds) so the lambda
  always compiles.
- CI: `actions/checkout` gains `fetch-depth: 0` on the compile job so tags
  reach `git describe`. Shallow/local builds degrade to `dev-g<sha>` or
  `dev` — never empty, never blocking.

## Data flow

1. Compile: codegen resolves tag → define → baked string.
2. Boot: template sensor publishes `HW_FW_VERSION` once (static string).
3. `http://<node>/` lists "HeatWhisper version"; HA gets the entity via
   the native API automatically.

## Error handling

- Dirty tree keeps the `-dirty` suffix — a hacked local build can't pose as
  a clean release.
- No tags reachable → `--always` yields short SHA; shown as-is (still
  identifies the build). Git absent → `"dev"`.
- Version chars are tag-safe by construction; define is quoted at the
  codegen boundary.

## Testing

- `python -m pytest tests/ -q` (existing suite).
- `esphome config` on all three boards (validates codegen define + YAML
  lambda path).
- Manual: flash, open `http://<node>/`, confirm "HeatWhisper version"
  matches `git describe --tags --dirty --always`.

## Skipped

- Picker-page `"fw"` field + HTML header (rev 1): redundant once the sensor
  exists — `/` already lists it.
- Stock `platform: version`: reports toolchain, not HeatWhisper release.
- Manual `version.txt`: drifts, adds a release step.
- Reading ESPHome `project.version`: stale hardcoded `"1.0"`.
