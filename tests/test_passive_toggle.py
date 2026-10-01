# tests/test_passive_toggle.py — verify passive mode is completely removed.
import os

REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")
HDR = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")
INIT_PY = os.path.join(REPO, "components", "heatwhisper", "__init__.py")


def _read(p):
    with open(p) as fh:
        return fh.read()


def test_passive_removed_from_python_schema():
    src = _read(INIT_PY)
    assert "passive" not in src


def test_passive_removed_from_header():
    src = _read(HDR)
    assert "HeatWhisperPassive" not in src
    assert "set_passive" not in src
    assert "load_passive" not in src
    assert "save_passive" not in src
    assert "is_passive" not in src
    assert "apply_runtime_passive_" not in src
    assert "passive_" not in src


def test_passive_removed_from_cpp_runtime():
    src = _read(CPP)
    assert "apply_runtime_passive_" not in src
    assert "HW_PASSIVE_TYPE" not in src
    assert "passive_" not in src
    assert "if (passive_)" not in src
    assert "if (!passive_)" not in src


def test_picker_has_no_passive_controls():
    src = _read(CPP)
    assert "id=\"psv\"" not in src
    assert "id='psv'" not in src
    assert "listen-only" not in src
    assert '"passive":' not in src
    assert "arg(\"passive\")" not in src
    assert "arg('passive')" not in src
