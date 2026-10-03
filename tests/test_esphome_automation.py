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


def test_dependabot_covers_esphome_pin_and_actions():
    cfg = _read(".github", "dependabot.yml")
    assert "version: 2" in cfg
    assert "package-ecosystem: pip" in cfg
    assert "package-ecosystem: github-actions" in cfg
    assert cfg.count("interval: weekly") == 2


def test_beta_on_bump_workflow_contract():
    yml = _read(".github", "workflows", "beta-on-bump.yml")
    assert "branches: [main]" in yml and "paths: [requirements.txt]" in yml
    assert "contents: write" in yml and "actions: write" in yml
    assert "fetch-depth: 0" in yml
    assert 'python-version: "3.12"' in yml
    assert "pip install pytest -r requirements.txt" in yml
    assert "scripts/release.sh beta auto" in yml
    assert 'gh workflow run build.yml --ref "$TAG"' in yml

