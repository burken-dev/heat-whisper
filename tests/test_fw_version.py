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


def test_resolve_fw_version_all_unsafe_is_dev(monkeypatch):
    from components.heatwhisper import subprocess as hw_subprocess
    class R:
        stdout = '";"'
    monkeypatch.setattr(hw_subprocess, "run", lambda *a, **k: R())
    from components.heatwhisper import resolve_fw_version
    assert resolve_fw_version() == "dev"


def test_codegen_bakes_fw_define():
    src = open(os.path.join(REPO, "components", "heatwhisper", "__init__.py")).read()
    assert '"git", "describe"' in src  # ponytail: argv-list form, no shell (brief said "git describe"; list form never contains that substring)
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
