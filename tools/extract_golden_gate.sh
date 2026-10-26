#!/usr/bin/env bash
set -e

echo "=== System Information ==="
sw_vers
df -h

OUTPUT_DIR="$(pwd)/output_traffic_lights"
mkdir -p "$OUTPUT_DIR/golden_gate_assets"
mkdir -p "$OUTPUT_DIR/live_captures"

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
echo "=== Step 1: Downloading macOS 27 Golden Gate Installer from Apple CDN ==="
echo "URL: $PKG_URL"
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg

echo "=== Step 2: Unpacking Package with xar ==="
mkdir -p /tmp/pkg_xar
cd /tmp/pkg_xar
xar -xf /tmp/InstallAssistant.pkg
ls -lh

echo "=== Step 3: Inspecting & Mounting SharedSupport.dmg ==="
SHARED_DMG=$(find /tmp/pkg_xar -name "SharedSupport.dmg" | head -n 1)
if [ -n "$SHARED_DMG" ]; then
    echo "Found $SHARED_DMG, attaching..."
    MOUNT_POINT="/tmp/shared_support_mount"
    mkdir -p "$MOUNT_POINT"
    hdiutil attach "$SHARED_DMG" -mountpoint "$MOUNT_POINT" -nobrowse -noverify -readonly || true
    echo "Contents of $MOUNT_POINT:"
    ls -la "$MOUNT_POINT" || true
    find "$MOUNT_POINT" -maxdepth 3 -ls || true
    
    # Check for BaseSystem.dmg or nested dmgs
    NESTED_DMG=$(find "$MOUNT_POINT" -name "*.dmg" | head -n 1)
    if [ -n "$NESTED_DMG" ]; then
        echo "Found nested DMG: $NESTED_DMG, mounting..."
        BASE_MOUNT="/tmp/base_system_mount"
        mkdir -p "$BASE_MOUNT"
        hdiutil attach "$NESTED_DMG" -mountpoint "$BASE_MOUNT" -nobrowse -noverify -readonly || true
        ls -la "$BASE_MOUNT" || true
    fi
fi

echo "=== Step 4: Locating and Extracting Assets.car Files ==="
FOUND_CARS=$(find /tmp -name "Assets.car" 2>/dev/null | grep -iE 'appearance|appkit|system' || true)
echo "Found Assets.car files: $FOUND_CARS"

# Build cartool
git clone --depth 1 https://github.com/steventroughtonsmith/cartool /tmp/cartool_src 2>/dev/null || true
if [ -d /tmp/cartool_src ]; then
    clang -framework Foundation -framework CoreUI /tmp/cartool_src/cartool/main.m -o /tmp/cartool 2>/dev/null || true
fi

for car in $FOUND_CARS; do
    echo "Processing $car..."
    car_name=$(basename "$(dirname "$car")")_$(basename "$car")
    mkdir -p "$OUTPUT_DIR/golden_gate_assets/$car_name"
    /usr/bin/assetutil -I "$car" > "$OUTPUT_DIR/golden_gate_assets/${car_name}_catalog.json" 2>/dev/null || true
    if [ -f /tmp/cartool ]; then
        /tmp/cartool "$car" "$OUTPUT_DIR/golden_gate_assets/$car_name" 2>/dev/null || true
    fi
done

echo "=== Step 5: Screen captures of native app window controls ==="
open -a TextEdit || true
sleep 2
screencapture -x "$OUTPUT_DIR/live_captures/screen_textedit.png" || true

echo "=== Summary ==="
find "$OUTPUT_DIR" -type f | head -n 50
echo "Done!"
