# Versioning + OTA Channels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship trunk-based stable/beta releases via tags with zero firmware code change.

**Architecture:** Tag-only versioning; existing `build.yml` split by `-beta` suffix into stable (`/`) vs beta (`/beta/`) Pages channels + pre-release flag; one enforcement skill file.

**Tech Stack:** GitHub Actions, GitHub Releases, GitHub Pages, ESP Web Tools manifest.json, Python pytest.

## Global Constraints

- Trunk-based lite on `main`; no `develop`, no release branches, no nightly job.
- Version source of truth = git tag only.
- Stable tag format `^v\d+\.\d+\.\d+$`, beta tag format `^v\d+\.\d+\.\d+-beta\.\d+$`.
- `manifest.json` in repo = `0.0.0-dev`, stamped at deploy time to tag version.
- `esphome.project.version` in `packages/base.yaml` left static.
- `main` push / PR = `pytest + esphome config/compile` only, no publish.
- No firmware C++ change, no on-device updater, no new workflows.

---

### Task 1: CI channel split (stable vs beta)

**Files:**
- Modify: `.github/workflows/build.yml:41-85`
- Test: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/build.yml'))"` + `python -m pytest tests/ -q`

**Interfaces:**
- Consumes: `github.ref` tag string (e.g. `refs/tags/v0.2.0-beta.1`), existing `compile` artifact `fw/`.
- Produces: `release` job with `prerelease` flag set for `-beta` tags; `pages` job writing to `public/` (stable) or `public/beta/` (beta) with stamped `manifest.json`.

- [ ] **Step 1: Prove current CI has no channel split (failing test)**

Run: `grep -c "beta" .github/workflows/build.yml`
Expected: FAIL / output `0` (no beta handling today).

- [ ] **Step 2: Add prerelease flag to release job**

Edit `.github/workflows/build.yml`, replace:
```yaml
      - uses: softprops/action-gh-release@v2
        with: { files: dist/** }
```
with:
```yaml
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/**
          prerelease: ${{ contains(github.ref, '-beta') }}
```

- [ ] **Step 3: Parameterize pages job by channel**

Replace the two `run:` blocks in `pages` (stamp + copy) with:
```yaml
      - run: |
          TAG=${GITHUB_REF##*/}; VERSION=${TAG#v}; DEST=public; case "$TAG" in *-beta*) DEST=public/beta;; esac
          python3 -c "import json; v='$VERSION'; m=json.load(open('manifest.json')); m['version']=v; json.dump(m,open('manifest.json','w'),indent=2)"
          echo "TAG=$TAG VERSION=$VERSION DEST=$DEST" >> $GITHUB_ENV
      - run: |
          mkdir -p "$DEST"
          cp index.html manifest.json "$DEST"/
          cp fw/firmware.factory.bin "$DEST"/heatwhisper_esp32.factory.bin
          cp fw/firmware.ota.bin "$DEST"/heatwhisper_esp32.ota.bin
          cp fw/firmware.bin "$DEST"/heatwhisper_pico_w.bin
          cp fw/firmware.uf2 "$DEST"/heatwhisper_pico_w.uf2
          cp fw/heatwhisper_esp32_s3_rs485.factory.bin fw/heatwhisper_esp32_s3_rs485.ota.bin "$DEST"/
```

- [ ] **Step 4: Verify YAML parses and tests pass**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/build.yml')); print('yaml ok')"`
Expected: PASS `yaml ok`.
Run: `python -m pytest tests/ -q`
Expected: PASS (same count as `main` today).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/build.yml
git commit -m "ci: split stable/beta release channels by -beta tag suffix"
```

### Task 2: Manifest + flasher wiring

**Files:**
- Modify: `manifest.json:2`
- Modify: `index.html:27`
- Test: `python3 -c "import json; assert json.load(open('manifest.json'))['version']=='0.0.0-dev'"`

**Interfaces:**
- Consumes: Task 1 `DEST` + stamp step (reads repo `manifest.json`).
- Produces: repo manifest with dev sentinel; stable page linking to beta channel.

- [ ] **Step 1: Prove sentinel missing (failing test)**

Run: `python3 -c "import json; assert json.load(open('manifest.json'))['version']=='0.0.0-dev'"`
Expected: FAIL (`AssertionError`, current value `0.1.0`).

- [ ] **Step 2: Set dev sentinel**

Edit `manifest.json`, replace `"version": "0.1.0"` with `"version": "0.0.0-dev"`.

- [ ] **Step 3: Add beta link to flasher page**

Edit `index.html`, append after the troubleshooting `<p>` (line 27):
```html
<p>Beta testers: flash from <a href="./beta/">/beta/</a> or download <code>.ota.bin</code> from the latest <code>-beta</code> pre-release.</p>
```

- [ ] **Step 4: Verify sentinel + HTML**

Run: `python3 -c "import json; assert json.load(open('manifest.json'))['version']=='0.0.0-dev'; print('manifest ok')"`
Expected: PASS `manifest ok`.
Run: `grep -c "beta" index.html`
Expected: PASS (output `>=1`).

- [ ] **Step 5: Commit**

```bash
git add manifest.json index.html
git commit -m "chore: dev manifest sentinel + beta flasher link"
```

### Task 3: Release-workflow enforcement skill

**Files:**
- Create: `.opencode/skills/release-workflow/SKILL.md`
- Test: `test -f .opencode/skills/release-workflow/SKILL.md && grep -c "beta" .opencode/skills/release-workflow/SKILL.md`

**Interfaces:**
- Consumes: spec `docs/superpowers/specs/2026-09-22-versioning-ota-design.md` (tag regex, channel table).
- Produces: auto-loaded gate future agents must follow before tagging.

- [ ] **Step 1: Prove skill missing (failing test)**

Run: `test -f .opencode/skills/release-workflow/SKILL.md`
Expected: FAIL (exit 1).

- [ ] **Step 2: Create the skill file**

Write `.opencode/skills/release-workflow/SKILL.md` with exactly:
```markdown
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
```

- [ ] **Step 3: Verify skill loads**

Run: `test -f .opencode/skills/release-workflow/SKILL.md && grep -c "vX.Y.Z-beta" .opencode/skills/release-workflow/SKILL.md`
Expected: PASS (count `>=2`).

- [ ] **Step 4: Commit**

```bash
git add .opencode/skills/release-workflow/SKILL.md docs/superpowers/plans/2026-09-22-versioning-ota.md
git commit -m "chore: add release-workflow enforcement skill"
```

### Task 4: Manual GitHub settings + dry-run verify

**Files:**
- Modify: none (UI-only). Record result in PR/tag message.
- Test: `gh api repos/{owner}/{repo} --jq .default_branch` returns `main` (replace owner/repo).

**Interfaces:**
- Consumes: Tasks 1-3 merged to `main`.
- Produces: protected `main`, protected `v*` tags, Pages via Actions.

- [ ] **Step 1: Set branch protection (solo mode)**

GitHub → Settings → Branches → Add rule for `main`: check `Require status checks` (`host-tests`, `compile`), `Block force pushes`, `Block deletions`. Leave `Require pull request` OFF until collaborators join.

- [ ] **Step 2: Set tag protection + Pages**

Settings → Tags → Add `v*` (limit tag creators to you). Settings → Pages → Source `GitHub Actions`.

- [ ] **Step 3: Dry-run a beta tag on a fork or test tag then delete**

Run: `git tag v0.0.0-beta.0 && git push origin v0.0.0-beta.0`
Expected: Actions `release` shows `prerelease:true`, `pages` writes `public/beta/` with manifest `0.0.0-beta.0`. Then run: `git push --delete origin v0.0.0-beta.0 && git tag -d v0.0.0-beta.0 && gh release delete v0.0.0-beta.0 --yes || true`
Expected: cleanup done.

- [ ] **Step 4: Commit (docs only if settings noted)**

```bash
git status --short
```
Expected: clean (no code change; settings are UI-side).
```

## Self-Review

1. Spec coverage: branching/versioning → Task 3 skill; channels → Task 1 CI + Task 2 manifest/index; build/release → Task 1; enforcement/GitHub settings → Task 3 + Task 4; testing → each task Step 4 + Task 4 dry-run. No gaps.
2. Placeholder scan: no TBD/TODO, all steps show exact code/commands, no "similar to Task N".
3. Type consistency: `TAG/VERSION/DEST` env names match across Task 1 steps; `0.0.0-dev` sentinel matches Task 2 test + Task 3 rule; tag regex identical in plan header, Task 3, spec.
