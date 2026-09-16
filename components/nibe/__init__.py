# components/nibe/__init__.py (stub, full codegen in Task 2)
import esphome.codegen as cg
import esphome.config_validation as cv
CODEOWNERS = ["@andreas"]
nibe_ns = cg.esphome_ns.namespace("nibe")
Nibe = nibe_ns.class_("NibeComponent", cg.Component, cg.uart.UARTDevice)
CONFIG_SCHEMA = cv.Schema({cv.GenerateID(): cv.declare_id(Nibe)})
async def to_code(config):
    pass
