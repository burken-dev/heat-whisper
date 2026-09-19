// components/heatwhisper/heatwhisper.cpp (core loop + router + LE decoder)
#include "heatwhisper.h"
#include "picker.h"
#include "esphome/components/sensor/filter.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
namespace esphome {
namespace heatwhisper {
static float scale(int32_t raw, int16_t f) { return f ? (float) raw / f : (float) raw; }
static const uint32_t HW_SEL_TYPE = 0x6E696273UL;  // keep: saved selections survive OTA
bool HeatWhisperComponent::load_selection(HeatWhisperSelection *out) {
  ESPPreferenceObject pref = global_preferences->make_preference<HeatWhisperSelection>(HW_SEL_TYPE, true);
  if (!pref.load(out) || out->version != 1 || out->count > HW_MAX_SELECTION) return false;
  return true;
}
bool HeatWhisperComponent::save_selection(const uint16_t *addrs, uint16_t n) {
  if (n > HW_MAX_SELECTION) return false;
  HeatWhisperSelection s{};
  s.version = 1;
  s.count = n;
  if (n) memcpy(s.addrs, addrs, n * sizeof(uint16_t));
  ESPPreferenceObject pref = global_preferences->make_preference<HeatWhisperSelection>(HW_SEL_TYPE, true);
  return pref.save(&s);
}
// Post-Task-5 name authority: factory names for the 18 HW_DEFAULTS addrs,
// copied verbatim from packages/base.yaml so HA entity names stay identical.
// Task 5 deletes the YAML blocks; this table is then the single source.
static const struct { uint16_t addr; const char *name; } HW_FACTORY_NAMES[] = {
  {40004, "BT1 Outdoor"}, {40008, "Supply Temp S1"}, {40012, "Return Temp"},
  {40013, "Hot Water Top BT7"}, {40014, "Hot Water BT6"}, {43009, "Calculated Supply"},
  {43136, "Compressor Frequency"}, {43005, "Degree Minutes"}, {40033, "Room Temp S1"},
  {43144, "Compressor Energy Total"}, {43305, "Compressor Energy HW"}, {47011, "Heat Offset S1"},
  {47007, "Heat Curve S1"}, {47041, "Hot Water Comfort Mode"}, {47371, "Allow Heating"},
  {47370, "Allow Additive Heating"}, {47387, "Hot Water Production"}, {47043, "Hot Water Luxury Start Temp"},
};
static const char *base_name_for(uint16_t addr) {
  for (uint8_t i = 0; i < sizeof(HW_FACTORY_NAMES) / sizeof(HW_FACTORY_NAMES[0]); i++)
    if (HW_FACTORY_NAMES[i].addr == addr) return HW_FACTORY_NAMES[i].name;
  return nullptr;
}
// Parse hint opts "raw:label;raw:label" (labels carry \" and \\ escapes from _esc).
static void parse_opts(const char *opts, std::vector<int32_t> *raws, std::vector<std::string> *labels) {
  for (const char *p = opts; *p;) {
    const char *colon = strchr(p, ':');
    if (colon == nullptr) break;
    raws->push_back(atoi(std::string(p, colon).c_str()));
    std::string label;
    p = colon + 1;
    while (*p && *p != ';') {
      if (*p == '\\' && (p[1] == '"' || p[1] == '\\')) p++;
      label += *p++;
    }
    labels->push_back(label);
    if (*p == ';') p++;
  }
}
void HeatWhisperComponent::create_entities() {
  static const uint16_t TITLES_N = sizeof(HW_TITLES) / sizeof(HwTitle);  // no HW_TITLES_N in catalog.h
  uint16_t addrs[HW_MAX_SELECTION];
  uint16_t n = 0;
  HeatWhisperSelection sel{};
  if (load_selection(&sel)) {
    n = sel.count;
    if (n) memcpy(addrs, sel.addrs, n * sizeof(uint16_t));
  } else {
    n = std::min(HW_DEFAULTS_N, HW_MAX_SELECTION);
    memcpy(addrs, HW_DEFAULTS, n * sizeof(uint16_t));
  }
  std::vector<uint32_t> used_hashes;  // catalog titles collide across models; skip dupes
  for (uint16_t i = 0; i < n; i++) {
    uint16_t addr = addrs[i];
    const HwMeta *meta = nullptr;
    for (uint16_t k = 0; k < HW_META_N; k++)  // ponytail: linear scan, same as decode loop
      if (HW_META[k].addr == addr) { meta = &HW_META[k]; break; }
    if (meta == nullptr) { ESP_LOGW("heatwhisper", "Skipping unknown register %u (map updated after save?)", addr); continue; }
    const char *title = base_name_for(addr);  // post-Task-5 name authority; catalog title otherwise
    if (title == nullptr)
      for (uint16_t t = 0; t < TITLES_N; t++)
        if (HW_TITLES[t].addr == addr) { title = HW_TITLES[t].title; break; }
    if (title == nullptr) { ESP_LOGW("heatwhisper", "Skipping register %u without catalog title", addr); continue; }
    // ponytail: canonical hash codegen passes to App.register_* (helpers.h),
    // not a hand mirror of object_id_for.
    uint32_t hash = fnv1_hash_object_id(title, strlen(title));
    bool dupe = false;
    for (uint32_t h : used_hashes)
      if (h == hash) { dupe = true; break; }
    if (dupe) { ESP_LOGW("heatwhisper", "Skipping register %u with duplicate object id", addr); continue; }
    const HwHint *hint = nullptr;
    for (uint8_t k = 0; k < HW_HINTS_N; k++)
      if (HW_HINTS[k].addr == addr) { hint = &HW_HINTS[k]; break; }
    uint8_t kind = (hint != nullptr) ? hint->kind : (uint8_t)(meta->rw ? 1 : 0);
    if (addr < 20000 && kind != 0) kind = 0;  // RMU range: queue_write drops writes, offer read-only
    if (kind == 0) {
      auto *sen = new HeatWhisperSensor();
      sen->set_parent(this);
      sen->set_register(addr);
      sen->set_accuracy_decimals(1);  // ponytail: no runtime unit setter in 2026.9.0; units are codegen-pooled
      // ponytail: mirrors codegen for `delta: 0.1 / throttle: 60s / heartbeat: 5min`
      // (sensor/__init__.py: delta_filter_to_code etc.; USE_SENSOR_FILTER via cg.add_define in __init__.py)
      sen->set_filters({
        new esphome::sensor::DeltaFilter(0.1f, 0.0f, std::numeric_limits<float>::infinity(), 0.0f),
        new esphome::sensor::ThrottleFilter(60000),
        new esphome::sensor::HeartbeatFilter(300000),
      });
      App.register_sensor(sen, title, hash, 0);
      add_sensor(sen);
    } else if (kind == 1) {
      float f = meta->factor ? (float) meta->factor : 1.0f;
      auto *num = new HeatWhisperNumber();
      num->set_parent(this);
      num->set_register(addr);
      num->traits.set_min_value((float) meta->min / f);
      num->traits.set_max_value((float) meta->max / f);
      num->traits.set_step(1.0f / f);  // one raw LSB; no step info in catalog
      App.register_number(num, title, hash, 0);
      add_number(num);
    } else if (kind == 2) {
      auto *sw = new HeatWhisperSwitch();
      sw->set_parent(this);
      sw->set_register(addr);
      App.register_switch(sw, title, hash, 0);
      add_switch(sw);
    } else if (kind == 3 && hint != nullptr) {
      std::vector<int32_t> raws;
      std::vector<std::string> labels;
      parse_opts(hint->opts, &raws, &labels);
      if (labels.empty()) { ESP_LOGW("heatwhisper", "Skipping select %u with no options", addr); continue; }
      auto *sel = new HeatWhisperSelect();
      sel->set_parent(this);
      sel->set_register(addr);
      sel->set_mapping(raws);
      sel->set_labels(labels);
      App.register_select(sel, title, hash, 0);
      add_select(sel);
    } else {
      ESP_LOGW("heatwhisper", "Skipping register %u with unknown kind %u", addr, kind);
      continue;
    }
    used_hashes.push_back(hash);
  }
}
void HeatWhisperComponent::setup() {
  if (flow_pin_ != nullptr) {
    flow_pin_->setup();
    flow_pin_->digital_write(false);
  }
  create_entities();
}
void HeatWhisperComponent::tx_(const uint8_t *d, size_t len) {
  if (flow_pin_ != nullptr) flow_pin_->digital_write(true);
  write_array(d, len);
  flush();
  if (flow_pin_ != nullptr) flow_pin_->digital_write(false);
}
void HeatWhisperComponent::loop() {
  uint8_t b;
  while (available()) { read_byte(&b); rx_.push_back(b); }
  if (rx_.size() > 512) rx_.erase(rx_.begin(), rx_.begin() + (rx_.size() - 512));
  for (;;) {
    if (rx_.size() >= 2 && rx_[0] == 0x06 && rx_[1] == 0x5C) rx_.erase(rx_.begin());
    auto it = std::find(rx_.begin(), rx_.end(), 0x5C);
    if (it == rx_.end()) { rx_.clear(); return; }
    if (it != rx_.begin()) rx_.erase(rx_.begin(), it);
    if (rx_.size() < 5) return;
    uint8_t len = rx_[4];
    if (len > 64) { rx_.erase(rx_.begin()); continue; }
    if (rx_.size() < (size_t) len + 6) return;
    std::vector<uint8_t> f(rx_.begin(), rx_.begin() + len + 6);
    if (calc_crc_nibe(f.data()) != f[len + 5]) {
      send_nack_();
      rx_.erase(rx_.begin());
      continue;
    }
    rx_.erase(rx_.begin(), rx_.begin() + len + 6);
    for (size_t i = 5; i + 1 < f.size() - 1;) {  // ponytail: 5C 5C escape, backend.js:169-184
      if (f[i] == 0x5C && f[i + 1] == 0x5C) { f.erase(f.begin() + i); f[4]--; continue; }
      i++;
    }
    if (f.size() != (size_t) f[4] + 6) { send_nack_(); continue; }
    uint8_t c = 0;
    for (size_t i = 2; i < (size_t) f[4] + 5; i++) c ^= f[i];
    f[f[4] + 5] = c;
    on_frame_(f.data(), f.size());
  }
}
void HeatWhisperComponent::on_frame_(const uint8_t *f, uint8_t n) {
  if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x69 && f[4] == 0x00) {
    if (passive_) return;
    size_t laps = reads_.size();
    bool sent = false;
    while (laps-- > 0 && !reads_.empty()) {
      auto r = reads_.front(); reads_.pop();
      reads_.push(r); tx_(r.data(), r.size()); sent = true; break;
    }
    if (!sent) send_ack_();
  } else if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x6B && f[4] == 0x00) {
    if (passive_) return;
    if (!writes_.empty()) {
      auto w = writes_.front(); writes_.pop();
      uint8_t o[10] = {0xC0, 0x6B, 0x06, (uint8_t)(w.addr & 0xFF), (uint8_t)(w.addr >> 8),
                       (uint8_t)(w.raw & 0xFF), (uint8_t)((w.raw >> 8) & 0xFF),
                       (uint8_t)((w.raw >> 16) & 0xFF), (uint8_t)((w.raw >> 24) & 0xFF), 0};
      o[9] = calc_crc_c0_nibe(o);
      tx_(o, 10);
    } else send_ack_();
  } else if (f[3] == 0x68 || f[3] == 0x6A || f[3] == 0x62 || f[3] == 0x6D) {
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
        const HwMeta *reg = nullptr;
        for (uint16_t k = 0; k < HW_META_N; k++)  // ponytail: linear scan, catalog-wide
          if (HW_META[k].addr == addr) { reg = &HW_META[k]; break; }
        if (reg == nullptr) { i += 4; continue; }
        bool wide = (reg->size == HW_U32 || reg->size == HW_S32);
        uint8_t need = wide ? (f[3] == 0x68 ? 8 : 6) : 4;
        if (i + need > n - 1) break;
        float v;
        if (!wide) {
          uint16_t w = f[i + 2] | ((uint16_t) f[i + 3] << 8);
          int32_t raw = w;
          if (reg->size == HW_S8) {  // fixup matches reference
            if (raw > 128 && raw < 32768) raw -= 256;
            else if (raw >= 32768) raw -= 65536;
          } else if (reg->size == HW_S16) {
            if (w >= 32768) raw -= 65536;
          }
          v = scale(raw, reg->factor);
        } else {
          uint32_t u = (f[3] == 0x68)
              ? ((uint32_t) f[i + 2] | ((uint32_t) f[i + 3] << 8) | ((uint32_t) f[i + 6] << 16) |
                 ((uint32_t) f[i + 7] << 24))
              : ((uint32_t) f[i + 4] | ((uint32_t) f[i + 5] << 8) | ((uint32_t) f[i + 2] << 16) |
                 ((uint32_t) f[i + 3] << 24));
          v = (reg->size == HW_S32) ? scale((int32_t) u, reg->factor)
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
    if (f[3] == 0x63) {
      if (passive_) return;
      uint8_t r[6] = {0xC0, 0x60, 0x02, 0x63, 0x00, 0x00};
      r[5] = calc_crc_c0_nibe(r);  // == 0xC1, matches backend.js:283
      tx_(r, 6);
      return;
    }
    if (f[3] == 0xEE) {
      if (passive_) return;
      const uint8_t ver[7] = {0xC0, 0xEE, 0x03, 0xEE, 0x03, 0x01, 0x00};
      uint8_t r[7];
      memcpy(r, ver, 7);
      r[6] = calc_crc_c0_nibe(r);  // == 0xC1, matches backend.js:293
      tx_(r, 7);
      return;
    }
    if (!passive_) send_ack_();
  } else {
    if (!passive_) send_ack_();
  }
}
void HeatWhisperComponent::set_poll_registers(const std::vector<uint16_t> &addrs) {
  for (uint16_t a : addrs) ensure_polled(a);
}
void HeatWhisperComponent::ensure_polled(uint16_t addr) {
  uint8_t lo = addr & 0xFF, hi = addr >> 8;
  size_t laps = reads_.size();  // ponytail: queue has no iterators, rotate like on_frame_
  while (laps-- > 0) {
    auto q = reads_.front(); reads_.pop();
    if (q.size() == 6 && q[3] == lo && q[4] == hi) { reads_.push(q); return; }
    reads_.push(q);
  }
  uint8_t o[6] = {0xC0, 0x69, 0x02, lo, hi, 0};
  o[5] = calc_crc_c0_nibe(o);
  reads_.emplace(o, o + 6);
}
void HeatWhisperComponent::on_value(uint16_t addr, float v) {
  for (auto *s : sensors_)
    if (s->get_register() == addr) s->publish_value(v);
  for (auto *n : numbers_)
    if (n->get_register() == addr) n->publish_value(v);
  for (auto *sw : switches_)
    if (sw->get_register() == addr) sw->publish_state(v != 0);
  for (auto *sel : selects_)
    if (sel->get_register() == addr) {
      const HwMeta *meta = nullptr;
      for (uint16_t k = 0; k < HW_META_N; k++)
        if (HW_META[k].addr == addr) { meta = &HW_META[k]; break; }
      float f = (meta != nullptr && meta->factor) ? (float) meta->factor : 1.0f;
      sel->publish_raw((int32_t) std::lround(v * f));
    }
}
void HeatWhisperSelect::set_labels(const std::vector<std::string> &labels) {
  labels_ = labels;  // ponytail: fill before set_options; realloc would dangle traits pointers
  esphome::FixedVector<const char *> opts;
  opts.init(labels_.size());
  for (auto &l : labels_) opts.push_back(l.c_str());
  this->traits.set_options(opts);
}
void HeatWhisperSelect::publish_raw(int32_t raw) {
  for (size_t i = 0; i < raws_.size(); i++)
    if (raws_[i] == raw) { publish_state(i); return; }
  // unknown raws skipped
}
void HeatWhisperSelect::control(const std::string &value) {
  if (parent_ == nullptr) return;
  auto idx = this->index_of(value);
  if (idx.has_value() && idx.value() < raws_.size()) {
    parent_->queue_write(addr_, raws_[idx.value()]);
    publish_state(value);
  }
}
void HeatWhisperSwitch::write_state(bool state) {
  if (parent_ == nullptr) return;
  parent_->queue_write(addr_, state ? 1 : 0);
  publish_state(state);
}
void HeatWhisperNumber::control(float value) {
  if (parent_ == nullptr) return;
  float v = value;
  int32_t raw;
  const HwMeta *reg = nullptr;
  for (uint16_t k = 0; k < HW_META_N; k++)  // ponytail: linear scan, catalog-wide
    if (HW_META[k].addr == addr_) { reg = &HW_META[k]; break; }
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
// Register picker web UI (Task 4). Implementations live here (not picker.h)
// so the JSON builder can reuse base_name_for + catalog tables directly.
#if defined(USE_NETWORK) && !defined(USE_ZEPHYR)
// ponytail: dependency-free page; fetch JSON, render checkboxes, POST addrs CSV back.
static const char HW_PICKER_HTML[] = R"HTML(<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>HeatWhisper registers</title>
<style>body{font-family:sans-serif;max-width:60em;margin:1em auto}li{list-style:none}.k{color:#888;font-size:.8em}</style>
</head><body><h1>HeatWhisper register picker</h1><p id="note"></p>
<p><input id="q" placeholder="Filter&hellip;" size="30"> <label><input type="checkbox" id="eo"> enabled only</label>
<span id="count"></span></p><ul id="list"></ul>
<p><button id="save">Save selection</button> <span id="msg"></span></p>
<script>
const Q=document.getElementById('q'),E=document.getElementById('eo'),L=document.getElementById('list'),
C=document.getElementById('count'),N=document.getElementById('note'),M=document.getElementById('msg'),
S=document.getElementById('save');let regs=[];
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function render(){const q=Q.value.toLowerCase(),eo=E.checked;let n=0;
L.innerHTML=regs.filter(r=>(!eo||r.en)&&(!q||r.t.toLowerCase().includes(q)||String(r.a).includes(q)))
.map(r=>{n++;return '<li><label><input type="checkbox" data-a="'+r.a+'"'+(r.en?' checked':'')+'> '+r.a+' '+esc(r.t)+
' <span class="k">'+r.u+' '+r.kind+'</span></label></li>'}).join('');C.textContent=n+'/'+regs.length+' shown';}
fetch('?format=json').then(r=>r.json()).then(j=>{regs=j.addrs;
N.textContent=j.model==null?'Waiting for pump announcement — showing defaults.':'Model: '+j.model;render();});
S.onclick=()=>{const a=[...L.querySelectorAll('input:checked')].map(c=>c.dataset.a).join(',');
fetch('/heatwhisper/registers/save',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
body:'addrs='+encodeURIComponent(a)}).then(async r=>{
M.textContent=r.ok?'Saved. Reboot via ESPHome restart to apply.':'Save failed: '+await r.text()})
.catch(e=>M.textContent='Save failed: '+e);};
Q.oninput=render;E.onchange=render;
</script></body></html>)HTML";
bool HeatWhisperPickerHandler::canHandle(AsyncWebServerRequest *request) const {
#ifdef USE_ESP32
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  StringRef url = request->url_to(url_buf);
#else
  const auto &url = request->url();
#endif
  auto m = request->method();
  return (m == HTTP_GET && url == ESPHOME_F("/heatwhisper/registers")) ||
         (m == HTTP_POST && url == ESPHOME_F("/heatwhisper/registers/save"));
}
void HeatWhisperPickerHandler::handleRequest(AsyncWebServerRequest *request) {
  if (request->method() == HTTP_POST) {
    this->handle_save_(request);
    return;
  }
  if (request->hasArg("format") && request->arg("format") == "json") {
    request->send(200, "application/json", this->list_json_().c_str());
    return;
  }
  request->send(200, "text/html", HW_PICKER_HTML);
}
static void picker_esc_(std::string &o, const char *s) {
  for (; *s; s++) {
    char c = *s;
    if (c == '"' || c == '\\') { o += '\\'; o += c; }
    else if (c == '\n') o += "\\n";
    else if (c == '\r') o += "\\r";
    else if (c == '\t') o += "\\t";
    else if ((unsigned char) c < 0x20) { char u[8]; snprintf(u, sizeof(u), "\\u%04X", c); o += u; }
    else o += c;
  }
}
std::string HeatWhisperPickerHandler::list_json_() const {
  static const uint16_t TITLES_N = sizeof(HW_TITLES) / sizeof(HwTitle);  // no HW_TITLES_N in catalog.h
  const uint16_t *addrs = HW_DEFAULTS;
  uint16_t n = HW_DEFAULTS_N;
  bool have_model = false;
  const std::string &model = this->parent_->get_model();
  if (!model.empty())
    for (uint8_t i = 0; i < HW_MODELS_N; i++)
      if (model == HW_MODELS[i].name) { addrs = HW_MODELS[i].addrs; n = HW_MODELS[i].n; have_model = true; break; }
  HeatWhisperSelection sel{};
  const uint16_t *cur = HW_DEFAULTS;  // effective set mirrors create_entities: saved, else defaults
  uint16_t cn = HW_DEFAULTS_N;
  if (this->parent_->load_selection(&sel)) { cur = sel.addrs; cn = sel.count; }
  static const char *KINDS[] = {"sensor", "number", "switch", "select"};
  std::string o = "{\"model\":";
  if (have_model) {
    o += '"';
    picker_esc_(o, model.c_str());
    o += '"';
  } else {
    o += "null";  // waiting for pump announcement; page renders the notice
  }
  o += ",\"addrs\":[";
  bool first = true;
  char num[8];
  for (uint16_t i = 0; i < n; i++) {
    uint16_t addr = addrs[i];
    const HwMeta *meta = nullptr;
    for (uint16_t k = 0; k < HW_META_N; k++)  // ponytail: linear scan, catalog-wide
      if (HW_META[k].addr == addr) { meta = &HW_META[k]; break; }
    if (meta == nullptr) continue;
    const HwTitle *te = nullptr;
    const char *title = base_name_for(addr);  // HA-identical display names (Task 3 override table)
    for (uint16_t t = 0; t < TITLES_N; t++)
      if (HW_TITLES[t].addr == addr) {
        if (title == nullptr) title = HW_TITLES[t].title;
        te = &HW_TITLES[t];
        break;
      }
    if (title == nullptr) continue;
    const HwHint *hint = nullptr;
    for (uint8_t k = 0; k < HW_HINTS_N; k++)
      if (HW_HINTS[k].addr == addr) { hint = &HW_HINTS[k]; break; }
    uint8_t kind = (hint != nullptr) ? hint->kind : (uint8_t)(meta->rw ? 1 : 0);
    if (addr < 20000 && kind != 0) kind = 0;  // RMU range: queue_write drops writes, offer read-only
    bool en = false;
    for (uint16_t c = 0; c < cn; c++)
      if (cur[c] == addr) { en = true; break; }
    if (!first) o += ',';
    first = false;
    snprintf(num, sizeof(num), "%u", addr);
    o += "{\"a\":";
    o += num;
    o += ",\"t\":\"";
    picker_esc_(o, title);
    o += "\",\"u\":\"";
    if (te != nullptr) picker_esc_(o, te->unit);
    o += "\",\"kind\":\"";
    o += KINDS[kind > 3 ? 0 : kind];
    o += "\",\"en\":";
    o += en ? '1' : '0';
    o += '}';
  }
  o += "]}";
  return o;
}
void HeatWhisperPickerHandler::handle_save_(AsyncWebServerRequest *request) {
  std::string s = request->hasArg("addrs") ? request->arg("addrs").c_str() : std::string();
  uint16_t addrs[HW_MAX_SELECTION];
  uint16_t count = 0;
  std::string err;
  for (size_t i = 0; i <= s.size();) {
    size_t j = s.find(',', i);
    if (j == std::string::npos) j = s.size();
    std::string tok = s.substr(i, j - i);
    i = j + 1;
    if (tok.empty()) continue;
    char *end = nullptr;
    long v = strtol(tok.c_str(), &end, 10);
    if (end == tok.c_str() || *end != '\0' || v <= 0 || v > 65535) { err = "bad addr '" + tok + "'"; break; }
    bool known = false;
    for (uint16_t k = 0; k < HW_META_N; k++)
      if (HW_META[k].addr == (uint16_t) v) { known = true; break; }
    if (!known) { err = "unknown register " + tok; break; }
    bool dupe = false;  // ponytail: repeats must not consume cap slots or persist twice
    for (uint16_t k = 0; k < count; k++)
      if (addrs[k] == (uint16_t) v) { dupe = true; break; }
    if (dupe) continue;
    if (count >= HW_MAX_SELECTION) {
      char m[32];
      snprintf(m, sizeof(m), "too many (max %u)", HW_MAX_SELECTION);
      err = m;
      break;
    }
    addrs[count++] = (uint16_t) v;
  }
  if (!err.empty()) {
    request->send(400, "text/plain", err.c_str());
    return;
  }
  if (!this->parent_->save_selection(addrs, count)) {
    request->send(500, "text/plain", "save failed");
    return;
  }
  request->send(200, "text/plain", "saved,reboot");
}
#endif  // USE_NETWORK && !USE_ZEPHYR
}  // namespace heatwhisper
}  // namespace esphome
