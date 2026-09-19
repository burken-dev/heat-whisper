# tests/conftest.py — stub `esphome` (unavailable in sandbox) so the
# component package imports without the ESPHome toolchain.
import sys
from unittest.mock import MagicMock

for _name in ("esphome", "esphome.codegen", "esphome.config_validation", "esphome.core",
              "esphome.components", "esphome.components.uart"):
    sys.modules.setdefault(_name, MagicMock(name=_name))
