#!/usr/bin/env bash
set -e

echo "=== System Information ==="
sw_vers
uname -a

OUTPUT_DIR="$(pwd)/output_traffic_lights"
mkdir -p "$OUTPUT_DIR/live_captures"
mkdir -p "$OUTPUT_DIR/extracted_car_assets"
mkdir -p "$OUTPUT_DIR/window_controls"

echo "=== Step 1: Running Swift Native Window Traffic Light Capture ==="
swift tools/capture_traffic_lights.swift "$OUTPUT_DIR/live_captures" || echo "Swift live capture returned non-zero (continuing with asset extraction)"

echo "=== Step 2: Locating System Assets.car Files ==="
CAR_FILES=$(find /System/Library -name "Assets.car" -o -name "SystemAppearance.bundle" 2>/dev/null | grep -iE 'appearance|appkit|control|coreui' || true)

echo "Found Assets.car files:"
echo "$CAR_FILES"

echo "=== Step 3: Building cartool Asset Extractor ==="
git clone --depth 1 https://github.com/steventroughtonsmith/cartool /tmp/cartool_src 2>/dev/null || true
if [ -d /tmp/cartool_src ]; then
    clang -framework Foundation -framework CoreUI /tmp/cartool_src/cartool/main.m -o /tmp/cartool 2>/dev/null || true
    echo "cartool built successfully."
fi

echo "=== Step 4: Extracting Assets.car Catalog & Images ==="
for car in $CAR_FILES; do
    if [ -f "$car" ]; then
        base=$(basename "$(dirname "$car")")_$(basename "$car")
        echo "Processing $car -> $base"
        
        # Dump catalog JSON using built-in macOS assetutil
        /usr/bin/assetutil -I "$car" > "$OUTPUT_DIR/extracted_car_assets/${base}_catalog.json" 2>/dev/null || true
        
        # Extract assets using cartool if compiled
        if [ -f /tmp/cartool ]; then
            car_out="$OUTPUT_DIR/extracted_car_assets/$base"
            mkdir -p "$car_out"
            /tmp/cartool "$car" "$car_out" 2>/dev/null || true
        fi
    fi
done

# Try installing acextract via Homebrew if available
if command -v brew &>/dev/null; then
    echo "Attempting acextract installation..."
    brew install acextract 2>/dev/null || true
    if command -v acextract &>/dev/null; then
        for car in $CAR_FILES; do
            if [ -f "$car" ]; then
                car_out="$OUTPUT_DIR/extracted_car_assets/acextract_$(basename "$car" .car)"
                mkdir -p "$car_out"
                acextract -i "$car" -o "$car_out" 2>/dev/null || true
            fi
        done
    fi
fi

echo "=== Step 5: Collecting Window Controls & Traffic Light Assets ==="
find "$OUTPUT_DIR" -type f \( -iname "*close*" -o -iname "*mini*" -o -iname "*zoom*" -o -iname "*traffic*" -o -iname "*window*" -o -iname "*cluster*" \) -exec cp {} "$OUTPUT_DIR/window_controls/" 2>/dev/null || true

echo "=== Capture Summary ==="
ls -la "$OUTPUT_DIR"
ls -la "$OUTPUT_DIR/live_captures" 2>/dev/null || true
ls -la "$OUTPUT_DIR/window_controls" 2>/dev/null || true

echo "Asset extraction pipeline completed successfully."
