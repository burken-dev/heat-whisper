// components/heatwhisper/nibe.h — Nibe wire quirks, no ESPHome deps.
// ponytail: host-compilable seam; brand #2 gets its own header behind a Bus
// interface, this file stays untouched. Verbatim logic moved from
// heatwhisper.{h,cpp} so behavior is identical.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string>
namespace esphome {
namespace heatwhisper {
namespace nibe {
// 5C-framed pump frames [5C,X,ADDR,CMD,LEN,DATA,CHK], LEN at [4].
inline uint8_t calc_crc_5c(const uint8_t *d) {
  uint8_t c = 0;
  for (int i = 2; i < d[4] + 5; i++) c ^= d[i];
  return c;
}
// C0-framed slave frames [C0,CMD,LEN,DATA,CHK], LEN at [2].
inline uint8_t calc_crc_c0(const uint8_t *d) {
  uint8_t c = 0;
  for (int i = 0; i < d[2] + 3; i++) c ^= d[i];
  return c;
}
// RMU 1xxxx range is read-only on the wire; writes are dropped.
inline bool is_writable(uint16_t addr) { return addr >= 20000; }
// C0 69 02 lo hi CRC — answer to a 0x69 read-poll slot.
inline void encode_poll(uint16_t addr, uint8_t out[6]) {
  out[0] = 0xC0;
  out[1] = 0x69;
  out[2] = 0x02;
  out[3] = (uint8_t)(addr & 0xFF);
  out[4] = (uint8_t)(addr >> 8);
  out[5] = calc_crc_c0(out);
}
// C0 6B 06 lo hi raw[4] CRC — answer to a 0x6B write-poll slot.
inline void encode_write(uint16_t addr, int32_t raw, uint8_t out[10]) {
  out[0] = 0xC0;
  out[1] = 0x6B;
  out[2] = 0x06;
  out[3] = (uint8_t)(addr & 0xFF);
  out[4] = (uint8_t)(addr >> 8);
  out[5] = (uint8_t)(raw & 0xFF);
  out[6] = (uint8_t)((raw >> 8) & 0xFF);
  out[7] = (uint8_t)((raw >> 16) & 0xFF);
  out[8] = (uint8_t)((raw >> 24) & 0xFF);
  out[9] = calc_crc_c0(out);
}
// Model bytes at f[8..n-2] of a 0x6D announcement (cf. index.js slice).
inline std::string parse_model(const uint8_t *f, size_t n) {
  std::string model;
  if (n > 9) {
    model.assign((const char *)(f + 8), n - 9);
    auto sp = model.find(' ');
    if (sp != std::string::npos) {
      std::string first = model.substr(0, sp);
      if (first == "VVM" || first == "SMO" || first == "Tehowatti" || first == "STAR") {
        auto sp2 = model.find(' ', sp + 1);
        std::string second = model.substr(sp + 1, sp2 == std::string::npos ? sp2 : sp2 - sp - 1);
        model = second.empty() ? first : first + second;
      } else {
        model.erase(sp);
      }
    }
    auto cut = model.find_first_of("-,");
    if (cut != std::string::npos) model.erase(cut);
  }
  return model;
}
// RMU fixed replies (cf. reference-project/backend.js:283,293).
inline void build_rmu63(uint8_t out[6]) {
  out[0] = 0xC0;
  out[1] = 0x60;
  out[2] = 0x02;
  out[3] = 0x63;
  out[4] = 0x00;
  out[5] = calc_crc_c0(out);  // == 0xC1
}
inline void build_rmu_version(uint8_t out[7]) {
  out[0] = 0xC0;
  out[1] = 0xEE;
  out[2] = 0x03;
  out[3] = 0xEE;
  out[4] = 0x03;
  out[5] = 0x01;
  out[6] = calc_crc_c0(out);  // == 0xC1
}
}  // namespace nibe
}  // namespace heatwhisper
}  // namespace esphome
