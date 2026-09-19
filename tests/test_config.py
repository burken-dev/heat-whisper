# tests/test_config.py — source-level contract (esphome is stubbed; see conftest.py).
import os
SRC = open(os.path.join(os.path.dirname(__file__), "..", "components", "heatwhisper", "__init__.py")).read()

def test_protocol_keys_present():
    for key in ('"protocol"', '"model"', '"modbus_address"', '"slave_address"'):
        assert key in SRC, key

def test_modbus_model_required():
    assert "modbus" in SRC and "model" in SRC
    assert "transports" in SRC
