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

echo "=== Step 2: Unpacking Package ==="
mkdir -p /tmp/pkg_xar
cd /tmp/pkg_xar
xar -xf /tmp/InstallAssistant.pkg
ls -la

echo "=== Step 3: Extracting Payload ==="
mkdir -p /tmp/payload_extracted
cd /tmp/payload_extracted
if [ -f /tmp/pkg_xar/Payload ]; then
    cat /tmp/pkg_xar/Payload | cpio -idmv "*/SharedSupport.dmg" "*/Assets.car" "*/SystemAppearance*" || true
elif [ -f /tmp/pkg_xar/InstallAssistant.pkg/Payload ]; then
    cat /tmp/pkg_xar/InstallAssistant.pkg/Payload | cpio -idmv "*/SharedSupport.dmg" "*/Assets.car" "*/SystemAppearance*" || true
fi

find /tmp -name "*.dmg" -o -name "Assets.car" 2>/dev/null

echo "=== Step 4: Mounting SharedSupport.dmg if found ==="
SHARED_DMG=$(find /tmp -name "SharedSupport.dmg" | head -n 1)
if [ -n "$SHARED_DMG" ]; then
    echo "Mounting $SHARED_DMG..."
    hdiutil attach "$SHARED_DMG" -nobrowse -readonly || true
fi

echo "=== Step 5: Locating and Extracting Assets.car ==="
# Find all Assets.car across /Volumes and /tmp
FOUND_CARS=$(find /Volumes /tmp -name "Assets.car" 2>/dev/null | grep -iE 'appearance|appkit' || true)
echo "Found Assets.car files:"
echo "$FOUND_CARS"

# Build cartool or acextract to dump PNG assets
git clone --depth 1 https://github.com/steventroughtonsmith/cartool /tmp/cartool_src 2>/dev/null || true
if [ -d /tmp/cartool_src ]; then
    clang -framework Foundation -framework CoreUI /tmp/cartool_src/cartool/main.m -o /tmp/cartool 2>/dev/null || true
fi

for car in $FOUND_CARS; do
    echo "Processing $car..."
    car_name=$(basename "$(dirname "$car")")_$(basename "$car")
    mkdir -p "$OUTPUT_DIR/golden_gate_assets/$car_name"
    
    # 1. Catalog JSON
    /usr/bin/assetutil -I "$car" > "$OUTPUT_DIR/golden_gate_assets/${car_name}_catalog.json" 2>/dev/null || true
    
    # 2. Extract PNGs with cartool if compiled
    if [ -f /tmp/cartool ]; then
        /tmp/cartool "$car" "$OUTPUT_DIR/golden_gate_assets/$car_name" 2>/dev/null || true
    fi
done

echo "=== Step 6: Native screencapture of system window buttons ==="
# Test native screencapture of standard app windows on the runner
open -a TextEdit || true
sleep 2
screencapture -x "$OUTPUT_DIR/live_captures/screen_textedit.png" || true

echo "=== Step 7: Summary of Extracted Assets ==="
find "$OUTPUT_DIR" -type f | head -n 50
echo "Finished!"
