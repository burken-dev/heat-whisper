# tests/test_runtime_peer.py — runtime RMU slot select (no recompile), S2 default keeps BT50.
# Contract: factory default is RMU S2 (0x1A); picker saves peer to flash,
# reboot applies it; UI shows peer + poll status with BT50-preserving guidance.
import os

REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")
HDR = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")
INIT = os.path.join(REPO, "components", "heatwhisper", "__init__.py")


def _read(p):
    with open(p) as fh:
        return fh.read()


def test_default_peer_is_s2():
    assert "default=0x1A" in _read(INIT)
    assert "peer_{0x1A}" in _read(HDR)


def test_peer_persisted_in_flash():
    src = _read(HDR)
    assert "HeatWhisperPeer" in src
    assert "load_peer" in src and "save_peer" in src


def test_setup_applies_runtime_peer_before_entities():
    src = _read(CPP)
    setup = src.split("void HeatWhisperComponent::setup")[1].split("void HeatWhisperComponent::tx_")[0]
    assert "apply_runtime_peer_" in setup
    assert setup.index("apply_runtime_peer_") < setup.index("create_entities")


def test_picker_json_exposes_peer_and_poll_status():
    src = _read(CPP)
    body = src.split("HeatWhisperPickerHandler::list_json_")[1].split("HeatWhisperPickerHandler::handle_save_")[0]
    assert '\\"peer\\"' in body
    assert "peer_seen" in body


def test_mode_save_accepts_peer_s1_to_s4():
    src = _read(CPP)
    body = src.split("HeatWhisperPickerHandler::handle_mode_save_")[1].split("#endif")[0]
    assert "peer" in body
    assert "0x19" in body and "0x1C" in body


def test_picker_ui_has_rmu_slot_selector_with_bt50_guidance():
    src = _read(CPP)
    assert "rmu" in src.lower() and "BT50" in src
    assert "5.2" in src
