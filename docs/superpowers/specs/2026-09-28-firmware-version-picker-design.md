# Firmware build number on picker page — design

Date: 2026-09-28. Approach A (approved): codegen-baked `git describe`, picker page only.

## Problem

Firmware carries no build identity. `base.yaml` project version is a stale
hardcoded `"1.0"`, `manifest.json` stays `0.0.0-dev` until Pages stamps it —
neither reaches the device. Debugging ("which build is this node running?")
needs the git tag visible on the node itself.

## Decisions

- Source: git tag at compile time (`git describe --tags --dirty --always`).
  No hand-maintained version string; tag stays the single source of truth.
- Surface: `/heatwhisper/registers` page only (header line + `"fw"` JSON
  field). `/` is owned by ESPHome's `web_server` — injecting there is fragile.
  No HA sensor (revisit if needed; picker covers the debugging need).

## Architecture

`components/heatwhisper/__init__.py`, `heatwhisper.{h,cpp}`, `build.yml` only.
No YAML schema change.

- Codegen (`to_code`): subprocess `git describe --tags --dirty --always`,
  fallback `"dev"` (git missing / not-a-repo / describe fails). Bakes
  `-DHW_FW_VERSION="<ver>"` via `cg.add_define`. ~5 lines.
- C++: `HW_FW_VERSION` defaults to `"dev"` when the define is absent (host
  tests, stale builds). `list_json_()` gains `"fw":"<ver>"` (escaped like
  model strings).
- HTML: header line `Firmware: <ver>` rendered from `j.fw` on the existing
  `?format=json` fetch. No new endpoint, no new request.
- CI: `actions/checkout` gains `fetch-depth: 0` on the compile job so tags
  reach `git describe`. Shallow/local builds degrade to `dev-g<sha>` or
  `dev` — never empty, never blocking.

## Data flow

1. Compile: codegen resolves tag → define → baked string.
2. Page `GET ?format=json` → `{..., fw: "v0.2.0-beta.13-4-g1bc7a0c"}`.
3. Page renders `Firmware: ...` in the header.

## Error handling

- Dirty tree keeps the `-dirty` suffix — a hacked local build can't pose as
  a clean release.
- No tags reachable → `--always` yields short SHA; shown as-is (still
  identifies the build). Git absent → `"dev"`.
- JSON escaping reuses `picker_esc_`; version chars are tag-safe by construction.

## Testing

- `python -m pytest tests/ -q` (existing suite; add assertion that picker
  JSON contains `"fw"`).
- `esphome config` on all three boards (validates codegen define path).
- Manual: flash, open `/heatwhisper/registers`, confirm header matches
  `git describe --tags --dirty --always`.

## Skipped

- Manual `version.txt`: drifts, adds a release step.
- Reading ESPHome `project.version`: answers the wrong question (stale).
- Injecting into `/`: fragile, owned by upstream `web_server`.
- HA `text_sensor`: not needed for the debugging use case; say so if wanted.
