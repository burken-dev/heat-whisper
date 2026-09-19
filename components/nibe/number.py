import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import number
import logging, os, json
from . import Nibe, nibe_ns
from .registers import is_known

_LOGGER = logging.getLogger(__name__)
NibeNumber = nibe_ns.class_("NibeNumber", number.Number, cg.Component)

CONFIG_SCHEMA = number.number_schema(NibeNumber).extend({
    cv.GenerateID("nibe_id"): cv.use_id(Nibe),
    cv.Required("register"): cv.int_,
    cv.Required("min_value"): cv.float_,
    cv.Required("max_value"): cv.float_,
    cv.Optional("step", default=0.5): cv.float_,
})

async def to_code(config):
    mdir = os.path.join(os.path.dirname(__file__), "models")
    models = {}
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    if not is_known(config["register"], models):
        _LOGGER.warning("nibe number register %s not in model maps; entity will never fire", config["register"])
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
