# components/heatwhisper/__init__.py
import os, json, subprocess, esphome.codegen as cg
import esphome.config_validation as cv
from esphome import pins
from esphome.components import uart, web_server_base
from .registers import (generate_catalog_header, load_hints, load_transports, MAX_SELECTION,
                         canon_unit, device_class_for_unit)
CODEOWNERS = ["@andreas"]
AUTO_LOAD = ["sensor", "number", "switch", "select", "web_server_base"]  # boot factory new entities; no YAML platforms required
heatwhisper_ns = cg.esphome_ns.namespace("heatwhisper")
HeatWhisper = heatwhisper_ns.class_("HeatWhisperComponent", cg.Component, uart.UARTDevice)
HeatWhisperPickerHandler = heatwhisper_ns.class_("HeatWhisperPickerHandler", cg.Component)
CONF_EXTRA_POLL = "extra_poll"
CONF_PICKER_ID = "picker_id"
CONF_WEB_SERVER_BASE_ID = web_server_base.CONF_WEB_SERVER_BASE_ID  # attr, not submodule import (see tests/conftest.py stubs)
def resolve_fw_version():
    # ponytail: git tag is the single source of truth; never hand-bump.
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--dirty", "--always"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."),
            check=True,
        ).stdout.strip()
    except Exception:
        return "dev"
    if not out:
        return "dev"
    # ponytail: tag-safe by construction; allow-list so the -D quote can't break.
    safe = "".join(c for c in out if (c.isascii() and c.isalnum()) or c in "._-+")
    return safe or "dev"
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(HeatWhisper),
    cv.Optional("protocol", default="nibe"): cv.one_of("nibe", "modbus_rtu"),
    cv.Optional("model", default=""): cv.string,
    cv.Optional("modbus_address", default=1): cv.int_range(min=1, max=247),
    cv.Optional(CONF_EXTRA_POLL, default=[]): cv.ensure_list(cv.int_),
    cv.Optional("passive", default=False): cv.boolean,
    cv.Optional("flow_control_pin"): pins.gpio_output_pin_schema,
    cv.GenerateID(CONF_PICKER_ID): cv.declare_id(HeatWhisperPickerHandler),
    cv.GenerateID(CONF_WEB_SERVER_BASE_ID): cv.use_id(web_server_base.WebServerBase),
}).extend(uart.UART_DEVICE_SCHEMA)  # provides uart_id (register_uart_device needs it)
async def to_code(config):
    var = cg.new_Pvariable(config[cv.GenerateID()])
    await cg.register_component(var, config)
    # ponytail: factory sensors carry delta/throttle/heartbeat filters but no YAML
    # sensor platform exists to trigger it — define what sensor codegen would.
    cg.add_define("USE_SENSOR_FILTER")
    await uart.register_uart_device(var, config)
    cg.add(var.set_passive(config["passive"]))
    cg.add_define("HW_FW_VERSION", f'"{resolve_fw_version()}"')
    if "flow_control_pin" in config:
        pin = await cg.gpio_pin_expression(config["flow_control_pin"])
        cg.add(var.set_flow_control_pin(pin))
    cg.add(var.set_poll_registers(config[CONF_EXTRA_POLL]))
    base = await cg.get_variable(config[CONF_WEB_SERVER_BASE_ID])
    picker = cg.new_Pvariable(config[CONF_PICKER_ID], base, var)
    await cg.register_component(picker, config)
    models = {}
    mdir = os.path.join(os.path.dirname(__file__), "models")  # ponytail: vendored MIT maps, see models/LICENSE
    for f in sorted(os.listdir(mdir)):
        if f.endswith(".json"):
            with open(os.path.join(mdir, f)) as fh:
                models[f[:-5]] = json.load(fh)
    hints_path = os.path.join(os.path.dirname(__file__), "entity_hints.json")
    hints = load_hints(hints_path) if os.path.exists(hints_path) else {}
    transports_path = os.path.join(os.path.dirname(__file__), "transports.json")
    transports = load_transports(transports_path) if os.path.exists(transports_path) else {}
    protocol = config["protocol"]
    if protocol == "modbus_rtu":
        if not config["model"] or config["model"] not in transports:
            raise cv.Invalid("modbus_rtu protocol requires model: one of " + ", ".join(sorted(transports)))
    cg.add(var.set_protocol_is_modbus(protocol == "modbus_rtu"))
    cg.add(var.set_modbus_address(config["modbus_address"]))
    cg.add(var.set_model(config["model"]))
    # ponytail: entity strings (unit/device_class) live in codegen string tables;
    # runtime-created entities can only reference them by index, so register the
    # catalog's distinct strings here and bake the indices into catalog.h.
    from esphome.core import entity_helpers as _eh  # local: host pytest stubs esphome
    str_idx = {"uom": {}, "dc": {}}
    for regs in models.values():
        for r in regs:
            u = canon_unit(r.get("unit"))
            if not u or u in str_idx["uom"]:
                continue
            str_idx["uom"][u] = _eh.register_unit_of_measurement(u)
            dc = device_class_for_unit(u)
            if dc and dc not in str_idx["dc"]:
                str_idx["dc"][dc] = _eh.register_device_class(dc)
    if str_idx["uom"]:
        cg.add_define("USE_ENTITY_UNIT_OF_MEASUREMENT")
    if str_idx["dc"]:
        cg.add_define("USE_ENTITY_DEVICE_CLASS")
    catalog_out = os.path.join(os.path.dirname(__file__), "catalog.h")
    with open(catalog_out, "w") as fh:
        fh.write(generate_catalog_header(models, hints, transports, str_idx))
    # ponytail: App entity slots are StaticVectors sized from codegen counts and
    # push_back silently drops on overflow; the boot factory new up to
    # MAX_SELECTION entities at runtime, so reserve slots here (also defines
    # USE_SELECT when no YAML select platform exists).
    from esphome.core import CORE  # local: host pytest stubs esphome (see tests/conftest.py)
    for _ in range(MAX_SELECTION):
        CORE.register_platform_component("sensor", var)
        CORE.register_platform_component("number", var)
        CORE.register_platform_component("switch", var)
        CORE.register_platform_component("select", var)
