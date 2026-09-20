# tests/test_runtime_modbus.py — runtime Modbus select + detect (no recompile).
# Contract: YAML stays default nibe; picker saves {mode, model} to flash,
# reboot applies it; UI emphasizes Modbus only while no NIBE model heard.
import os

REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")
HDR = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")
PICKER = os.path.join(REPO, "components", "heatwhisper", "picker.h")


def _read(p):
    with open(p) as fh:
        return fh.read()


def test_mode_persisted_in_flash():
    src = _read(HDR)
    assert "HeatWhisperMode" in src
    assert "load_mode" in src and "save_mode" in src


def test_setup_applies_runtime_mode_before_entities():
    src = _read(CPP)
    setup = src.split("void HeatWhisperComponent::setup")[1].split("void HeatWhisperComponent::tx_")[0]
    assert "apply_runtime_mode_" in setup
    assert setup.index("apply_runtime_mode_") < setup.index("create_entities")


def test_runtime_model_compared_by_value_not_pointer():
    # char[24] vs const char*: == would compare pointers, always false.
    src = _read(CPP)
    body = src.split("void HeatWhisperComponent::apply_runtime_mode_")[1].split("void HeatWhisperComponent::setup")[0]
    assert "strcmp(m.model" in body


def test_picker_json_suggests_modbus_when_no_model():
    src = _read(CPP)
    body = src.split("HeatWhisperPickerHandler::list_json_")[1].split("HeatWhisperPickerHandler::handle_save_")[0]
    assert "suggest_modbus" in body
    assert "modbus_models" in body
    assert "runtime" in body


def test_picker_saves_mode_without_recompile():
    src = _read(CPP)
    assert "handle_mode_save_" in src
    assert "/heatwhisper/registers/mode" in src
    picker = _read(PICKER)
    assert "handle_mode_save_" in picker


def test_picker_ui_has_select_and_detect_with_smart_emphasis():
    src = _read(CPP)
    assert "mm" in src and "Detect" in src
    # smart emphasis: banner when suggested, collapsed <details> otherwise
    assert "<details" in src and "suggest_modbus" in src


def test_modbus_model_list_comes_from_transports():
    from components.heatwhisper.registers import load_transports
    t = load_transports(os.path.join(REPO, "components", "heatwhisper", "transports.json"))
    assert "F750" in t and "Lambda_EUL" in t
    assert t["Lambda_EUL"]["baud"] == 19200 and t["Lambda_EUL"]["parity"] == "EVEN"
