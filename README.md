# Simple IPTV EPG 3.1.0 r1 — AIO IPTV PL

Wtyczka Enigma2 (Python 2 i Python 3) importuje XMLTV do EPG kanałów w bukietach IPTV. Nie zastępuje BouquetMakerXtream ani EPGImport, nie edytuje bukietów.

## Nowości

- **BouquetMakerXtream — EPG dostawcy (AUTO)**: odczytuje `/etc/epgimport/bouquetmakerxtream*.sources.xml` i powiązane `*.channels.xml`, dopasowuje XMLTV ID do referencji kanałów IPTV zapisanych na tunerze.
- Alternatywnie można wybrać `AUTO Polska` lub podać **własny URL XMLTV**; zachowano poprzednie źródła.
- Poprawiony interfejs z natywnym API `eEPGCache.importEvents((ref,), events)`.
- Obsługa XMLTV i XMLTV.GZ (także skompresowany zwrot z `xmltv.php?...`).
- Automatyczne dopasowanie nazw dla brakujących mapowań; istniejące powiązania BMX mają pierwszeństwo.
- Dziennik, próbkowa weryfikacja widoczności EPG, raport liczby dopasowań.
- Możliwość kopiowania SAT → IPTV jako opcja, domyślnie wyłączona przy nowych instalacjach.

## Uruchomienie z BMX

1. Stwórz bukiety IPTV w BouquetMakerXtream i upewnij się, że w `/etc/epgimport/` są pliki `bouquetmakerxtream*.sources.xml` i `.channels.xml`.
2. Wtyczka Simple IPTV EPG → **Źródło EPG: BouquetMakerXtream — EPG dostawcy (AUTO)**.
3. Żółty: **Test źródła**. Zielony: **Importuj EPG**.
4. Niebieski → **Diagnostyka**. Sprawdź `trafienia BMX`, `XMLTV kanały/zdarzenia` i kontrolę widoczności.
5. Jeśli nie ma mapowania w BMX, wybierz `CUSTOM` (adres XMLTV) lub inne źródło i sprawdź listę niedopasowanych usług w `/etc/enigma2/simpleiptvepg_report.json`.

**Uwaga:** Sam link XMLTV nie gwarantuje EPG. Wymagana jest zgodność `channel id` i prawidłowej referencji usług (lub pewne dopasowanie po nazwie). Jeśli źródło nie zawiera danego programu, wtyczka go nie wymyśli.

## Instalacja IPK

Przenieś IPK do `/tmp/`, połącz się SSH i wykonaj:

```sh
opkg install /tmp/enigma2-plugin-extensions-simpleiptvepg_3.1.0-r1_all.ipk
```

Jeśli w obrazie jest dpkg zamiast opkg, użyj `dpkg -i /tmp/...ipk` **tylko jeśli menedżer pakietów obrazu obsługuje ten format**. Po instalacji zrestartuj GUI Enigma2.

## AIO Panel

Pozostawiono bez zmian `enigma2-plugin-extensions-simpleiptvepg` oraz katalog `Plugins/Extensions/SimpleIPTV_EPG`. AIO Panel korzysta z `https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh` — żeby użytkownicy AIO dostawali tę wersję, należy wgrać **źródła z ZIP** do repozytorium `SimpleIPTV_EPG` (a potem zmienić `version`). Do chwili aktualizacji repozytorium AIO Panel nadal zainstaluje starszą wersję.

## Pliki użytkownika

- `/etc/enigma2/simpleiptvepg_mapping.json` — cache mapowania;
- `/etc/enigma2/simpleiptvepg_overrides.json` — ręczne mapowanie, np. `{ "TVP1": "TVP1.pl" }`;
- `/etc/enigma2/simpleiptvepg_report.json` — raport;
- `/tmp/simpleiptvepg.log` — log importu.

Nie zapisujemy danych logowania do repozytorium GitHub. W URL wpisanym na tunerze mogą występować dane dostępowe — raport i nowe logi maskują linki.

**Autor: Paweł Pawełek — AIO IPTV PL**
