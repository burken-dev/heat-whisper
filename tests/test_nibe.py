# tests/test_nibe.py — seam contract for the Nibe wire protocol extract.
# RED test for the lazy fix: Nibe quirks (5C framing, XOR CRC, C0 poll/write
# frames, 0x6D model parse, RMU fixed replies, <20000 write guard) must live in
# components/heatwhisper/nibe.h (no ESPHome deps, host-compilable) and
# heatwhisper.{h,cpp} must delegate to it.
import os
import subprocess
import tempfile

REPO = os.path.join(os.path.dirname(__file__), "..")
NIBE_H = os.path.join(REPO, "components", "heatwhisper", "nibe.h")

HARNESS = r"""
#include "nibe.h"
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace esphome::heatwhisper::nibe;
int main() {
  // CRC vectors (see tests/vectors.py)
  uint8_t read[] = {0x5C,0x00,0xC0,0x69,0x02,0x44,0x9C,0x73};
  assert(calc_crc_5c(read) == 0x73);
  read[7] = 0x00;
  assert(calc_crc_5c(read) != 0x00);
  uint8_t wr[] = {192,107,6,115,176,1,0,0,0,111};
  assert(calc_crc_c0(wr) == 0x6F);
  // poll / write encoders
  uint8_t poll[6];
  encode_poll(40004, poll);
  uint8_t exp_poll[] = {0xC0,0x69,0x02,0x44,0x9C,0x73};
  assert(memcmp(poll, exp_poll, 6) == 0);
  uint8_t enc[10];
  encode_write(45171, 1, enc);
  assert(memcmp(enc, wr, 10) == 0);
  // writability guard (RMU range)
  assert(!is_writable(19999));
  assert(is_writable(20000));
  // model parse (0x6D announce payloads)
  uint8_t vvm[] = {0x5C,0x00,0x20,0x6D,0x0A,0x00,0x01,0x02,0x56,0x56,0x4D,0x20,0x35,0x30,0x30,0x1C};
  assert(parse_model(vvm, sizeof(vvm)) == "VVM500");
  uint8_t f750[] = {0x5C,0x00,0x20,0x6D,0x08,0x00,0x01,0x02,0x46,0x37,0x35,0x30,0x20,0x12};
  assert(parse_model(f750, sizeof(f750)) == "F750");
  // RMU fixed replies (backend.js:283,293)
  uint8_t r63[6], exp63[] = {0xC0,0x60,0x02,0x63,0x00,0xC1};
  build_rmu63(r63);
  assert(memcmp(r63, exp63, 6) == 0);
  uint8_t rver[7], expver[] = {0xC0,0xEE,0x03,0xEE,0x03,0x01,0xC1};
  build_rmu_version(rver);
  assert(memcmp(rver, expver, 7) == 0);
  printf("nibe harness ok\n");
  return 0;
}
"""


def _compile_and_run():
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
        assert "nibe harness ok" in p.stdout


def test_nibe_header_compiles_and_passes_vectors():
    assert os.path.exists(NIBE_H), "components/heatwhisper/nibe.h missing"
    _compile_and_run()


def test_nibe_header_has_no_esphome_deps():
    src = open(NIBE_H).read()
    assert "esphome" not in src.lower() or "namespace esphome" in src
    for bad in ("UARTDevice", "ESP_LOG", "App.", "Component.h", "uart/uart.h"):
        assert bad not in src, f"nibe.h must stay host-compilable, found {bad}"


def test_heatwhisper_delegates_to_nibe():
    h = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.h")).read()
    cpp = open(os.path.join(REPO, "components", "heatwhisper", "heatwhisper.cpp")).read()
    assert '#include "nibe.h"' in h or '#include "nibe.h"' in cpp
    for sym in ("nibe::calc_crc_5c", "nibe::calc_crc_c0", "nibe::encode_poll",
                "nibe::encode_write", "nibe::parse_model", "nibe::is_writable"):
        assert sym in (h + cpp), f"heatwhisper must delegate to {sym}"
