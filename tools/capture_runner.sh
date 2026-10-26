#!/usr/bin/env bash
set -e

echo "=== System Information ==="
sw_vers
uname -a

OUTPUT_DIR="$(pwd)/output_traffic_lights"
mkdir -p "$OUTPUT_DIR"

echo "=== Running Native Window Capture ==="
swift tools/capture_traffic_lights.swift "$OUTPUT_DIR/live_captures" || echo "Swift live capture returned non-zero (continuing with asset extraction)"

echo "=== Searching and Extracting Assets.car Files ==="
mkdir -p "$OUTPUT_DIR/extracted_car_assets"

# Locate SystemAppearance.bundle and AppKit assets
CAR_FILES=$(find /System/Library -name "Assets.car" -o -name "SystemAppearance.bundle" 2>/dev/null | grep -iE 'appearance|appkit|control' | head -n 10 || true)

for car in $CAR_FILES; do
    if [ -f "$car" ]; then
        base=$(basename "$(dirname "$car")")_$(basename "$car")
        echo "Processing $car -> $base"
        
        # Dump catalog JSON using built-in macOS assetutil
        /usr/bin/assetutil -I "$car" > "$OUTPUT_DIR/extracted_car_assets/${base}_catalog.json" 2>/dev/null || true
    fi
done

# Try installing acextract to dump raster and vector assets if brew is present
if command -v brew &>/dev/null; then
    echo "Installing acextract via Homebrew..."
    brew install acextract || true
    if command -v acextract &>/dev/null; then
        for car in $CAR_FILES; do
            if [ -f "$car" ]; then
                target_folder="$OUTPUT_DIR/extracted_car_assets/$(basename "$car" .car)"
                mkdir -p "$target_folder"
                acextract -i "$car" -o "$target_folder" || true
            fi
        done
    fi
fi

# Filter/copy window control images (close, min, zoom, titlebar, traffic) to a quick access folder
mkdir -p "$OUTPUT_DIR/window_controls"
find "$OUTPUT_DIR" -type f \( -iname "*close*" -o -iname "*mini*" -o -iname "*zoom*" -o -iname "*traffic*" -o -iname "*window*" \) -exec cp {} "$OUTPUT_DIR/window_controls/" 2>/dev/null || true

echo "=== Capture and Extraction Summary ==="
ls -la "$OUTPUT_DIR"
ls -la "$OUTPUT_DIR/live_captures" 2>/dev/null || true
ls -la "$OUTPUT_DIR/window_controls" 2>/dev/null || true

echo "Done!"
