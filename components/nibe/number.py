# components/nibe/number.py
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import number
from . import Nibe, nibe_ns

NibeNumber = nibe_ns.class_("NibeNumber", number.Number, cg.Component)

CONFIG_SCHEMA = number.number_schema(NibeNumber).extend({
    cv.GenerateID("nibe_id"): cv.use_id(Nibe),
    cv.Required("register"): cv.int_,
    cv.Required("min_value"): cv.float_,
    cv.Required("max_value"): cv.float_,
    cv.Optional("step", default=0.5): cv.float_,
})


async def to_code(config):
    parent = await cg.get_variable(config["nibe_id"])
    var = await number.new_number(
        config,
        min_value=config["min_value"],
        max_value=config["max_value"],
        step=config["step"],
    )
    await cg.register_component(var, config)
    cg.add(var.set_parent(parent))
    cg.add(var.set_register(config["register"]))
    cg.add(parent.add_number(var))
