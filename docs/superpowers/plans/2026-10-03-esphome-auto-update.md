# Automated ESPHome Updates → Beta Releases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dependabot opens a PR when a new stable ESPHome is released; merging it automatically builds and publishes a beta.

**Architecture:** ESPHome is pinned in `requirements.txt` and installed from there by CI. Dependabot (`pip` + `github-actions`, weekly) opens bump PRs that run the normal PR CI. A new `beta-on-bump.yml` runs on pushes to `main` that touch `requirements.txt`: it runs `scripts/release.sh beta auto` (new mode picking the correct beta base) and dispatches `build.yml` on the new tag (tag pushes made with `GITHUB_TOKEN` don't trigger workflows), which publishes through the existing `release`/`pages` jobs.

**Tech Stack:** GitHub Actions, Dependabot, bash (`scripts/release.sh`), pytest (source-level string asserts + isolated temp git repos).

**Spec:** [docs/superpowers/specs/2026-10-03-esphome-auto-update-design.md](../specs/2026-10-03-esphome-auto-update-design.md)

## Global Constraints

- ESPHome version lives only in `requirements.txt` as a single line `esphome==X.Y.Z` (no other packages; `pytest` stays installed separately).
- `build.yml` triggers: `push`, `pull_request`, `workflow_dispatch`. No other job logic changes; the `release`/`pages` guards (`startsWith(github.ref, 'refs/tags/v')`, `-beta` channel detection) stay untouched.
- `beta-on-bump.yml` triggers on `push` to `main` with `paths: [requirements.txt]`; permissions `contents: write` and `actions: write`; Python 3.12 (ESPHome requires `>=3.12`).
- `release.sh`: existing `stable ...` and `beta [X.Y.Z]` behaviour and validation unchanged; `DRY_RUN=1` prints only the tag; normal mode's last line is `released <tag>`.
- Tag regexes: stable `^v[0-9]+\.[0-9]+\.[0-9]+$`, beta `^v[0-9]+\.[0-9]+\.[0-9]+-beta\.[0-9]+$`.
- `beta auto` base: highest `vX.Y.Z` base across all stable and beta tags (`sort -V`); if that stable tag doesn't exist (series in progress) use it, else next patch; no tags → `v0.1.0`.
- Existing tests that read `build.yml` (`test_fw_version.py`, `test_final_fixes.py`, `test_ota_manifest.py`) must keep passing. Baseline: 144 tests pass.
- Do not push tags or branches as part of this plan; the maintainer decides when to push/merge.

> **Heads-up for the maintainer:** once this work is merged to `main`, adding `requirements.txt` itself matches the `paths` filter, so that first merge cuts a beta (expected: `v0.2.1-beta.1`) and doubles as the end-to-end verification.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/release.sh` | Modify | Add `beta auto` mode + `auto_base` helper |
| `tests/test_release_beta_auto.py` | Create | Isolated temp-git-repo tests for `beta auto` |
| `.opencode/skills/release-workflow/SKILL.md` | Modify | Document `beta auto` and the automation |
| `requirements.txt` | Create | Pinned ESPHome |
| `.github/workflows/build.yml` | Modify | Install from `requirements.txt`; add `workflow_dispatch` |
| `.github/dependabot.yml` | Create | Weekly `pip` + `github-actions` PRs |
| `.github/workflows/beta-on-bump.yml` | Create | Tag beta + dispatch build on bump merge |
| `tests/test_esphome_automation.py` | Create | Source-level assertions for pin, build.yml, dependabot, beta workflow |
| `README.md` | Modify | Dev install from `requirements.txt`; explain automation |

---

### Task 1: `release.sh beta auto`

**Files:**
- Modify: `scripts/release.sh:2` (usage comment), `scripts/release.sh:11-12` (add helper), `scripts/release.sh:23-28` (beta branch), `scripts/release.sh:32` (usage string)
- Create: `tests/test_release_beta_auto.py`
- Modify: `.opencode/skills/release-workflow/SKILL.md` (Pre-tag checklist block)

**Interfaces:**
- Produces: CLI `scripts/release.sh beta auto` → in `DRY_RUN=1` prints the tag (e.g. `v0.2.1-beta.1`) only; in normal mode runs pytest + `esphome config`, tags, pushes, and prints `released <tag>` as the last line. Task 4 relies on that last line.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_release_beta_auto.py`:

```python
# tests/test_release_beta_auto.py — `release.sh beta auto` picks the beta base from existing tags.
import os
import subprocess

import pytest

REPO = os.path.join(os.path.dirname(__file__), "..")
SCRIPT = os.path.abspath(os.path.join(REPO, "scripts", "release.sh"))


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo_with_tags(tmp_path, tags):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "commit", "--allow-empty", "-m", "init")
    for t in tags:
        _git(tmp_path, "tag", t)


@pytest.mark.parametrize("tags,expected", [
    ([], "v0.1.0-beta.1"),                                           # no tags: existing fallback base
    (["v0.2.0"], "v0.2.1-beta.1"),                                   # latest released -> next patch
    (["v0.2.0", "v0.2.0-beta.18"], "v0.2.1-beta.1"),                 # betas of a released version don't count
    (["v0.2.0", "v0.3.0-beta.1", "v0.3.0-beta.2"], "v0.3.0-beta.3"), # open series continues
    (["v0.2.0", "v0.2.1-beta.1"], "v0.2.1-beta.2"),                  # open patch series continues
    (["v0.9.0", "v0.10.0-beta.1"], "v0.10.0-beta.2"),                # version sort, not lexical
])
def test_beta_auto_resolves_base(tmp_path, tags, expected):
    _repo_with_tags(tmp_path, tags)
    res = subprocess.run([SCRIPT, "beta", "auto"], cwd=tmp_path,
                         env={**os.environ, "DRY_RUN": "1"}, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == expected


def test_release_skill_documents_beta_auto():
    skill = open(os.path.join(REPO, ".opencode", "skills", "release-workflow", "SKILL.md")).read()
    assert "scripts/release.sh beta auto" in skill
    assert "requirements.txt" in skill
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_release_beta_auto.py -v`
Expected: all 7 FAIL (`beta auto` currently builds the invalid tag `vauto-beta.1` and exits 1; the skill assertions fail).

- [ ] **Step 3: Implement `beta auto` in `scripts/release.sh`**

Change line 2 to:

```bash
# Usage: scripts/release.sh stable patch|minor|major|X.Y.Z | scripts/release.sh beta [X.Y.Z|auto]
```

Insert directly after the closing `}` of `next_stable()` (after current line 11):

```bash
# Highest version base across stable + beta tags. Continue it while its stable tag
# doesn't exist (beta series in progress); otherwise start the next patch.
auto_base() {
  local top
  top=$(git tag --list | grep -E "$STABLE_RE|$BETA_RE" | sed -E 's/-beta\.[0-9]+$//' | sort -V | uniq | tail -1 || true)
  if [ -z "$top" ]; then echo v0.1.0
  elif git rev-parse -q --verify "refs/tags/$top" >/dev/null; then next_stable "$top" patch
  else echo "$top"
  fi
}
```

Replace the beta branch's inner `if` (current lines 24-28):

```bash
  if [ "$ARG" = auto ]; then
    BASE=$(auto_base)
  elif [ -n "$ARG" ]; then
    BASE="v$ARG"; BASE=${BASE%-beta*}
  else
    LATEST=$(latest_stable || true); BASE=${LATEST:-v0.1.0}
  fi
```

Change the usage string (current line 32) to:

```bash
else echo "usage: $0 stable patch|minor|major|X.Y.Z | $0 beta [X.Y.Z|auto]"; exit 1; fi
```

- [ ] **Step 4: Update the release skill**

In `.opencode/skills/release-workflow/SKILL.md`, replace the code block under "Never hand-tag. Only entry point:" and the sentence after it with:

````markdown
```bash
scripts/release.sh stable patch|minor|major|X.Y.Z
scripts/release.sh beta [X.Y.Z|auto]
```

The script validates semver, runs `pytest` + all three `esphome config`, then tags + pushes. CI does the rest.

`beta auto` continues an in-progress beta series, otherwise starts the next patch beta. It is what `.github/workflows/beta-on-bump.yml` runs automatically after a Dependabot ESPHome bump (pinned in `requirements.txt`) is merged to `main`. Promotion to stable stays manual.
````

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_release_beta_auto.py tests/test_ota_manifest.py -v`
Expected: all PASS (new 7 plus the existing release-script/skill tests, which must be unaffected).

- [ ] **Step 6: Commit**

```bash
git add scripts/release.sh tests/test_release_beta_auto.py .opencode/skills/release-workflow/SKILL.md
git commit -m "feat(release): add 'beta auto' mode choosing the beta base from existing tags"
```

---

### Task 2: Pin ESPHome and make `build.yml` dispatchable

**Files:**
- Create: `requirements.txt`, `tests/test_esphome_automation.py`
- Modify: `.github/workflows/build.yml:2` (triggers), `.github/workflows/build.yml:20` (install step)
- Modify: `README.md:153-164`

**Interfaces:**
- Produces: `requirements.txt` containing `esphome==2026.9.1`; `build.yml` with `workflow_dispatch` (Task 4 dispatches it with `--ref <tag>`) and `pip install -r requirements.txt` (Task 4 reuses the same install).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_esphome_automation.py`:

```python
# tests/test_esphome_automation.py — source-level contract for the ESPHome auto-update pipeline
# (see docs/superpowers/specs/2026-10-03-esphome-auto-update-design.md).
import os
import re

REPO = os.path.join(os.path.dirname(__file__), "..")


def _read(*parts):
    return open(os.path.join(REPO, *parts)).read()


def test_requirements_pins_only_esphome_exactly():
    lines = [l.strip() for l in _read("requirements.txt").splitlines() if l.strip() and not l.startswith("#")]
    assert len(lines) == 1
    assert re.fullmatch(r"esphome==\d{4}\.\d+\.\d+", lines[0]), lines[0]


def test_build_yml_installs_pinned_esphome():
    yml = _read(".github", "workflows", "build.yml")
    assert "pip install -r requirements.txt" in yml
    assert "pip install esphome" not in yml


def test_build_yml_is_dispatchable():
    assert "workflow_dispatch" in _read(".github", "workflows", "build.yml")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_esphome_automation.py -v`
Expected: 3 FAIL (`requirements.txt` missing → FileNotFoundError; build.yml assertions fail).

- [ ] **Step 3: Create `requirements.txt`**

Exact content (one line, trailing newline):

```
esphome==2026.9.1
```

(2026.9.1 is the current PyPI release, i.e. what CI's unpinned install resolves to today, so pinning changes nothing yet and no Dependabot PR is opened immediately.)

- [ ] **Step 4: Edit `.github/workflows/build.yml`**

Replace line 2 `on: [push, pull_request]` with:

```yaml
on:
  push:
  pull_request:
  workflow_dispatch:
```

Replace `      - run: pip install esphome` (in the `compile` job) with:

```yaml
      - run: pip install -r requirements.txt
```

- [ ] **Step 5: Update the README dev notes**

In `README.md`, replace the block at lines 153-164 (from `## Build / test / release` through the `CI (...)` paragraph) with:

````markdown
## Build / test / release

```bash
pip install -r requirements.txt   # pinned ESPHome (same version CI uses)
python -m pytest tests/ -v
esphome config heatwhisper_esp32.yaml
esphome config heatwhisper_esp32_s3_rs485.yaml
esphome compile heatwhisper_esp32.yaml
esphome compile heatwhisper_esp32_s3_rs485.yaml
esphome compile heatwhisper_pico_w.yaml
```

CI (`.github/workflows/build.yml`): pytest → `esphome config` + `compile` all three boards → artifacts on tags attached to the GitHub release + deployed to GitHub Pages (web flasher).
````

(Task 4 adds the automation paragraph after this.)

- [ ] **Step 6: Run the full test suite**

Run: `python3 -m pytest tests -q`
Expected: all PASS (144 baseline + 7 from Task 1 + 3 new = 154).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .github/workflows/build.yml tests/test_esphome_automation.py README.md
git commit -m "build: pin ESPHome in requirements.txt and allow manual build dispatch"
```

---

### Task 3: Dependabot configuration

**Files:**
- Create: `.github/dependabot.yml`
- Modify: `tests/test_esphome_automation.py` (append)

**Interfaces:**
- Consumes: `requirements.txt` at repo root (Task 2) — Dependabot's `pip` ecosystem reads the `esphome==` pin.
- Produces: weekly PRs; merged bump PRs change `requirements.txt`, which Task 4's workflow listens for. `github-actions` PRs don't touch `requirements.txt` and so never publish a beta.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_esphome_automation.py`:

```python
def test_dependabot_covers_esphome_pin_and_actions():
    cfg = _read(".github", "dependabot.yml")
    assert "version: 2" in cfg
    assert "package-ecosystem: pip" in cfg
    assert "package-ecosystem: github-actions" in cfg
    assert cfg.count("interval: weekly") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_esphome_automation.py::test_dependabot_covers_esphome_pin_and_actions -v`
Expected: FAIL (FileNotFoundError).

- [ ] **Step 3: Create `.github/dependabot.yml`**

```yaml
# Weekly update PRs. The pip entry keeps the pinned ESPHome (requirements.txt) current;
# merging it triggers .github/workflows/beta-on-bump.yml. The github-actions entry keeps
# the actions used by CI from going stale (it never touches requirements.txt).
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    commit-message:
      prefix: "chore(deps)"
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    commit-message:
      prefix: "chore(ci)"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_esphome_automation.py -v && python3 -c "import yaml; yaml.safe_load(open('.github/dependabot.yml'))"`
Expected: PASS, and the YAML loads without error.

- [ ] **Step 5: Commit**

```bash
git add .github/dependabot.yml tests/test_esphome_automation.py
git commit -m "ci: add Dependabot for the ESPHome pin and GitHub Actions"
```

---

### Task 4: Beta on bump workflow and docs

**Files:**
- Create: `.github/workflows/beta-on-bump.yml`
- Modify: `tests/test_esphome_automation.py` (append), `README.md` (after the `CI (...)` paragraph in `## Build / test / release`)

**Interfaces:**
- Consumes: `scripts/release.sh beta auto` and its final `released <tag>` line (Task 1); `requirements.txt` + `pip install -r requirements.txt` (Task 2); `build.yml` `workflow_dispatch` (Task 2).
- Produces: on every push to `main` touching `requirements.txt`: a pushed beta tag and a dispatched `build.yml` run on that tag.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_esphome_automation.py`:

```python
def test_beta_on_bump_workflow_contract():
    yml = _read(".github", "workflows", "beta-on-bump.yml")
    assert "branches: [main]" in yml and "paths: [requirements.txt]" in yml
    assert "contents: write" in yml and "actions: write" in yml
    assert "fetch-depth: 0" in yml
    assert 'python-version: "3.12"' in yml
    assert "pip install pytest -r requirements.txt" in yml
    assert "scripts/release.sh beta auto" in yml
    assert 'gh workflow run build.yml --ref "$TAG"' in yml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_esphome_automation.py::test_beta_on_bump_workflow_contract -v`
Expected: FAIL (FileNotFoundError).

- [ ] **Step 3: Create `.github/workflows/beta-on-bump.yml`**

```yaml
name: beta-on-bump
# After an ESPHome pin bump (usually a merged Dependabot PR) lands on main, tag and publish a beta.
# Design: docs/superpowers/specs/2026-10-03-esphome-auto-update-design.md
on:
  push:
    branches: [main]
    paths: [requirements.txt]
concurrency:
  group: beta-on-bump
  cancel-in-progress: false
permissions:
  contents: write   # push the beta tag
  actions: write    # dispatch build.yml
jobs:
  beta:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }  # release.sh resolves the beta base from all tags
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }  # ESPHome requires >=3.12
      - run: pip install pytest -r requirements.txt  # release.sh runs pytest + esphome config
      - run: cp secrets.yaml.example secrets.yaml || true
      - id: tag
        shell: bash
        run: |
          scripts/release.sh beta auto | tee "$RUNNER_TEMP/release.log"
          TAG=$(sed -n 's/^released //p' "$RUNNER_TEMP/release.log" | tail -1)
          [ -n "$TAG" ] || { echo "no tag reported by release.sh"; exit 1; }
          echo "tag=$TAG" >> "$GITHUB_OUTPUT"
      # Tags pushed with GITHUB_TOKEN don't start workflow runs, so dispatch the build explicitly.
      # With --ref <tag>, GITHUB_REF is the tag and build.yml's release/pages jobs + beta channel apply.
      - run: gh workflow run build.yml --ref "$TAG"
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ steps.tag.outputs.tag }}
```

- [ ] **Step 4: Document the automation in the README**

In `README.md`, directly after the `CI (...)` paragraph in `## Build / test / release`, add:

```markdown
**Staying current with ESPHome:** the ESPHome version is pinned in `requirements.txt`. Dependabot opens a weekly PR when a new stable ESPHome is out (plus PRs for GitHub Actions updates); PR CI runs the tests and compiles all boards. Merging an ESPHome bump to `main` automatically tags and publishes a **beta** (`.github/workflows/beta-on-bump.yml` → `scripts/release.sh beta auto`). Promote to stable manually with `scripts/release.sh stable patch|minor|major`.
```

- [ ] **Step 5: Run the full verification**

Run each and confirm:

```bash
python3 -m pytest tests -q
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ('.github/workflows/build.yml', '.github/workflows/beta-on-bump.yml', '.github/dependabot.yml')]; print('yaml ok')"
esphome config heatwhisper_esp32.yaml >/dev/null && esphome config heatwhisper_esp32_s3_rs485.yaml >/dev/null && esphome config heatwhisper_pico_w.yaml >/dev/null && echo "esphome config ok"
git status --short
```

Expected: 156 tests PASS (144 baseline + 12 new: 7 in `test_release_beta_auto.py`, 5 in `test_esphome_automation.py`), `yaml ok`, `esphome config ok`, and a clean tree after committing.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/beta-on-bump.yml tests/test_esphome_automation.py README.md
git commit -m "ci: publish a beta automatically when an ESPHome bump lands on main"
```

---

## Self-Review

**Spec coverage:** pinning in `requirements.txt` + `build.yml` install + `workflow_dispatch` → Task 2. Dependabot `pip` + `github-actions` weekly, no grouping → Task 3. `beta-on-bump.yml` (trigger, permissions, concurrency, fetch-depth, setup-python, install, `release.sh`, tag capture, dispatch) → Task 4. `release.sh beta auto` with four required cases plus extras → Task 1. README developer notes and skill update → Tasks 1, 2, 4. Source-level tests including the existing-`build.yml` tests staying green → Tasks 2 and 4 (full suite runs). Error handling is inherent in the workflows (no extra code needed). Manual setup (branch protection required checks, Actions write permission) is outside the repo; it is reported to the maintainer at handoff rather than implemented.

**Placeholder scan:** none; every code step contains full content. The one count hedge in Task 4 Step 5 is explicit: all tests must pass, new tests = 12.

**Type/name consistency:** `auto_base` (Task 1) is used only inside `release.sh`; `released <tag>` output (Task 1) is parsed by `sed 's/^released //p'` (Task 4); `build.yml` `workflow_dispatch` (Task 2) is what `gh workflow run build.yml --ref "$TAG"` (Task 4) needs; test string `pip install pytest -r requirements.txt` matches the workflow line exactly.
