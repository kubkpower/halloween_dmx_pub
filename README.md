# halloween_dmx_pub

Public asset repository for Halloween DMX IoT devices based on the ESP32.  
Devices fetch **firmware binaries**, **SPIFFS/LittleFS images**, and **YAML
config files** from this repository over HTTPS.

---

## Repository layout

```
halloween_dmx_pub/
├── firmware/
│   ├── <device-name>/
│   │   └── v<major>.<minor>.<patch>/
│   │       └── firmware.bin          # ESP32 OTA firmware image
│   └── <device-name>.manifest.json   # Per-device OTA manifest (auto-updated)
├── spiffs/
│   └── <device-name>/
│       └── v<major>.<minor>.<patch>/
│           └── spiffs.bin            # SPIFFS / LittleFS filesystem image
├── config/
│   └── <device-name>/
│       └── config.yaml               # Device YAML configuration (no secrets)
├── manifest.schema.json              # JSON Schema for manifest files
└── scripts/
    └── update_manifests.py           # Utility: recompute checksums in manifests
```

---

## OTA manifest format

Each device type has a `firmware/<device-name>.manifest.json` that devices poll
to discover updates.  The manifest is validated against
[`manifest.schema.json`](manifest.schema.json).

```json
{
  "name": "halloween-dmx-controller",
  "chip": "esp32",
  "version": "1.2.0",
  "min_version": "1.0.0",
  "firmware": {
    "url": "https://raw.githubusercontent.com/kubkpower/halloween_dmx_pub/main/firmware/halloween-dmx-controller/v1.2.0/firmware.bin",
    "sha256": "<64-char hex digest>",
    "size": 983040
  },
  "spiffs": {
    "url": "https://raw.githubusercontent.com/kubkpower/halloween_dmx_pub/main/spiffs/halloween-dmx-controller/v1.2.0/spiffs.bin",
    "sha256": "<64-char hex digest>",
    "size": 262144
  },
  "config": {
    "url": "https://raw.githubusercontent.com/kubkpower/halloween_dmx_pub/main/config/halloween-dmx-controller/config.yaml",
    "sha256": "<64-char hex digest>"
  }
}
```

The `min_version` field enables **rollback protection**: devices running a
firmware version lower than `min_version` must update through intermediate
releases before applying this one.

---

## Automation – checksum updates

A GitHub Actions workflow (`.github/workflows/update-checksums.yml`) runs
automatically on every push to `main` that touches a `.bin` or `.yaml` file.
It executes `scripts/update_manifests.py`, which:

1. Scans `firmware/`, `spiffs/`, and `config/` for device directories.
2. Finds the highest semantic-version subdirectory for each device.
3. Computes the SHA-256 digest and file size for every binary/config.
4. Writes the results back into `firmware/<device>.manifest.json`.
5. Commits the updated manifests automatically.

To run locally:

```bash
python3 scripts/update_manifests.py
```

---

## Adding a new device

1. Create the directory tree and drop in your binaries:

   ```
   firmware/<device-name>/v1.0.0/firmware.bin
   spiffs/<device-name>/v1.0.0/spiffs.bin   (optional)
   config/<device-name>/config.yaml          (optional)
   ```

2. Push to `main`. The workflow auto-creates / updates
   `firmware/<device-name>.manifest.json` with correct checksums.

3. Point your ESP32 firmware at:

   ```
   https://raw.githubusercontent.com/kubkpower/halloween_dmx_pub/main/firmware/<device-name>.manifest.json
   ```

---

## Security

### HTTPS on ESP32

All URLs served by this repository use
`https://raw.githubusercontent.com`, which is TLS-protected.  
ESP32 devices **must** verify the server certificate to prevent
man-in-the-middle attacks.  Embed the **DigiCert Global Root CA G2**
certificate (PEM) in your firmware and pass it to `esp_http_client` /
`esp_https_ota`:

```c
// In your esp_https_ota_config_t:
.http_config = &(esp_http_client_config_t){
    .url            = MANIFEST_URL,
    .cert_pem       = digicert_global_root_g2_pem,  // include in your firmware
    .skip_cert_common_name_check = false,
},
```

Verify the active root CA and keep it up-to-date in your firmware:

```bash
openssl s_client -connect raw.githubusercontent.com:443 -showcerts 2>/dev/null \
  | openssl x509 -noout -text | grep "Issuer:"
```

Always embed the current root CA certificate and update it with each firmware
release.  GitHub's TLS certificate chain may change over time (e.g. during CA
rotations); verify the current root CA before shipping a new firmware build and
consider a fallback mechanism (e.g. a bundled Mozilla CA store) so that devices
remain updatable if the CA changes unexpectedly.

### Integrity verification

Devices **must** verify the SHA-256 checksum after downloading a binary and
before flashing it.  Reject the update if checksums do not match.

### No secrets in config files

YAML config files committed to this repository **must not** contain passwords,
API keys, Wi-Fi credentials, or any other sensitive data.  Use BLE provisioning
or a secure on-device key store for secrets.

### Memory considerations

- Stream large binaries directly into flash using `esp_https_ota` rather than
  buffering the entire image in RAM.
- Parse config YAML in a streaming/chunked manner; avoid loading the full file
  into the ESP32 heap at once.
- Keep SPIFFS images within the partition size defined in your partition table
  (typically 1–2 MB).

