// components/nibe/nibe.cpp (core loop + router + LE decoder)
#include "nibe.h"
#include "registers.h"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace esphome {
namespace nibe {
static float scale(int32_t raw, int16_t f) { return f ? (float) raw / f : (float) raw; }
void NibeComponent::setup() {
  if (flow_pin_ != nullptr) {
    flow_pin_->setup();
    flow_pin_->digital_write(false);
  }
}
void NibeComponent::tx_(const uint8_t *d, size_t len) {
  if (flow_pin_ != nullptr) flow_pin_->digital_write(true);
  write_array(d, len);
  flush();
  if (flow_pin_ != nullptr) flow_pin_->digital_write(false);
}
void NibeComponent::loop() {
  uint8_t b;
  while (available()) { read_byte(&b); rx_.push_back(b); }
  for (;;) {
    auto it = std::find(rx_.begin(), rx_.end(), 0x5C);
    if (it == rx_.end()) { rx_.clear(); return; }
    if (it != rx_.begin()) rx_.erase(rx_.begin(), it);
    if (rx_.size() < 5) return;
    uint8_t len = rx_[4];
    if (rx_.size() < (size_t) len + 6) return;
    if (calc_crc(rx_.data()) != rx_[len + 5]) {
      send_nack_();
      rx_.erase(rx_.begin());
      continue;
    }
    std::vector<uint8_t> f(rx_.begin(), rx_.begin() + len + 6);
    rx_.erase(rx_.begin(), rx_.begin() + len + 6);
    on_frame_(f.data(), f.size());
  }
}
void NibeComponent::on_frame_(const uint8_t *f, uint8_t n) {
  if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x69 && f[4] == 0x00) {
    if (passive_) return;
    if (!reads_.empty()) { auto r = reads_.front(); reads_.pop(); tx_(r.data(), r.size()); }
    else send_ack_();
  } else if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x6B && f[4] == 0x00) {
    if (passive_) return;
    if (!writes_.empty()) {
      auto w = writes_.front(); writes_.pop();
      uint8_t o[10] = {0xC0, 0x6B, 0x06, (uint8_t)(w.addr & 0xFF), (uint8_t)(w.addr >> 8),
                       (uint8_t)(w.raw & 0xFF), (uint8_t)((w.raw >> 8) & 0xFF),
                       (uint8_t)((w.raw >> 16) & 0xFF), (uint8_t)((w.raw >> 24) & 0xFF), 0};
      o[9] = calc_crc_c0(o);
      tx_(o, 10);
    } else send_ack_();
  } else if (f[3] == 0x68 || f[3] == 0x6A || f[3] == 0x6D) {
    if (f[3] == 0x6D) {
      if (n > 9) {  // model bytes at f[8..n-2] (matches index.js announcement slice)
        model_.assign((const char *) (f + 8), n - 9);
        auto sp = model_.find(' ');
        if (sp != std::string::npos) {
          std::string first = model_.substr(0, sp);
          if (first == "VVM" || first == "SMO" || first == "Tehowatti" || first == "STAR") {
            auto sp2 = model_.find(' ', sp + 1);
            std::string second = model_.substr(sp + 1, sp2 == std::string::npos ? sp2 : sp2 - sp - 1);
            model_ = second.empty() ? first : first + second;
          } else {
            model_.erase(sp);
          }
        }
        auto cut = model_.find_first_of("-,");
        if (cut != std::string::npos) model_.erase(cut);
      }
    } else {
      for (uint8_t i = 5; i + 3 < n - 1;) {
        uint16_t addr = f[i] | ((uint16_t) f[i + 1] << 8);
        const NibeReg *reg = nullptr;
        for (uint16_t k = 0; k < NIBE_COMMON_N; k++)  // ponytail: linear scan, table is ~10 entries
          if (NIBE_COMMON[k].addr == addr) { reg = &NIBE_COMMON[k]; break; }
        if (reg == nullptr) { i += 4; continue; }
        bool wide = (reg->size == NIBE_U32 || reg->size == NIBE_S32);
        uint8_t need = wide ? (f[3] == 0x68 ? 8 : 6) : 4;
        if (i + need > n - 1) break;
        float v;
        if (!wide) {
          uint16_t w = f[i + 2] | ((uint16_t) f[i + 3] << 8);
          int32_t raw = w;
          if (reg->size == NIBE_S8) {  // fixup matches reference
            if (raw > 128 && raw < 32768) raw -= 256;
            else if (raw >= 32768) raw -= 65536;
          } else if (reg->size == NIBE_S16) {
            if (w >= 32768) raw -= 65536;
          }
          v = scale(raw, reg->factor);
        } else {
          uint32_t u = (f[3] == 0x68)
              ? ((uint32_t) f[i + 2] | ((uint32_t) f[i + 3] << 8) | ((uint32_t) f[i + 6] << 16) |
                 ((uint32_t) f[i + 7] << 24))
              : ((uint32_t) f[i + 4] | ((uint32_t) f[i + 5] << 8) | ((uint32_t) f[i + 2] << 16) |
                 ((uint32_t) f[i + 3] << 24));
          v = (reg->size == NIBE_S32) ? scale((int32_t) u, reg->factor)
                                      : (reg->factor ? (float) u / reg->factor : (float) u);
        }
        i += need;
        if ((reg->min != 0 || reg->max != 0) && reg->factor &&  // corrupt -> skip, matches reference
            (v > (float) reg->max / reg->factor || v < (float) reg->min / reg->factor))
          continue;
        on_value(addr, v);  // ponytail: enum maps publish numeric; strings in Task 5
      }
    }
    if (!passive_) send_ack_();
  } else if (f[2] >= 0x19 && f[2] <= 0x1C) {
    // RMU slots (cf. reference-project/backend.js:232-305). TX only here; passive decodes silently.
    if (f[3] == 0x60) {
      if (passive_) return;
      send_ack_();  // ponytail: no RMU queue in MVP, ACK keeps pump happy
      return;
    }
    if (f[3] == 0x62) {
      if (!passive_) send_ack_();
      return;
    }
    if (f[3] == 0x63) {
      if (passive_) return;
      uint8_t r[6] = {0xC0, 0x60, 0x02, 0x63, 0x00, 0x00};
      r[5] = calc_crc_c0(r);  // == 0xC1, matches backend.js:283
      tx_(r, 6);
      return;
    }
    if (f[3] == 0xEE) {
      if (passive_) return;
      const uint8_t ver[7] = {0xC0, 0xEE, 0x03, 0xEE, 0x03, 0x01, 0x00};
      uint8_t r[7];
      memcpy(r, ver, 7);
      r[6] = calc_crc_c0(r);  // == 0xC1, matches backend.js:293
      tx_(r, 7);
      return;
    }
    if (!passive_) send_ack_();
  } else {
    if (!passive_) send_ack_();
  }
}
void NibeComponent::set_poll_registers(const std::vector<uint16_t> &addrs) {
  for (uint16_t a : addrs) {
    uint8_t o[6] = {0xC0, 0x69, 0x02, (uint8_t) (a & 0xFF), (uint8_t) (a >> 8), 0};
    o[5] = calc_crc_c0(o);
    reads_.emplace(o, o + 6);
  }
}
void NibeComponent::on_value(uint16_t addr, float v) {
  for (auto *s : sensors_)
    if (s->get_register() == addr) s->publish_value(v);
  for (auto *n : numbers_)
    if (n->get_register() == addr) n->publish_value(v);
}
void NibeNumber::control(float value) {
  if (parent_ == nullptr) return;
  float v = value;
  int32_t raw;
  const NibeReg *reg = nullptr;
  for (uint16_t k = 0; k < NIBE_COMMON_N; k++)  // ponytail: linear scan, table is ~10 entries
    if (NIBE_COMMON[k].addr == addr_) { reg = &NIBE_COMMON[k]; break; }
  if (reg != nullptr && reg->factor) {
    raw = (int32_t) std::lround(v * reg->factor);
    if (reg->min != 0 || reg->max != 0) {  // clamp to merged R/W range
      if (raw < reg->min) raw = reg->min;
      if (raw > reg->max) raw = reg->max;
      v = (float) raw / reg->factor;
    }
  } else {
    raw = (int32_t) std::lround(v);  // unknown register: factor 1
  }
  parent_->queue_write(addr_, raw);
  publish_state(v);
}
}  // namespace nibe
}  // namespace esphome
