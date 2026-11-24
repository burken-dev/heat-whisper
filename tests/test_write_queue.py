# tests/test_write_queue.py — host C++ unit tests for EEPROM-safe WriteQueue
# (deduplication, coalescing, cancellation, in-flight safety, cap eviction).
import os
import subprocess
import tempfile

REPO = os.path.join(os.path.dirname(__file__), "..")
WQ_H = os.path.join(REPO, "components", "heatwhisper", "write_queue.h")

HARNESS = r"""
#include "write_queue.h"
#include <cassert>
#include <cstdio>
using namespace esphome::heatwhisper;

int main() {
  // 1. Sub-20000 addresses dropped regardless of dedupe flag
  {
    WriteQueue q;
    assert(q.enqueue(19999, 1, true) == QueueResult::DROPPED_UNWRITABLE);
    assert(q.enqueue(10001, 1, false) == QueueResult::DROPPED_UNWRITABLE);
    assert(q.empty());
  }

  // 2. Cold boot (unknown register) always enqueues
  {
    WriteQueue q;
    assert(q.enqueue(47011, 0) == QueueResult::ENQUEUED);
    assert(q.size() == 1);
    assert(q.front().addr == 47011 && q.front().raw == 0);
  }

  // 3. Matching known pump readback is skipped as no-op; changed value enqueues
  {
    WriteQueue q;
    q.record_known(47011, 2);
    assert(q.enqueue(47011, 2) == QueueResult::SKIPPED_NOOP);
    assert(q.empty());
    assert(q.enqueue(47011, 3) == QueueResult::ENQUEUED);
    assert(q.size() == 1 && q.front().raw == 3);
  }

  // 4. Duplicate pending write skipped; rapid slider changes coalesce in place
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 1) == QueueResult::ENQUEUED);
    assert(q.enqueue(47011, 1) == QueueResult::SKIPPED_DUPE);
    assert(q.enqueue(47011, 2) == QueueResult::COALESCED);
    assert(q.enqueue(47011, 3) == QueueResult::COALESCED);
    assert(q.size() == 1 && q.front().raw == 3);
  }

  // 5. Pending write reverted back to known pump state cancels the queued write
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    assert(q.enqueue(47011, 0) == QueueResult::CANCELLED);
    assert(q.empty());
  }

  // 6. Post-TX pre-readback duplicate skipped; contradictory readback re-enables write
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    q.pop_sent();
    assert(q.empty());
    assert(q.enqueue(47011, 2) == QueueResult::SKIPPED_NOOP);
    // Pump readback reveals pump stayed at 0
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    assert(q.size() == 1);
  }

  // 7. pop_failed() does NOT update last_raw_, allowing retry
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    q.pop_failed();
    assert(q.empty());
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    assert(q.size() == 1);
  }

  // 8. In-flight Modbus write is never mutated; matching value skipped, change queues behind & coalesces
  {
    WriteQueue q;
    q.record_known(47011, 0);
    assert(q.enqueue(47011, 2) == QueueResult::ENQUEUED);
    // Now pending_[0] = {47011, 2} is in-flight
    assert(q.enqueue(47011, 2, true, true) == QueueResult::SKIPPED_DUPE);
    assert(q.size() == 1 && q.front().raw == 2);
    // New value queues at index 1 without touching in-flight index 0
    assert(q.enqueue(47011, 3, true, true) == QueueResult::ENQUEUED);
    assert(q.size() == 2 && q.front().raw == 2);
    // Further slider change coalesces index 1
    assert(q.enqueue(47011, 4, true, true) == QueueResult::COALESCED);
    assert(q.size() == 2 && q.front().raw == 2);
    // Reverting to in-flight value cancels index 1
    assert(q.enqueue(47011, 2, true, true) == QueueResult::CANCELLED);
    assert(q.size() == 1 && q.front().raw == 2);
    // Queue another value behind in-flight, finish in-flight, confirm next is sent
    assert(q.enqueue(47011, 5, true, true) == QueueResult::ENQUEUED);
    q.pop_sent();
    assert(q.size() == 1 && q.front().raw == 5);
  }

  // 9. Non-deduped one-shot command (45171 Reset Alarm) always enqueues and does not pollute last_raw_
  {
    WriteQueue q;
    assert(q.enqueue(45171, 1, false) == QueueResult::ENQUEUED);
    assert(q.enqueue(45171, 1, false) == QueueResult::ENQUEUED);
    assert(q.size() == 2);
    q.pop_sent();
    q.pop_sent();
    int32_t out = 0;
    assert(!q.lookup_known(45171, &out));
    assert(q.enqueue(45171, 1, false) == QueueResult::ENQUEUED);
  }

  // 10. Cap kMaxPending == 4: evicts oldest when full, never evicts in-flight index 0
  {
    WriteQueue q;
    static_assert(WriteQueue::kMaxPending == 4, "cap must stay 4");
    assert(q.enqueue(47011, 1) == QueueResult::ENQUEUED);
    assert(q.enqueue(47041, 2) == QueueResult::ENQUEUED);
    assert(q.enqueue(47370, 1) == QueueResult::ENQUEUED);
    assert(q.enqueue(47371, 1) == QueueResult::ENQUEUED);
    // Not in-flight: evicts 47011
    assert(q.enqueue(47387, 1, true, false) == QueueResult::EVICTED_OLDEST);
    assert(q.size() == 4 && q.front().addr == 47041);
    // Now 47041 is in-flight: evicts 47370 (index 1), keeps 47041 at index 0
    assert(q.enqueue(48132, 1, true, true) == QueueResult::EVICTED_OLDEST);
    assert(q.size() == 4 && q.front().addr == 47041);
    q.pop_sent();
    assert(q.front().addr == 47371);
  }

  printf("write_queue harness ok\n");
  return 0;
}
"""


def _compile_and_run():
    d = os.path.join(REPO, "components", "heatwhisper")
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "harness.cpp")
        exe = os.path.join(td, "harness")
        with open(src, "w") as fh:
            fh.write(HARNESS)
        p = subprocess.run(
            ["g++", "-std=c++17", "-Wall", "-Werror", src, "-o", exe, f"-I{d}"],
            capture_output=True, text=True)
        assert p.returncode == 0, f"compile failed:\n{p.stderr}"
        p = subprocess.run([exe], capture_output=True, text=True)
        assert p.returncode == 0, f"harness failed:\n{p.stdout}\n{p.stderr}"
        assert "write_queue harness ok" in p.stdout


def test_write_queue_header_compiles_and_passes_vectors():
    assert os.path.exists(WQ_H), "components/heatwhisper/write_queue.h missing"
    _compile_and_run()


def test_write_queue_header_has_no_esphome_deps():
    src = open(WQ_H).read()
    for bad in ("UARTDevice", "ESP_LOG", "App.", "Component.h", "uart/uart.h"):
        assert bad not in src, f"write_queue.h must stay host-compilable, found {bad}"
