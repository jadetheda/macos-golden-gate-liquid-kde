#!/usr/bin/env bash
set -e

echo "=== System Information ==="
sw_vers
uname -a
system_profiler SPDisplaysDataType || true

OUTPUT_DIR="$(pwd)/output_traffic_lights"
mkdir -p "$OUTPUT_DIR/live_captures"
mkdir -p "$OUTPUT_DIR/extracted_car_assets"
mkdir -p "$OUTPUT_DIR/raw_cars"

echo "=== Step 1: Building Native macOS 26 .app Bundle for Liquid Glass Capture ==="
APP_BUNDLE="/tmp/TrafficCalibrator.app"
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"

cat > "$APP_BUNDLE/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>TrafficCalibrator</string>
    <key>CFBundleIdentifier</key>
    <string>com.calibrator.trafficlights</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>TrafficCalibrator</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>26.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>UIDesignRequiresCompatibility</key>
    <false/>
</dict>
</plist>
EOF

swiftc -target arm64-apple-macosx26.0 tools/capture_traffic_lights.swift -o "$APP_BUNDLE/Contents/MacOS/TrafficCalibrator" || \
swiftc tools/capture_traffic_lights.swift -o "$APP_BUNDLE/Contents/MacOS/TrafficCalibrator"

codesign --force --deep --sign - "$APP_BUNDLE" || true

echo "=== Running TrafficCalibrator.app ==="
"$APP_BUNDLE/Contents/MacOS/TrafficCalibrator" "$OUTPUT_DIR/live_captures" || echo "TrafficCalibrator exited non-zero"

echo "=== Step 2: Listing All Files in SystemAppearance.bundle ==="
ls -la /System/Library/CoreServices/SystemAppearance.bundle/Contents/Resources/ || true

echo "=== Step 3: Copying Raw .car Files from SystemAppearance.bundle & AppKit ==="
for car in /System/Library/CoreServices/SystemAppearance.bundle/Contents/Resources/*.car /System/Library/Frameworks/AppKit.framework/Resources/*.car; do
    if [ -f "$car" ]; then
        base=$(basename "$(dirname "$(dirname "$(dirname "$car")")")")_$(basename "$car")
        cp "$car" "$OUTPUT_DIR/raw_cars/$base" || true
        echo "Copied raw car: $car -> $base"
    fi
done

echo "=== Step 4: Compiling extract_car.swift & Extracting All .car Catalogs ==="
swiftc tools/extract_car.swift -o /tmp/extract_car || true

ALL_CARS=$(find /System/Library/CoreServices/SystemAppearance.bundle /System/Library/Frameworks/AppKit.framework /System/Library/PrivateFrameworks/CoreUI.framework /System/Library/PrivateFrameworks/SystemDesktopAppearance.framework -name "*.car" 2>/dev/null || true)

for car in $ALL_CARS; do
    if [ -f "$car" ]; then
        slug=$(echo "$car" | sed 's|/System/Library/||g' | tr '/' '_')
        echo "Processing $car -> $slug"
        json_out="$OUTPUT_DIR/extracted_car_assets/${slug}_catalog.json"
        /usr/bin/assetutil -I "$car" > "$json_out" 2>/dev/null || true
        if [ -f /tmp/extract_car ]; then
            car_out="$OUTPUT_DIR/extracted_car_assets/$slug"
            mkdir -p "$car_out"
            /tmp/extract_car "$car" "$car_out" "$json_out" || true
        fi
    fi
done

echo "=== Step 5: Capture Summary ==="
ls -lh "$OUTPUT_DIR/live_captures" || true
ls -lh "$OUTPUT_DIR/raw_cars" || true
find "$OUTPUT_DIR/extracted_car_assets" -type f | head -n 80 || true
