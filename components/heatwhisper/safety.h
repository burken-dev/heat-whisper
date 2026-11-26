// components/heatwhisper/safety.h — safety tiers, unclamped bounds, and v2 selection
// persistence/migration helpers, no ESPHome deps (host-compilable seam).
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <string>

namespace esphome {
namespace heatwhisper {

enum HwTier : uint8_t {
  HW_TIER_RO = 0,
  HW_TIER_STANDARD = 1,
  HW_TIER_ADVANCED = 2,
  HW_TIER_HIGH_RISK = 3,
};

static constexpr uint16_t kMaxSelectionSlots = 50;

// Legacy v1 NVS layout (108 bytes, preserved for lossless OTA migration).
struct HeatWhisperSelectionV1 {
  uint32_t version{1};
  uint16_t count{0};
  uint16_t addrs[50];
};
static_assert(sizeof(HeatWhisperSelectionV1{}) == 108, "HeatWhisperSelectionV1 layout");

// v2 NVS layout (116 bytes): adds per-slot read-only bitmask (`ro_lo`/`ro_hi`)
// so any R/W register can be exposed safely as a read-only HA sensor.
struct HeatWhisperSelection {
  uint32_t version{2};
  uint16_t count{0};
  uint16_t reserved{0};
  uint32_t ro_lo{0};  // bits 0..31: 1 = expose slot i as read-only sensor
  uint32_t ro_hi{0};  // bits 32..49: 1 = expose slot i as read-only sensor
  uint16_t addrs[50];

  bool is_ro(uint16_t idx) const {
    if (idx >= kMaxSelectionSlots) return false;
    return idx < 32 ? ((ro_lo >> idx) & uint32_t{1}) != 0
                    : ((ro_hi >> (idx - 32)) & uint32_t{1}) != 0;
  }

  void set_ro(uint16_t idx, bool ro) {
    if (idx >= kMaxSelectionSlots) return;
    if (idx < 32) {
      uint32_t bit = uint32_t{1} << idx;
      if (ro) ro_lo |= bit;
      else ro_lo &= ~bit;
    } else {
      uint32_t bit = uint32_t{1} << (idx - 32);
      if (ro) ro_hi |= bit;
      else ro_hi &= ~bit;
    }
  }

  uint64_t ro_mask() const { return (static_cast<uint64_t>(ro_hi) << 32) | ro_lo; }

  void set_ro_mask(uint64_t m) {
    ro_lo = static_cast<uint32_t>(m & 0xFFFFFFFFULL);
    ro_hi = static_cast<uint32_t>(m >> 32);
  }
};
static_assert(sizeof(HeatWhisperSelection{}) == 116, "HeatWhisperSelection layout");

namespace safety {

inline HwTier effective_tier(uint16_t addr, uint8_t rw) {
  if (addr < 20000 || rw == HW_TIER_RO) return HW_TIER_RO;
  if (rw >= HW_TIER_HIGH_RISK) return HW_TIER_HIGH_RISK;
  return static_cast<HwTier>(rw);
}

// True when a writable number register has no catalog min/max range (0..0)
// and no discrete switch/select hint (`hint_kind`: -1 = none, 2 = switch, 3 = select).
inline bool is_unclamped(uint16_t addr, uint8_t rw, int32_t min_v, int32_t max_v, int8_t hint_kind) {
  if (effective_tier(addr, rw) == HW_TIER_RO) return false;
  if (min_v != 0 || max_v != 0) return false;
  if (hint_kind == 2 || hint_kind == 3) return false;
  return true;
}

inline uint8_t resolve_kind(uint16_t addr, uint8_t rw, int8_t hint_kind, bool force_ro) {
  if (effective_tier(addr, rw) == HW_TIER_RO || force_ro) return 0;
  return hint_kind >= 0 ? static_cast<uint8_t>(hint_kind) : 1;
}

// Type-derived raw integer fallback bounds for unclamped R/W registers (`size_code` matches SIZE_CODES).
inline void type_raw_bounds(uint8_t size_code, int32_t *out_min, int32_t *out_max) {
  int32_t lo = -32768;
  int32_t hi = 32767;
  switch (size_code) {
    case 0: lo = 0; hi = 255; break;           // u8
    case 1: lo = -128; hi = 127; break;        // s8
    case 2: lo = 0; hi = 65535; break;         // u16
    case 3: lo = -32768; hi = 32767; break;    // s16
    case 4: lo = 0; hi = 1000000; break;       // u32 (exact float/int32 safe cap)
    case 5: lo = -1000000; hi = 1000000; break;  // s32
    default: break;
  }
  if (out_min != nullptr) *out_min = lo;
  if (out_max != nullptr) *out_max = hi;
}

inline void number_raw_bounds(uint8_t size_code, int32_t meta_min, int32_t meta_max,
                              int32_t *out_min, int32_t *out_max) {
  if (meta_min != 0 || meta_max != 0) {
    if (out_min != nullptr) *out_min = meta_min;
    if (out_max != nullptr) *out_max = meta_max;
    return;
  }
  type_raw_bounds(size_code, out_min, out_max);
}

inline int32_t clamp_raw_from_float(float value, int16_t factor, uint8_t size_code,
                                    int32_t meta_min, int32_t meta_max,
                                    float *out_clamped_value) {
  double f = factor ? static_cast<double>(factor) : 1.0;
  int32_t lo = 0;
  int32_t hi = 0;
  number_raw_bounds(size_code, meta_min, meta_max, &lo, &hi);
  double scaled = std::round(static_cast<double>(value) * f);
  double dlo = static_cast<double>(lo);
  double dhi = static_cast<double>(hi);
  if (std::isnan(scaled) || scaled < dlo) scaled = dlo;
  else if (scaled > dhi) scaled = dhi;
  int32_t raw = static_cast<int32_t>(scaled);
  if (out_clamped_value != nullptr) {
    *out_clamped_value = static_cast<float>(static_cast<double>(raw) / f);
  }
  return raw;
}

enum class SelectionParseError : uint8_t {
  OK = 0,
  BAD_TOKEN,
  UNKNOWN_ADDR,
  TOO_MANY,
};

// Parse comma-separated `<addr>[:r|ro|w|rw]` tokens, deduplicating before applying `max_count`.
inline SelectionParseError parse_selection_csv(
    const std::string &csv,
    bool (*is_known)(uint16_t),
    uint16_t *addrs_out,
    uint64_t *ro_mask_out,
    uint16_t *count_out,
    uint16_t max_count,
    std::string *bad_tok_out) {
  uint16_t count = 0;
  uint64_t mask = 0;
  for (size_t i = 0; i <= csv.size();) {
    size_t j = csv.find(',', i);
    if (j == std::string::npos) j = csv.size();
    std::string tok = csv.substr(i, j - i);
    i = j + 1;
    if (tok.empty()) continue;

    std::string addr_str = tok;
    bool ro = false;
    size_t colon = tok.find(':');
    if (colon != std::string::npos) {
      addr_str = tok.substr(0, colon);
      std::string mode = tok.substr(colon + 1);
      if (mode == "r" || mode == "ro") {
        ro = true;
      } else if (mode == "w" || mode == "rw") {
        ro = false;
      } else {
        if (bad_tok_out != nullptr) *bad_tok_out = tok;
        return SelectionParseError::BAD_TOKEN;
      }
    }

    if (addr_str.empty()) {
      if (bad_tok_out != nullptr) *bad_tok_out = tok;
      return SelectionParseError::BAD_TOKEN;
    }
    for (char ch : addr_str) {
      if (ch < '0' || ch > '9') {
        if (bad_tok_out != nullptr) *bad_tok_out = tok;
        return SelectionParseError::BAD_TOKEN;
      }
    }
    char *end = nullptr;
    long v = strtol(addr_str.c_str(), &end, 10);
    if (end == addr_str.c_str() || *end != '\0' || v <= 0 || v > 65535) {
      if (bad_tok_out != nullptr) *bad_tok_out = tok;
      return SelectionParseError::BAD_TOKEN;
    }

    uint16_t addr = static_cast<uint16_t>(v);
    if (is_known == nullptr || !is_known(addr)) {
      if (bad_tok_out != nullptr) *bad_tok_out = addr_str;
      return SelectionParseError::UNKNOWN_ADDR;
    }

    bool dupe = false;
    for (uint16_t k = 0; k < count; k++) {
      if (addrs_out[k] == addr) {
        dupe = true;
        break;
      }
    }
    if (dupe) continue;

    if (count >= max_count) {
      return SelectionParseError::TOO_MANY;
    }
    if (ro && count < 64) {
      mask |= (uint64_t{1} << count);
    }
    addrs_out[count++] = addr;
  }
  if (count_out != nullptr) *count_out = count;
  if (ro_mask_out != nullptr) *ro_mask_out = mask;
  return SelectionParseError::OK;
}

template <typename UnclampedFn>
inline void migrate_v1_to_v2(const HeatWhisperSelectionV1 &v1,
                             HeatWhisperSelection *out,
                             UnclampedFn is_addr_unclamped) {
  if (out == nullptr) return;
  out->version = 2;
  out->reserved = 0;
  out->ro_lo = 0;
  out->ro_hi = 0;
  uint16_t n = v1.count <= kMaxSelectionSlots ? v1.count : kMaxSelectionSlots;
  out->count = n;
  for (uint16_t i = 0; i < kMaxSelectionSlots; i++) {
    out->addrs[i] = i < n ? v1.addrs[i] : 0;
  }
  for (uint16_t i = 0; i < n; i++) {
    if (is_addr_unclamped(out->addrs[i])) {
      out->set_ro(i, true);
    }
  }
}

}  // namespace safety
}  // namespace heatwhisper
}  // namespace esphome
