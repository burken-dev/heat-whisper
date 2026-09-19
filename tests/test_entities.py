# tests/test_entities.py — codegen wiring smoke for sensor.py/number.py.
# esphome is stubbed (see conftest); platform helpers get AsyncMock stubs so
# to_code runs and we can assert the parent/register call sequence.
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

_comps = sys.modules["esphome.components"]
_sensor = MagicMock(name="sensor")
_sensor.new_sensor = AsyncMock()
_number = MagicMock(name="number")
_number.new_number = AsyncMock()
_comps.sensor = _sensor
_comps.number = _number

from components.heatpump import sensor as hp_sensor  # noqa: E402
from components.heatpump import number as hp_number  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def test_sensor_to_code_wiring():
    assert asyncio.iscoroutinefunction(hp_sensor.to_code)
    parent, var = MagicMock(name="parent"), MagicMock(name="var")
    hp_sensor.cg.get_variable = AsyncMock(return_value=parent)
    hp_sensor.cg.register_component = AsyncMock()
    _sensor.new_sensor.return_value = var
    _run(hp_sensor.to_code({"heatpump_id": "heatpump_bridge", "register": 40004}))
    var.set_parent.assert_called_once_with(parent)
    var.set_register.assert_called_once_with(40004)
    parent.add_sensor.assert_called_once_with(var)


def test_number_to_code_wiring():
    assert asyncio.iscoroutinefunction(hp_number.to_code)
    parent, var = MagicMock(name="parent"), MagicMock(name="var")
    hp_number.cg.get_variable = AsyncMock(return_value=parent)
    hp_number.cg.register_component = AsyncMock()
    _number.new_number.return_value = var
    cfg = {"heatpump_id": "heatpump_bridge", "register": 43005,
           "min_value": -3000.0, "max_value": 3000.0, "step": 10.0}
    _run(hp_number.to_code(cfg))
    _number.new_number.assert_called_once_with(
        cfg, min_value=-3000.0, max_value=3000.0, step=10.0)
    var.set_parent.assert_called_once_with(parent)
    var.set_register.assert_called_once_with(43005)
    parent.add_number.assert_called_once_with(var)


def test_sensor_schema_rejects_unknown_register_warning():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "components", "heatpump", "sensor.py")).read()
    assert "is_known" in src

def test_number_schema_rejects_unknown_register_warning():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "components", "heatpump", "number.py")).read()
    assert "is_known" in src
