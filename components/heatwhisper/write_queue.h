// components/heatwhisper/write_queue.h — EEPROM-safe write queue with
// no-op deduplication and pending-write coalescing, no ESPHome deps.
#pragma once
#include "nibe.h"
#include <stddef.h>
#include <stdint.h>
#include <deque>
#include <utility>
#include <vector>
namespace esphome {
namespace heatwhisper {
struct WriteRequest {
  uint16_t addr;
  int32_t raw;
  bool dedupe{true};
};
enum class QueueResult : uint8_t {
  ENQUEUED = 0,
  COALESCED,
  CANCELLED,
  SKIPPED_NOOP,
  SKIPPED_DUPE,
  DROPPED_UNWRITABLE,
  EVICTED_OLDEST,
};
class WriteQueue {
 public:
  static constexpr size_t kMaxPending = 4;

  void record_known(uint16_t addr, int32_t raw) {
    for (auto &kv : last_raw_) {
      if (kv.first == addr) {
        kv.second = raw;
        return;
      }
    }
    last_raw_.push_back({addr, raw});
  }

  bool lookup_known(uint16_t addr, int32_t *out) const {
    for (const auto &kv : last_raw_) {
      if (kv.first == addr) {
        if (out != nullptr) *out = kv.second;
        return true;
      }
    }
    return false;
  }

  QueueResult enqueue(uint16_t addr, int32_t raw, bool dedupe = true, bool in_flight = false) {
    if (!nibe::is_writable(addr)) return QueueResult::DROPPED_UNWRITABLE;
    const size_t start = (in_flight && !pending_.empty()) ? 1 : 0;
    if (dedupe) {
      bool has_base = false;
      int32_t base_raw = 0;
      bool base_is_inflight = false;
      if (start == 1 && pending_[0].addr == addr) {
        has_base = true;
        base_raw = pending_[0].raw;
        base_is_inflight = true;
      } else {
        has_base = lookup_known(addr, &base_raw);
      }
      for (size_t i = start; i < pending_.size(); i++) {
        if (pending_[i].addr != addr) continue;
        if (pending_[i].raw == raw) return QueueResult::SKIPPED_DUPE;
        if (has_base && base_raw == raw) {
          pending_.erase(pending_.begin() + (ptrdiff_t) i);
          return QueueResult::CANCELLED;
        }
        pending_[i].raw = raw;
        return QueueResult::COALESCED;
      }
      if (has_base && base_raw == raw) {
        return base_is_inflight ? QueueResult::SKIPPED_DUPE : QueueResult::SKIPPED_NOOP;
      }
    }
    bool evicted = false;
    if (pending_.size() >= kMaxPending) {
      pending_.erase(pending_.begin() + (ptrdiff_t) start);
      evicted = true;
    }
    pending_.push_back({addr, raw, dedupe});
    return evicted ? QueueResult::EVICTED_OLDEST : QueueResult::ENQUEUED;
  }

  bool empty() const { return pending_.empty(); }
  size_t size() const { return pending_.size(); }
  const WriteRequest &front() const { return pending_.front(); }

  void pop_sent() {
    if (pending_.empty()) return;
    WriteRequest w = pending_.front();
    pending_.pop_front();
    if (w.dedupe) record_known(w.addr, w.raw);
  }

  void pop_failed() {
    if (!pending_.empty()) pending_.pop_front();
  }

 private:
  std::deque<WriteRequest> pending_;
  std::vector<std::pair<uint16_t, int32_t>> last_raw_;
};
}  // namespace heatwhisper
}  // namespace esphome
