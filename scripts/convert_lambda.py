#!/usr/bin/env python3
"""Lambda Modbusprotokoll v1.0.0 -> HeatWhisper Lambda_EUL model (transcription).

Source: Lambda Waermepumpen GmbH, MODBUS-PROTOKOLL Version 1.0 (c) 2026:
https://www.lambda-wp.com/fileadmin/userdaten/docs/downloads/regler/1_0_0_Modbusprotokoll.pdf
(fetched 2026-09-20; native RTU slave, one map shared across EU08/13/15/20/35L.)

ADDRESSING RULE: the PDF numbers datapoints as index/subindex/no; "register"
below stores the canonical index*1000+sub*100+no (e.g. HP1 COP 1/0/13 -> "1013").
Only subindex 0 (first module instance) is transcribed; sub>0 instances share
the same layout at their own canonical numbers.

Reads are FC03-only (§2); writes are FC16-only, even single-register (§2).
W-only table rows are marked R/W because §2 keeps FC03 reads open for all
registers (0002 outdoor temp, 3004/3006-3009 demand Vorgabe). 0102 Netzbezug
is marked R/W: the table shows R-only but §4.3 describes writing the PV
surplus value to it. 1013 prints INT16 but is u16 (efficiency always >= 0).
INT32 stats are one u32 entry at the first word (1020: words 1020/1021,
1022: words 1022/1023), word_order ABCD. Buffer demand block 3006-3008 must
be written together in one FC16 (§4.2); 3009 optional in the same write.
"Nicht definiert" datapoints (HP 14-18) have no R/W icons and are skipped.
No duplicate canonical numbers, so no first-wins drops.

Usage: python3 scripts/convert_lambda.py
"""
import csv
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "scripts", "lambda_registers.tsv")
DST = os.path.join(BASE, "components", "heatwhisper", "models", "Lambda_EUL.json")


def main():
    regs = []
    seen = set()
    skipped = 0
    with open(SRC, newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            reg = str(int(row["register"]))
            if reg in seen:
                skipped += 1  # ponytail: first wins, no dup canonical numbers in v1.0.0
                continue
            seen.add(reg)
            regs.append({
                "register": reg,
                "factor": int(row["factor"]),
                "size": row["size"],
                "mode": row["mode"],
                "titel": row["titel"],
                "info": row.get("info", ""),
                "unit": row.get("unit", ""),
                "min": str(row.get("min", "0")),
                "max": str(row.get("max", "0")),
                "mb_fc": 3,
                "word_order": "ABCD",
            })
    regs.sort(key=lambda r: int(r["register"]))
    with open(DST, "w") as fh:
        json.dump(regs, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {len(regs)} registers to {DST} (skipped {skipped} dups)")


if __name__ == "__main__":
    sys.exit(main())
