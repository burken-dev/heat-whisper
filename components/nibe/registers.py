# components/nibe/registers.py
SIZE_CODES = {"u8": 0, "s8": 1, "u16": 2, "s16": 3, "u32": 4, "s32": 5}
DEFAULT_ALLOWLIST = [40004, 40008, 40012, 40013, 40014, 43136, 43005, 40033, 43009, 10001]

def _num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def common_and_deltas(models: dict):
    by_reg = {}
    for regs in models.values():
        for r in regs:
            by_reg.setdefault(r["register"], r)
    # ponytail: allowlist-seeded, not intersection (register sets differ per model)
    common, seen = [], set()
    for a in DEFAULT_ALLOWLIST:
        s = str(a)
        if s in by_reg and s not in seen:
            seen.add(s)
            common.append(s)
    in_common = set(common)
    deltas = {m: sorted({r["register"] for r in regs} - in_common, key=lambda x: int(x))
              for m, regs in models.items()}
    return common, deltas

def generate_header(models: dict) -> str:
    common, deltas = common_and_deltas(models)
    by_reg = {}
    for regs in models.values():
        for r in regs:
            by_reg.setdefault(r["register"], r)
    lines = ["#pragma once", "#include <stdint.h>",
             "struct NibeReg { uint16_t addr; int16_t factor; uint8_t size; uint8_t rw; int32_t min; int32_t max; };"]
    entries = ",".join(
        f"{{{r},{_num((by_reg[r]).get('factor',1))},"
        f"{SIZE_CODES[(by_reg[r]).get('size','s16')]},"
        f"{1 if (by_reg[r]).get('mode')=='R/W' else 0},"
        f"{_num((by_reg[r]).get('min',0))},{_num((by_reg[r]).get('max',0))}}}"
        for r in common)
    lines.append(f"static const NibeReg NIBE_COMMON[] = {{{entries}}};")
    lines.append(f"static const uint16_t NIBE_COMMON_N = {len(common)};")
    return "\n".join(lines) + "\n"
