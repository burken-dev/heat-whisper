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
    assert "python3 scripts/stamp_manifest.py" in yml  # md5 computed there (hashlib)
    assert "hashlib.md5" in open(os.path.join(REPO, "scripts", "stamp_manifest.py")).read()

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

def test_release_script_resolves_next_tags(tmp_path):
    import subprocess
    # Initialize a temporary git repo to test tag resolution in isolation
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "tag", "v0.1.0"], cwd=tmp_path, check=True)
    subprocess.run(["git", "tag", "v0.2.0-beta.1"], cwd=tmp_path, check=True)
    subprocess.run(["git", "tag", "v0.2.0-beta.2"], cwd=tmp_path, check=True)

    p = os.path.abspath(os.path.join(REPO, "scripts", "release.sh"))
    env = {**os.environ, "DRY_RUN": "1"}

    # With v0.1.0 stable and v0.2.0-beta.* in progress, stable minor must resolve to v0.2.0 (not v0.1.0 or v0.0.0)
    res = subprocess.run([p, "stable", "minor"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v0.2.0"

    # stable patch resolves to v0.1.1
    res = subprocess.run([p, "stable", "patch"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v0.1.1"

    # stable major resolves to v1.0.0
    res = subprocess.run([p, "stable", "major"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v1.0.0"

    # beta 0.2.0 resolves to next beta number (v0.2.0-beta.3)
    res = subprocess.run([p, "beta", "0.2.0"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v0.2.0-beta.3"

    # Once v0.2.0 is tagged:
    subprocess.run(["git", "tag", "v0.2.0"], cwd=tmp_path, check=True)
    res = subprocess.run([p, "stable", "minor"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"failed: {res.stderr}\n{res.stdout}"
    assert res.stdout.strip() == "v0.3.0"



def test_project_version_comes_from_fw_version_substitution():
    # ESPHome's update entity compares manifest "version" with esphome.project.version.
    base = open(os.path.join(REPO, "packages", "base.yaml")).read()
    assert 'version: "${fw_version}"' in base
    assert "fw_version: dev" in base
    yml = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert "-s fw_version" in yml or "fw_version \"$FW_VERSION\"" in yml


def _stamp(tmp_path, version, base, ota_files):
    import importlib.util
    spec = importlib.util.spec_from_file_location("stamp_manifest", os.path.join(REPO, "scripts", "stamp_manifest.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    for name, data in ota_files.items():
        (tmp_path / name).write_bytes(data)
    return mod.stamp(os.path.join(REPO, "manifest.json"), version, base, str(tmp_path))


def test_stamp_manifest_uses_own_binaries_and_channel_base(tmp_path):
    import hashlib
    m = _stamp(tmp_path, "0.2.0-beta.3", "https://x.io/hw/beta/",
               {"heatwhisper_esp32.ota.bin": b"esp32", "heatwhisper_esp32_s3_rs485.ota.bin": b"s3"})
    assert m["version"] == "0.2.0-beta.3"
    esp32, s3 = m["builds"]
    assert esp32["ota"] == {"md5": hashlib.md5(b"esp32").hexdigest(), "path": "https://x.io/hw/beta/heatwhisper_esp32.ota.bin"}
    assert s3["ota"] == {"md5": hashlib.md5(b"s3").hexdigest(), "path": "https://x.io/hw/beta/heatwhisper_esp32_s3_rs485.ota.bin"}


def test_stamp_manifest_skips_ota_for_missing_binary(tmp_path):
    m = _stamp(tmp_path, "0.1.0", "https://x.io/hw", {"heatwhisper_esp32.ota.bin": b"esp32"})
    assert "ota" in m["builds"][0] and "ota" not in m["builds"][1]


def test_ci_stamps_both_channels_via_script():
    yml = open(os.path.join(REPO, ".github", "workflows", "build.yml")).read()
    assert yml.count("python3 scripts/stamp_manifest.py") == 2  # deployed channel + counterpart channel
    assert "json.load(open('manifest.json'))" not in yml  # no inline stamping that leaks ota across channels
