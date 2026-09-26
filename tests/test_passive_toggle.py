# tests/test_passive_toggle.py — passive toggle in picker UI (no recompile).
import os

REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")
HDR = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")
PICKER = os.path.join(REPO, "components", "heatwhisper", "picker.h")


def _read(p):
    with open(p) as fh:
        return fh.read()


def test_passive_persisted_in_flash():
    src = _read(HDR)
    assert "HeatWhisperPassive" in src
    assert "load_passive" in src and "save_passive" in src


def test_setup_applies_runtime_passive_before_entities():
    src = _read(CPP)
    setup = src.split("void HeatWhisperComponent::setup")[1].split("void HeatWhisperComponent::tx_")[0]
    assert "apply_runtime_passive_" in setup
    assert setup.index("apply_runtime_mode_") < setup.index("apply_runtime_passive_")
    assert setup.index("apply_runtime_passive_") < setup.index("create_entities")


def test_picker_json_exposes_passive():
    src = _read(CPP)
    body = src.split("HeatWhisperPickerHandler::list_json_")[1].split("HeatWhisperPickerHandler::handle_save_")[0]
    assert '"passive"' in body or "'passive'" in body or "passive" in body


def test_mode_save_accepts_passive():
    src = _read(CPP)
    body = src.split("HeatWhisperPickerHandler::handle_mode_save_")[1].split("#endif")[0]
    assert "passive" in body
    assert "400" in body


def test_picker_ui_has_passive_checkbox():
    src = _read(CPP)
    assert "psv" in src and "passive" in src.lower()
