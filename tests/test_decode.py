# tests/test_decode.py — host mirrors of HeatWhisperComponent::calc_crc_nibe / calc_crc_c0_nibe.
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
    # contract for HeatWhisperComponent::set_poll_registers: C0 69 02 lo hi CRC
    assert poll_frame_40004() == bytes([0xC0, 0x69, 0x02, 0x44, 0x9C, 0x73])
    assert calc_crc_c0(poll_frame_40004()) == poll_frame_40004()[5]


# 0x6D announcement vectors: [5C, 00, ADDR, 6D, LEN, 00, 01, 02, model bytes, CHK]
ANNOUNCE_VVM500 = bytes([0x5C, 0x00, 0x20, 0x6D, 0x0A, 0x00, 0x01, 0x02,
                         0x56, 0x56, 0x4D, 0x20, 0x35, 0x30, 0x30, 0x1C])
ANNOUNCE_F750 = bytes([0x5C, 0x00, 0x20, 0x6D, 0x08, 0x00, 0x01, 0x02,
                       0x46, 0x37, 0x35, 0x30, 0x20, 0x12])

def parse_model_6d(frame: bytes) -> str:
    # mirror of HeatWhisperComponent::on_frame_ 0x6D branch: model bytes at f[8..n-2]
    raw = frame[8:len(frame) - 1].decode("ascii")
    sp = raw.find(" ")
    if sp != -1:
        first = raw[:sp]
        if first in ("VVM", "SMO", "Tehowatti", "STAR"):
            second = raw[sp + 1:].split(" ")[0]
            raw = first + second if second else first
        else:
            raw = first
    for sep in ("-", ","):
        i = raw.find(sep)
        if i != -1:
            raw = raw[:i]
    return raw

def test_announce_model_names():
    assert calc_crc(ANNOUNCE_VVM500) == ANNOUNCE_VVM500[-1]
    assert calc_crc(ANNOUNCE_F750) == ANNOUNCE_F750[-1]
    assert parse_model_6d(ANNOUNCE_VVM500) == "VVM500"
    assert parse_model_6d(ANNOUNCE_F750) == "F750"
