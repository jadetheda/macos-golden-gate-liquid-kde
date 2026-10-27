#!/usr/bin/env bash
set -e

echo "=== System Information ==="
sw_vers
uname -a

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
ls -lh /System/Library/CoreServices/SystemAppearance.bundle/Contents/Resources/ > "$OUTPUT_DIR/system_appearance_files.txt" 2>&1 || true
cat "$OUTPUT_DIR/system_appearance_files.txt"

echo "=== Step 3: Copying Core .car Files from SystemAppearance.bundle & AppKit ==="
for car_name in Aqua.car DarkAqua.car SystemAppearance.car Assets.car VibrantLight.car VibrantDark.car; do
    car="/System/Library/CoreServices/SystemAppearance.bundle/Contents/Resources/$car_name"
    if [ -f "$car" ]; then
        cp "$car" "$OUTPUT_DIR/raw_cars/SystemAppearance_$car_name" || true
        echo "Copied $car"
    fi
done
if [ -f "/System/Library/Frameworks/AppKit.framework/Resources/Assets.car" ]; then
    cp "/System/Library/Frameworks/AppKit.framework/Resources/Assets.car" "$OUTPUT_DIR/raw_cars/AppKit_Assets.car" || true
fi

echo "=== Step 4: Fast Catalog Dump with 10s Timeout ==="
for car_name in SystemAppearance.car Aqua.car DarkAqua.car Assets.car; do
    car="/System/Library/CoreServices/SystemAppearance.bundle/Contents/Resources/$car_name"
    if [ -f "$car" ]; then
        echo "Dumping catalog for $car_name..."
        perl -e 'alarm 10; exec @ARGV' /usr/bin/assetutil -I "$car" > "$OUTPUT_DIR/extracted_car_assets/${car_name}_catalog.json" 2>/dev/null || true
    fi
done

echo "=== Step 5: Capture Summary ==="
ls -lh "$OUTPUT_DIR/live_captures" || true
ls -lh "$OUTPUT_DIR/raw_cars" || true
ls -lh "$OUTPUT_DIR/extracted_car_assets" || true
