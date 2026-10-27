#!/usr/bin/env bash
set -e

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg
mkdir -p /tmp/xar7
cd /tmp/xar7
xar -xf /tmp/InstallAssistant.pkg

echo "Mounting SharedSupport.dmg..."
hdiutil attach SharedSupport.dmg -mountpoint /tmp/sm7 -nobrowse -noverify -readonly

echo "Searching for dmg files inside shared_mount7:"
find /tmp/sm7 -name "*.dmg" -print

hdiutil detach /tmp/sm7 || true
