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
OLD_ENTITY_REGS = (40004, 40008, 40012, 40013, 40014, 43009, 43136, 43005,
                 40033, 43144, 43305, 47011, 47007, 47041, 47371, 47370, 47387, 47043)

def _base_text():
    return open(os.path.join(os.path.dirname(__file__), "..", "packages", "base.yaml")).read()

def _base_names_table():
    # NIBE_BASE_NAMES is the post-base.yaml name authority; extract addr->name.
    import re
    cpp = open(os.path.join(os.path.dirname(__file__), "..", "components", "nibe", "nibe.cpp")).read()
    block = cpp.split("NIBE_BASE_NAMES[] = {", 1)[1].split("};", 1)[0]
    return {int(a): n for a, n in re.findall(r"\{(\d+),\s*\"([^\"]+)\"\}", block)}

def test_base_yaml_has_no_static_entities():
    # Picker contract: per-register sensor/number/switch blocks live in
    # flash now; base.yaml keeps only infra + the model text_sensor.
    base = _base_text()
    assert "platform: nibe" not in base
    assert "set_register_enabled(" not in base
    assert "on_boot" not in base
    assert "RESTORE_DEFAULT_ON" not in base
    assert "Heat Pump Model" in base
    assert "picked at runtime" in base

def test_factory_covers_old_entity_set():
    # Factory defaults must cover exactly the old static entity set, with
    # the old base.yaml names, so HA entity ids carry over.
    from components.nibe.registers import DEFAULT_ENABLED
    table = _base_names_table()
    assert sorted(table) == sorted(OLD_ENTITY_REGS)
    assert sorted(table) == sorted(DEFAULT_ENABLED)
    assert len(set(table.values())) == len(table)
