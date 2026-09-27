# components/heatwhisper/registers.py
SIZE_CODES = {"u8": 0, "s8": 1, "u16": 2, "s16": 3, "u32": 4, "s32": 5}
DEFAULT_ALLOWLIST = [40004, 40008, 40012, 40013, 40014, 43136, 43005, 40033, 43009, 10001,
                     43144, 43305, 45001, 47011, 47041, 47370, 47371, 47387, 48132, 47043]

def _num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def canon_unit(u):
    # ponytail: single normalization for catalog units (mojibake + ºC typo),
    # shared by the title table and the HA string-pool mapping.
    return ((u or "").replace("�", "°").replace("º", "°").strip())


# ponytail: unit -> HA device_class; only unambiguous exact matches, else ""
# (unit-only, no wrong HA unit conversion). Bare "%" stays classless.
DEVICE_CLASS_FOR_UNIT = {
    "°C": "temperature", "K": "temperature",
    "%RH": "humidity",
    "V": "voltage", "A": "current",
    "W": "power", "kW": "power",
    "Wh": "energy", "kWh": "energy",
    "Hz": "frequency",
    "bar": "pressure", "kPa": "pressure", "Pa": "pressure",
    "s": "duration", "min": "duration", "h": "duration",
}


def device_class_for_unit(u):
    return DEVICE_CLASS_FOR_UNIT.get(canon_unit(u), "")


def state_class_for_unit(u):
    # ponytail: ESPHome enum ints (1=measurement, 2=total_increasing); 0 = none.
    u = canon_unit(u)
    if u in ("Wh", "kWh"):
        return 2
    return 1 if u in DEVICE_CLASS_FOR_UNIT else 0


def _has_range(r):
    return _num(r.get("min", 0)) != 0 or _num(r.get("max", 0)) != 0


def _by_reg(models: dict):
    # ponytail: prefer entries with nonzero min/max so shared R/W regs keep
    # their clamp range (first-wins could lock in 0/0 and disable the corrupt
    # filter + number clamp); first nonzero wins, later ones kept as-is.
    by_reg = {}
    for regs in models.values():
        for r in regs:
            prev = by_reg.get(r["register"])
            if prev is None or (not _has_range(prev) and _has_range(r)):
                by_reg[r["register"]] = r
    return by_reg


def is_known(addr: int, models: dict) -> bool:
    want = str(addr)
    for regs in models.values():
        for r in regs:
            if r.get("register") == want:
                return True
    return False

import json as _json
MAX_SELECTION = 50
DEFAULT_ENABLED = [40004, 40008, 40012, 40013, 40014, 43009, 43136, 43005,
                   40033, 43144, 43305, 45001, 47011, 47041, 47371, 47370, 47387, 48132, 47043]

def load_hints(path):
    with open(path) as fh:
        return _json.load(fh)

def load_transports(path):
    with open(path) as fh:
        return {k: v for k, v in _json.load(fh).items() if not k.startswith("_")}

_FC_ALLOWED = (1, 2, 3, 4)
_WO_CODES = {"ABCD": 0, "CDAB": 1}
_PARITY_CODES = {"NONE": 0, "EVEN": 1, "ODD": 2}


def _fc_of(r):
    try:
        fc = int(r.get("mb_fc", 3))
    except (TypeError, ValueError):
        return 3
    return fc if fc in _FC_ALLOWED else 3


def _wo_of(r):
    return _WO_CODES.get(str(r.get("word_order", "ABCD")).upper(), 0)

def normalize_model(name):
    out = "".join(c for c in (name or "").upper() if c.isalnum())
    return out

def model_registers(models, model_name):
    want = normalize_model(model_name)
    for key in sorted(models):
        if normalize_model(key) == want:
            return sorted({int(r["register"]) for r in models[key]})
    return []

def object_id_for(title):
    out = []
    for c in title.lower().replace(" ", "_"):
        if c.isalnum() or c == "_":
            out.append(c)
    return "".join(out).strip("_")

def entity_kind_for(addr, by_reg, hints):
    h = hints.get(str(addr))
    if h is not None:
        return h["type"], h.get("options", [])
    rw = (by_reg.get(str(addr)) or {}).get("mode") == "R/W"
    return ("number" if rw else "sensor"), []

def validate_selection(addrs, models):
    seen, clean = set(), []
    for a in addrs:
        a = int(a)
        if a in seen:
            continue
        if not is_known(a, models):
            return None, f"unknown register {a}"
        seen.add(a)
        clean.append(a)
    if len(clean) > MAX_SELECTION:
        return None, f"too many registers ({len(clean)} > {MAX_SELECTION})"
    return clean, ""

def _esc(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')

def generate_catalog_header(models, hints, transports=None, str_idx=None):
    # str_idx: codegen-time string-pool indices {"uom": {unit: idx}, "dc": {dc: idx}}
    # (1-based, 0 = unset); None keeps every row zero = today's behavior.
    by_reg = _by_reg(models)
    addrs = sorted({int(r["register"]) for regs in models.values() for r in regs})
    titles = {}
    for regs in models.values():
        for r in regs:
            titles.setdefault(r["register"], (r.get("titel") or f"Register {r['register']}",
                                              canon_unit(r.get("unit"))))
    lines = ["#pragma once", '#include <stdint.h>',
             "struct HwMeta { uint16_t addr; int16_t factor; uint8_t size; uint8_t rw; int32_t min; int32_t max; uint8_t fc; uint8_t wo; };",
             "struct HwTitle { uint16_t addr; const char *title; const char *unit; };",
             "struct HwStr { uint16_t addr; uint8_t dc; uint8_t uom; uint8_t sc; };",
             "struct HwModel { const char *name; const uint16_t *addrs; uint16_t n; };",
             "struct HwHint { uint16_t addr; uint8_t kind; const char *opts; };",
             "struct HwTransport { uint8_t model_idx; uint32_t baud; uint8_t parity; uint8_t addr; uint8_t write_fc; };"]
    entries = ",".join(
        f"{{{a},{_num(by_reg[str(a)].get('factor', 1))},"
        f"{SIZE_CODES.get(by_reg[str(a)].get('size') or 's16', SIZE_CODES['s16'])},"        f"{1 if by_reg[str(a)].get('mode') == 'R/W' else 0},"
        f"{_num(by_reg[str(a)].get('min', 0))},{_num(by_reg[str(a)].get('max', 0))},"
        f"{_fc_of(by_reg[str(a)])},{_wo_of(by_reg[str(a)])}}}"
        for a in addrs)
    lines.append(f"static const HwMeta HW_META[] = {{{entries}}};")
    lines.append(f"static const uint16_t HW_META_N = {len(addrs)};")
    trows = ",".join(f'{{{a},"{_esc(titles[str(a)][0])}","{_esc(titles[str(a)][1])}"}}' for a in addrs)
    lines.append(f"static const HwTitle HW_TITLES[] = {{{trows}}};")
    def _str_row(a):
        if not str_idx:
            return f"{{{a},0,0,0}}"
        unit = titles[str(a)][1]
        uom = (str_idx.get("uom", {}).get(unit, 0)) if unit else 0
        dc = str_idx.get("dc", {}).get(device_class_for_unit(unit), 0)
        sc = state_class_for_unit(unit) if unit else 0
        return f"{{{a},{dc},{uom},{sc}}}"
    srows = ",".join(_str_row(a) for a in addrs)
    lines.append(f"static const HwStr HW_STRS[] = {{{srows}}};")
    lines.append(f"static const uint16_t HW_STRS_N = {len(addrs)};")
    for m, regs in sorted(models.items()):
        want = normalize_model(m)
        lst = sorted({int(r["register"]) for r in regs})
        lines.append(f"static const uint16_t HW_MODEL_{want}[] = {{{','.join(map(str, lst))}}};")
    mrows = []
    for m, regs in sorted(models.items()):
        want = normalize_model(m)
        n = len({int(r["register"]) for r in regs})
        mrows.append(f'{{"{m}",HW_MODEL_{want},{n}}}')
    lines.append(f"static const HwModel HW_MODELS[] = {{{','.join(mrows)}}};")
    lines.append(f"static const uint8_t HW_MODELS_N = {len(models)};")
    kinds = {"sensor": 0, "number": 1, "switch": 2, "select": 3}
    hrows = []
    for a_str, h in sorted(hints.items(), key=lambda kv: int(kv[0])):
        opts = ";".join(f"{v}:{_esc(l)}" for v, l in h.get("options", []))
        hrows.append(f'{{{a_str},{kinds[h["type"]]},"{opts}"}}')
    lines.append(f"static const HwHint HW_HINTS[] = {{{','.join(hrows)}}};")
    lines.append(f"static const uint8_t HW_HINTS_N = {len(hrows)};")
    lines.append(f"static const uint16_t HW_DEFAULTS[] = {{{','.join(map(str, DEFAULT_ENABLED))}}};")
    lines.append(f"static const uint8_t HW_DEFAULTS_N = {len(DEFAULT_ENABLED)};")
    lines.append(f"static const uint8_t HW_MAX_SELECTION = {MAX_SELECTION};")
    names = [m for m, _ in sorted(models.items())]  # same order as HW_MODELS rows
    trows = []
    for i, m in enumerate(names):
        t = (transports or {}).get(m)
        if t is None:
            continue  # ponytail: no sidecar entry = no Modbus row, C++ treats as unsupported
        trows.append(f"{{{i},{int(t.get('baud', 9600))},"
                      f"{_PARITY_CODES.get(str(t.get('parity', 'NONE')).upper(), 0)},"
                      f"{int(t.get('address', 1))},{int(t.get('write_fc', 16))}}}")
    lines.append(f"static const HwTransport HW_TRANSPORTS[] = {{{','.join(trows)}}};")
    lines.append(f"static const uint8_t HW_TRANSPORTS_N = {len(trows)};")
    return "\n".join(lines) + "\n"
