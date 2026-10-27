#!/usr/bin/env bash
set -e

OUTPUT_DIR="$(pwd)/output_gg_full4"
mkdir -p "$OUTPUT_DIR"

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
echo "Downloading InstallAssistant.pkg..."
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg

echo "Unpacking xar..."
mkdir -p /tmp/xar_unpacked4
cd /tmp/xar_unpacked4
xar -xf /tmp/InstallAssistant.pkg

echo "Finding all files in xar unpacked:"
find . -print

SHARED_DMG=$(find . -name "SharedSupport.dmg" | head -n 1)
if [ -n "$SHARED_DMG" ]; then
    echo "Mounting $SHARED_DMG..."
    MOUNT_POINT="/tmp/shared_mount4"
    mkdir -p "$MOUNT_POINT"
    hdiutil attach "$SHARED_DMG" -mountpoint "$MOUNT_POINT" -nobrowse -noverify -readonly
    
    echo "Listing shared_mount4:"
    find "$MOUNT_POINT" -maxdepth 3 -print
    
    hdiutil detach "$MOUNT_POINT" || true
fi
