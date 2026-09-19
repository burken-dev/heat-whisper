# tests/test_fixwave.py — fix-wave regression guards (filter chain, save dedupe,
# factory RMU coercion, disabled-path removal, picker escaping, cap message).
import os

REPO = os.path.join(os.path.dirname(__file__), "..")
CPP = open(os.path.join(REPO, "components", "heatpump", "heatpump.cpp")).read()
HDR = open(os.path.join(REPO, "components", "heatpump", "heatpump.h")).read()
INIT = open(os.path.join(REPO, "components", "heatpump", "__init__.py")).read()


def test_factory_sensors_carry_stock_filters():
    # mirrors codegen for `delta: 0.1 / throttle: 60s / heartbeat: 5min`
    body = CPP.split("void HeatpumpComponent::create_entities")[1].split("void HeatpumpComponent::setup")[0]
    assert "set_filters" in body
    assert "DeltaFilter(0.1f, 0.0f, std::numeric_limits<float>::infinity(), 0.0f)" in body
    assert "ThrottleFilter(60000)" in body
    assert "HeartbeatFilter(300000)" in body
    assert 'cg.add_define("USE_SENSOR_FILTER")' in INIT


def test_save_dedupes_before_cap():
    body = CPP.split("HeatpumpPickerHandler::handle_save_")[1].split("#endif")[0]
    assert "dupe" in body
    assert '"too many (max 50)"' not in body
    assert '"too many (max %u)"' in body and "HP_MAX_SELECTION" in body


def test_factory_coerces_rmu_to_sensor():
    body = CPP.split("void HeatpumpComponent::create_entities")[1].split("void HeatpumpComponent::setup")[0]
    assert "addr < 20000 && kind != 0" in body


def test_picker_escapes_titles_and_controls():
    assert "&amp;" in CPP and "esc(r.t)" in CPP
    assert "\\u%04X" in CPP


def test_registers_emitter_gone():
    assert "generate_header" not in INIT
    assert "common_and_deltas" not in open(os.path.join(REPO, "components", "heatpump", "registers.py")).read()
    assert '#include "registers.h"' not in CPP
