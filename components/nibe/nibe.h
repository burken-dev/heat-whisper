// components/nibe/nibe.h
#pragma once
#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include <queue>
#include <vector>
struct WriteRequest { uint16_t addr; int32_t raw; };
class NibeComponent : public esphome::Component, public esphome::uart::UARTDevice {
 public:
  void set_slave_address(uint8_t a) { slave_ = a; }
  void set_passive(bool p) { passive_ = p; }
  void queue_write(uint16_t addr, int32_t raw) { writes_.push({addr, raw}); }
  void loop() override;
  // calc_crc: 5C-framed pump frames [5C,X,ADDR,CMD,LEN,DATA,CHK], LEN at [4].
  static uint8_t calc_crc(const uint8_t *d) {
    uint8_t c = 0;
    for (int i = 2; i < d[4] + 5; i++) c ^= d[i];
    return c;
  }
  // calc_crc_c0: C0-framed slave frames [C0,CMD,LEN,DATA,CHK], LEN at [2].
  static uint8_t calc_crc_c0(const uint8_t *d) {
    uint8_t c = 0;
    for (int i = 0; i < d[2] + 3; i++) c ^= d[i];
    return c;
  }
 protected:
  void on_frame_(const uint8_t *f, uint8_t n);
  void send_ack_() { uint8_t b = 0x06; write_array(&b, 1); }
  void send_nack_() { uint8_t b = 0x15; write_array(&b, 1); }
  uint8_t slave_{0x19};
  bool passive_{false};
  std::vector<uint8_t> rx_;
  std::queue<WriteRequest> writes_;
  std::queue<std::vector<uint8_t>> reads_;
};
