# Simple IPTV EPG 3.2.0 RC5 AUTO

**Enigma2 • Python 2 / Python 3 • XMLTV EPG i picony IPTV**  
**Autor:** Paweł Pawełek | AIO Team  
**Status:** wersja testowa RC5 (nie wydanie stabilne)

Simple IPTV EPG automatycznie dopasowuje dostępne przewodniki XMLTV do kanałów w bukietach IPTV tunera Enigma2 i importuje wydarzenia do systemowej pamięci EPG. Potrafi też uzupełniać brakujące picony IPTV. Nie wymaga edytowania bukietów przez użytkownika i **nie zapisuje zmian w listach kanałów**.

> **Ważne:** EPG jest importowane tylko dla usług, dla których istnieje wiarygodne dopasowanie i źródło zawiera rzeczywistą ramówkę. Kamera internetowa, transmisja okazjonalna lub kanał bez publikowanego XMLTV może pozostać bez EPG. Wersja RC5 jest nadal testowana.

## Nowości 3.2.0 RC5 AUTO

- **Prostszy ekran główny:** tylko źródło EPG, częstotliwość automatycznego importu i uzupełnianie piconów.
- **Ustawienia zaawansowane:** wszystkie dotychczasowe opcje są nadal dostępne przez niebieski przycisk **NARZĘDZIA → Ustawienia zaawansowane**.
- **AUTO AIO Polska:** stopniowe uzupełnianie brakujących wydarzeń z niezależnych źródeł XMLTV (EPG.OVH, EPGShare, PolishTeam, iptv-epg.org i EPG.PW). Dodatkowe źródła są używane do brakujących usług, nie do zamiany prawidłowo przypisanej ramówki.
- **EPG Autopilot:** może wybrać do dwóch dodatkowych regionalnych przewodników EPGShare dla kanałów oznaczonych kodem kraju, np. `[UK]` czy `[DE]`, jeśli jest odpowiednio dużo takich usług. Pokrycie zależy od jakości danych dostawców.
- **Bezpieczniejsze mapowanie:** weryfikacja nazw kanałów oraz aliasów XMLTV; ograniczenie fałszywych dopasowań, odrzucanie kolizyjnych i nieprawidłowych referencji.
- **Duplikaty:** deduplikacja wpisów IPTV różniących się tylko zapisem części szesnastkowej referencji; adresy strumieni pozostają niezmienione.
- **Poprawiony importer Enigma2:** prawidłowe przekazanie listy referencji do `eEPGCache.importEvents()`.
- **Picony IPTV:** uzupełnianie brakujących PNG z dostępnych katalogów i logotypów XMLTV. Istniejące picony nie są celowo nadpisywane.
- **Trwały zapis ustawień:** konfiguracja jest zapisywana do `/etc/enigma2/settings`, a błąd zapisu jest wyświetlany użytkownikowi.
- **Raportowanie:** liczby kanałów i wydarzeń XMLTV, udział kolejnych źródeł, plan źródeł regionalnych, problemy z referencjami i wynik próbki kontroli EPG.

## Pierwsze uruchomienie — zalecane ustawienia

Na świeżej instalacji zalecane wartości domyślne:

| Ustawienie na ekranie głównym | Wartość |
|---|---|
| Źródło EPG | **AUTO AIO Polska** |
| Automatyczny import | **Co 24 godziny** |
| Uzupełnianie piconów IPTV | **Tak** |

W ustawieniach zaawansowanych domyślnie wyłączone są: **Kopiuj EPG SAT → IPTV** i **Preferuj EPG z SAT**. Nie włączaj ich bez potrzeby. **Aktualizacja istniejącej instalacji zachowuje wcześniejsze zapisane ustawienia**, więc po aktualizacji sprawdź te dwa przełączniki.

### Przyciski pilota

- **Zielony:** import EPG zgodnie z bieżącymi ustawieniami.
- **Żółty:** test dostępności źródła.
- **Niebieski:** narzędzia (diagnostyka, log, pełny import i nowe mapowanie, osobne uzupełnianie piconów, opcje zaawansowane).
- **OK:** zapis ustawień.
- **Czerwony:** zamknięcie.

Po pierwszej instalacji zalecane jest **Niebieski → Wymuś pełny import + nowe mapowanie**. Poczekaj na zakończenie i sprawdź EPG na kilku różnych kanałach, nie tylko licznik wydarzeń.

## Instalacja

### A. Instalator z GitHub (aktualny kod z `main`)

Na tunerze Enigma2 z działającą siecią oraz narzędziami `wget` lub `curl` i `unzip`:

```sh
wget -O /tmp/simpleiptvepg_installer.sh https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh
sh /tmp/simpleiptvepg_installer.sh
```

Instalator pobiera kod z katalogu **`src/`**, nie starych modułów znajdujących się dawniej w katalogu głównym. Po instalacji **zrestartuj GUI Enigma2**.

### B. Instalacja lokalnego IPK

Jeśli masz zbudowany pakiet `enigma2-plugin-extensions-simpleiptvepg_3.2.0-rc5-auto_all.ipk`, skopiuj go do `/tmp/` i na obrazach z `opkg` wykonaj:

```sh
opkg install /tmp/enigma2-plugin-extensions-simpleiptvepg_3.2.0-rc5-auto_all.ipk
```

Ten pakiet RC5 jest **testowy**. Brak opublikowanego Release RC5 na GitHubie nie oznacza, że ten plik można pobrać z zakładki Releases. Nie próbuj instalować pliku `.ipk` poleceniem `dpkg -i`, jeśli obraz obsługuje tylko pakiety `.deb`.

## Ustawienia zaawansowane i źródła

W **NARZĘDZIA → Ustawienia zaawansowane** dostępne są m.in.:

- zakres importu 2–10 dni;
- uzupełnianie EPG z dodatkowych źródeł;
- wyszukiwanie piconów w katalogu internetowym;
- czułość mapowania (ścisłe, zbalansowane, elastyczne);
- kopiowanie SAT → IPTV i preferencja EPG SAT (domyślnie wyłączone);
- powiadomienia, zapis bazy EPG, pliki tymczasowe i opóźnienie zadania po starcie.

Dostępne jest również automatyczne odczytywanie `sources.xml` / `channels.xml` z BouquetMakerXtream oraz własny adres XMLTV. Nie jest wymagane posiadanie BouquetMakerXtream, by używać `AUTO AIO Polska`.

## Diagnostyka i bezpieczeństwo

| Plik na tunerze | Przeznaczenie |
|---|---|
| `/etc/enigma2/simpleiptvepg_mapping.json` | Zapisane mapowanie XMLTV ↔ IPTV |
| `/etc/enigma2/simpleiptvepg_overrides.json` | Ręczne przypisania nazw do XMLTV ID |
| `/etc/enigma2/simpleiptvepg_report.json` | Ostatni raport importu, w tym `source_coverage` i `epg_autopilot` |
| `/etc/enigma2/simpleiptvepg_state.json` | Stan ostatniego uruchomienia |
| `/tmp/simpleiptvepg.log` | Dziennik zdarzeń |

W raporcie `verification.visible / verification.checked` oznacza wynik **próbki** — nie dowodzi poprawności EPG na wszystkich kanałach. `xml_service_refs` liczy referencje IPTV z wydarzeniami, a niekoniecznie unikalne marki stacji. Wykryte kolizje z SAT są chronione przed importem. Wtyczka nie naprawia automatycznie błędnych referencji bukietów.

Źródła XMLTV mogą być czasowo niedostępne, a automatyczne dopasowanie nie gwarantuje poprawnej ramówki każdej stacji. Nie publikuj raportów zawierających prywatne adresy dostawców bez ich sprawdzenia.

## Wersje i projekt

- Kod bieżący: **3.2.0 RC5 AUTO** (`src/constants.py`).
- Plik `version`: **3.2.0** (bez oznaczenia kandydata; używany przez prosty mechanizm porównywania wersji).
- Ostatni opublikowany **GitHub Release** może być starszy niż kod na gałęzi `main`.
- Nazwa pakietu: `enigma2-plugin-extensions-simpleiptvepg`.
- Katalog instalacyjny: `/usr/lib/enigma2/python/Plugins/Extensions/SimpleIPTV_EPG`.

**Repozytorium:** https://github.com/OliOli2013/SimpleIPTV_EPG  
**Autor:** Paweł Pawełek | AIO Team

---

### English — quick start

**Simple IPTV EPG 3.2.0 RC5 AUTO** is a test release for Enigma2 (Python 2 / Python 3). It imports XMLTV schedules into IPTV services, completes missing IPTV picons and protects satellite EPG service identities. The simplified interface offers three everyday settings: **EPG source, automatic import interval, and IPTV picons**. All other controls remain available under **Blue → Tools → Advanced settings**.

The default configuration uses **AUTO AIO Poland**, imports every **24 hours**, and enables IPTV picon completion. SAT-to-IPTV cloning is off by default for new installations. Multi-source fallback, strict channel-name validation, duplicate-reference filtering and limited country-based EPG feed selection improve safety, but do not guarantee coverage of every channel. After installation restart Enigma2 GUI and run **Tools → Force full import + remap**. See the Polish guide above for full installation and diagnostics.
