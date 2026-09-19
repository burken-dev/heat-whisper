// components/heatwhisper/heatwhisper.h
#pragma once
#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/number/number.h"
#include "esphome/components/select/select.h"
#include "esphome/components/switch/switch.h"
#include "esphome/core/preferences.h"
#include "esphome/core/application.h"
#include "catalog.h"
#include <queue>
#include <string>
#include <vector>
// ponytail: must match SIZE_CODES in registers.py
namespace esphome {
namespace heatwhisper {
enum HwSize : uint8_t { HW_U8 = 0, HW_S8, HW_U16, HW_S16, HW_U32, HW_S32 };
struct WriteRequest { uint16_t addr; int32_t raw; };
class HeatWhisperComponent;  // entities hold a parent pointer only
class HeatWhisperSensor : public esphome::sensor::Sensor, public esphome::Component {
 public:
  void set_parent(HeatWhisperComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void publish_value(float v) { publish_state(v); }
 protected:
  HeatWhisperComponent *parent_{nullptr};
  uint16_t addr_{0};
};
class HeatWhisperNumber : public esphome::number::Number, public esphome::Component {
 public:
  void set_parent(HeatWhisperComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void publish_value(float v) { publish_state(v); }
  void control(float value) override;  // clamp to HW_META range, queue_write
 protected:
  HeatWhisperComponent *parent_{nullptr};
  uint16_t addr_{0};
};
class HeatWhisperSelect : public esphome::select::Select, public esphome::Component {
 public:
  void set_parent(HeatWhisperComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void set_mapping(const std::vector<int32_t> &raws) { raws_ = raws; }
  void set_labels(const std::vector<std::string> &labels);  // owns strings, publishes traits options
  void publish_raw(int32_t raw);  // raw->index fan-out; unknown raws skipped
  void control(const std::string &value) override;
 protected:
  HeatWhisperComponent *parent_{nullptr};
  uint16_t addr_{0};
  std::vector<int32_t> raws_;
  std::vector<std::string> labels_;  // owns option strings; traits hold pointers into these
};
class HeatWhisperSwitch : public esphome::switch_::Switch, public esphome::Component {
 public:
  void set_parent(HeatWhisperComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void write_state(bool state) override;
 protected:
  HeatWhisperComponent *parent_{nullptr};
  uint16_t addr_{0};
};
struct HeatWhisperSelection {
  uint32_t version{1};
  uint16_t count{0};
  uint16_t addrs[50];
};
// ponytail: brief said 4+2+2*50=106, but alignment pads the struct to 108
// (verified with host g++); NVS save/load use sizeof consistently so the
// trailing pad bytes are harmless.
static_assert(sizeof(HeatWhisperSelection{}) == 108, "HeatWhisperSelection layout");
static_assert(50 == HW_MAX_SELECTION, "selection slots match catalog cap");
class HeatWhisperComponent : public esphome::Component, public esphome::uart::UARTDevice {
  public:
  void set_slave_address(uint8_t a) { peer_ = a; }
  void set_protocol_is_modbus(bool m) { modbus_ = m; }
  void set_peer_address(uint8_t a) { peer_ = a; }
  void set_model(const std::string &m) { model_ = m; }
  void set_passive(bool p) { passive_ = p; }
  void set_flow_control_pin(esphome::GPIOPin *p) { flow_pin_ = p; }
  void setup() override;
  void set_poll_registers(const std::vector<uint16_t> &addrs);
  void ensure_polled(uint16_t addr);
  void queue_write(uint16_t addr, int32_t raw) {
    if (addr < 20000) { ESP_LOGW("heatwhisper", "Dropping RMU-range write addr %u", addr); return; }
    if (writes_.size() >= 4) { ESP_LOGW("heatwhisper", "Write queue full, dropping oldest"); writes_.pop(); }
    writes_.push({addr, raw});
  }
  void add_sensor(HeatWhisperSensor *s) { sensors_.push_back(s); ensure_polled(s->get_register()); }
  void add_number(HeatWhisperNumber *n) { numbers_.push_back(n); ensure_polled(n->get_register()); }
  void add_select(HeatWhisperSelect *s) { selects_.push_back(s); ensure_polled(s->get_register()); }
  void add_switch(HeatWhisperSwitch *s) { switches_.push_back(s); ensure_polled(s->get_register()); }
  bool load_selection(HeatWhisperSelection *out);
  bool save_selection(const uint16_t *addrs, uint16_t n);
  void create_entities();
  virtual void on_value(uint16_t addr, float v);  // fans out to entities (Task 5)
  const std::string &get_model() const { return model_; }
  bool is_modbus() const { return modbus_; }
  void loop() override;
  static uint16_t crc16_modbus(const uint8_t *d, size_t n);
  // calc_crc_nibe: 5C-framed pump frames [5C,X,ADDR,CMD,LEN,DATA,CHK], LEN at [4].
  static uint8_t calc_crc_nibe(const uint8_t *d) {
    uint8_t c = 0;
    for (int i = 2; i < d[4] + 5; i++) c ^= d[i];
    return c;
  }
  // calc_crc_c0_nibe: C0-framed slave frames [C0,CMD,LEN,DATA,CHK], LEN at [2].
  static uint8_t calc_crc_c0_nibe(const uint8_t *d) {
    uint8_t c = 0;
    for (int i = 0; i < d[2] + 3; i++) c ^= d[i];
    return c;
  }
 protected:
  void on_frame_(const uint8_t *f, uint8_t n);
  void poll_one_();
  void on_modbus_frame_(const uint8_t *f, size_t n);
  uint8_t write_fc_for_model_() const;
  bool decode_modbus_(uint16_t addr, const uint16_t *words, uint8_t nwords, float *out) const;
  void tx_(const uint8_t *d, size_t len);
  void send_ack_() { uint8_t b = 0x06; tx_(&b, 1); }
  void send_nack_() { uint8_t b = 0x15; tx_(&b, 1); }
  uint8_t peer_{0x19};  // renamed from slave_: Nibe RMU addr or Modbus peer addr
  bool modbus_{false};
  uint32_t last_poll_{0};
  uint8_t retry_{0};
  std::vector<uint16_t> polled_;
  size_t poll_idx_{0};
  uint16_t pending_addr_{0};
  uint8_t pending_fc_{0};
  uint8_t pending_cnt_{0};
  bool pending_{false};
  bool passive_{false};
  esphome::GPIOPin *flow_pin_{nullptr};
  std::string model_;
  std::vector<uint8_t> rx_;
  std::vector<uint8_t> mrx_;
  std::queue<WriteRequest> writes_;
  std::queue<std::vector<uint8_t>> reads_;
  std::vector<HeatWhisperSensor *> sensors_;
  std::vector<HeatWhisperNumber *> numbers_;
  std::vector<HeatWhisperSelect *> selects_;
  std::vector<HeatWhisperSwitch *> switches_;
};
}  // namespace heatwhisper
}  // namespace esphome
