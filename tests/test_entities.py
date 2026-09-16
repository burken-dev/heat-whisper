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

from components.nibe import sensor as nibe_sensor  # noqa: E402
from components.nibe import number as nibe_number  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def test_sensor_to_code_wiring():
    assert asyncio.iscoroutinefunction(nibe_sensor.to_code)
    parent, var = MagicMock(name="parent"), MagicMock(name="var")
    nibe_sensor.cg.get_variable = AsyncMock(return_value=parent)
    nibe_sensor.cg.register_component = AsyncMock()
    _sensor.new_sensor.return_value = var
    _run(nibe_sensor.to_code({"nibe_id": "nibe_bridge", "register": 40004}))
    var.set_parent.assert_called_once_with(parent)
    var.set_register.assert_called_once_with(40004)
    parent.add_sensor.assert_called_once_with(var)


def test_number_to_code_wiring():
    assert asyncio.iscoroutinefunction(nibe_number.to_code)
    parent, var = MagicMock(name="parent"), MagicMock(name="var")
    nibe_number.cg.get_variable = AsyncMock(return_value=parent)
    nibe_number.cg.register_component = AsyncMock()
    _number.new_number.return_value = var
    cfg = {"nibe_id": "nibe_bridge", "register": 43005,
           "min_value": -3000.0, "max_value": 3000.0, "step": 10.0}
    _run(nibe_number.to_code(cfg))
    _number.new_number.assert_called_once_with(
        cfg, min_value=-3000.0, max_value=3000.0, step=10.0)
    var.set_parent.assert_called_once_with(parent)
    var.set_register.assert_called_once_with(43005)
    parent.add_number.assert_called_once_with(var)
