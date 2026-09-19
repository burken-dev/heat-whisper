# components/nibe/__init__.py
import os, json, esphome.codegen as cg
import esphome.config_validation as cv
from esphome import pins
from esphome.components import uart
from .registers import generate_header, generate_catalog_header, load_hints, DEFAULT_ALLOWLIST
CODEOWNERS = ["@andreas"]
nibe_ns = cg.esphome_ns.namespace("nibe")
Nibe = nibe_ns.class_("NibeComponent", cg.Component, uart.UARTDevice)
CONF_EXTRA_POLL = "extra_poll"
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(Nibe),
    cv.Optional("slave_address", default=0x19): cv.hex_int,
    cv.Optional(CONF_EXTRA_POLL, default=[]): cv.ensure_list(cv.int_),
    cv.Optional("passive", default=False): cv.boolean,
    cv.Optional("flow_control_pin"): pins.gpio_output_pin_schema,
}).extend(uart.UART_DEVICE_SCHEMA)  # provides uart_id (register_uart_device needs it)
async def to_code(config):
    var = cg.new_Pvariable(config[cv.GenerateID()])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)
    cg.add(var.set_slave_address(config["slave_address"]))
    cg.add(var.set_passive(config["passive"]))
    if "flow_control_pin" in config:
        pin = await cg.gpio_pin_expression(config["flow_control_pin"])
        cg.add(var.set_flow_control_pin(pin))
    cg.add(var.set_poll_registers(config[CONF_EXTRA_POLL]))
    models = {}
    mdir = os.path.join(os.path.dirname(__file__), "models")  # ponytail: vendored MIT maps, see models/LICENSE
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    out = os.path.join(os.path.dirname(__file__), "registers.h")
    with open(out, "w") as fh:
        fh.write(generate_header(models))
    hints_path = os.path.join(os.path.dirname(__file__), "entity_hints.json")
    hints = load_hints(hints_path) if os.path.exists(hints_path) else {}
    catalog_out = os.path.join(os.path.dirname(__file__), "catalog.h")
    with open(catalog_out, "w") as fh:
        fh.write(generate_catalog_header(models, hints))
