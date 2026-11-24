# tests/test_board_naming.py — unified board naming, CI build isolation, doc count sync.
import os

REPO = os.path.join(os.path.dirname(__file__), "..")


def test_all_boards_share_unified_name_and_friendly_name():
    for fname in ("heatwhisper_esp32.yaml", "heatwhisper_esp32_s3_rs485.yaml", "heatwhisper_pico_w.yaml"):
        src = open(os.path.join(REPO, fname)).read()
        assert "name: heat-whisper\n" in src, fname
        assert "friendly_name: HeatWhisper\n" in src, fname


def test_ci_isolates_shared_build_dir_between_boards():
    yml = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "heat-whisper-s3" not in yml
    assert "heat-whisper-pico" not in yml
    assert ".esphome/build/heat-whisper/.pioenvs/heat-whisper/firmware.uf2" in yml
    # Each board must copy its outputs before the next compile overwrites .esphome/build/heat-whisper
    esp32_compile = yml.index("compile heatwhisper_esp32.yaml")
    esp32_copy = yml.index("cp .esphome/build/heat-whisper/build/firmware.factory.bin fw/")
    pico_compile = yml.index("compile heatwhisper_pico_w.yaml")
    pico_copy = yml.index("cp .esphome/build/heat-whisper/.pioenvs/heat-whisper/firmware.uf2 fw/")
    s3_compile = yml.index("compile heatwhisper_esp32_s3_rs485.yaml")
    s3_copy = yml.index("cp .esphome/build/heat-whisper/build/firmware.factory.bin fw/heatwhisper_esp32_s3_rs485.factory.bin")
    assert esp32_compile < esp32_copy < pico_compile < pico_copy < s3_compile < s3_copy
    assert yml.count("rm -rf .esphome/build/heat-whisper") >= 2


def test_default_register_count_synced_across_docs_and_config():
    readme = open(os.path.join(REPO, "README.md")).read()
    html = open(os.path.join(REPO, "index.html")).read()
    base = open(os.path.join(REPO, "packages", "base.yaml")).read()
    assert "17 registers" in readme
    assert "17 defaults" in html and "18 defaults" not in html
    assert "17 entities" in base and "18 entities" not in base
    # Exact HA entity IDs documented in README for key optimizer entities
    for eid in (
        "sensor.heatwhisper_bt1_outdoor",
        "sensor.heatwhisper_supply_temp_s1",
        "sensor.heatwhisper_return_temp",
        "sensor.heatwhisper_calculated_supply",
        "sensor.heatwhisper_electrical_addition_power",
        "sensor.heatwhisper_operating_priority",
        "number.heatwhisper_degree_minutes",
        "number.heatwhisper_heat_offset_s1",
        "select.heatwhisper_hot_water_comfort_mode",
        "select.heatwhisper_temporary_lux",
        "switch.heatwhisper_allow_additive_heating",
        "switch.heatwhisper_allow_heating",
        "switch.heatwhisper_hot_water_production",
    ):
        assert eid in readme, f"missing {eid} in README.md"
    assert "doens't" not in readme and "forcast" not in readme
