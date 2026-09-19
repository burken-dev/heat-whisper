// components/nibe/nibe.cpp (core loop + router + LE decoder)
#include "nibe.h"
#include "registers.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace esphome {
namespace nibe {
static float scale(int32_t raw, int16_t f) { return f ? (float) raw / f : (float) raw; }
static const uint32_t NIBE_SEL_TYPE = 0x6E696273UL;  // 'nibs'
bool NibeComponent::load_selection(NibeSelection *out) {
  ESPPreferenceObject pref = global_preferences->make_preference<NibeSelection>(NIBE_SEL_TYPE, true);
  if (!pref.load(out) || out->version != 1 || out->count > NIBE_MAX_SELECTION) return false;
  return true;
}
bool NibeComponent::save_selection(const uint16_t *addrs, uint16_t n) {
  if (n > NIBE_MAX_SELECTION) return false;
  NibeSelection s{};
  s.version = 1;
  s.count = n;
  if (n) memcpy(s.addrs, addrs, n * sizeof(uint16_t));
  ESPPreferenceObject pref = global_preferences->make_preference<NibeSelection>(NIBE_SEL_TYPE, true);
  return pref.save(&s);
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
void NibeComponent::create_entities() {
  static const uint16_t TITLES_N = sizeof(NIBE_TITLES) / sizeof(NibeTitle);  // no NIBE_TITLES_N in catalog.h
  uint16_t addrs[NIBE_MAX_SELECTION];
  uint16_t n = 0;
  NibeSelection sel{};
  if (load_selection(&sel)) {
    n = sel.count;
    if (n) memcpy(addrs, sel.addrs, n * sizeof(uint16_t));
  } else {
    n = NIBE_DEFAULTS_N;
    memcpy(addrs, NIBE_DEFAULTS, n * sizeof(uint16_t));
  }
  std::vector<uint32_t> used_hashes;  // catalog titles collide across models; skip dupes
  for (uint16_t i = 0; i < n; i++) {
    uint16_t addr = addrs[i];
    const NibeMeta *meta = nullptr;
    uint16_t mi = 0;
    for (; mi < NIBE_META_N; mi++)  // ponytail: linear scan, same as decode loop
      if (NIBE_META[mi].addr == addr) { meta = &NIBE_META[mi]; break; }
    if (meta == nullptr) { ESP_LOGW("nibe", "Skipping unknown register %u (map updated after save?)", addr); continue; }
    // NIBE_TITLES parallels NIBE_META (same sorted addr list in generate_catalog_header).
    const char *title = (mi < TITLES_N && NIBE_TITLES[mi].addr == addr) ? NIBE_TITLES[mi].title : nullptr;
    if (title == nullptr) { ESP_LOGW("nibe", "Skipping register %u without catalog title", addr); continue; }
    // ponytail: canonical hash codegen passes to App.register_* (helpers.h),
    // not a hand mirror of object_id_for.
    uint32_t hash = fnv1_hash_object_id(title, strlen(title));
    bool dupe = false;
    for (uint32_t h : used_hashes)
      if (h == hash) { dupe = true; break; }
    if (dupe) { ESP_LOGW("nibe", "Skipping register %u with duplicate object id", addr); continue; }
    const NibeHint *hint = nullptr;
    for (uint8_t k = 0; k < NIBE_HINTS_N; k++)
      if (NIBE_HINTS[k].addr == addr) { hint = &NIBE_HINTS[k]; break; }
    uint8_t kind = (hint != nullptr) ? hint->kind : (uint8_t)(meta->rw ? 1 : 0);
    if (kind == 0) {
      auto *sen = new NibeSensor();
      sen->set_parent(this);
      sen->set_register(addr);
      sen->set_accuracy_decimals(1);  // ponytail: no runtime unit setter in 2026.9.0; units are codegen-pooled
      App.register_sensor(sen, title, hash, 0);
      add_sensor(sen);
    } else if (kind == 1) {
      float f = meta->factor ? (float) meta->factor : 1.0f;
      auto *num = new NibeNumber();
      num->set_parent(this);
      num->set_register(addr);
      num->traits.set_min_value((float) meta->min / f);
      num->traits.set_max_value((float) meta->max / f);
      num->traits.set_step(1.0f / f);  // one raw LSB; no step info in catalog
      App.register_number(num, title, hash, 0);
      add_number(num);
    } else if (kind == 2) {
      auto *sw = new NibeSwitch();
      sw->set_parent(this);
      sw->set_register(addr);
      App.register_switch(sw, title, hash, 0);
      add_switch(sw);
    } else if (kind == 3 && hint != nullptr) {
      std::vector<int32_t> raws;
      std::vector<std::string> labels;
      parse_opts(hint->opts, &raws, &labels);
      if (labels.empty()) { ESP_LOGW("nibe", "Skipping select %u with no options", addr); continue; }
      auto *sel = new NibeSelect();
      sel->set_parent(this);
      sel->set_register(addr);
      sel->set_mapping(raws);
      sel->set_labels(labels);
      App.register_select(sel, title, hash, 0);
      add_select(sel);
    } else {
      ESP_LOGW("nibe", "Skipping register %u with unknown kind %u", addr, kind);
      continue;
    }
    used_hashes.push_back(hash);
  }
}
void NibeComponent::setup() {
  if (flow_pin_ != nullptr) {
    flow_pin_->setup();
    flow_pin_->digital_write(false);
  }
  create_entities();
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
    if (calc_crc(f.data()) != f[len + 5]) {
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
void NibeComponent::on_frame_(const uint8_t *f, uint8_t n) {
  if ((f[2] == slave_ || f[2] == 0x20) && f[3] == 0x69 && f[4] == 0x00) {
    if (passive_) return;
    size_t laps = reads_.size();
    bool sent = false;
    while (laps-- > 0 && !reads_.empty()) {
      auto r = reads_.front(); reads_.pop();
      uint16_t a = (r.size() == 6) ? (uint16_t)(r[3] | (r[4] << 8)) : 0;
      if (r.size() == 6 && !is_enabled(a)) { reads_.push(r); continue; }
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
      o[9] = calc_crc_c0(o);
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
  for (uint16_t a : addrs) ensure_polled(a);
}
void NibeComponent::ensure_polled(uint16_t addr) {
  uint8_t lo = addr & 0xFF, hi = addr >> 8;
  size_t laps = reads_.size();  // ponytail: queue has no iterators, rotate like on_frame_
  while (laps-- > 0) {
    auto q = reads_.front(); reads_.pop();
    if (q.size() == 6 && q[3] == lo && q[4] == hi) { reads_.push(q); return; }
    reads_.push(q);
  }
  uint8_t o[6] = {0xC0, 0x69, 0x02, lo, hi, 0};
  o[5] = calc_crc_c0(o);
  reads_.emplace(o, o + 6);
}
void NibeComponent::on_value(uint16_t addr, float v) {
  if (!is_enabled(addr)) return;
  for (auto *s : sensors_)
    if (s->get_register() == addr) s->publish_value(v);
  for (auto *n : numbers_)
    if (n->get_register() == addr) n->publish_value(v);
  for (auto *sw : switches_)
    if (sw->get_register() == addr) sw->publish_state(v != 0);
  for (auto *sel : selects_)
    if (sel->get_register() == addr) {
      const NibeMeta *meta = nullptr;
      for (uint16_t k = 0; k < NIBE_META_N; k++)
        if (NIBE_META[k].addr == addr) { meta = &NIBE_META[k]; break; }
      float f = (meta != nullptr && meta->factor) ? (float) meta->factor : 1.0f;
      sel->publish_raw((int32_t) std::lround(v * f));
    }
}
void NibeSelect::set_labels(const std::vector<std::string> &labels) {
  labels_ = labels;  // ponytail: fill before set_options; realloc would dangle traits pointers
  esphome::FixedVector<const char *> opts;
  opts.init(labels_.size());
  for (auto &l : labels_) opts.push_back(l.c_str());
  this->traits.set_options(opts);
}
void NibeSelect::publish_raw(int32_t raw) {
  for (size_t i = 0; i < raws_.size(); i++)
    if (raws_[i] == raw) { publish_state(i); return; }
  // unknown raws skipped
}
void NibeSelect::control(const std::string &value) {
  if (parent_ == nullptr) return;
  auto idx = this->index_of(value);
  if (idx.has_value() && idx.value() < raws_.size()) {
    parent_->queue_write(addr_, raws_[idx.value()]);
    publish_state(value);
  }
}
void NibeSwitch::write_state(bool state) {
  if (parent_ == nullptr) return;
  parent_->queue_write(addr_, state ? 1 : 0);
  publish_state(state);
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
