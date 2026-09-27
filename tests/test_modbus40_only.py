# tests/test_modbus40_only.py — NIBE bus emulates MODBUS40 (0x20) only; no RMU.
import os
REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")
HDR = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")
NIBE_H = os.path.join(REPO, "components", "heatwhisper", "nibe.h")


def _read(p):
    with open(p) as fh:
        return fh.read()


def test_no_rmu_slot_concept():
    blob = _read(CPP) + _read(HDR)
    assert "HeatWhisperPeer" not in blob
    assert "load_peer" not in blob and "save_peer" not in blob
    assert "apply_runtime_peer_" not in blob
    assert "build_rmu63" not in blob
    assert "0x60" not in blob.split("void HeatWhisperComponent::on_frame_")[1].split("void HeatWhisperComponent::set_poll_registers")[0]


def test_modbus40_address_constant_and_members():
    hdr = _read(HDR)
    assert "kModbus40Addr" in hdr
    assert "modbus_addr_" in hdr
    assert "modbus40_seen" in hdr
    assert "peer_" not in hdr


def test_no_rmu_selector_in_picker():
    src = _read(CPP)
    assert "RMU slot" not in src and "BT50" not in src
    assert 'modbus40_seen' in src
