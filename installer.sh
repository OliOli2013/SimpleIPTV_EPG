#!/bin/sh
# Simple IPTV EPG 3.1.0-r1 - AIO IPTV PL / Pawel Pawelek
set -eu
PLUGIN_DIR="/usr/lib/enigma2/python/Plugins/Extensions/SimpleIPTV_EPG"
REPO_ARCHIVE="https://github.com/OliOli2013/SimpleIPTV_EPG/archive/refs/heads/main.zip"
TEMP="/tmp/simpleiptvepg_install_$$"
BACKUP="$TEMP/backup"
cleanup() { rm -rf "$TEMP"; }
trap cleanup EXIT HUP INT TERM
[ -d /usr/lib/enigma2/python/Plugins/Extensions ] || { echo "Enigma2 not found"; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo "unzip not installed"; exit 1; }
mkdir -p "$TEMP"
if command -v wget >/dev/null 2>&1; then
    wget -q -O "$TEMP/code.zip" "$REPO_ARCHIVE"
elif command -v curl >/dev/null 2>&1; then
    curl -fLsS --connect-timeout 20 --max-time 180 -o "$TEMP/code.zip" "$REPO_ARCHIVE"
else
    echo "wget or curl required"; exit 1
fi
[ -s "$TEMP/code.zip" ] || { echo "Empty archive"; exit 1; }
unzip -q "$TEMP/code.zip" -d "$TEMP"
SRC="$TEMP/SimpleIPTV_EPG-main/src"
[ -s "$SRC/plugin.py" ] && [ -s "$SRC/worker.py" ] && [ -s "$SRC/epgimport_bridge.py" ] || { echo "Incomplete plugin source"; exit 1; }
if [ -d "$PLUGIN_DIR" ]; then
    mv "$PLUGIN_DIR" "$BACKUP"
fi
if ! mkdir -p "$PLUGIN_DIR" || ! cp -a "$SRC"/. "$PLUGIN_DIR"/; then
    echo "Install failed - restoring previous version"
    rm -rf "$PLUGIN_DIR"
    if [ -d "$BACKUP" ]; then mv "$BACKUP" "$PLUGIN_DIR"; fi
    exit 1
fi
find "$PLUGIN_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find "$PLUGIN_DIR" -type d -name __pycache__ -exec rm -rf {} \; 2>/dev/null || true
chmod 755 "$PLUGIN_DIR"
echo "Simple IPTV EPG installed. Restart Enigma2 GUI from its menu."
