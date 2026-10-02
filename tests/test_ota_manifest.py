# tests/test_ota_manifest.py — managed OTA via channel manifest.
import os
REPO = os.path.join(os.path.dirname(__file__), "..")

def test_base_yaml_has_managed_update():
    update = open(os.path.join(REPO, "packages", "ota_update.yaml")).read()
    assert "http_request:" in update
    assert "platform: http_request" in update
    assert "source: ${ota_manifest_url}" in update
    assert "update_interval:" in update
    base = open(os.path.join(REPO, "packages", "base.yaml")).read()
    assert "platform: esphome" in base  # dashboard OTA stays for all boards

def test_top_level_yamls_define_channel_url():
    for f in ("heatwhisper_esp32.yaml", "heatwhisper_esp32_s3_rs485.yaml"):
        src = open(os.path.join(REPO, f)).read()
        assert "ota_manifest_url:" in src, f
        assert "https://burken-dev.github.io/heat-whisper/manifest.json" in src, f
        assert "ota_update.yaml" in src, f
    pico = open(os.path.join(REPO, "heatwhisper_pico_w.yaml")).read()
    assert "ota_update.yaml" not in pico  # Pico W stays manual UF2

def test_repo_manifest_stays_dev_without_ota():
    import json
    m = json.load(open(os.path.join(REPO, "manifest.json")))
    assert m["version"] == "0.0.0-dev"
    assert {b["chipFamily"] for b in m["builds"]} == {"ESP32", "ESP32-S3"}

def test_ci_overrides_channel_and_stamps_ota():
    yml = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "-s ota_manifest_url" in yml
    assert "beta/manifest.json" in yml
    assert "md5sum" in yml

def test_release_script_exists_and_validates_semver():
    import stat
    p = os.path.join(REPO, "scripts", "release.sh")
    src = open(p).read()
    assert bool(os.stat(p).st_mode & stat.S_IXUSR)
    assert "^v" in src and "-beta" in src
    assert "pytest" in src and "esphome config" in src

def test_release_skill_enforces_workflow():
    skill = open(os.path.join(REPO, ".opencode", "skills", "release-workflow", "SKILL.md")).read()
    assert "scripts/release.sh" in skill
    assert "ota_update.yaml" in skill
    assert "Pico" in skill
    assert "git tag vX.Y.Z" not in skill  # script is the only entry point

def test_release_script_resolves_next_tags():
    import subprocess
    p = os.path.join(REPO, "scripts", "release.sh")
    env = {**os.environ, "DRY_RUN": "1"}

    # stable minor should resolve to v0.3.0 (since v0.2.0 is the latest stable tag)
    res = subprocess.run([p, "stable", "minor"], env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v0.3.0"

    # stable patch should resolve to v0.2.1
    res = subprocess.run([p, "stable", "patch"], env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v0.2.1"

    # stable major should resolve to v1.0.0
    res = subprocess.run([p, "stable", "major"], env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v1.0.0"

    # beta default should resolve to v0.2.0-beta.19
    res = subprocess.run([p, "beta"], env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v0.2.0-beta.19"

