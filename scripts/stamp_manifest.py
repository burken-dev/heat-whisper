#!/usr/bin/env python3
"""Stamp a channel manifest: version + per-chip OTA path/md5 derived from the OTA binaries.

Usage: stamp_manifest.py TEMPLATE OUT VERSION BASE_URL OTA_DIR

TEMPLATE is the pristine repo manifest.json (never stamped in place). BASE_URL is where
this channel's binaries are served (root for stable, .../beta for beta). md5 is always
computed from the actual .ota.bin in OTA_DIR, so version, path and md5 can't drift apart.
A chip whose .ota.bin is missing gets no "ota" entry (ESPHome then skips it).
"""
import hashlib, json, os, sys

OTA_FILES = {"ESP32": "heatwhisper_esp32.ota.bin", "ESP32-S3": "heatwhisper_esp32_s3_rs485.ota.bin"}


def stamp(template, version, base_url, ota_dir):
    with open(template) as f:
        m = json.load(f)
    m["version"] = version
    for build in m["builds"]:
        name = OTA_FILES.get(build["chipFamily"])
        path = os.path.join(ota_dir, name) if name else None
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                md5 = hashlib.md5(f.read()).hexdigest()
            build["ota"] = {"md5": md5, "path": f"{base_url.rstrip('/')}/{name}"}
    return m


if __name__ == "__main__":
    template, out, version, base_url, ota_dir = sys.argv[1:6]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(stamp(template, version, base_url, ota_dir), f, indent=2)
