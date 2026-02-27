Place firmware .bin files in this directory following the naming convention:
  firmware/halloween-dmx-controller/v1.0.0/firmware.bin

The GitHub Actions workflow will automatically compute the SHA-256 checksum
and update halloween-dmx-controller.manifest.json when new binaries are pushed.
