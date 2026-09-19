// components/heatwhisper/picker.h — runtime register picker web UI (Task 4).
#pragma once
#include "esphome/core/defines.h"
#if defined(USE_NETWORK) && !defined(USE_ZEPHYR)
#include "esphome/components/web_server_base/web_server_base.h"
#include "esphome/core/component.h"
#include <string>
namespace esphome {
namespace heatwhisper {
class HeatWhisperComponent;
class HeatWhisperPickerHandler final : public AsyncWebHandler, public Component {
 public:
  HeatWhisperPickerHandler(web_server_base::WebServerBase *base, HeatWhisperComponent *parent)
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
  HeatWhisperComponent *parent_;
};
}  // namespace heatwhisper
}  // namespace esphome
#endif  // USE_NETWORK && !USE_ZEPHYR
