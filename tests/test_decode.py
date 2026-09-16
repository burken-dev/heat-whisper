# tests/test_decode.py — host mirror of NibeComponent::calc_crc.
from tests.vectors import READ_40004, CORRUPT


def calc_crc(data: bytes) -> int:
    c = 0
    for b in data[2:2 + data[4] + 3]:
        c ^= b
    return c


def test_crc_ok():
    assert calc_crc(READ_40004) == READ_40004[7]


def test_crc_reject():
    assert calc_crc(CORRUPT) != CORRUPT[7]
