# tests/test_final_fixes.py — final-review wave (C1,C2,I1 + src guards for I2/I5/I6/I3/I4).
import os
from collections import deque

REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")).read()
HDR = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")).read()


def calc_crc(data: bytes) -> int:
    c = 0
    for b in data[2:2 + data[4] + 3]:
        c ^= b
    return c


# C1: round-robin — mirror pop-front/push-back
def test_poll_round_robin_cycles():
    assert "reads_.push(" in CPP or "reads_.push(r)" in CPP  # C++ re-queues after pop
    q = deque([b"\x01", b"\x02"])
    out = []
    for _ in range(3):
        r = q.popleft()
        q.append(r)
        out.append(r)
    assert out == [b"\x01", b"\x02", b"\x01"]
    assert list(q) == [b"\x02", b"\x01"]


# C2a: fused [06][5C...] → parses one frame
def test_fused_06_parses_one_frame():
    from tests.vectors import READ_40004
    assert "rx_[0] == 0x06" in CPP  # explicit fused-ACK drop
    rx = bytearray(b"\x06" + READ_40004)
    if len(rx) >= 2 and rx[0] == 0x06 and rx[1] == 0x5C:
        del rx[0]
    assert bytes(rx) == READ_40004
    assert calc_crc(bytes(rx)) == rx[rx[4] + 5]


# C2b: 5C 5C escape squeeze per backend.js:169-184 (verify raw, squeeze, recompute)
def test_5c_escape_squeeze():
    # unescaped payload [44,9C,5C,00] (value holds 0x5C), LEN=4
    raw_payload = bytes([0x44, 0x9C, 0x5C, 0x00])
    # wire-escaped: 5C->5C 5C, LEN=5
    wire = bytearray([0x5C, 0x00, 0x20, 0x68, 0x05, 0x44, 0x9C, 0x5C, 0x5C, 0x00, 0x00])
    chk = 0
    for b in wire[2:2 + wire[4] + 3]:
        chk ^= b
    wire[-1] = chk
    assert calc_crc(bytes(wire)) == wire[wire[4] + 5]  # raw verifies on wire
    # mirror C++ squeeze loop exactly:
    f = bytearray(wire)
    i = 5
    while i + 1 < len(f) - 1:
        if f[i] == 0x5C and f[i + 1] == 0x5C:
            del f[i]
            f[4] -= 1
            continue
        i += 1
    assert f[4] == 4
    assert bytes(f[5:-1]) == raw_payload
    c2 = 0
    for b in f[2:2 + f[4] + 3]:
        c2 ^= b
    f[-1] = c2  # recompute like reference
    assert calc_crc(bytes(f)) == f[f[4] + 5]
    assert "f[i] == 0x5C" in CPP  # squeeze loop present


# I1: 0x62 routed through same decoder as 0x68/0x6A
def test_0x62_decoded():
    line = next(l for l in CPP.splitlines() if "0x68" in l and "0x6A" in l)
    assert "0x62" in line


def test_rmu_write_guard():
    assert "addr < 20000" in HDR  # I2: RMU 1xxxx dropped from 0x6B slot


def test_write_queue_capped():
    assert "writes_.size() >= 4" in HDR  # I5


def test_rx_resync():
    assert "len > 64" in CPP and "512" in CPP  # I6


def test_ci_artifacts_explicit():
    yml = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "firmware.factory.bin" in yml and "firmware.uf2" in yml  # I3
    assert "if-no-files-found: error" in yml
    assert "**/*.bin" not in yml


def test_manifest_esp_only():
    import json
    m = json.load(open(os.path.join(REPO, "manifest.json")))
    fams = [b["chipFamily"] for b in m["builds"]]
    assert "ESP32" in fams and "RP2040" not in fams  # I4
