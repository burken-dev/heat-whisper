# tests/test_safety.py — host C++ unit tests for safety.h, register tier
# classification tests, catalog check, and picker UI / NVS migration wiring.
import json
import os
import re
import subprocess
import tempfile

REPO = os.path.join(os.path.dirname(__file__), "..")
SAFETY_H = os.path.join(REPO, "components", "heatwhisper", "safety.h")
HDR = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")
CPP = os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")
CAT_H = os.path.join(REPO, "components", "heatwhisper", "catalog.h")
MDIR = os.path.join(REPO, "components", "heatwhisper", "models")

HARNESS = r"""
#include "safety.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <limits>
#include <string>
using namespace esphome::heatwhisper;

static bool dummy_known(uint16_t a) {
  return a == 40004 || a == 47011 || a == 47019 || a == 47099 || a == 48132 ||
         (a >= 40000 && a <= 40100);
}

int main() {
  // 1. Struct layout invariants
  static_assert(sizeof(HeatWhisperSelectionV1{}) == 108, "v1 size");
  static_assert(sizeof(HeatWhisperSelection{}) == 116, "v2 size");

  // 2. ro_mask bit operations across 32-bit boundary and out-of-bounds slots
  {
    HeatWhisperSelection s{};
    assert(s.version == 2);
    s.set_ro(0, true);
    s.set_ro(1, true);
    s.set_ro(31, true);
    s.set_ro(32, true);
    s.set_ro(49, true);
    s.set_ro(50, true);  // out-of-bounds ignored
    s.set_ro(63, true);  // out-of-bounds ignored
    assert(s.is_ro(0) && s.is_ro(1) && s.is_ro(31) && s.is_ro(32) && s.is_ro(49));
    assert(!s.is_ro(2) && !s.is_ro(30) && !s.is_ro(48) && !s.is_ro(50) && !s.is_ro(63));
    uint64_t expected = (uint64_t{1} << 0) | (uint64_t{1} << 1) | (uint64_t{1} << 31) |
                        (uint64_t{1} << 32) | (uint64_t{1} << 49);
    assert(s.ro_mask() == expected);
    s.set_ro(31, false);
    s.set_ro(49, false);
    assert(!s.is_ro(31) && !s.is_ro(49));
    assert(s.is_ro(32));
  }

  // 3. effective_tier
  {
    assert(safety::effective_tier(10001, 1) == HW_TIER_RO);
    assert(safety::effective_tier(19999, 3) == HW_TIER_RO);
    assert(safety::effective_tier(40004, 0) == HW_TIER_RO);
    assert(safety::effective_tier(47011, 1) == HW_TIER_STANDARD);
    assert(safety::effective_tier(47054, 2) == HW_TIER_ADVANCED);
    assert(safety::effective_tier(47019, 3) == HW_TIER_HIGH_RISK);
    assert(safety::effective_tier(47019, 99) == HW_TIER_HIGH_RISK);
  }

  // 4. is_unclamped & resolve_kind
  {
    assert(safety::is_unclamped(47099, HW_TIER_HIGH_RISK, 0, 0, -1));
    assert(!safety::is_unclamped(48132, HW_TIER_STANDARD, 0, 0, 3));  // select hint
    assert(!safety::is_unclamped(47371, HW_TIER_STANDARD, 0, 0, 2));  // switch hint
    assert(!safety::is_unclamped(47011, HW_TIER_STANDARD, -10, 10, -1));
    assert(!safety::is_unclamped(40004, HW_TIER_RO, 0, 0, -1));
    assert(!safety::is_unclamped(2050, HW_TIER_STANDARD, 0, 0, -1));  // < 20000

    assert(safety::resolve_kind(10001, HW_TIER_STANDARD, 1, false) == 0);
    assert(safety::resolve_kind(40004, HW_TIER_RO, -1, false) == 0);
    assert(safety::resolve_kind(47011, HW_TIER_STANDARD, -1, true) == 0);
    assert(safety::resolve_kind(47011, HW_TIER_STANDARD, -1, false) == 1);
    assert(safety::resolve_kind(47041, HW_TIER_STANDARD, 3, true) == 0);
    assert(safety::resolve_kind(47041, HW_TIER_STANDARD, 3, false) == 3);
    assert(safety::resolve_kind(47371, HW_TIER_STANDARD, 2, false) == 2);
  }

  // 5. type_raw_bounds & number_raw_bounds
  {
    int32_t lo = 0, hi = 0;
    safety::type_raw_bounds(0, &lo, &hi); assert(lo == 0 && hi == 255);
    safety::type_raw_bounds(1, &lo, &hi); assert(lo == -128 && hi == 127);
    safety::type_raw_bounds(2, &lo, &hi); assert(lo == 0 && hi == 65535);
    safety::type_raw_bounds(3, &lo, &hi); assert(lo == -32768 && hi == 32767);
    safety::type_raw_bounds(4, &lo, &hi); assert(lo == 0 && hi == 1000000);
    safety::type_raw_bounds(5, &lo, &hi); assert(lo == -1000000 && hi == 1000000);
    safety::type_raw_bounds(99, &lo, &hi); assert(lo == -32768 && hi == 32767);

    // Clamped catalog range overrides type bounds
    safety::number_raw_bounds(3, -10, 10, &lo, &hi);
    assert(lo == -10 && hi == 10);
    // Unclamped falls back to type bounds
    safety::number_raw_bounds(0, 0, 0, &lo, &hi);
    assert(lo == 0 && hi == 255);
  }

  // 6. clamp_raw_from_float (scaled, unclamped, extreme & NaN safety)
  {
    float cv = 0.0f;
    assert(safety::clamp_raw_from_float(20.5f, 10, 3, 50, 800, &cv) == 205);
    assert(std::fabs(cv - 20.5f) < 1e-5f);
    assert(safety::clamp_raw_from_float(99.0f, 10, 3, 50, 800, &cv) == 800);
    assert(std::fabs(cv - 80.0f) < 1e-5f);

    // Unclamped u8 (factor 10 -> 0.0..25.5)
    assert(safety::clamp_raw_from_float(-5.0f, 10, 0, 0, 0, &cv) == 0);
    assert(std::fabs(cv - 0.0f) < 1e-5f);
    assert(safety::clamp_raw_from_float(99.0f, 10, 0, 0, 0, &cv) == 255);
    assert(std::fabs(cv - 25.5f) < 1e-5f);

    // Unclamped s8, s16, u32 with extreme floats / NaN
    assert(safety::clamp_raw_from_float(-1e20f, 1, 1, 0, 0, &cv) == -128);
    assert(safety::clamp_raw_from_float(1e20f, 1, 3, 0, 0, &cv) == 32767);
    assert(safety::clamp_raw_from_float(1e20f, 1, 4, 0, 0, &cv) == 1000000);
    assert(safety::clamp_raw_from_float(std::numeric_limits<float>::quiet_NaN(), 1, 1, 0, 0, &cv) == -128);
  }

  // 7. parse_selection_csv
  {
    uint16_t addrs[50]{};
    uint64_t mask = 99;
    uint16_t cnt = 99;
    std::string bad;

    // Empty CSV
    assert(safety::parse_selection_csv("", dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::OK);
    assert(cnt == 0 && mask == 0);

    // Plain + :r/:ro/:w/:rw + dedupe preserving first occurrence
    assert(safety::parse_selection_csv(
               "40004,47011:r,47019:ro,48132:w,47099:rw,47011:w",
               dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::OK);
    assert(cnt == 5);
    assert(addrs[0] == 40004 && addrs[1] == 47011 && addrs[2] == 47019 &&
           addrs[3] == 48132 && addrs[4] == 47099);
    assert(mask == ((uint64_t{1} << 1) | (uint64_t{1} << 2)));

    // Dedupe happens before cap check: 50 unique + duplicate at end succeeds
    std::string csv50;
    for (uint16_t a = 40000; a < 40050; a++) {
      if (!csv50.empty()) csv50 += ',';
      csv50 += std::to_string(a);
    }
    std::string csv50_dupe = csv50 + ",40000:r";
    assert(safety::parse_selection_csv(csv50_dupe, dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::OK);
    assert(cnt == 50);

    // 51 unique triggers TOO_MANY
    std::string csv51 = csv50 + ",40050";
    assert(safety::parse_selection_csv(csv51, dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::TOO_MANY);

    // Invalid suffix / bad tokens / unknown addr
    assert(safety::parse_selection_csv("47011:x", dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::BAD_TOKEN);
    assert(safety::parse_selection_csv("47011:r:extra", dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::BAD_TOKEN);
    assert(safety::parse_selection_csv("+47011", dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::BAD_TOKEN);
    assert(safety::parse_selection_csv("0", dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::BAD_TOKEN);
    assert(safety::parse_selection_csv("65536", dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::BAD_TOKEN);
    assert(safety::parse_selection_csv("49999", dummy_known, addrs, &mask, &cnt, 50, &bad) ==
           safety::SelectionParseError::UNKNOWN_ADDR);
    assert(bad == "49999");
  }

  // 8. migrate_v1_to_v2
  {
    HeatWhisperSelectionV1 v1{};
    v1.version = 1;
    v1.count = 4;
    v1.addrs[0] = 40004;  // RO sensor
    v1.addrs[1] = 47011;  // clamped R/W
    v1.addrs[2] = 47099;  // unclamped R/W (no hint) -> migrated to RO!
    v1.addrs[3] = 48132;  // unclamped 0/0 in catalog, but select hint -> stays writable!

    HeatWhisperSelection v2{};
    safety::migrate_v1_to_v2(v1, &v2, [](uint16_t a) {
      if (a == 47099) return safety::is_unclamped(a, HW_TIER_HIGH_RISK, 0, 0, -1);
      if (a == 48132) return safety::is_unclamped(a, HW_TIER_STANDARD, 0, 0, 3);
      if (a == 47011) return safety::is_unclamped(a, HW_TIER_STANDARD, -10, 10, -1);
      return safety::is_unclamped(a, HW_TIER_RO, 0, 0, -1);
    });
    assert(v2.version == 2 && v2.count == 4);
    assert(v2.addrs[0] == 40004 && v2.addrs[1] == 47011 &&
           v2.addrs[2] == 47099 && v2.addrs[3] == 48132);
    assert(!v2.is_ro(0));
    assert(!v2.is_ro(1));
    assert(v2.is_ro(2));
    assert(!v2.is_ro(3));
  }

  printf("safety harness ok\n");
  return 0;
}
"""


def test_safety_header_compiles_and_passes_vectors():
    assert os.path.exists(SAFETY_H), "components/heatwhisper/safety.h missing"
    d = os.path.join(REPO, "components", "heatwhisper")
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "harness.cpp")
        exe = os.path.join(td, "harness")
        with open(src, "w") as fh:
            fh.write(HARNESS)
        p = subprocess.run(
            ["g++", "-std=c++17", "-Wall", "-Werror", src, "-o", exe, f"-I{d}"],
            capture_output=True, text=True)
        assert p.returncode == 0, f"compile failed:\n{p.stderr}"
        p = subprocess.run([exe], capture_output=True, text=True)
        assert p.returncode == 0, f"harness failed:\n{p.stdout}\n{p.stderr}"
        assert "safety harness ok" in p.stdout


def test_safety_header_has_no_esphome_deps():
    src = open(SAFETY_H).read()
    for bad in ("UARTDevice", "ESP_LOG", "App.", "Component.h", "esphome/"):
        assert bad not in src, f"safety.h must stay host-compilable, found {bad}"


def test_curated_tier_sets_valid_and_disjoint():
    from components.heatwhisper.registers import (
        DEFAULT_ENABLED, HIGH_RISK_REGS, STANDARD_CONTROL_REGS,
        TIER_ADVANCED, TIER_HIGH_RISK, TIER_RO, TIER_STANDARD,
        _by_reg, register_tier,
    )
    assert STANDARD_CONTROL_REGS
    assert HIGH_RISK_REGS
    assert not (STANDARD_CONTROL_REGS & HIGH_RISK_REGS)

    models = {
        f[:-5]: json.load(open(os.path.join(MDIR, f)))
        for f in sorted(os.listdir(MDIR)) if f.endswith(".json")
    }
    all_addrs = {int(r["register"]) for regs in models.values() for r in regs}
    assert not (STANDARD_CONTROL_REGS - all_addrs)
    assert not (HIGH_RISK_REGS - all_addrs)

    by_reg = _by_reg(models)
    for addr in DEFAULT_ENABLED:
        r = by_reg[str(addr)]
        if r.get("mode") == "R/W":
            assert register_tier(addr, "R/W") == TIER_STANDARD, addr
        else:
            assert register_tier(addr, "R") == TIER_RO, addr

    assert register_tier(40004, "R") == TIER_RO
    for a in (47011, 47041, 48132):
        assert register_tier(a, "R/W") == TIER_STANDARD, a
    for a in (47054, 49999):
        assert register_tier(a, "R/W") == TIER_ADVANCED, a
    for a in (47019, 47214, 47276, 47103, 47381, 47050, 47365, 48852):
        assert register_tier(a, "R/W") == TIER_HIGH_RISK, a


def test_catalog_header_has_all_tiers_and_nonzero_strs():
    cat = open(CAT_H).read()
    meta_block = cat.split("HW_META[] = {", 1)[1].split("};", 1)[0]
    tiers = {int(m.group(1)) for m in re.finditer(r"\{\d+,-?\d+,\d+,(\d+),", meta_block)}
    assert tiers == {0, 1, 2, 3}, f"expected tiers {{0,1,2,3}}, got {tiers}"

    strs_block = cat.split("HW_STRS[] = {", 1)[1].split("};", 1)[0]
    nonzero = re.search(r"\{\d+,[1-9]\d*,[1-9]\d*,[1-9]\d*\}", strs_block)
    assert nonzero is not None, "HW_STRS lost non-zero unit/device_class indices"


def test_heatwhisper_wires_safety_and_picker_ui():
    h = open(HDR).read()
    cpp = open(CPP).read()
    assert '#include "safety.h"' in h
    assert "uint64_t ro_mask = 0" in h

    assert "HW_SEL_V2_TYPE" in cpp
    assert "safety::migrate_v1_to_v2" in cpp
    assert "safety::resolve_kind" in cpp
    assert "safety::number_raw_bounds" in cpp
    assert "safety::clamp_raw_from_float" in cpp
    assert "safety::parse_selection_csv" in cpp

    lj = cpp.split("HeatWhisperPickerHandler::list_json_")[1].split("HeatWhisperPickerHandler::handle_save_")[0]
    assert '\\"tier\\"' in lj and '\\"ro\\"' in lj and '\\"uncl\\"' in lj

    html = cpp.split("HW_PICKER_HTML[] =")[1].split("bool HeatWhisperPickerHandler::canHandle")[0]
    for needle in ('id="adv"', 'id="tf"', 'Read-only (sensor)', ':r', 'confirm('):
        assert needle in html, f"missing picker UI element/logic: {needle}"
