---
name: release-workflow
description: Enforce trunk-based stable/beta versioning, managed OTA, and release channels. Use before any tag, release, version bump, or OTA change.
---

# Release Workflow

Trunk-based lite. `main` always releasable. Solo: direct or `feat/*`. Agents: PR required.

## Tags (version = tag only)

- Stable: `vX.Y.Z` regex `^v\d+\.\d+\.\d+$`
- Beta: `vX.Y.Z-beta.N` regex `^v\d+\.\d+\.\d+-beta\.\d+$`
- Never hand-bump `manifest.json` (repo stays `0.0.0-dev`, CI stamps it).

## Pre-tag checklist (run in order)

Never hand-tag. Only entry point:

```bash
scripts/release.sh stable patch|minor|major|X.Y.Z
scripts/release.sh beta [X.Y.Z]
```

The script validates semver, runs `pytest` + all three `esphome config`, then tags + pushes. CI does the rest.

## Managed OTA (standard `update/http_request`)

- Wiring lives in `packages/ota_update.yaml` (ESP32-only), included by `heatwhisper_esp32.yaml` + `heatwhisper_esp32_s3_rs485.yaml` via `ota_manifest_url` substitution (stable default; CI overrides to `/beta/` on beta tags with `esphome -s`). Beta polls beta, stable polls stable.
- One manifest per channel serves both chips via `builds[].chipFamily` + `ota.{md5,path}`. Never hand-edit them — CI stamps `version`+`ota` on tag deploy.
- Pico W stays manual UF2: no `ota_update` include (RP2040 has no Web-Tools chipFamily, no HTTPS cert verification). Never set `verify_ssl: false` on ESP32 to "fix" Pico. Never create per-board update JSONs.

## Channels

| Tag | GitHub Release | Pages dir | manifest version | device polls |
|---|---|---|---|---|
| `vX.Y.Z` | Release (`prerelease:false`) | `public/` | `X.Y.Z` | `/manifest.json` |
| `vX.Y.Z-beta.N` | Pre-release (`prerelease:true`) | `public/beta/` | `X.Y.Z-beta.N` | `/beta/manifest.json` |

Beta users flash from `/beta/` or download `*.ota.bin` from the pre-release.
