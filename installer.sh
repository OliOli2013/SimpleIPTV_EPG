#!/bin/sh
# Simple IPTV EPG installer
# AIO IPTV PL / Paweł Pawełek
# Version 3.0.0 build r1

PLUGIN_PATH="/usr/lib/enigma2/python/Plugins/Extensions/SimpleIPTV_EPG"
REPO_URL="https://github.com/OliOli2013/SimpleIPTV_EPG/archive/refs/heads/main.zip"
TEMP_DIR="/tmp/simpleiptvepg_install"
ARCHIVE="$TEMP_DIR/main.zip"
SRC_DIR="$TEMP_DIR/SimpleIPTV_EPG-main/src"

cleanup() {
    rm -rf "$TEMP_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

echo "================================================"
echo " Simple IPTV EPG 3.0.0 r1 - AIO IPTV PL"
echo "================================================"

# Enigma2 itself provides the Python runtime. The plugin contains Py2/Py3-compatible code paths.
if [ ! -d "/usr/lib/enigma2/python/Plugins/Extensions" ]; then
    echo "ERROR: Enigma2 plugin directory was not found."
    exit 1
fi

if ! command -v unzip >/dev/null 2>&1; then
    echo "ERROR: unzip is required but is not installed."
    exit 1
fi

rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR" || exit 1

echo "Downloading current files from GitHub..."
if command -v wget >/dev/null 2>&1; then
    wget -O "$ARCHIVE" "$REPO_URL" || exit 1
elif command -v curl >/dev/null 2>&1; then
    curl -fL --connect-timeout 20 --max-time 180 -o "$ARCHIVE" "$REPO_URL" || exit 1
else
    echo "ERROR: wget or curl is required."
    exit 1
fi

[ -s "$ARCHIVE" ] || {
    echo "ERROR: downloaded archive is empty."
    exit 1
}

echo "Extracting..."
unzip -q "$ARCHIVE" -d "$TEMP_DIR" || exit 1

if [ ! -f "$SRC_DIR/plugin.py" ] || [ ! -f "$SRC_DIR/constants.py" ] || [ ! -f "$SRC_DIR/screens.py" ]; then
    echo "ERROR: repository archive does not contain a valid Simple IPTV EPG source tree."
    exit 1
fi

echo "Installing plugin..."
rm -rf "$PLUGIN_PATH"
mkdir -p "$PLUGIN_PATH" || exit 1
cp -a "$SRC_DIR"/. "$PLUGIN_PATH"/ || exit 1

# Remove stale bytecode so an older build cannot survive an update.
find "$PLUGIN_PATH" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
find "$PLUGIN_PATH" -type d -name '__pycache__' -exec rm -rf {} \; 2>/dev/null || true

find "$PLUGIN_PATH" -type f -name '*.py' -exec chmod 644 {} \; 2>/dev/null || true
find "$PLUGIN_PATH" -type f -name '*.png' -exec chmod 644 {} \; 2>/dev/null || true
chmod 755 "$PLUGIN_PATH" 2>/dev/null || true

# Keep root metadata available inside the installed plugin as a convenience.
if [ -f "$TEMP_DIR/SimpleIPTV_EPG-main/version" ]; then
    cp -f "$TEMP_DIR/SimpleIPTV_EPG-main/version" "$PLUGIN_PATH/version" 2>/dev/null || true
fi
if [ -f "$TEMP_DIR/SimpleIPTV_EPG-main/CHANGELOG.txt" ]; then
    cp -f "$TEMP_DIR/SimpleIPTV_EPG-main/CHANGELOG.txt" "$PLUGIN_PATH/CHANGELOG.txt" 2>/dev/null || true
fi

echo "================================================"
echo " Installation completed: Simple IPTV EPG 3.0.0 r1"
echo " Restart Enigma2 GUI before using the plugin."
echo "================================================"
exit 0
