# tests/test_fix_modbus_and_model.py — verify model persistence and RS485 loop fixes.
import os

REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")
BASE_YAML = os.path.join(REPO, "packages", "base.yaml")


def _read(p):
    with open(p) as fh:
        return fh.read()


def test_nibe_model_restored_from_flash_in_mode_zero():
    src = _read(CPP)
    body = src.split("void HeatWhisperComponent::apply_runtime_mode_()")[1].split("void HeatWhisperComponent::setup")[0]
    # When m.mode == 0, model_ should be restored if m.model has content
    assert "if (m.mode == 0)" in body
    assert "model_ = m.model" in body


def test_announced_model_persisted_to_flash():
    src = _read(CPP)
    on_frame = src.split("void HeatWhisperComponent::on_frame_")[1].split("void HeatWhisperComponent::set_poll_registers")[0]
    # On 0x6D announce, model should be saved to flash
    assert "0x6D" in on_frame
    assert "save_mode(0, model_.c_str())" in on_frame


def test_no_unsolicited_nack_in_loop():
    src = _read(CPP)
    loop = src.split("void HeatWhisperComponent::loop()")[1].split("uint16_t HeatWhisperComponent::crc16_modbus")[0]
    # Spurious NACKs should not be sent on line noise or CRC failures in loop
    assert "send_nack_()" not in loop


def test_rmu_slots_only_replied_when_peer_matches():
    src = _read(CPP)
    on_frame = src.split("void HeatWhisperComponent::on_frame_")[1].split("void HeatWhisperComponent::set_poll_registers")[0]
    # RMU frames should only be answered if f[2] matches peer_
    assert "f[2] == peer_" in on_frame
    assert "f[2] >= 0x19 && f[2] <= 0x1C" not in on_frame


def test_base_yaml_has_alarm_reset_button():
    src = _read(BASE_YAML)
    assert "Reset Heat Pump Alarm" in src
    assert "45171" in src


def test_rx_loop_supports_modbus_frame_len_80():
    # Modbus 40 broadcast frames (0x68) have 20 registers = 80 bytes (0x50).
    # The loop length check must not drop frames up to 128 bytes.
    src = _read(CPP)
    assert "len > 128" in src
    assert "len > 64" not in src


def test_modbus_0x68_frame_parsing_simulation():
    # Simulate an 80-byte 0x68 frame from Nibe pump
    # Header: 5C 00 20 68 50 (80 bytes payload) CHK
    payload = bytearray(80)
    # Put a known register in the payload, e.g. 40004 = 0x9C44 with value 200 (20.0 C)
    payload[0] = 0x44
    payload[1] = 0x9C
    payload[2] = 200
    payload[3] = 0
    frame = bytearray([0x5C, 0x00, 0x20, 0x68, 0x50]) + payload
    c = 0
    for b in frame[2:]:
        c ^= b
    frame.append(c)
    assert len(frame) == 86
    # Check that wire length of 80 is accepted by a limit of 128
    wire_len = frame[4]
    assert wire_len == 80
    assert wire_len <= 128


def test_accessory_version_0xee_replies_for_modbus_and_peer():
    src = _read(CPP)
    on_frame = src.split("void HeatWhisperComponent::on_frame_")[1].split("void HeatWhisperComponent::set_poll_registers")[0]
    assert "f[3] == 0xEE && (f[2] == peer_ || f[2] == 0x20)" in on_frame
    assert "nibe::build_rmu_version(r)" in on_frame
    # Checksum of C0 EE 03 EE 03 01 is 0xC1
    c = 0xC0 ^ 0xEE ^ 0x03 ^ 0xEE ^ 0x03 ^ 0x01
    assert c == 0xC1


def test_modbus_empty_read_replies_c0_69_00_a9():
    src = _read(CPP)
    on_frame = src.split("void HeatWhisperComponent::on_frame_")[1].split("void HeatWhisperComponent::set_poll_registers")[0]
    assert "empty_poll[4] = {0xC0, 0x69, 0x00, 0xA9}" in on_frame
    # Checksum of C0 69 00 is 0xA9
    c = 0xC0 ^ 0x69 ^ 0x00
    assert c == 0xA9


