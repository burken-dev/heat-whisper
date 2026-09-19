# tests/test_subscription.py
import os
REPO = os.path.join(os.path.dirname(__file__), "..")
HDR = open(os.path.join(REPO, "components", "nibe", "nibe.h")).read()

def test_enabled_set_api_present():
    assert "set_register_enabled" in HDR
    assert "is_enabled" in HDR
    assert "disabled_" in HDR

def test_ensure_polled_present():
    assert "ensure_polled" in HDR
