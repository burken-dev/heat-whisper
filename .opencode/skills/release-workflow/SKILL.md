---
name: release-workflow
description: Enforce trunk-based stable/beta versioning and OTA release channels. Use before any tag, release, or version bump.
---

# Release Workflow

Trunk-based lite. `main` always releasable. Solo: direct or `feat/*`. Agents: PR required.

## Tags (version = tag only)

- Stable: `vX.Y.Z` regex `^v\d+\.\d+\.\d+$`
- Beta: `vX.Y.Z-beta.N` regex `^v\d+\.\d+\.\d+-beta\.\d+$`
- Never hand-bump `manifest.json` (repo stays `0.0.0-dev`, CI stamps it).

## Pre-tag checklist (run in order)

```bash
python -m pytest tests/ -q
esphome config heatwhisper_esp32.yaml
esphome config heatwhisper_esp32_s3_rs485.yaml
esphome config heatwhisper_pico_w.yaml
git tag vX.Y.Z # or vX.Y.Z-beta.N
git push origin vX.Y.Z
```

## Channels

| Tag | GitHub Release | Pages dir | manifest version |
|---|---|---|---|
| `vX.Y.Z` | Release (`prerelease:false`) | `public/` | `X.Y.Z` |
| `vX.Y.Z-beta.N` | Pre-release (`prerelease:true`) | `public/beta/` | `X.Y.Z-beta.N` |

Beta users flash from `/beta/` or download `*.ota.bin` from the pre-release.
