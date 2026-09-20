#!/usr/bin/env python3
"""Intesis IN485DAI001A000 manual -> HeatWhisper Daikin_Altherma3 model (transcription).

Source: HMS Networks user manual IN485DAI001A000 v1.0.2 (2025-07-18), Modbus
registers §8.2.1-8.2.8:
https://www.hms-networks.com/docs/default-source/products/intesis/manuals-and-guides---manuals/user-manual-in485dai001a000.pdf
(fetched 2026-09-20; gateway capacity: one Altherma 3 unit, MMI=MAIN present.)

ADDRESSING RULE: the manual prints wire (base0) + PLC (base1) addresses.
"register" below stores the PLC (base1) number, so wire = reg - 1 holds
(e.g. base0 149 / PLC 150 -> register "150").

Temps: manual unit is °C/°F x1/x10 per DIP SW2-P7/P8. Factors assume
factory DIP (SW2-P7 OFF = x1) -> s16/factor 1; °C (P8 OFF). If an installer
flips P7 to x10, values read 10x high and a model variant would be needed.
Enums/counters -> u16 (factor 1); 0/1 and 0..2 and 1..8/1..63 ranges kept,
else min/max "0"/"0" (F750 unknown-convention). Mode R/R-W per manual R/W
column. All single-register -> mb_fc 3 (gateway also answers FC04 reads and
FC06/FC16 writes; FC16 single-register only). word_order ABCD, JSON sorted.
No duplicate PLC numbers in §8.2.1-8.2.8, so no first-wins drops.
Manual quirks: p33 virtual-temp text cites Room setpoint "PLC 161" (typo for
201; table §8.2.5 base0 200 / PLC 201 used); p37 repeats it, same fix.

Usage: scripts/convert_daikin.py <out.json>
"""
import json
import sys

# (register[PLC base1], titel, info, unit, size, factor, mode, min, max, mb_fc)
DATA = [
    # 8.2.1 gateway registers (R; 464 R/W)
    (461, "Device Identifier", "fixed 0x2900 (10496); §8.2.1", "", "u16", 1, "R", "0", "0", 3),
    (462, "FW Version MSB", "first two numbers, hex; §8.2.1", "", "u16", 1, "R", "0", "0", 3),
    (463, "FW Version LSB", "last two numbers, hex; §8.2.1", "", "u16", 1, "R", "0", "0", 3),
    (464, "Device Reset", "write 1 to reset gateway; §8.2.1", "", "u16", 1, "R/W", "0", "1", 3),
    (465, "Baudrate", "1:2400 2:4800 3:9600 4:19200 5:38500 6:57600 7:76800 8:115200; §8.2.1", "", "u16", 1, "R", "1", "8", 3),
    (466, "Modbus Slave Address", "1..63; §8.2.1", "", "u16", 1, "R", "1", "63", 3),
    (467, "Dip-Switches Value", "decimal, binary = SW1+SW2 positions; §8.2.1", "", "u16", 1, "R", "0", "0", 3),
    # 8.2.2 general registers
    (109, "Error: Code", "0 = no error; §8.2.2", "", "u16", 1, "R", "0", "0", 3),
    (110, "Error: Sub Code", "0 = no error; §8.2.2", "", "u16", 1, "R", "0", "0", 3),
    (117, "Operating Time Counter", "heat pump hours, resets at 65535; needs 370 or 372 enabled; §8.2.2", "h", "u16", 1, "R/W", "0", "65535", 3),
    (119, "Remote Control Lock", "0 unlocked 1 locked (BMS only); §8.2.2", "", "u16", 1, "R/W", "0", "1", 3),
    (120, "Modbus Control Lock", "0 unlocked 1 locked (remote only); §8.2.2", "", "u16", 1, "R/W", "0", "1", 3),
    # 8.2.3 zone registers
    (141, "Zones: On/Off", "0 off 1 on; §8.2.3", "", "u16", 1, "R/W", "0", "1", 3),
    (142, "Zones: Operation", "0 not operating 1 operating (demand); §8.2.3", "", "u16", 1, "R", "0", "1", 3),
    (143, "Zones: Mode", "0 heat 1 cool; §8.2.3", "", "u16", 1, "R/W", "0", "1", 3),
    # 8.2.4 main zone registers
    (150, "Zone 1: Control Type", "0 outlet water 1 ext ambient 2 room thermostat; §8.2.4", "", "u16", 1, "R", "0", "2", 3),
    (151, "Zone 1: Setpoint Mode", "0 fixed 1 weather dependent; §8.2.4", "", "u16", 1, "R/W", "0", "1", 3),
    (152, "Zone 1: Setpoint Mode: Type", "0 WD-heat/fixed-cool 1 WD-heat+cool; §8.2.4", "", "u16", 1, "R", "0", "1", 3),
    (161, "Zone 1: Temperature: Setpoint", "main zone setpoint; §8.2.4", "°C", "s16", 1, "R/W", "0", "0", 3),
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
    (191, "Zone 1: Scheduled Mode", "0 off 1 on; §8.2.4", "", "u16", 1, "R/W", "0", "1", 3),
    # 8.2.5 room registers
    (201, "Room 1: Temperature: Setpoint", "room setpoint (manual p37 cites PLC 161, typo); §8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (202, "Room 1: Setpoint: Custom Lower Limit: Heat", "§8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (203, "Room 1: Setpoint: Custom Upper Limit: Heat", "§8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (204, "Room 1: Setpoint: Custom Lower Limit: Cool", "§8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (205, "Room 1: Setpoint: Custom Upper Limit: Cool", "§8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (206, "Room 1: Setpoint: Unit Lower Limit: Heat", "absolute unit limit; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (207, "Room 1: Setpoint: Unit Upper Limit: Heat", "absolute unit limit; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (208, "Room 1: Setpoint: Unit Lower Limit: Cool", "absolute unit limit; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (209, "Room 1: Setpoint: Unit Upper Limit: Cool", "absolute unit limit; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (210, "Room 1: Setpoint: Applied Lower Limit: Heat", "currently applied; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (211, "Room 1: Setpoint: Applied Upper Limit: Heat", "currently applied; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (212, "Room 1: Setpoint: Applied Lower Limit: Cool", "currently applied; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (213, "Room 1: Setpoint: Applied Upper Limit: Cool", "currently applied; §8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    (215, "Room 1: Temperature: Modbus Room Thermostat Ambient Reference", "BMS thermistor write, activates virtual temp; §8.2.5", "°C", "s16", 1, "R/W", "0", "0", 3),
    (217, "Room 1: Antifrost Mode", "0 off 1 on; §8.2.5", "", "u16", 1, "R", "0", "1", 3),
    (218, "Room 1: Antifrost Room Setpoint Temperature: Heat", "§8.2.5", "°C", "s16", 1, "R", "0", "0", 3),
    # 8.2.6 domestic hot water registers
    (271, "DHW: On/Off", "0 off 1 on; §8.2.6", "", "u16", 1, "R/W", "0", "1", 3),
    (272, "DHW: Operation", "0 not operating 1 operating (demand); §8.2.6", "", "u16", 1, "R", "0", "1", 3),
    (274, "DHW: Setpoint Mode", "0 fixed 1 weather dependent; §8.2.6", "", "u16", 1, "R/W", "0", "1", 3),
    (277, "DHW: Temperature: Setpoint", "DHW setpoint; §8.2.6", "°C", "s16", 1, "R/W", "0", "0", 3),
    (278, "DHW: Setpoint: Custom Lower Limit", "§8.2.6", "°C", "s16", 1, "R/W", "0", "0", 3),
    (279, "DHW: Setpoint: Custom Upper Limit", "§8.2.6", "°C", "s16", 1, "R/W", "0", "0", 3),
    (280, "DHW: Setpoint: Tank Lower Limit", "absolute tank limit; §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (281, "DHW: Setpoint: Tank Upper Limit", "absolute tank limit; §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (282, "DHW: Setpoint: Applied Lower Limit", "currently applied; §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (283, "DHW: Setpoint: Applied Upper Limit", "currently applied; §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (286, "DHW: Temperature: Tank Reference", "tank thermistor(s); §8.2.6", "°C", "s16", 1, "R", "0", "0", 3),
    (297, "DHW: Scheduled Mode", "0 off 1 on; §8.2.6", "", "u16", 1, "R", "0", "1", 3),
    (299, "DHW: Powerful Operation", "tank e-heater on/off; §8.2.6", "", "u16", 1, "R/W", "0", "1", 3),
    (301, "DHW: Disinfection Mode", "antilegionella status; §8.2.6", "", "u16", 1, "R", "0", "1", 3),
    # 8.2.7 outdoor unit temperature registers (all R)
    (305, "Temperature: A2W Unit Outdoor Ambient Reference", "outdoor ambient; §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    (306, "Temperature: Refrigerant Reference", "outdoor refrigerant; §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    (307, "Temperature: Outlet Water Reference", "leaving-water temp; §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    (308, "Temperature: Outlet Water Reference (Plate Heat Exchanger)", "PHE inlet from outdoor; §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    (309, "Temperature: Inlet Water Reference", "inlet backup heater water; §8.2.7", "°C", "s16", 1, "R", "0", "0", 3),
    # 8.2.8 extra registers
    (362, "Quiet Mode (Low Noise Operation)", "0 off 1 on; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (370, "Compressor Operation", "0 off 1 on; feeds 117; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (371, "Compressor Operating Time", "hours, reset with 0; §8.2.8", "h", "u16", 1, "R/W", "0", "65535", 3),
    (372, "Pump Operation", "0 off 1 on; feeds 117; §8.2.8", "", "u16", 1, "R", "0", "1", 3),
    (373, "Pump Operating Time", "hours, reset with 0; §8.2.8", "h", "u16", 1, "R/W", "0", "65535", 3),
    (374, "Water Flow Rate", "flow sensor; §8.2.8", "l/h", "u16", 1, "R", "0", "65535", 3),
    (375, "Water Pressure: DHW", "DHW tank; §8.2.8", "Pa", "u16", 1, "R", "0", "0", 3),
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
