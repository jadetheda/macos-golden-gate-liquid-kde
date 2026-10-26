#!/usr/bin/env bash
set -e

OUTPUT_DIR="$(pwd)/output_gg_full"
mkdir -p "$OUTPUT_DIR"

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
echo "Downloading InstallAssistant.pkg..."
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg

echo "Unpacking xar..."
mkdir -p /tmp/xar_unpacked
cd /tmp/xar_unpacked
xar -xf /tmp/InstallAssistant.pkg

SHARED_DMG=$(find . -name "SharedSupport.dmg")
if [ -n "$SHARED_DMG" ]; then
    echo "Mounting $SHARED_DMG..."
    MOUNT_POINT="/tmp/shared_mount"
    mkdir -p "$MOUNT_POINT"
    hdiutil attach "$SHARED_DMG" -mountpoint "$MOUNT_POINT" -nobrowse -noverify -readonly || true
    
    echo "Finding Assets.car in mount..."
    find "$MOUNT_POINT" -name "Assets.car" -print
    
    # Also find any embedded DMGs or bundles
    find "$MOUNT_POINT" -name "*.dmg" -print
fi

echo "Finding all Assets.car across system..."
find / -name "Assets.car" 2>/dev/null | grep -iE 'appearance|appkit|system' || true
