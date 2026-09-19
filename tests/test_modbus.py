# tests/test_modbus.py — TDD reference vectors for the Modbus-RTU master.
# Wire rule: full 1-based register number -> wire address = reg - 1
# (e.g. holding 40004 -> wire 0x9C43). CRC is standard Modbus CRC-16
# (poly 0xA001, init 0xFFFF); canonical pair 01 03 00 00 00 01 -> 0x0A84.
from components.heatwhisper.modbus_rtu import (
    crc16, build_read, build_write_single, build_write_multi,
    parse_read_response, decode_be)


def test_crc16_known_vector():
    # Canonical pair: FC03 slave 1, wire 0x0000, 1 reg.
    assert crc16(bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x01])) == 0x0A84
    # FC03 read holding reg 40004 (wire 0x9C43), 1 reg, slave 1.
    assert crc16(bytes([0x01, 0x03, 0x9C, 0x43, 0x00, 0x01])) == 0x8E5B


def test_build_read_holding():
    f = build_read(1, 3, 40004, 1)
    assert f == bytes([0x01, 0x03, 0x9C, 0x43, 0x00, 0x01, 0x5B, 0x8E])


def test_write_multi_single_register():
    # MODBUS40 path: one R/W register via FC16, value 0x00D2
    f = build_write_multi(1, 43005, [0x00D2])
    assert f[:4] == bytes([0x01, 0x10, 0xA7, 0xFC]) and f[4:6] == bytes([0x00, 0x01])
    assert len(f) == 11  # addr+fc+reg(2)+count(2)+bytes(1)+data(2)+crc(2)


def test_parse_read_response():
    f = bytes([0x01, 0x03, 0x02, 0x00, 0xD2, 0x38, 0x19])
    assert parse_read_response(f, 3, 1) == [0x00D2]


def test_decode_be_scales_and_sign():
    assert decode_be([0x00D2], "s16", 10, "ABCD") == 21.0
    assert decode_be([0xFF38], "s16", 10, "ABCD") == -20.0
    assert decode_be([0x0001, 0x0000], "u32", 1, "ABCD") == 65536.0
    assert decode_be([0x0000, 0x0001], "u32", 1, "CDAB") == 65536.0
