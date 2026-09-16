// components/nibe/nibe.cpp (core loop + router)
#include "nibe.h"
#include <algorithm>
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
  if (passive_) return;  // ponytail: decode wired in Task 4; passive reuses it
  if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x69 && f[4] == 0x00) {
    if (!reads_.empty()) { auto r = reads_.front(); reads_.pop(); write_array(r.data(), r.size()); }
    else send_ack_();
  } else if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x6B && f[4] == 0x00) {
    if (!writes_.empty()) {
      auto w = writes_.front(); writes_.pop();
      uint8_t o[10] = {0xC0, 0x6B, 0x06, (uint8_t)(w.addr & 0xFF), (uint8_t)(w.addr >> 8),
                       (uint8_t)(w.raw & 0xFF), (uint8_t)((w.raw >> 8) & 0xFF),
                       (uint8_t)((w.raw >> 16) & 0xFF), (uint8_t)((w.raw >> 24) & 0xFF), 0};
      o[9] = calc_crc(o);
      write_array(o, 10);
    } else send_ack_();
  } else if (f[3] == 0x68 || f[3] == 0x6A || f[3] == 0x6D) {
    send_ack_();  // decode + publish in Task 4
  } else {
    send_ack_();
  }
}
