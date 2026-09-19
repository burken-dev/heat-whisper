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
