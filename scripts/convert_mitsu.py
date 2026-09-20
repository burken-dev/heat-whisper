#!/usr/bin/env python3
"""Intesis IN485MIT001A000 manual -> HeatWhisper Mitsubishi_Ecodan model (transcription).

Source: HMS Networks user manual IN485MIT001A000 v1.0.3 (2025-12-02), Modbus
registers §8.2.1-8.2.8:
https://www.hms-networks.com/docs/default-source/products/intesis/manuals-and-guides---manuals/user-manual-in485mit001a000.pdf
(fetched 2026-09-20; gateway capacity: one Ecodan air-to-water unit.)

ADDRESSING RULE: the manual prints wire (base0) + PLC (base1) addresses.
"register" below stores the PLC (base1) number, so wire = reg - 1 holds
(e.g. base0 306 / PLC 307 -> register "307").

Temps: manual unit is °C/°F x1/x10 per DIP SW2-P7/P8. Factors assume
factory DIP (SW2-P7 OFF = x1) -> s16/factor 1; °C (P8 OFF). If an installer
flips P7 to x10, values read 10x high and a model variant would be needed.
Enums/counters -> u16 (factor 1); 0/1 and 0..2 and 1..2 and 1..8/1..63 and
0..65535 ranges kept, else min/max "0"/"0" (F750 unknown-convention). Mode
R/R-W per manual R/W column, except the two virtual-temp writes listed as
W-only (182, 257) which are modeled as R/W (schema allows only R/R-W; init
0x8000 = inactive). All single-register -> mb_fc 3 (gateway also answers
FC04 reads and FC06/FC16 writes; FC16 single-register only). word_order
ABCD, JSON sorted. No duplicate PLC numbers in §8.2.1-8.2.8, so no
first-wins drops. Manual quirks: Zones Mode is 1:Heat/2:Cool (Daikin 0/1);
Zone Control Type is 0/1/2 (Daikin R-only, here R/W); DHW On/Off is R-only
(Daikin R/W); Operating Time Counter is R-only (Daikin R/W); PLC 308 absent
(outlet-water base0 306 -> PLC 307, inlet-water base0 308 -> PLC 309);
polling limit 50 regs/request.

Usage: scripts/convert_mitsu.py <out.json>
"""
import json
import sys

# (register[PLC base1], titel, info, unit, size, factor, mode, min, max, mb_fc)
DATA = [
    # 8.2.1 gateway registers (R; 464 R/W)
    (461, "Device Identifier", "fixed 0x3100 (12544); §8.2.1", "", "u16", 1, "R", "0", "0", 3),
    (462, "FW Version MSB", "first two numbers, hex; §8.2.1", "", "u16", 1, "R", "0", "0", 3),
    (463, "FW Version LSB", "last two numbers, hex; §8.2.1", "", "u16", 1, "R", "0", "0", 3),
    (464, "Device Reset", "write 1 to reset gateway; §8.2.1", "", "u16", 1, "R/W", "0", "1", 3),
    (465, "Baudrate", "1:2400 2:4800 3:9600 4:19200 5:38500 6:57600 7:76800 8:115200; §8.2.1", "", "u16", 1, "R", "1", "8", 3),
    (466, "Modbus Server Address", "1..63; §8.2.1", "", "u16", 1, "R", "1", "63", 3),
    (467, "Dip-Switches Value", "decimal, binary = SW1+SW2 positions; §8.2.1", "", "u16", 1, "R", "0", "0", 3),
    # 8.2.2 general registers
    (102, "Indoor Unit Address", "address of connected unit; §8.2.2", "", "u16", 1, "R/W", "0", "65535", 3),
    (108, "Error: Flag", "0 no error 1 error present; §8.2.2", "", "u16", 1, "R", "0", "1", 3),
    (109, "Error: Code", "centralized-controller code, 0 = no error; §8.2.2", "", "u16", 1, "R", "0", "0", 3),
    (110, "Error: Sub Code", "Ecodan unit code, 0 = no error; §8.2.2", "", "u16", 1, "R", "0", "0", 3),
    (115, "Refrigerant Error: Flag", "0 no error 1 error present; §8.2.2", "", "u16", 1, "R", "0", "1", 3),
    (117, "Operating Time Counter", "heat pump hours, resets at 65535; §8.2.2", "h", "u16", 1, "R", "0", "65535", 3),
    (119, "Remote Control Lock", "0 unlocked 1 locked (BMS only); §8.2.2", "", "u16", 1, "R/W", "0", "1", 3),
    (120, "Modbus Control Lock", "0 unlocked 1 locked (remote only); §8.2.2", "", "u16", 1, "R/W", "0", "1", 3),
    (131, "On/Off", "turns Ecodan system on/off; §8.2.2", "", "u16", 1, "R/W", "0", "1", 3),
    (132, "Operation", "0 not operating 1 operating (demand); §8.2.2", "", "u16", 1, "R", "0", "1", 3),
    # 8.2.3 zones registers
    (141, "Zones: On/Off", "0 off 1 on; §8.2.3", "", "u16", 1, "R", "0", "1", 3),
    (142, "Zones: Operation", "0 not operating 1 operating (demand); §8.2.3", "", "u16", 1, "R", "0", "1", 3),
    (143, "Zones: Mode", "1 heat 2 cool, both zones; §8.2.3", "", "u16", 1, "R/W", "1", "2", 3),
    # 8.2.4 zone 1 registers
    (147, "Zone 1: On/Off", "0 off 1 on; §8.2.4", "", "u16", 1, "R", "0", "1", 3),
    (148, "Zone 1: Operation", "0 not operating 1 operating (demand); §8.2.4", "", "u16", 1, "R", "0", "1", 3),
    (150, "Zone 1: Control Type", "0 outlet water 1 room thermostat 2 weather curve; §8.2.4", "", "u16", 1, "R/W", "0", "2", 3),
    (161, "Zone 1: Temperature: Setpoint", "zone 1 setpoint; §8.2.4", "°C", "s16", 1, "R/W", "0", "0", 3),
    (162, "Zone 1: Setpoint: Custom Lower Limit: Heat", "§8.2.4", "°C", "s16", 1, "R/W", "0", "0", 3),
    (163, "Zone 1: Setpoint: Custom Upper Limit: Heat", "§8.2.4", "°C", "s16", 1, "R/W", "0", "0", 3),
    (164, "Zone 1: Setpoint: Custom Lower Limit: Cool", "§8.2.4", "°C", "s16", 1, "R/W", "0", "0", 3),
    (165, "Zone 1: Setpoint: Custom Upper Limit: Cool", "§8.2.4", "°C", "s16", 1, "R/W", "0", "0", 3),
    (166, "Zone 1: Setpoint: Unit Lower Limit: Heat", "absolute unit limit; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (167, "Zone 1: Setpoint: Unit Upper Limit: Heat", "absolute unit limit; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (168, "Zone 1: Setpoint: Unit Lower Limit: Cool", "absolute unit limit; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (169, "Zone 1: Setpoint: Unit Upper Limit: Cool", "absolute unit limit; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (170, "Zone 1: Setpoint: Applied Lower Limit: Heat", "currently applied; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (171, "Zone 1: Setpoint: Applied Upper Limit: Heat", "currently applied; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (172, "Zone 1: Setpoint: Applied Lower Limit: Cool", "currently applied; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (173, "Zone 1: Setpoint: Applied Upper Limit: Cool", "currently applied; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (181, "Zone 1: Temperature: Reference", "current reference temp; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (182, "Zone 1: Temperature: Modbus Room Thermostat Ambient Reference", "BMS thermistor write, activates virtual temp (W-only -> R/W); §8.2.4", "°C", "s16", 1, "R/W", "0", "0", 3),
    (185, "Zone 1: Temperature: Outlet Water Reference", "flow water thermistor; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    (186, "Zone 1: Temperature: Inlet Water Reference", "return water thermistor; §8.2.4", "°C", "s16", 1, "R", "0", "0", 3),
    # 8.2.5 zone 2 registers
    (231, "Zone 2: On/Off", "0 off 1 on; §8.2.5", "", "u16", 1, "R", "0", "1", 3),
    (232, "Zone 2: Operation", "0 not operating 1 operating (demand); §8.2.5", "", "u16", 1, "R", "0", "1", 3),
    (236, "Zone 2: Control Type", "0 outlet water 1 room thermostat 2 weather curve; §8.2.5", "", "u16", 1, "R/W", "0", "2", 3),
    (241, "Zone 2: Temperature: Setpoint", "zone 2 setpoint; §8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (242, "Zone 2: Setpoint: Custom Lower Limit: Heat", "§8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (243, "Zone 2: Setpoint: Custom Upper Limit: Heat", "§8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (244, "Zone 2: Setpoint: Custom Lower Limit: Cool", "§8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (245, "Zone 2: Setpoint: Custom Upper Limit: Cool", "§8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (246, "Zone 2: Setpoint: Unit Lower Limit: Heat", "absolute unit limit; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (247, "Zone 2: Setpoint: Unit Upper Limit: Heat", "absolute unit limit; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (248, "Zone 2: Setpoint: Unit Lower Limit: Cool", "absolute unit limit; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (249, "Zone 2: Setpoint: Unit Upper Limit: Cool", "absolute unit limit; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (250, "Zone 2: Setpoint: Applied Lower Limit: Heat", "currently applied; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (251, "Zone 2: Setpoint: Applied Upper Limit: Heat", "currently applied; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (252, "Zone 2: Setpoint: Applied Lower Limit: Cool", "currently applied; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (253, "Zone 2: Setpoint: Applied Upper Limit: Cool", "currently applied; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (255, "Zone 2: Temperature: Reference", "current reference temp; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (257, "Zone 2: Temperature: Modbus Room Thermostat Ambient Reference", "BMS thermistor write, activates virtual temp (W-only -> R/W); §8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (259, "Zone 2: Temperature: Outlet Water Reference", "flow water thermistor; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (260, "Zone 2: Temperature: Inlet Water Reference", "return water thermistor; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    # 8.2.6 domestic hot water registers
    (271, "DHW: On/Off", "0 off 1 on; §8.2.6", "", "u16", 1, "R", "0", "1", 3),
    (272, "DHW: Operation", "0 not operating 1 operating (demand); §8.2.6", "", "u16", 1, "R", "0", "1", 3),
    (277, "DHW: Temperature: Setpoint", "DHW setpoint; §8.2.6", "°C", "s16", 1, "R/W", "0", "0", 3),
    (278, "DHW: Setpoint: Custom Lower Limit", "§8.2.6", "°C", "s16", 1, "R/W", "0", "0", 3),
    (279, "DHW: Setpoint: Custom Upper Limit", "§8.2.6", "°C", "s16", 1, "R/W", "0", "0", 3),
    (280, "DHW: Setpoint: Tank Lower Limit", "absolute tank limit; §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (281, "DHW: Setpoint: Tank Upper Limit", "absolute tank limit; §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (282, "DHW: Setpoint: Applied Lower Limit", "currently applied; §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (283, "DHW: Setpoint: Applied Upper Limit", "currently applied; §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (286, "DHW: Temperature: Tank Reference", "tank thermistor(s); §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (291, "DHW: Eco Mode", "eco mode on/off; §8.2.6", "", "u16", 1, "R/W", "0", "1", 3),
    (299, "DHW: Boost", "tank e-heater on/off; §8.2.6", "", "u16", 1, "R/W", "0", "1", 3),
    (301, "DHW: Legionella", "antilegionella status; §8.2.6", "", "u16", 1, "R", "0", "1", 3),
    # 8.2.7 outdoor unit temperature registers (all R)
    (305, "Temperature: A2W Unit Outdoor Ambient Reference", "outdoor ambient; §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    (306, "Temperature: Refrigerant Reference", "outdoor refrigerant; §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    (307, "Temperature: Outlet Water Reference", "flow water from outdoor; §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    (309, "Temperature: Inlet Water Reference", "return water to outdoor (PLC 308 absent); §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    # 8.2.8 extra registers
    (361, "Holiday Mode", "0 off 1 on; §8.2.8", "", "u16", 1, "R/W", "0", "1", 3),
    (363, "Emergency Operation", "0 off 1 on; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (364, "Defrost/Normal Operation", "0 defrost 1 normal; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (366, "3-Way Valve Operation", "0 climatize 1 DHW; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (367, "Back Up Heater Operation: Level 1", "resistor 1 on/off; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (368, "Back Up Heater Operation: Level 2", "resistor 2 on/off; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (370, "Compressor Operation", "0 off 1 on; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (371, "Compressor Operating Time", "hours, reset with 0; §8.2.8", "h", "u16", 1, "R/W", "0", "65535", 3),
    (372, "Pump Operation", "0 off 1 on; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (373, "Pump Operating Time", "hours, reset with 0; §8.2.8", "h", "u16", 1, "R/W", "0", "65535", 3),
    (374, "Water Flow Rate", "flow sensor; §8.2.8", "l/h", "u16", 1, "R", "0", "65535", 3),
    (379, "Energy Consumption: Total", "kWh, write 0 resets all energy+dates; §8.2.8", "kWh", "u16", 1, "R/W", "0", "65535", 3),
    (380, "Energy Consumption: Zones: Heat", "kWh heating; §8.2.8", "kWh", "u16", 1, "R", "0", "65535", 3),
    (381, "Energy Consumption: Zones: Cool", "kWh cooling; §8.2.8", "kWh", "u16", 1, "R", "0", "65535", 3),
    (382, "Energy Consumption: DHW", "kWh DHW; §8.2.8", "kWh", "u16", 1, "R", "0", "65535", 3),
    (384, "Zones: Heat Mode Support", "0 no 1 yes; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (385, "Zones: Cool Mode Support", "0 no 1 yes; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (386, "DHW Support", "0 no 1 yes; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
]


def convert(dst):
    out, seen, skipped = [], set(), 0
    for addr, titel, info, unit, size, factor, mode, mn, mx, fc in DATA:
        if addr in seen:
            skipped += 1  # ponytail: no dup PLC numbers in §8.2.1-8.2.8, never hit
            continue
        seen.add(addr)
        out.append({"register": str(addr), "factor": factor, "size": size,
                    "mode": mode, "titel": titel, "info": info, "unit": unit,
                    "min": mn, "max": mx, "mb_fc": fc, "word_order": "ABCD"})
    out.sort(key=lambda r: int(r["register"]))
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"wrote {len(out)} registers, skipped {skipped} dup views",
          file=sys.stderr)


if __name__ == "__main__":
    convert(sys.argv[1])
