#!/usr/bin/env python3
"""
update_manifests.py
-------------------
Scans firmware/ and spiffs/ for .bin files, computes their SHA-256 checksums
and sizes, then updates the corresponding *.manifest.json files in firmware/.

Expected layout:
  firmware/<device>/v<version>/firmware.bin   -> firmware/<device>.manifest.json
  spiffs/<device>/v<version>/spiffs.bin       -> firmware/<device>.manifest.json
  config/<device>/config.yaml                 -> firmware/<device>.manifest.json

The manifest URL base uses HTTPS so that ESP32 devices can verify the TLS
certificate when fetching files from raw.githubusercontent.com.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
REPO_URL_BASE = (
    "https://raw.githubusercontent.com/kubkpower/halloween_dmx_pub/main"
)

VERSION_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def latest_version_dir(device_dir: Path) -> tuple[str, Path] | None:
    """Return (version_string, path) for the highest semver sub-directory."""
    best = None
    for entry in device_dir.iterdir():
        if not entry.is_dir():
            continue
        m = VERSION_RE.match(entry.name)
        if not m:
            continue
        ver_tuple = tuple(int(x) for x in m.group(1).split("."))
        if best is None or ver_tuple > best[0]:
            best = (ver_tuple, m.group(1), entry)
    if best is None:
        return None
    return best[1], best[2]


def load_manifest(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_manifest(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def process_firmware(manifest: dict, device: str, firmware_dir: Path) -> bool:
    """Update firmware section; returns True if a binary was found."""
    result = latest_version_dir(firmware_dir)
    if result is None:
        return False
    version, vdir = result
    bin_path = vdir / "firmware.bin"
    if not bin_path.exists():
        return False
    rel = bin_path.relative_to(REPO_ROOT)
    manifest["version"] = version
    manifest["firmware"] = {
        "url": f"{REPO_URL_BASE}/{rel.as_posix()}",
        "sha256": sha256_of(bin_path),
        "size": bin_path.stat().st_size,
    }
    return True


def process_spiffs(manifest: dict, device: str, spiffs_dir: Path) -> None:
    result = latest_version_dir(spiffs_dir)
    if result is None:
        return
    version, vdir = result
    bin_path = vdir / "spiffs.bin"
    if not bin_path.exists():
        return
    rel = bin_path.relative_to(REPO_ROOT)
    manifest["spiffs"] = {
        "url": f"{REPO_URL_BASE}/{rel.as_posix()}",
        "sha256": sha256_of(bin_path),
        "size": bin_path.stat().st_size,
    }


def process_config(manifest: dict, device: str, config_dir: Path) -> None:
    cfg_path = config_dir / "config.yaml"
    if not cfg_path.exists():
        return
    rel = cfg_path.relative_to(REPO_ROOT)
    manifest["config"] = {
        "url": f"{REPO_URL_BASE}/{rel.as_posix()}",
        "sha256": sha256_of(cfg_path),
    }


def main() -> None:
    firmware_root = REPO_ROOT / "firmware"
    spiffs_root = REPO_ROOT / "spiffs"
    config_root = REPO_ROOT / "config"

    # Collect all device names from all three directories
    devices: set[str] = set()
    for root in (firmware_root, spiffs_root, config_root):
        if root.exists():
            for entry in root.iterdir():
                if entry.is_dir():
                    devices.add(entry.name)

    if not devices:
        print("No device directories found; nothing to do.")
        return

    updated = []
    for device in sorted(devices):
        manifest_path = firmware_root / f"{device}.manifest.json"
        manifest = load_manifest(manifest_path)

        manifest.setdefault(
            "$schema",
            f"{REPO_URL_BASE}/manifest.schema.json",
        )
        manifest.setdefault("name", device)
        manifest.setdefault("chip", "esp32")

        fw_dir = firmware_root / device
        sp_dir = spiffs_root / device
        cfg_dir = config_root / device

        found_fw = process_firmware(manifest, device, fw_dir) if fw_dir.exists() else False
        if not found_fw:
            print(f"  Note: no firmware binary found for {device}; firmware section not updated.")
        if sp_dir.exists():
            process_spiffs(manifest, device, sp_dir)
        if cfg_dir.exists():
            process_config(manifest, device, cfg_dir)

        save_manifest(manifest_path, manifest)
        updated.append(manifest_path.name)
        print(f"Updated {manifest_path.name}")

    print(f"\nDone. {len(updated)} manifest(s) updated.")


if __name__ == "__main__":
    main()
