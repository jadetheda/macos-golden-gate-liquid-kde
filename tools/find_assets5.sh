#!/usr/bin/env bash
set -e

OUTPUT_DIR="$(pwd)/output_gg_full5"
mkdir -p "$OUTPUT_DIR"

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
echo "Downloading InstallAssistant.pkg..."
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg

echo "Unpacking xar..."
mkdir -p /tmp/xar_unpacked5
cd /tmp/xar_unpacked5
xar -xf /tmp/InstallAssistant.pkg

SHARED_DMG=$(find . -name "SharedSupport.dmg" | head -n 1)
MOUNT_POINT="/tmp/shared_mount5"
mkdir -p "$MOUNT_POINT"
hdiutil attach "$SHARED_DMG" -mountpoint "$MOUNT_POINT" -nobrowse -noverify -readonly

echo "Searching for all .dmg files inside SharedSupport..."
find "$MOUNT_POINT" -name "*.dmg" -print

# Mount the largest dmg inside SharedSupport (usually BaseSystem.dmg or similar)
BIGGEST_DMG=$(find "$MOUNT_POINT" -name "*.dmg" -exec ls -l {} + | sort -n -k5 | tail -n 1 | awk '{print $NF}')
if [ -n "$BIGGEST_DMG" ]; then
    echo "Mounting biggest DMG: $BIGGEST_DMG"
    BASE_POINT="/tmp/base_mount5"
    mkdir -p "$BASE_POINT"
    hdiutil attach "$BIGGEST_DMG" -mountpoint "$BASE_POINT" -nobrowse -noverify -readonly || true
    
    echo "Finding Assets.car in base_mount5:"
    find "$BASE_POINT" -name "Assets.car" -print
fi
