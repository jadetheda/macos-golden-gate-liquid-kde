#!/usr/bin/env bash
set -e

echo "=== Listing files in shared_mount3 ==="
hdiutil attach ./SharedSupport.dmg -mountpoint /tmp/sm3 -nobrowse -noverify -readonly
find /tmp/sm3 -maxdepth 4 -print
hdiutil detach /tmp/sm3 || true
