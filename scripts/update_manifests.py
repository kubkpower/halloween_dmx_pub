#!/usr/bin/env python3
"""
update_manifests.py
-------------------
Scans firmware/ and spiffs/ for versioned sub-directories, computes SHA-256
checksums and builds the manifest files consumed by OtaManager on the ESP32.

Output files:
  firmware/<device>.manifest.json
  spiffs/<device>.manifest.json

Manifest format:
  {
    "latest": "<semver>",
    "versions": [
      { "version", "date", "notes", "url", "sha256" },
      ...
    ]
  }

Version selection policy (bounded list):
  - The 4 most recent builds (sorted by semver descending),
  - The most recent build of the previous minor series
    (same major, minor < latest_minor),
  - The most recent build of the previous major series
    (major < latest_major).
  Maximum 6 entries -- keeps manifest JSON small for constrained devices.

Expected layout:
  firmware/<device>/v<version>/firmware.bin
  spiffs/<device>/v<version>/spiffs.bin
  firmware/<device>/v<version>/meta.json   (optional: "date", "notes")
"""
import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
REPO_URL_BASE = "https://raw.githubusercontent.com/kubkpower/halloween_dmx_pub/main"
VERSION_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ver_key(entry):
    m = VERSION_RE.match(entry.name)
    if not m:
        return (0, 0, 0)
    return tuple(int(x) for x in m.group(1).split("."))


def read_meta(vdir):
    meta = vdir / "meta.json"
    if meta.exists():
        try:
            # PowerShell 5.1 writes UTF-8 with BOM -> utf-8-sig strips it.
            d = json.loads(meta.read_text(encoding="utf-8-sig"))
            return d.get("date", ""), d.get("notes", "")
        except Exception:
            pass
    return "", ""


def select_versions(versions):
    """Selectionne au plus 6 versions selon la politique suivante :
    - les 4 builds les plus recents,
    - le build le plus recent de la serie mineure precedente,
    - le build le plus recent de la serie majeure precedente.
    Les entrees doivent etre triees par semver decroissant.
    """
    if len(versions) <= 4:
        return versions

    vt0 = tuple(int(x) for x in versions[0]["version"].split("."))
    latest_major, latest_minor = vt0[0], vt0[1]

    selected = list(versions[:4])
    seen = {v["version"] for v in selected}

    # Derniere build de la serie mineure precedente (meme major, minor < latest)
    if latest_minor > 0:
        for v in versions:
            vt = tuple(int(x) for x in v["version"].split("."))
            if vt[0] == latest_major and vt[1] < latest_minor:
                if v["version"] not in seen:
                    selected.append(v)
                    seen.add(v["version"])
                break

    # Derniere build de la serie majeure precedente (major < latest)
    if latest_major > 0:
        for v in versions:
            vt = tuple(int(x) for x in v["version"].split("."))
            if vt[0] < latest_major:
                if v["version"] not in seen:
                    selected.append(v)
                    seen.add(v["version"])
                break

    return selected


def build_version_list(bin_name, root_dir, url_prefix):
    """Construit la liste complete des versions disponibles (triee desc.)."""
    versions = []
    vdirs = sorted(
        (p for p in root_dir.iterdir() if p.is_dir() and VERSION_RE.match(p.name)),
        key=ver_key,
        reverse=True,
    )
    for vdir in vdirs:
        bin_path = vdir / bin_name
        if not bin_path.exists():
            continue
        ver = vdir.name.lstrip("v")
        date, notes = read_meta(vdir)
        versions.append({
            "version": ver,
            "date":    date,
            "notes":   notes,
            "url":     f"{REPO_URL_BASE}/{url_prefix}/{vdir.name}/{bin_name}",
            "sha256":  sha256_of(bin_path),
        })
    return versions


def main():
    fw_root = REPO_ROOT / "firmware"
    sp_root = REPO_ROOT / "spiffs"

    if not fw_root.exists():
        print("firmware/ directory not found.")
        return

    devices = sorted(p.name for p in fw_root.iterdir() if p.is_dir())
    if not devices:
        print("No device directories found; nothing to do.")
        return

    for device in devices:
        dev_fw_dir = fw_root / device
        dev_sp_dir = sp_root / device

        # Firmware manifest
        fw_versions = build_version_list("firmware.bin", dev_fw_dir, f"firmware/{device}")
        fw_versions = select_versions(fw_versions)
        if fw_versions:
            manifest = {"latest": fw_versions[0]["version"], "versions": fw_versions}
            out = fw_root / f"{device}.manifest.json"
            out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            print(f"[OK] {out.name}: {len(fw_versions)} version(s) -- latest {manifest['latest']}")
        else:
            print(f"[skip] {device} -- aucun firmware.bin trouve")

        # SPIFFS manifest
        if dev_sp_dir.exists():
            sp_versions = build_version_list("spiffs.bin", dev_sp_dir, f"spiffs/{device}")
            sp_versions = select_versions(sp_versions)
            if sp_versions:
                manifest = {"latest": sp_versions[0]["version"], "versions": sp_versions}
                out = sp_root / f"{device}.manifest.json"
                out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
                print(f"[OK] {out.name}: {len(sp_versions)} version(s) -- latest {manifest['latest']}")
            else:
                print(f"[skip] {device} SPIFFS -- aucun spiffs.bin trouve")


if __name__ == "__main__":
    main()