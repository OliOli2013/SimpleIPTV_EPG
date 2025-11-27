```bash
#!/bin/sh
# Simple IPTV EPG Installer by OliOli2013

PLUGIN_PATH="/usr/lib/enigma2/python/Plugins/Extensions/SimpleIPTV_EPG"
REPO_URL="https://github.com/OliOli2013/SimpleIPTV_EPG/archive/refs/heads/main.zip"
TEMP_DIR="/tmp/simple_epg_install"

echo "================================================"
echo "   INSTALLING SIMPLE IPTV EPG v1.0..."
echo "================================================"

# 1. Sprawdzenie Pythona
if [ ! -f /usr/bin/python3 ]; then
    echo "❌ BŁĄD: Wymagany Python 3 (OpenATV 6.4+ lub nowsze)!"
    exit 1
fi

# 2. Usuwanie starej wersji
if [ -d "$PLUGIN_PATH" ]; then
    echo "🗑️  Usuwanie starej wersji..."
    rm -rf "$PLUGIN_PATH"
fi

# 3. Pobieranie nowej wersji
echo "📥 Pobieranie plików z GitHub..."
rm -rf $TEMP_DIR
mkdir -p $TEMP_DIR
cd $TEMP_DIR

# Próba pobrania przez wget lub curl
if which wget > /dev/null; then
    wget --no-check-certificate -O main.zip "$REPO_URL"
elif which curl > /dev/null; then
    curl -k -L -o main.zip "$REPO_URL"
else
    echo "❌ Brak wget lub curl! Nie można pobrać wtyczki."
    exit 1
fi

# 4. Instalacja
if [ -f main.zip ]; then
    echo "📦 Rozpakowywanie..."
    unzip -q main.zip
    
    # Tworzenie katalogu docelowego
    mkdir -p "$PLUGIN_PATH"
    
    # Przenoszenie plików z folderu src
    echo "📂 Instalowanie wtyczki..."
    cp -r SimpleIPTV_EPG-main/src/* "$PLUGIN_PATH/"
    
    # Kopiowanie changeloga i wersji do głównego katalogu wtyczki (opcjonalnie)
    cp SimpleIPTV_EPG-main/version "$PLUGIN_PATH/"
    cp SimpleIPTV_EPG-main/CHANGELOG.txt "$PLUGIN_PATH/"

    # 5. Nadawanie uprawnień (KLUCZOWE)
    echo "🔑 Nadawanie uprawnień..."
    chmod -R 755 "$PLUGIN_PATH"
    
    # Sprzątanie
    cd /tmp
    rm -rf $TEMP_DIR
    
    echo "================================================"
    echo "✅ INSTALACJA ZAKOŃCZONA SUKCESEM!"
    echo "   Zrestartuj GUI Enigmy (Menu -> Czuwanie -> Restart GUI)"
    echo "================================================"
else
    echo "❌ Błąd pobierania archiwum zip!"
    exit 1
fi

exit 0
