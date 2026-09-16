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
