# components/nibe/__init__.py
import os, json, esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart
from .registers import generate_header, DEFAULT_ALLOWLIST
CODEOWNERS = ["@andreas"]
nibe_ns = cg.esphome_ns.namespace("nibe")
Nibe = nibe_ns.class_("NibeComponent", cg.Component, cg.uart.UARTDevice)
CONF_REGISTERS = "registers"
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(Nibe),
    cv.Optional("slave_address", default=0x19): cv.hex_int,
    cv.Optional(CONF_REGISTERS, default=list(DEFAULT_ALLOWLIST)): cv.ensure_list(cv.int_),
    cv.Optional("passive", default=False): cv.boolean,
}).extend(uart.UART_DEVICE_SCHEMA)  # provides uart_id (register_uart_device needs it)
async def to_code(config):
    var = cg.new_Pvariable(config[cv.GenerateID()])
    await cg.register_component(var, config)
    await cg.uart.register_uart_device(var, config)
    cg.add(var.set_slave_address(config["slave_address"]))
    cg.add(var.set_passive(config["passive"]))
    cg.add(var.set_poll_registers(config[CONF_REGISTERS]))
    models = {}
    mdir = os.path.join(os.path.dirname(__file__), "..", "..", "reference-project", "models")
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    out = os.path.join(os.path.dirname(__file__), "registers.h")
    with open(out, "w") as fh:
        fh.write(generate_header(models))
