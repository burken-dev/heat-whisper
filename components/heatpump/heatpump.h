// components/heatpump/heatpump.h
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
namespace heatpump {
enum HpSize : uint8_t { HP_U8 = 0, HP_S8, HP_U16, HP_S16, HP_U32, HP_S32 };
struct WriteRequest { uint16_t addr; int32_t raw; };
class HeatpumpComponent;  // entities hold a parent pointer only
class HeatpumpSensor : public esphome::sensor::Sensor, public esphome::Component {
 public:
  void set_parent(HeatpumpComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void publish_value(float v) { publish_state(v); }
 protected:
  HeatpumpComponent *parent_{nullptr};
  uint16_t addr_{0};
};
class HeatpumpNumber : public esphome::number::Number, public esphome::Component {
 public:
  void set_parent(HeatpumpComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void publish_value(float v) { publish_state(v); }
  void control(float value) override;  // clamp to HP_META range, queue_write
 protected:
  HeatpumpComponent *parent_{nullptr};
  uint16_t addr_{0};
};
class HeatpumpSelect : public esphome::select::Select, public esphome::Component {
 public:
  void set_parent(HeatpumpComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void set_mapping(const std::vector<int32_t> &raws) { raws_ = raws; }
  void set_labels(const std::vector<std::string> &labels);  // owns strings, publishes traits options
  void publish_raw(int32_t raw);  // raw->index fan-out; unknown raws skipped
  void control(const std::string &value) override;
 protected:
  HeatpumpComponent *parent_{nullptr};
  uint16_t addr_{0};
  std::vector<int32_t> raws_;
  std::vector<std::string> labels_;  // owns option strings; traits hold pointers into these
};
class HeatpumpSwitch : public esphome::switch_::Switch, public esphome::Component {
 public:
  void set_parent(HeatpumpComponent *p) { parent_ = p; }
  void set_register(uint16_t a) { addr_ = a; }
  uint16_t get_register() const { return addr_; }
  void write_state(bool state) override;
 protected:
  HeatpumpComponent *parent_{nullptr};
  uint16_t addr_{0};
};
struct HeatpumpSelection {
  uint32_t version{1};
  uint16_t count{0};
  uint16_t addrs[50];
};
// ponytail: brief said 4+2+2*50=106, but alignment pads the struct to 108
// (verified with host g++); NVS save/load use sizeof consistently so the
// trailing pad bytes are harmless.
static_assert(sizeof(HeatpumpSelection{}) == 108, "HeatpumpSelection layout");
static_assert(50 == HP_MAX_SELECTION, "selection slots match catalog cap");
class HeatpumpComponent : public esphome::Component, public esphome::uart::UARTDevice {
  public:
  void set_slave_address(uint8_t a) { slave_ = a; }
  void set_passive(bool p) { passive_ = p; }
  void set_flow_control_pin(esphome::GPIOPin *p) { flow_pin_ = p; }
  void setup() override;
  void set_poll_registers(const std::vector<uint16_t> &addrs);
  void ensure_polled(uint16_t addr);
  void queue_write(uint16_t addr, int32_t raw) {
    if (addr < 20000) { ESP_LOGW("heatpump", "Dropping RMU-range write addr %u", addr); return; }
    if (writes_.size() >= 4) { ESP_LOGW("heatpump", "Write queue full, dropping oldest"); writes_.pop(); }
    writes_.push({addr, raw});
  }
  void add_sensor(HeatpumpSensor *s) { sensors_.push_back(s); ensure_polled(s->get_register()); }
  void add_number(HeatpumpNumber *n) { numbers_.push_back(n); ensure_polled(n->get_register()); }
  void add_select(HeatpumpSelect *s) { selects_.push_back(s); ensure_polled(s->get_register()); }
  void add_switch(HeatpumpSwitch *s) { switches_.push_back(s); ensure_polled(s->get_register()); }
  bool load_selection(HeatpumpSelection *out);
  bool save_selection(const uint16_t *addrs, uint16_t n);
  void create_entities();
  virtual void on_value(uint16_t addr, float v);  // fans out to entities (Task 5)
  const std::string &get_model() const { return model_; }
  void loop() override;
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
  void tx_(const uint8_t *d, size_t len);
  void send_ack_() { uint8_t b = 0x06; tx_(&b, 1); }
  void send_nack_() { uint8_t b = 0x15; tx_(&b, 1); }
  uint8_t slave_{0x19};
  bool passive_{false};
  esphome::GPIOPin *flow_pin_{nullptr};
  std::string model_;
  std::vector<uint8_t> rx_;
  std::queue<WriteRequest> writes_;
  std::queue<std::vector<uint8_t>> reads_;
  std::vector<HeatpumpSensor *> sensors_;
  std::vector<HeatpumpNumber *> numbers_;
  std::vector<HeatpumpSelect *> selects_;
  std::vector<HeatpumpSwitch *> switches_;
};
}  // namespace heatpump
}  // namespace esphome
