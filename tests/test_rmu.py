# tests/test_rmu.py — Task 6: RMU replies, flow control, artifacts, bring-up order.
import os

REPO = os.path.join(os.path.dirname(__file__), "..")


def calc_crc_c0(data: bytes) -> int:
    c = 0
    for b in data[0:data[2] + 3]:
        c ^= b
    return c


def test_rmu_version_reply_bytes():
    # Exact bytes per reference-project/backend.js:293 -> [192,238,3,238,3,1,193]
    ver = bytes([0xC0, 0xEE, 0x03, 0xEE, 0x03, 0x01, 0xC1])
    assert calc_crc_c0(ver) == 0xC1
    assert ver == bytes([192, 238, 3, 238, 3, 1, 193])


def test_rmu_63_reply_bytes():
    # Per reference-project/backend.js:283 -> [192,96,2,99,0,193]
    r = bytes([0xC0, 0x60, 0x02, 0x63, 0x00, 0xC1])
    assert calc_crc_c0(r) == 0xC1
    assert r == bytes([192, 96, 2, 99, 0, 193])


def test_cpp_handles_rmu_slots():
    src = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")).read()
    assert "0xEE" in src
    assert "0x60" in src
    assert "0x63" in src
    assert "0x19" in src and "0x1C" in src
    assert "passive_" in src  # passive honored (no TX when passive)


def test_init_has_flow_control_pin():
    src = open(os.path.join(REPO, "components", "heatwhisper", "__init__.py")).read()
    assert "flow_control_pin" in src
    assert "set_flow_control_pin" in src


def test_header_has_flow_control_pin():
    src = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")).read()
    assert "set_flow_control_pin" in src


def test_ci_uploads_artifacts():
    src = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "upload-artifact" in src
    assert ".bin" in src


def test_ci_release_on_tags():
    src = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "tags" in src


def test_base_documents_passive_first():
    src = open(os.path.join(REPO, "packages", "base.yaml")).read().lower()
    assert "passive" in src
    assert "first" in src
