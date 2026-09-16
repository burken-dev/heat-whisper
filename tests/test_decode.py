# tests/test_decode.py — host mirrors of NibeComponent::calc_crc / calc_crc_c0.
from tests.vectors import READ_40004, CORRUPT, WRITE_EXAMPLE


def calc_crc(data: bytes) -> int:
    c = 0
    for b in data[2:2 + data[4] + 3]:
        c ^= b
    return c


def calc_crc_c0(data: bytes) -> int:
    c = 0
    for b in data[0:data[2] + 3]:
        c ^= b
    return c


def test_crc_ok():
    assert calc_crc(READ_40004) == READ_40004[7]


def test_crc_reject():
    assert calc_crc(CORRUPT) != CORRUPT[7]


def test_crc_c0_ok():
    assert calc_crc_c0(WRITE_EXAMPLE) == WRITE_EXAMPLE[9] == 0x6F


def decode_s16_lo_hi(lo, hi, factor):
    v = lo | (hi << 8)
    if v >= 32768:
        v -= 65536
    return v / factor

def test_bt1_negative():
    assert decode_s16_lo_hi(0x2E, 0xFF, 10) == -21.0  # raw -210


def poll_frame_40004():
    lo, hi = 0x44, 0x9C  # 40004 LE
    c = 0xC0 ^ 0x69 ^ 0x02 ^ lo ^ hi
    return bytes([0xC0, 0x69, 0x02, lo, hi, c])

def test_poll_frame_40004():
    # contract for NibeComponent::set_poll_registers: C0 69 02 lo hi CRC
    assert poll_frame_40004() == bytes([0xC0, 0x69, 0x02, 0x44, 0x9C, 0x73])
    assert calc_crc_c0(poll_frame_40004()) == poll_frame_40004()[5]
