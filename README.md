# SimpleIPTV_EPG

**Lekki i inteligentny importer EPG dla list IPTV na tunery Enigma2 (Python 3).**

Wtyczka automatycznie dopasowuje program telewizyjny (EPG) do Twojej listy kanałów IPTV, nawet jeśli nazwy kanałów różnią się od tych w źródłach (np. obsługuje dopiski FHD, HEVC, RAW, PL itp.).

![Logo](src/Kod_QR_buycoffee.png)

## 🔥 Główne funkcje
* **Multi-Source:** Obsługa najlepszych polskich źródeł (EPG Share, Mbebe, OVH, GlobeTV).
* **Smart Mapper:** Inteligentne łączenie kanałów (jeden XML pasuje do wielu wersji kanału: FHD, Backup, HEVC).
* **Background Mode:** Możliwość pobierania EPG w tle podczas oglądania TV.
* **Hybrid Download:** Używa CURL, WGET lub bibliotek Pythona, aby ominąć blokady serwerów.
* **Bezpieczeństwo:** Nie zawiesza tunera, zarządza pamięcią RAM.

## 📥 Instalacja

Uruchom poniższą komendę w terminalu (SSH) swojego tunera:

```bash
wget -qO - [https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh](https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh) | /bin/sh
