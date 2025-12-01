# Simple IPTV EPG v1.3 🚀

![Logo](src/Kod_QR_buycoffee.png)

## 🇵🇱 Opis (PL)
**Lekki, inteligentny i hybrydowy importer EPG dla Enigma2.**
Wtyczka rozwiązuje problem braku EPG na listach IPTV. Działa hybrydowo: pobiera pliki XML z internetu oraz **kopiuje EPG z kanałów satelitarnych** (jeśli są dostępne na liście).

**Nowość w v1.3:**
* Pełna obsługa list typu **MAC Portal / Stalker** (JediMaker, XStreamity).
* Nowy silnik skanowania (czyta systemową bazę `lamedb`), naprawiający problem "0 połączonych kanałów SAT".
* Możliwość ukrycia wtyczki w tle (Czerwony przycisk).

## 🇬🇧 Description (EN)
**Lightweight, smart, and hybrid EPG Importer for Enigma2.**
This plugin solves the missing EPG issue on IPTV channels. It works in hybrid mode: downloading XML files from the web AND **copying EPG data from Satellite channels** (if available in your bouquets).

**New in v1.3:**
* Full support for **MAC Portal / Stalker** playlists (JediMaker, XStreamity).
* New Core Engine (reads system `lamedb`), fixing the "0 linked SAT channels" issue.
* Background mode (Red button hides the plugin).

---

## 🔥 Główne funkcje / Key Features

* **🌍 International Sources:** Wbudowane źródła EPG dla: **PL, UK, DE, IT, ES, Global** (EPG Share, EPG.PW, IPTV-Org).
* **🧠 Smart Linking (SAT -> IPTV):**
    * Automatycznie łączy kanały SAT z IPTV (np. `TVP 1 HD` -> `TVP1 FHD VIP`).
    * Ignoruje śmieci w nazwach: `HEVC`, `FHD`, `RAW`, `4K`, `PL`, `H.265`.
* **📺 MAC/Stalker Fix:** Poprawnie wykrywa strumienie IPTV udające kanały DVB (`1:0:1...http...`).
* **🚀 Fast Mapper:** Błyskawiczne mapowanie XML (słownikowe) – tysiące kanałów w kilka sekund.
* **🔴 Background Mode:** Naciśnij **Czerwony**, aby ukryć wtyczkę i oglądać TV. Wtyczka powiadomi Cię, gdy skończy pobieranie.
* **⚡ Performance:** Zwiększony limit czasu (do 45 min) dla ogromnych plików XML.

---

## 📥 Instalacja / Installation

Zaloguj się do tunera przez terminal (SSH/Telnet) i wklej komendę:
**Connect to your STB via Terminal (SSH/Telnet) and run:**

```bash
wget -qO - [https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh](https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh) | /bin/sh
