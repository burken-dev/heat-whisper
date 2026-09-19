# tests/test_subscription.py
import os
REPO = os.path.join(os.path.dirname(__file__), "..")
HDR = open(os.path.join(REPO, "components", "nibe", "nibe.h")).read()

def test_enabled_set_api_present():
    assert "set_register_enabled" in HDR
    assert "is_enabled" in HDR
    assert "disabled_" in HDR

def test_ensure_polled_present():
    assert "ensure_polled" in HDR
import os
REPO2 = os.path.join(os.path.dirname(__file__), "..")
CPP = open(os.path.join(REPO2, "components", "nibe", "nibe.cpp")).read()

def _poll_frame(addr):
    lo, hi = addr & 0xFF, addr >> 8
    c = 0xC0 ^ 0x69 ^ 0x02 ^ lo ^ hi
    return bytes([0xC0, 0x69, 0x02, lo, hi, c])

def _rotate(queue, disabled):
    # mirror of the C++ 0x69 handler: rotate past disabled, max one full lap
    for _ in range(len(queue)):
        front_addr = queue[0][3] | (queue[0][4] << 8)
        if front_addr in disabled:
            queue.append(queue.pop(0))
            continue
        return queue.pop(0)
    return None  # all disabled -> ACK

def test_rotate_skips_disabled():
    q = [_poll_frame(40004), _poll_frame(40008), _poll_frame(40012)]
    assert _rotate(q, {40004}) == _poll_frame(40008)

def test_all_disabled_acks():
    q = [_poll_frame(40004)]
    assert _rotate(q, {40004}) is None

def test_cpp_gates_present():
    assert "is_enabled" in CPP
    assert "ensure_polled" in CPP

def test_number_control_still_queues_when_disabled():
    # spec §4: explicit user write is honored even if readbacks are suppressed;
    # control() must NOT consult the disabled set.
    body = CPP.split("NibeNumber::control")[1].split("}  // namespace")[0]
    assert "queue_write" in body
    assert "disabled_" not in body and "is_enabled" not in body
import os
def test_base_yaml_switches_match_entities():
    import re
    base = open(os.path.join(os.path.dirname(__file__), "..", "packages", "base.yaml")).read()
    assert "extra_poll" not in base or "registers:" not in base.split("extra_poll")[0].split("nibe:")[-1]
    assert "registers:" not in base  # manual poll list gone
    for reg in (40004, 40008, 40012, 40013, 40014, 43009, 43136, 43005,
                40033, 43144, 43305, 47011, 47007, 47041, 47371, 47370, 47387, 47043):
        assert f"set_register_enabled({reg}," in base
        assert "RESTORE_DEFAULT_ON" in base

def test_on_boot_reasserts_toggles():
    base = open(os.path.join(os.path.dirname(__file__), "..", "packages", "base.yaml")).read()
    assert "on_boot" in base
    boot = base.split("on_boot", 1)[1]
    for reg in (40004, 40008, 40012, 40013, 40014, 43009, 43136, 43005,
                40033, 43144, 43305, 47011, 47007, 47041, 47371, 47370, 47387, 47043):
        assert f"set_register_enabled({reg}, id(en_{reg}).state)" in boot

def test_smart_sensors_wired():
    base = open("packages/base.yaml").read()
    for reg in (40033, 43144, 43305):
        assert f"register: {reg}" in base
        assert f"set_register_enabled({reg}," in base
        assert f"id(en_{reg}).state" in base

def test_smart_numbers_wired():
    base = open("packages/base.yaml").read()
    for reg in (47011, 47007, 47041, 47371, 47370, 47387, 47043):
        assert f"register: {reg}" in base
        assert f"set_register_enabled({reg}," in base
        assert f"id(en_{reg}).state" in base
