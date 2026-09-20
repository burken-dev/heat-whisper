#!/usr/bin/env python3
"""Thermia Genesis YAML -> HeatWhisper model JSON (scripted, no vendored YAML).

Source: nielsbasjes/modbus-devices ThermiaGenesis101213.yaml (combined schema
for Genesis platform v10/12/13; units inline) cross-checked against the official
Genesis 13 PDF (ACMBDH01UG0102, Atlas/Calibra/Diplomat Inverter).

Mapping: c:N->de-facto N+1 (mb_fc 1, R/W); di:N->10001+N (fc 2, R);
ir:N->30001+N (fc 4, R); hr:N->40001+N (fc 3, R/W). factor from /div suffix;
size from YAML type (int16->s16 etc.); concat/bitsetbit views skipped, first
entry wins on duplicate registers.

Usage: scripts/convert_thermia.py /tmp/ThermiaGenesis101213.yaml <out.json>
"""
import json
import re
import sys

import yaml

BASE = {"c": (0, 1), "di": (10001, 2), "ir": (30001, 4), "hr": (40001, 3)}
MODE = {"c": "R/W", "di": "R", "ir": "R", "hr": "R/W"}
SIZE = {"boolean": "u16", "enum": "u16", "bitset": "u16",
        "int16": "s16", "uint16": "u16", "int32": "s32", "uint32": "u32"}


def convert(src, dst):
    doc = yaml.safe_load(open(src, encoding="utf-8"))
    out, seen, skipped = [], set(), 0
    for block in doc.get("blocks", []):
        for f in block.get("fields", []) or []:
            m = re.match(r"(\w+)\(\s*(c|di|ir|hr):(\d+)", f.get("expression", ""))
            if not m:
                skipped += 1  # ponytail: derived concat views, no hw address
                continue
            fn, tbl, num = m.group(1), m.group(2), int(m.group(3))
            addr = BASE[tbl][0] + num + (1 if tbl == "c" else 0)
            if addr in seen:
                skipped += 1  # ponytail: bitsetbit dup views of one register
                continue
            seen.add(addr)
            d = re.search(r"\)/(\d+)\s*$", f.get("expression", ""))
            out.append({"register": str(addr), "factor": int(d.group(1)) if d else 1,
                        "size": SIZE[fn], "mode": MODE[tbl], "titel": f.get("id", ""),
                        "info": f.get("description", ""), "unit": f.get("unit") or "",
                        "min": "0", "max": "0", "mb_fc": BASE[tbl][1],
                        "word_order": "ABCD"})
    out.sort(key=lambda r: int(r["register"]))
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"wrote {len(out)} registers, skipped {skipped} derived/dup views",
          file=sys.stderr)


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
