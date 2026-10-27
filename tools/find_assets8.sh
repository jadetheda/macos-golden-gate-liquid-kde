#!/usr/bin/env bash
set -e

PKG_URL="https://swcdn.apple.com/content/downloads/52/46/142-50055-A_O5SYDX5BLY/c72meffi1hj2eaf9fgtakkgwds73ujrr5u/InstallAssistant.pkg"
curl -L --retry 3 --retry-delay 5 "$PKG_URL" -o /tmp/InstallAssistant.pkg
mkdir -p /tmp/xar8
cd /tmp/xar8
xar -xf /tmp/InstallAssistant.pkg

hdiutil attach SharedSupport.dmg -mountpoint /tmp/sm8 -nobrowse -noverify -readonly
find /tmp/sm8 -print
hdiutil detach /tmp/sm8 || true
