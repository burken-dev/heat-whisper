# components/heatwhisper/registers.py
SIZE_CODES = {"u8": 0, "s8": 1, "u16": 2, "s16": 3, "u32": 4, "s32": 5}
MAX_SELECTION = 50
DEFAULT_ENABLED = [40004, 40008, 40012, 40013, 40014, 40033,
                   43005, 43009, 43084, 43086, 45001,
                   47011, 47041, 47370, 47371, 47387, 48132]

# 2-bit safety tiers packed into HwMeta.rw (must match safety.h HwTier).
TIER_RO = 0
TIER_STANDARD = 1
TIER_ADVANCED = 2
TIER_HIGH_RISK = 3

STANDARD_CONTROL_REGS = frozenset({
    # Factory R/W defaults (all 7)
    43005, 47011, 47041, 47370, 47371, 47387, 48132,
    # Heating curves & offsets (S1-S4) + point offset + external adjustment
    47004, 47005, 47006, 47007,
    47008, 47009, 47010,
    47027, 47028,
    47029, 47030, 47031, 47032, 47033, 47034, 47035, 47036,
    # Degree minutes (32-bit & cooling)
    40940, 44266,
    # Room sensor & climate mode thresholds
    47372, 47374, 47375, 47376,
    47391, 47392, 47393, 47394,
    47395, 47396, 47397, 47398,
    47399, 47400, 47401, 47402,
    # Hot water comfort temperatures
    47043, 47044, 47045, 47047, 47048, 47049,
    48120, 48148,
    # Ventilation / fan mode & night cooling
    47260, 47271, 47272, 47273, 47274,
    47537, 47538, 47539,
    49358, 49359, 49360, 49361, 49362, 49363, 49364, 49365, 49366,
    # Holiday, smart home room control, silent mode max speed
    48043, 48976, 49282,
    # S-series HW demand
    40056,
})

HIGH_RISK_REGS = frozenset({
    # Min/Max supply temperature limits (underfloor / pipe over-temp risk)
    40034, 40036,
    47012, 47013, 47014, 47015, 47016, 47017, 47018, 47019,
    48495, 48496, 48497, 48498, 48499, 48500, 48501, 48502,
    # Floor drying program (multi-day high-temp baking)
    *range(47276, 47291),
    # Compressor frequency limits, regulator, manual overrides & inverter init
    *range(47092, 47106),
    48567, 48568, 49227,
    # Electrical safety: fuse size & max internal additive power
    47212, 47214, 48914, 49225,
    # Periodic HW / Legionella disinfection
    40065, 40066, 47046, 47050, 47051,
    # Operational modes, pump modes, manual pump speeds & brine freeze protection
    40021, 40068, 40069, 42097, 44323,
    47137, 47138, 47139,
    47380, 47381, 47382, 47383, 48944,
    47413, 47414, 47415, 47416, 47417, 47418,
    48107, 48130, 48131, 48208,
    48275, 48452, 48453, 48454, 48455, 48456, 48458, 48459, 48487, 48977,
    49190, 49191, 49192, 49193,
    *range(49243, 49253),
    49289, 49290, 49291, 49292, 49293,
    *range(49301, 49309),
    # Defrost parameters (icing / freeze risk)
    47294, 47295, 47296, 47299, 47313, 47473,
    # Compressor & additive DM start/step thresholds
    47206, 47208, 47209, 47210, 48072, 49228, 49229, 49294,
    # Bus / accessory & alarm behavior config (can break MODBUS40 or disable alarm protection)
    40196, 40197, 41020, 41031,
    47365, 47366, 47367, 47368,
    47388, 47389,
    48852, 48889,
})


def register_tier(addr, mode):
    """Classify a register into a fail-safe 2-bit tier (defaulting unknown R/W to Advanced)."""
    if mode != "R/W":
        return TIER_RO
    a = int(addr)
    if a in HIGH_RISK_REGS:
        return TIER_HIGH_RISK
    if a in STANDARD_CONTROL_REGS:
        return TIER_STANDARD
    return TIER_ADVANCED

def _num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def canon_unit(u):
    # ponytail: single normalization for catalog units (mojibake + ºC typo),
    # shared by the title table and the HA string-pool mapping.
    return ((u or "").replace("\ufffd", "°").replace("º", "°").strip())


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
    return "".join(c for c in (name or "").upper() if c.isalnum())

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
        f"{SIZE_CODES.get(by_reg[str(a)].get('size') or 's16', SIZE_CODES['s16'])},"        f"{register_tier(a, by_reg[str(a)].get('mode'))},"
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
