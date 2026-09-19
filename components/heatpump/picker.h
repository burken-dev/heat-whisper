// components/heatpump/picker.h — runtime register picker web UI (Task 4).
#pragma once
#include "esphome/core/defines.h"
#if defined(USE_NETWORK) && !defined(USE_ZEPHYR)
#include "esphome/components/web_server_base/web_server_base.h"
#include "esphome/core/component.h"
#include <string>
namespace esphome {
namespace heatpump {
class HeatpumpComponent;
class HeatpumpPickerHandler final : public AsyncWebHandler, public Component {
 public:
  HeatpumpPickerHandler(web_server_base::WebServerBase *base, HeatpumpComponent *parent)
      : base_(base), parent_(parent) {}
  bool canHandle(AsyncWebServerRequest *request) const override;
  void handleRequest(AsyncWebServerRequest *request) override;
  void setup() override {
    this->base_->init();
    this->base_->add_handler(this);  // auth inherited, never add_handler_without_auth
  }
  float get_setup_priority() const override { return esphome::setup_priority::AFTER_WIFI; }
 protected:
  std::string list_json_() const;
  void handle_save_(AsyncWebServerRequest *request);
  web_server_base::WebServerBase *base_;
  HeatpumpComponent *parent_;
};
}  // namespace heatpump
}  // namespace esphome
#endif  // USE_NETWORK && !USE_ZEPHYR
