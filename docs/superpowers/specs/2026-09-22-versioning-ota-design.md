# Versioning + OTA channels (design)

Date: 2026-09-22. Status: approved (Approach A-lite, no nightly, all sections confirmed by user).

## Problem

Single dev on `main` with tag `v0.1.0`. CI builds + tests on push/PR, publishes Release + Pages only on `v*` tags. Need a trunk-based base that also serves stable + beta OTA via GitHub Releases + web flasher, and stays enforceable for future collaborators / AI agents.

## Decisions (from brainstorming Q&A)

- OTA delivery: ESPHome-native, no on-device self-updater. Channels = separate Pages URLs + GitHub Releases (`*.factory.bin`, `*.ota.bin`, `*.uf2`).
- Beta opt-in: separate URL is fine. No on-device channel switch.
- Nightly: skipped per user. Only stable + beta. `main` pushes = CI check only.

## Rejected alternatives

- **B — GitHub Flow strict, manual alphas only, no auto-publish:** less CI noise but testers wait on manual tags. Rejected (loses merge-to-main = testable for beta).
- **C — GitFlow (main/develop/release branches):** hardening isolation but merge overhead for 1 dev. Rejected per YAGNI.
- **On-device `http_request` self-update + channel selector:** one-click UX but adds flash, TLS, security surface to zero-config image. Rejected; add when manual re-flash measurably hurts.
- **Nightly channel:** dated auto-builds from `main`. Rejected per user (stable + beta only).

## Architecture (chosen)

Trunk-based lite on `main`. Solo: direct commits or short `feat/*` branches. Future humans/agents: PRs required (enforced later via protection).

Version source of truth = git tag only. `manifest.json` in repo set once to `0.0.0-dev` (from current `0.1.0`); stamped at deploy time (existing step, parameterized per channel). `esphome.project.version` in `packages/base.yaml` left static.

Tag format:
- stable: `^v\d+\.\d+\.\d+$` (e.g. `v0.2.0`)
- beta: `^v\d+\.\d+\.\d+-beta\.\d+$` (e.g. `v0.2.0-beta.1`)

## Data flow (channels)

- `vX.Y.Z` → GitHub Release (stable, `prerelease: false`) → Pages `/` with `manifest.json` version `X.Y.Z` + 3-board bins.
- `vX.Y.Z-beta.N` → GitHub Pre-release (`prerelease: true`) → Pages `/beta/` with version `X.Y.Z-beta.N`.
- `main` push / PR: `pytest + esphome config/compile` only, artifacts 7-day retention, no publish.
- Beta users: flash from `<user>.github.io/heat-whisper/beta/` or download `*.ota.bin` / `*.uf2` from pre-release. `index.html` stable page links to beta.

## Error handling

- Wrong tag (`v0.2` / `v0.2.0_beta1`): CI release/pages jobs skip (regex gate); skill flags format before push.
- Dirty `main` breaks beta: protection requires `host-tests` + `compile` green before tag job runs; tag on red = release job still needs green `compile` (needs: chain).
- Stale flasher cache: version stamp forces ESP Web Tools update prompt; keep `manifest.json` version == tag.
- Tag moved / re-pushed: block via tag protection `v*`; delete + re-tag requires admin.

## Build / release

- `.github/workflows/build.yml` only: split `release` + `pages` by tag suffix (`*-beta*` → beta). Parameterize `dest` (`public/` vs `public/beta/`) and `prerelease` flag. No new workflows, no nightly job.
- `index.html`: one-line beta link. No firmware code change.

## Testing

- Existing `pytest + esphome config/compile` gates stay required checks.
- Manual: push beta tag on a test repo fork → verify pre-release + `/beta/` manifest version; push stable tag → verify `/` manifest.
- No new C++ tests (workflow-only change).

## Enforcement

- One skill file: `.opencode/skills/release-workflow/SKILL.md` (branch rules, tag regex, pre-tag checklist, channel table). Single file so agents auto-load it.
- GitHub settings (manual): `main` protection (require `host-tests` + `compile`, block force-push/deletion; PR reviews off for solo, on when team grows); tag protection `v*`; Pages source = GitHub Actions.

## Non-goals

Nightly channel, on-device channel switch / auto-update, GitFlow, commit hooks, separate beta skill file.
