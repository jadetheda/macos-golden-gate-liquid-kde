#!/usr/bin/env bash
set -e

OUTPUT_DIR="$(pwd)/output_gg_full6"
mkdir -p "$OUTPUT_DIR"

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
echo "Downloading InstallAssistant.pkg..."
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg

echo "Unpacking xar..."
mkdir -p /tmp/xar_unpacked6
cd /tmp/xar_unpacked6
xar -xf /tmp/InstallAssistant.pkg

echo "Listing all files in xar unpacked:"
find . -print
