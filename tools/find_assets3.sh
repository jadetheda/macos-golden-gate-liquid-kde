#!/usr/bin/env bash
set -e

OUTPUT_DIR="$(pwd)/output_gg_full3"
mkdir -p "$OUTPUT_DIR"

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
echo "Downloading InstallAssistant.pkg..."
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg

echo "Unpacking xar..."
mkdir -p /tmp/xar_unpacked3
cd /tmp/xar_unpacked3
xar -xf /tmp/InstallAssistant.pkg

echo "Finding all .dmg files in xar payload..."
find . -name "*.dmg" -print

# Mount SharedSupport.dmg
SHARED_DMG=$(find . -name "SharedSupport.dmg" | head -n 1)
if [ -n "$SHARED_DMG" ]; then
    echo "Mounting $SHARED_DMG..."
    MOUNT_POINT="/tmp/shared_mount3"
    mkdir -p "$MOUNT_POINT"
    hdiutil attach "$SHARED_DMG" -mountpoint "$MOUNT_POINT" -nobrowse -noverify -readonly || true
    
    echo "Finding all .dmg and .pkg files inside SharedSupport mount..."
    find "$MOUNT_POINT" -name "*.dmg" -o -name "*.pkg" -print
    
    # Mount BaseSystem.dmg if present
    BASE_DMG=$(find "$MOUNT_POINT" -name "BaseSystem.dmg" | head -n 1)
    if [ -n "$BASE_DMG" ]; then
        echo "Mounting BaseSystem.dmg: $BASE_DMG"
        BASE_POINT="/tmp/base_mount3"
        mkdir -p "$BASE_POINT"
        hdiutil attach "$BASE_DMG" -mountpoint "$BASE_POINT" -nobrowse -noverify -readonly || true
        
        echo "Listing Assets.car in BaseSystem mount:"
        find "$BASE_POINT" -name "Assets.car" -print
    fi
fi
