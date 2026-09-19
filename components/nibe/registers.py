# components/nibe/registers.py
SIZE_CODES = {"u8": 0, "s8": 1, "u16": 2, "s16": 3, "u32": 4, "s32": 5}
DEFAULT_ALLOWLIST = [40004, 40008, 40012, 40013, 40014, 43136, 43005, 40033, 43009, 10001,
                     43144, 43305, 47007, 47011, 47041, 47370, 47371, 47387, 47043]

def _num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


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
                   40033, 43144, 43305, 47011, 47007, 47041, 47371, 47370, 47387, 47043]

def load_hints(path):
    with open(path) as fh:
        return _json.load(fh)

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

def generate_catalog_header(models, hints):
    by_reg = _by_reg(models)
    addrs = sorted({int(r["register"]) for regs in models.values() for r in regs})
    titles = {}
    for regs in models.values():
        for r in regs:
            titles.setdefault(r["register"], (r.get("titel") or f"Register {r['register']}",
                                              (r.get("unit") or "").replace("�", "°")))
    lines = ["#pragma once", '#include <stdint.h>',
             "struct NibeMeta { uint16_t addr; int16_t factor; uint8_t size; uint8_t rw; int32_t min; int32_t max; };",
             "struct NibeTitle { uint16_t addr; const char *title; const char *unit; };",
             "struct NibeModel { const char *name; const uint16_t *addrs; uint16_t n; };",
             "struct NibeHint { uint16_t addr; uint8_t kind; const char *opts; };"]
    entries = ",".join(
        f"{{{a},{_num(by_reg[str(a)].get('factor', 1))},"
        f"{SIZE_CODES.get(by_reg[str(a)].get('size') or 's16', SIZE_CODES['s16'])},"        f"{1 if by_reg[str(a)].get('mode') == 'R/W' else 0},"
        f"{_num(by_reg[str(a)].get('min', 0))},{_num(by_reg[str(a)].get('max', 0))}}}"
        for a in addrs)
    lines.append(f"static const NibeMeta NIBE_META[] = {{{entries}}};")
    lines.append(f"static const uint16_t NIBE_META_N = {len(addrs)};")
    trows = ",".join(f'{{{a},"{_esc(titles[str(a)][0])}","{_esc(titles[str(a)][1])}"}}' for a in addrs)
    lines.append(f"static const NibeTitle NIBE_TITLES[] = {{{trows}}};")
    for m, regs in sorted(models.items()):
        want = normalize_model(m)
        lst = sorted({int(r["register"]) for r in regs})
        lines.append(f"static const uint16_t NIBE_MODEL_{want}[] = {{{','.join(map(str, lst))}}};")
    mrows = []
    for m, regs in sorted(models.items()):
        want = normalize_model(m)
        n = len({int(r["register"]) for r in regs})
        mrows.append(f'{{"{m}",NIBE_MODEL_{want},{n}}}')
    lines.append(f"static const NibeModel NIBE_MODELS[] = {{{','.join(mrows)}}};")
    lines.append(f"static const uint8_t NIBE_MODELS_N = {len(models)};")
    kinds = {"sensor": 0, "number": 1, "switch": 2, "select": 3}
    hrows = []
    for a_str, h in sorted(hints.items(), key=lambda kv: int(kv[0])):
        opts = ";".join(f"{v}:{_esc(l)}" for v, l in h.get("options", []))
        hrows.append(f'{{{a_str},{kinds[h["type"]]},"{opts}"}}')
    lines.append(f"static const NibeHint NIBE_HINTS[] = {{{','.join(hrows)}}};")
    lines.append(f"static const uint8_t NIBE_HINTS_N = {len(hrows)};")
    lines.append(f"static const uint16_t NIBE_DEFAULTS[] = {{{','.join(map(str, DEFAULT_ENABLED))}}};")
    lines.append(f"static const uint8_t NIBE_DEFAULTS_N = {len(DEFAULT_ENABLED)};")
    lines.append(f"static const uint8_t NIBE_MAX_SELECTION = {MAX_SELECTION};")
    return "\n".join(lines) + "\n"
