# components/nibe/sensor.py
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from . import Nibe, nibe_ns

NibeSensor = nibe_ns.class_("NibeSensor", sensor.Sensor, cg.Component)

CONFIG_SCHEMA = sensor.sensor_schema(NibeSensor).extend({
    cv.GenerateID("nibe_id"): cv.use_id(Nibe),
    cv.Required("register"): cv.int_,
})


async def to_code(config):
    parent = await cg.get_variable(config["nibe_id"])
    var = await sensor.new_sensor(config)
    await cg.register_component(var, config)
    cg.add(var.set_parent(parent))
    cg.add(var.set_register(config["register"]))
    cg.add(parent.add_sensor(var))
