#!/usr/bin/env bash
set -e

OUTPUT_DIR="$(pwd)/output_gg_full2"
mkdir -p "$OUTPUT_DIR"

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
echo "Downloading InstallAssistant.pkg..."
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg

echo "Unpacking xar..."
mkdir -p /tmp/xar_unpacked2
cd /tmp/xar_unpacked2
xar -xf /tmp/InstallAssistant.pkg

SHARED_DMG=$(find . -name "SharedSupport.dmg")
if [ -n "$SHARED_DMG" ]; then
    echo "Mounting $SHARED_DMG..."
    MOUNT_POINT="/tmp/shared_mount2"
    mkdir -p "$MOUNT_POINT"
    hdiutil attach "$SHARED_DMG" -mountpoint "$MOUNT_POINT" -nobrowse -noverify -readonly || true
    
    echo "Listing shared_mount2 contents:"
    find "$MOUNT_POINT" -maxdepth 3 -print
    
    # Mount base system if present
    BASE_DMG=$(find "$MOUNT_POINT" -name "*.dmg" | head -n 1)
    if [ -n "$BASE_DMG" ]; then
        echo "Mounting base DMG: $BASE_DMG"
        BASE_POINT="/tmp/base_mount2"
        mkdir -p "$BASE_POINT"
        hdiutil attach "$BASE_DMG" -mountpoint "$BASE_POINT" -nobrowse -noverify -readonly || true
        echo "Listing base_mount2 contents:"
        find "$BASE_POINT" -name "Assets.car" -print
    fi
fi
