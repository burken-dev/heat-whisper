import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
import logging, os, json
from . import HeatWhisper, heatwhisper_ns
from .registers import is_known

_LOGGER = logging.getLogger(__name__)
HeatWhisperSensor = heatwhisper_ns.class_("HeatWhisperSensor", sensor.Sensor, cg.Component)

CONFIG_SCHEMA = sensor.sensor_schema(HeatWhisperSensor).extend({
    cv.GenerateID("heatwhisper_id"): cv.use_id(HeatWhisper),
    cv.Required("register"): cv.int_,
})

async def to_code(config):
    mdir = os.path.join(os.path.dirname(__file__), "models")
    models = {}
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    if not is_known(config["register"], models):
        _LOGGER.warning("heatwhisper sensor register %s not in model maps; entity will never fire", config["register"])
    parent = await cg.get_variable(config["heatwhisper_id"])
    var = await sensor.new_sensor(config)
    await cg.register_component(var, config)
    cg.add(var.set_parent(parent))
    cg.add(var.set_register(config["register"]))
    cg.add(parent.add_sensor(var))
