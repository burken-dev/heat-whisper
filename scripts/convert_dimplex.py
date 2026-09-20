#!/usr/bin/env python3
"""Dimplex WPM (via LWPM 410) wiki -> HeatWhisper model JSON (transcription).

Source: official Dimplex wiki "Modbus RTU connection (EN)"
https://dimplex.atlassian.net/wiki/spaces/DW/pages/2900787230/Modbus+RTU+connection+EN
(DATA below transcribed 2026-09-20 via the wiki REST API; my-gekko id_pk=92 PDF
not fetched, wiki is authoritative.)

Numbering: WPM software J/L/M, 1...207 address-range mode (middle column;
newer datapoints reach 352). H-variant regs differ (see info tags) and are NOT
this model. Slave addr 1...207, baud <=19200 (9600 factory), FC06 writes.

Mapping: "16 bit float" -> s16/factor 10 (tenths, per brief); uint16 -> u16
(factor 10 if wiki range has decimals, scaled min/max; s16 if min < 0);
boolean coils -> u16/mb_fc 1, min "0" max "1"; registers -> mb_fc 3;
W -> R/W (schema allows only R/R/W); unknown min/max -> "0"/"0" (F750 conv).
First entry wins on duplicate registers (wiki order), same as convert_thermia.

Usage: scripts/convert_dimplex.py <out.json>
"""
import json
import sys

# (register, titel, info, unit, size, factor, mode, min, max, mb_fc)
DATA = [
    # 6.1 operating data (R; H-reg in info)
    (1, "Outside temperature", "R1; H-reg 27", "°C", "s16", 10, "R", "0", "0", 3),
    (2, "Return temperature", "R2; H-reg 29", "°C", "s16", 10, "R", "0", "0", 3),
    (53, "Return temperature setpoint", "H-reg 28", "°C", "s16", 10, "R", "0", "0", 3),
    (3, "Hot water temperature", "R3; H-reg 30", "°C", "s16", 10, "R", "0", "0", 3),
    (58, "Set hot water temperature", "H-reg 40", "°C", "s16", 10, "R", "0", "0", 3),
    (5, "Flow temperature", "R9; H-reg 31", "°C", "s16", 10, "R", "0", "0", 3),
    (6, "Heat source inlet temperature", "R24, brine only; no H-reg", "°C", "s16", 10, "R", "0", "0", 3),
    (7, "Heat source outlet temperature", "R6; H-reg 41", "°C", "s16", 10, "R", "0", "0", 3),
    (54, "Target temperature 2nd heating circuit", "H-reg 32", "°C", "s16", 10, "R", "0", "0", 3),
    (9, "Temperature 2nd heating circuit", "R5; H-reg 33", "°C", "s16", 10, "R", "0", "0", 3),
    (55, "Target temperature 3rd heating circuit", "H-reg 34", "°C", "s16", 10, "R", "0", "0", 3),
    (10, "Temperature 3rd heating circuit", "R13; H-reg 35", "°C", "s16", 10, "R", "0", "0", 3),
    (11, "Room temperature 1", "RT-RTH Econ; H-reg 36", "°C", "s16", 10, "R", "0", "0", 3),
    (12, "Room temperature 2", "H-reg 38", "°C", "s16", 10, "R", "0", "0", 3),
    (13, "Room humidity 1", "RT-RTH Econ; H-reg 37; wiki unit sic", "°C", "s16", 10, "R", "0", "0", 3),
    (14, "Room humidity 2", "H-reg 39; wiki unit sic", "°C", "s16", 10, "R", "0", "0", 3),
    (19, "Flow temperature passive cooling", "R11; H-reg 42", "°C", "s16", 10, "R", "0", "0", 3),
    (20, "Return temperature passive cooling", "R4; H-reg 43", "°C", "s16", 10, "R", "0", "0", 3),
    (21, "Return temp. primary circuit", "R24 passive/active cooling; no H-reg", "°C", "s16", 10, "R", "0", "0", 3),
    (10, "Collector sensor", "R23; no H-reg; dup of 10, dropped", "°C", "s16", 10, "R", "0", "0", 3),
    (23, "Solar storage tank", "R22; no H-reg", "°C", "s16", 10, "R", "0", "0", 3),
    (120, "Outside air temperature (ventilation)", "no H-reg", "°C", "s16", 10, "R", "0", "0", 3),
    (121, "Supply air temperature", "no H-reg", "°C", "s16", 10, "R", "0", "0", 3),
    (122, "Exhaust air temperature", "no H-reg", "°C", "s16", 10, "R", "0", "0", 3),
    (123, "Exhaust air temperature", "2nd sensor, wiki dup label; no H-reg", "°C", "s16", 10, "R", "0", "0", 3),
    (125, "Supply air fan speed", "no H-reg", "1/min", "s16", 10, "R", "0", "0", 3),
    (126, "Exhaust fan speed", "no H-reg", "1/min", "s16", 10, "R", "0", "0", 3),
    # 6.2 history (R)
    (72, "Compressor 1 runtime", "H-reg 64", "hour", "u16", 1, "R", "0", "0", 3),
    (73, "Compressor 2 runtime", "H-reg 65", "hour", "u16", 1, "R", "0", "0", 3),
    (74, "Primary pump / fan (M11) runtime", "H-reg 66", "hour", "u16", 1, "R", "0", "0", 3),
    (75, "2nd heat generator (E10) runtime", "H-reg 67", "hour", "u16", 1, "R", "0", "0", 3),
    (76, "Heating pump (M13) runtime", "H-reg 68", "hour", "u16", 1, "R", "0", "0", 3),
    (77, "Hot water pump (M18) runtime", "H-reg 69", "hour", "u16", 1, "R", "0", "0", 3),
    (78, "Flange heating (E9) runtime", "H-reg 70", "hour", "u16", 1, "R", "0", "0", 3),
    (79, "Swimming pool pump (M19) runtime", "H-reg 71", "hour", "u16", 1, "R", "0", "0", 3),
    (71, "Additional circulation pump (M16) runtime", "from L12; no H-reg", "hour", "u16", 1, "R", "0", "0", 3),
    (303, "Heat amount Heating 1-4", "127-mode 223; H-reg 228", "kWh", "u16", 1, "R", "0", "0", 3),
    (304, "Heat amount Heating 5-8", "127-mode 224; H-reg 229", "kWh", "u16", 1, "R", "0", "0", 3),
    (305, "Heat amount Heating 9-12", "127-mode 225; H-reg 230", "kWh", "u16", 1, "R", "0", "0", 3),
    (306, "Heat amount Hot water 1-4", "127-mode 226; H-reg 231", "kWh", "u16", 1, "R", "0", "0", 3),
    (307, "Heat amount Hot water 5-8", "127-mode 227; H-reg 232", "kWh", "u16", 1, "R", "0", "0", 3),
    (308, "Heat amount Hot water 9-12", "127-mode 228; H-reg 233", "kWh", "u16", 1, "R", "0", "0", 3),
    (309, "Heat amount Swimming pool 1-4", "127-mode 229; H-reg 234", "kWh", "u16", 1, "R", "0", "0", 3),
    (310, "Heat amount Swimming pool 5-8", "127-mode 230; H-reg 235", "kWh", "u16", 1, "R", "0", "0", 3),
    (311, "Heat amount Swimming pool 9-12", "127-mode 231; H-reg 236", "kWh", "u16", 1, "R", "0", "0", 3),
    # 6.3.1 1st heating circuit (R/W)
    (243, "Parallel shift", "-19...+19K; 127-mode 163; H-reg 129", "", "u16", 1, "R/W", "0", "38", 3),
    (46, "Room temperature", "H-reg 21", "°C", "u16", 10, "R/W", "150", "300", 3),
    (244, "Fixed setpoint temperature", "127-mode 164; H-reg 130", "°C", "u16", 1, "R/W", "18", "60", 3),
    (245, "Heating curve end point", "127-mode 165; H-reg 142", "°C", "u16", 1, "R/W", "20", "70", 3),
    (47, "Hysteresis", "H-reg 22", "K", "u16", 10, "R/W", "5", "50", 3),
    (170, "Hysteresis", "127-mode only; H-reg 151", "°C", "u16", 1, "R/W", "10", "35", 3),
    (341, "Target temp. dyn. cooling", "207-mode only; no H-reg", "°C", "u16", 1, "R/W", "10", "35", 3),
    # 6.3.2 2nd/3rd heating circuit (R/W; shared addrs are H/J/L/M)
    (289, "Select heating circuit 2/3", "2=2nd 3=3rd; shared 209", "", "u16", 1, "R/W", "2", "3", 3),
    (291, "Heating curve end point", "shared 211", "°C", "u16", 1, "R/W", "20", "70", 3),
    (292, "Fixed value temperature", "shared 212", "°C", "u16", 1, "R/W", "20", "60", 3),
    (293, "Parallel shift", "-19...+19K; shared 213", "", "u16", 1, "R/W", "0", "38", 3),
    (294, "Mixer runtime", "shared 214", "min", "u16", 1, "R/W", "1", "6", 3),
    (93, "Mixer hysteresis", "shared addr", "K", "u16", 10, "R/W", "5", "20", 3),
    (295, "Mixer hysteresis", "shared 215", "°C", "u16", 1, "R/W", "30", "70", 3),
    (296, "Maximum temperature", "shared 216", "°C", "u16", 1, "R/W", "0", "30", 3),
    # 6.3.3 mode (R/W)
    (222, "Operation mode", "0 summer 1 auto 2 vacation 3 party 4 2nd-gen 5 cooling; 127:142; H-reg 134", "", "u16", 1, "R/W", "0", "5", 3),
    (223, "Number of party hours", "127-mode 143; H-reg 135", "", "u16", 1, "R/W", "0", "72", 3),
    (224, "Number of vacation days", "127-mode 144; H-reg 136", "", "u16", 1, "R/W", "0", "150", 3),
    (241, "Ventilation stages", "0 off 1 auto 2 L1 3 L2 4 L3 5 intermittent; 127:161; no H-reg", "", "u16", 1, "R/W", "0", "5", 3),
    (127, "Time value burst ventilation", "127-mode only; no H-reg", "", "u16", 1, "R/W", "15", "90", 3),
    # 6.3.4 hot water (R/W)
    (252, "Hysteresis", "127-mode 172; H-reg 131", "K", "u16", 1, "R/W", "2", "15", 3),
    (254, "Target temperature", "range Minimum-temp...85; 127:174; H-reg 149", "°C", "u16", 1, "R/W", "0", "0", 3),
    (352, "Target temperature minimum", "range 10...Target; 207-mode only; no H-reg", "°C", "u16", 1, "R/W", "0", "0", 3),
    (255, "Target temperature maximum", "range Target...85; 127:175; no H-reg", "°C", "u16", 1, "R/W", "0", "0", 3),
    # 6.3.5 swimming pool (R/W)
    (256, "Hysteresis", "127-mode 176; no H-reg", "K", "u16", 1, "R/W", "1", "20", 3),
    (258, "Target temperature", "127-mode 178; no H-reg", "°C", "u16", 1, "R/W", "5", "60", 3),
    # 6.3.6 2nd heat generator (R/W)
    (48, "Mixer hysteresis", "shared addr; H-reg 20", "K", "u16", 10, "R/W", "5", "20", 3),
    (227, "Limit temperature parallel", "127-mode 147; H-reg 19", "°C", "s16", 1, "R/W", "-25", "35", 3),
    (228, "Mixer runtime", "127-mode 148; H-reg 37", "min", "u16", 1, "R/W", "30", "85", 3),
    # 6.4.1 lowering/raising time functions (R/W; 272-288 shared across 6.4.x)
    (272, "Time function selector", "shared 6.4.x: 1-6 lower/raise, 7 DHW-block, 8 disinfection, 12 circ, 13 vent", "", "u16", 1, "R/W", "1", "13", 3),
    (273, "Start hour 1", "shared time fn", "hour", "u16", 1, "R/W", "0", "23", 3),
    (274, "Start minute 1", "shared time fn", "min", "u16", 1, "R/W", "0", "59", 3),
    (275, "End hour 1", "shared time fn", "hour", "u16", 1, "R/W", "0", "23", 3),
    (276, "End minute 1", "shared time fn", "min", "u16", 1, "R/W", "0", "59", 3),
    (277, "Start hour 2", "shared time fn", "hour", "u16", 1, "R/W", "0", "23", 3),
    (278, "Start minute 2", "shared time fn", "min", "u16", 1, "R/W", "0", "59", 3),
    (279, "End hour 2", "shared time fn", "hour", "u16", 1, "R/W", "0", "23", 3),
    (280, "End minute 2", "shared time fn", "min", "u16", 1, "R/W", "0", "59", 3),
    (281, "Sunday", "0 yes 1 no 2 time1 3 time2; shared", "", "u16", 1, "R/W", "0", "3", 3),
    (282, "Monday", "shared time fn", "", "u16", 1, "R/W", "0", "3", 3),
    (283, "Tuesday", "shared time fn", "", "u16", 1, "R/W", "0", "3", 3),
    (284, "Wednesday", "shared time fn", "", "u16", 1, "R/W", "0", "3", 3),
    (285, "Thursday", "shared time fn", "", "u16", 1, "R/W", "0", "3", 3),
    (286, "Friday", "shared time fn", "", "u16", 1, "R/W", "0", "3", 3),
    (287, "Saturday", "shared time fn", "", "u16", 1, "R/W", "0", "3", 3),
    (288, "Reduction / increase value", "shared with disinfection temp 60-85, first wins", "K", "u16", 1, "R/W", "0", "19", 3),
    # 6.5 display (R; L/M numbering per wiki)
    (103, "Status reports", "J-reg 43; H-reg 14; values wiki 6.5.1", "", "u16", 1, "R", "0", "30", 3),
    (104, "Heat pump lock", "J-reg 59; H-reg 94; values wiki 6.5.2", "", "u16", 1, "R", "1", "42", 3),
    (105, "Fault messages", "J-reg 42; H-reg 13; values wiki 6.5.3", "", "u16", 1, "R", "1", "31", 3),
    (106, "Sensors", "no J/H-reg; values wiki 6.5.4", "", "u16", 1, "R", "1", "27", 3),
    # 6.6 entrances (coils R; 3/5/6 dup registers, dropped)
    (3, "DHW thermostat", "H-coil 57; dup of reg 3, dropped", "", "u16", 1, "R", "0", "1", 1),
    (4, "Swimming pool thermostat", "H-coil 58", "", "u16", 1, "R", "0", "1", 1),
    (5, "EVU lock", "H-coil 56; dup of reg 5, dropped", "", "u16", 1, "R", "0", "1", 1),
    (6, "External lock", "H-coil 63; dup of reg 6, dropped", "", "u16", 1, "R", "0", "1", 1),
    # 6.7 outputs (coils R)
    (41, "Compressor 1", "H-coil 80", "", "u16", 1, "R", "0", "1", 1),
    (42, "Compressor 2", "H-coil 81", "", "u16", 1, "R", "0", "1", 1),
    (43, "Primary pump (M11) / fan (M2)", "H-coil 82", "", "u16", 1, "R", "0", "1", 1),
    (44, "2nd heat generator (E10)", "H-coil 83", "", "u16", 1, "R", "0", "1", 1),
    (45, "Heating pump (M13)", "H-coil 84", "", "u16", 1, "R", "0", "1", 1),
    (46, "Hot water pump (M18)", "H-coil 85; dup of reg 46, dropped", "", "u16", 1, "R", "0", "1", 1),
    (47, "Mixer (M21) open", "H-coil 86; dup of reg 47, dropped", "", "u16", 1, "R", "0", "1", 1),
    (48, "Mixer (M21) closed", "H-coil 87; dup of reg 48, dropped", "", "u16", 1, "R", "0", "1", 1),
    (49, "Additional circulation pump (M16)", "H-coil 88", "", "u16", 1, "R", "0", "1", 1),
    (50, "Flange heating (E9)", "H-coil 89", "", "u16", 1, "R", "0", "1", 1),
    (51, "Heating pump (M15)", "H-coil 90", "", "u16", 1, "R", "0", "1", 1),
    (52, "Mixer (M22) open", "H-coil 91", "", "u16", 1, "R", "0", "1", 1),
    (53, "Mixer (M22) closed", "H-coil 92; dup of reg 53, dropped", "", "u16", 1, "R", "0", "1", 1),
    (56, "Swimming pool pump (M19)", "H-coil 95", "", "u16", 1, "R", "0", "1", 1),
    (57, "Collective fault message (H5)", "no H-coil", "", "u16", 1, "R", "0", "1", 1),
    (59, "Heating pump (M14)", "H-coil 94", "", "u16", 1, "R", "0", "1", 1),
    (60, "Cooling pump (M17)", "H-coil 99", "", "u16", 1, "R", "0", "1", 1),
    (61, "Heating pump (M20)", "no H-coil", "", "u16", 1, "R", "0", "1", 1),
    (66, "Changeover room thermostats heating/cooling (N9)", "H-coil 96", "", "u16", 1, "R", "0", "1", 1),
    (68, "Primary pump cooling (M12)", "H-coil 98", "", "u16", 1, "R", "0", "1", 1),
    (71, "Solar pump (M23)", "no H-coil; dup of reg 71, dropped", "", "u16", 1, "R", "0", "1", 1),
    # 6.8 time alignment (regs R/W; set-coils W->R/W; 103-106 set-coils dup regs)
    (213, "Hour", "127-mode 133; H-reg 155", "", "u16", 1, "R/W", "0", "23", 3),
    (102, "Set hour", "wiki 'set Sour'; H-coil 130", "", "u16", 1, "R/W", "0", "1", 1),
    (214, "Minute", "127-mode 134; H-reg 156", "", "u16", 1, "R/W", "0", "59", 3),
    (103, "Set minute", "H-coil 131; dup of reg 103, dropped", "", "u16", 1, "R/W", "0", "1", 1),
    (215, "Month", "127-mode 135; H-reg 157", "", "u16", 1, "R/W", "1", "12", 3),
    (105, "Set month", "H-coil 133; dup of reg 105, dropped", "", "u16", 1, "R/W", "0", "1", 1),
    (216, "Weekday", "1 Mon...7 Sun; 127:136; H-reg 158", "", "u16", 1, "R/W", "1", "7", 3),
    (107, "Set weekday", "H-coil 135", "", "u16", 1, "R/W", "0", "1", 1),
    (217, "Day", "127-mode 137; H-reg 159", "", "u16", 1, "R/W", "1", "31", 3),
    (104, "Set day", "H-coil 132; dup of reg 104, dropped", "", "u16", 1, "R/W", "0", "1", 1),
    (218, "Year", "127-mode 138; H-reg 160", "", "u16", 1, "R/W", "0", "99", 3),
    (106, "Set year", "H-coil 134; dup of reg 106, dropped", "", "u16", 1, "R/W", "0", "1", 1),
    # 6.4.2-6.4.5 reuse 272-287 + coils 125/126 (dupes, dropped); 6.4.3
    # disinfection temp shares 288 (60-85C, dropped, 6.4.1 value wins).
    (288, "Disinfection temperature", "shared 208; 60-85C; dup of 288, dropped", "°C", "u16", 1, "R/W", "60", "85", 3),
]


def convert(dst):
    out, seen, skipped = [], set(), 0
    for addr, titel, info, unit, size, factor, mode, mn, mx, fc in DATA:
        if addr in seen:
            skipped += 1  # ponytail: wiki reuses addr (coil/reg, solar/3rd-ckt, time fns)
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
