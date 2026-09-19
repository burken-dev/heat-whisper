# tests/test_subscription.py
import os
REPO = os.path.join(os.path.dirname(__file__), "..")
HDR = open(os.path.join(REPO, "components", "nibe", "nibe.h")).read()

def test_disabled_path_removed():
    assert "set_register_enabled" not in HDR
    assert "is_enabled" not in HDR
    assert "disabled_" not in HDR

def test_ensure_polled_present():
    assert "ensure_polled" in HDR
REPO2 = os.path.join(os.path.dirname(__file__), "..")
CPP = open(os.path.join(REPO2, "components", "nibe", "nibe.cpp")).read()

def test_cpp_gates_present():
    assert "is_enabled" not in CPP
    assert "disabled_" not in CPP
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
    # ponytail: hardcoded snapshot of the 18 factory names; catches silent renames.
    EXPECTED_BASE_NAMES = ["BT1 Outdoor", "Supply Temp S1", "Return Temp",
        "Hot Water Top BT7", "Hot Water BT6", "Calculated Supply",
        "Compressor Frequency", "Room Temp S1", "Compressor Energy Total",
        "Compressor Energy HW", "Degree Minutes", "Heat Offset S1",
        "Heat Curve S1", "Hot Water Comfort Mode", "Allow Heating",
        "Allow Additive Heating", "Hot Water Production", "Hot Water Luxury Start Temp"]
    assert sorted(table.values()) == sorted(EXPECTED_BASE_NAMES)
