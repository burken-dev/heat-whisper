#!/usr/bin/env python3
"""Print YAML blocks for one register (sensor/number + enable switch + on_boot line).

Usage: python3 scripts/add_register.py 40033 [--writable]
Looks up components/nibe/models/*.json for title/unit/range. Paste output
into packages/base.yaml. Stdlib only.
"""
import argparse
import glob
import json
import os
import sys

MODELS = os.path.join(os.path.dirname(__file__), "..", "components", "nibe", "models")
FILTERS = "    filters:\n      - delta: 0.1\n      - throttle: 60s\n      - heartbeat: 5min"


def lookup(addr):
    want = str(addr)
    for f in sorted(glob.glob(os.path.join(MODELS, "*.json"))):
        for r in json.load(open(f)):
            if r.get("register") == want:
                return r
    return None


def main(addr, writable):
    r = lookup(addr)
    if r is None:
        sys.exit(f"unknown register {addr} (not in models/*.json)")
    title = r.get("titel", f"Register {addr}").replace('"', "")
    unit = (r.get("unit") or "").replace("�", "°")
    factor = int(r.get("factor", 1) or 1)
    if writable:
        lo, hi = int(r.get("min", 0) or 0) // factor, int(r.get("max", 0) or 0) // factor
        entity = (f"number:\n  - platform: nibe\n    nibe_id: nibe_bridge\n"
                  f"    register: {addr}\n    name: \"{title}\"\n"
                  f"    min_value: {lo}\n    max_value: {hi}\n    step: 10")
    else:
        entity = (f"sensor:\n  - platform: nibe\n    nibe_id: nibe_bridge\n"
                  f"    register: {addr}\n    name: \"{title}\"\n"
                  + (f"    unit_of_measurement: \"{unit}\"\n" if unit else "")
                  + "    accuracy_decimals: 1\n" + FILTERS)
    switch = (f"switch:\n  - platform: template\n    name: \"Enable {title}\"\n"
              f"    id: en_{addr}\n    entity_category: config\n"
              f"    optimistic: true\n    restore_mode: RESTORE_DEFAULT_ON\n"
              f"    turn_on_action: {{ lambda: 'id(nibe_bridge).set_register_enabled({addr}, true);' }}\n"
              f"    turn_off_action: {{ lambda: 'id(nibe_bridge).set_register_enabled({addr}, false);' }}")
    print(entity + "\n\n" + switch + "\n\n# on_boot (packages/base.yaml esphome: section):\n"
          + f"      - lambda: 'id(nibe_bridge).set_register_enabled({addr}, id(en_{addr}).state);'")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("addr", type=int)
    ap.add_argument("--writable", action="store_true")
    a = ap.parse_args()
    main(a.addr, a.writable)
