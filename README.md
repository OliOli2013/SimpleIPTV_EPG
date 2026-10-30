# Simple IPTV EPG 3.2.6 RC11.1

**Automatyczne EPG i prawdziwe picony dla kanałów IPTV w Enigma2**  
**Autor:** Paweł Pawełek | AIO Team  
**Wersja kodu:** `3.2.6` · **build:** `rc11.1-menu-cleanup`  
**Status:** wersja testowa (Release Candidate)  
**Środowisko:** Enigma2, kod przygotowany do pracy z Pythonem 2 i Pythonem 3

[Repozytorium projektu](https://github.com/OliOli2013/SimpleIPTV_EPG)

## Czym jest Simple IPTV EPG?

Simple IPTV EPG to wtyczka dla odbiorników z systemem **Enigma2**, która odczytuje kanały IPTV z istniejących bukietów, wyszukuje dla nich program telewizyjny w przewodnikach **XMLTV** i importuje odnalezione wydarzenia do systemowej pamięci EPG. Może również uzupełniać **prawdziwe logotypy kanałów (picony)**.

Nie jest odtwarzaczem IPTV, nie dostarcza list kanałów ani strumieni. Działa z bukietami już obecnymi w odbiorniku — nie tylko z listami AIO Team. Program TV pojawi się wyłącznie dla usług, dla których uda się znaleźć wiarygodne dopasowanie i aktualne dane XMLTV.

## Najważniejsze funkcje

- **EPG z wielu źródeł:** automatyczne uzupełnianie braków z przewodników polskich, regionalnych i globalnych, w tym EPG.OVH, EPGShare, PolishTeam, IPTV-EPG.org i EPG.PW.
- **Mapowanie IPTV ↔ XMLTV:** identyfikacja stacji według nazw, aliasów i dostępnych identyfikatorów; odrzucanie niejednoznacznych dopasowań.
- **Pełny import i przebudowa mapowania:** osobna funkcja w menu Narzędzia, przydatna po zmianie list IPTV.
- **Prawdziwe picony:** uzupełnianie dostępnych logo z danych XMLTV, katalogów internetowych i lokalnych zasobów. Aktualny build nie tworzy tekstowych atrap piconów.
- **Praca w tle:** po rozpoczęciu importu można zamknąć *okno wtyczki*. Zadanie działa dalej, dopóki uruchomione jest GUI Enigma2; restart GUI albo wyłączenie odbiornika może je przerwać.
- **Harmonogram:** automatyczny import co 6, 12, 24 lub 48 godzin albo wyłączenie harmonogramu.
- **Polski i angielski:** wybór automatyczny według języka Enigma2 lub ręczny w menu.
- **Diagnostyka:** informacje o etapach pracy, wykorzystanych źródłach, znalezionych dopasowaniach, liczbie wydarzeń, piconach i problemach z referencjami.
- **Ochrona usług SAT:** kontrola kolizji identyfikatorów IPTV z kanałami satelitarnymi podczas importu.
- **Opcjonalna naprawa referencji IPTV:** wyłącznie na polecenie użytkownika, z podglądem zakresu zmian i kopią zapasową bukietów.
- **Współpraca z BouquetMakerXtream:** możliwość wykorzystania wykrytych źródeł XMLTV i mapowań `channels.xml`, jeśli są dostępne.

## Instalacja

### Metoda 1 — AIO Panel

Otwórz **AIO Panel**, odszukaj **Simple IPTV EPG** na liście instalatorów wtyczek i uruchom instalację. Dostępność konkretnej wersji zależy od aktualizacji instalatora w AIO Panel.

### Metoda 2 — instalator z GitHub

Połącz się z tunerem przez SSH lub Telnet i wykonaj:

```sh
wget -O /tmp/simpleiptvepg_installer.sh https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh
sh /tmp/simpleiptvepg_installer.sh
```

Wymagania: Enigma2, połączenie z Internetem, `unzip` oraz `wget` (lub `curl` przy uruchamianiu instalatora inną drogą). Instalator pobiera bieżący kod z katalogu **`src/` na gałęzi `main`** i zastępuje pliki wtyczki. Nie korzysta ze starszych modułów znajdujących się w katalogu głównym repozytorium.

**Po instalacji uruchom ponownie GUI Enigma2.** Przed aktualizacją zalecana jest kopia ustawień i konfiguracji tunera.

### Metoda 3 — lokalny pakiet IPK

Jeśli masz pakiet IPK przeznaczony dla swojego obrazu Enigma2, skopiuj go do `/tmp` i zainstaluj odpowiednim menedżerem pakietów. W obrazach z `opkg` stosuje się polecenie:

```sh
opkg install /tmp/nazwa-pakietu.ipk
```

Zastąp `nazwa-pakietu.ipk` rzeczywistą nazwą pobranego pliku. **Uwaga:** pakiety udostępnione w sekcji [Releases](https://github.com/OliOli2013/SimpleIPTV_EPG/releases) mogą być starsze niż kod na gałęzi `main`. Nie zakładaj, że najnowszy build RC11.1 ma już osobny plik IPK w Releases.

## Pierwsze uruchomienie

1. Otwórz **Simple IPTV EPG** z listy wtyczek Enigma2.
2. Wybierz źródło **AUTO AIO Polska** (ustawienie domyślne).
3. Ustaw automatyczny import, np. **24 h**, i wybierz, czy chcesz uzupełniać picony.
4. Wejdź do **Narzędzia → Ustawienia zaawansowane** i sprawdź opcje kopiowania EPG z SAT (szczegóły poniżej).
5. Zapisz ustawienia przyciskiem **OK**.
6. Wybierz **Narzędzia → Wymuś pełny import + nowe mapowanie**.
7. Sprawdź program telewizyjny na kilku konkretnych kanałach IPTV. Sam licznik zdarzeń w raporcie nie jest dowodem pokrycia całej listy.

Import dużych przewodników może potrwać kilka lub kilkanaście minut, a na słabszych odbiornikach dłużej. Pełne źródło EPG.PW jest wykorzystywane jako uzupełnienie w trybach AUTO, o ile pozwala na to miejsce w pamięci tymczasowej; kod wymaga **co najmniej 90 MiB wolnego miejsca w `/tmp`** przed tą próbą.

## Ustawienia

| Opcja | Znaczenie | Wartość domyślna w aktualnym kodzie |
|---|---|---|
| Źródło EPG | Wybór przewodnika lub trybu AUTO | `AUTO AIO Polska` |
| Automatyczny import | Odstęp między aktualizacjami | `24 h` |
| Uzupełniaj picony IPTV | Pobieranie brakujących prawdziwych logo | `Tak` |
| Język interfejsu | Automatycznie / Polski / English | `Automatycznie` |
| Uzupełniaj brakujące EPG | Korzystanie z dodatkowych przewodników | `Tak` |
| Zakres importu | Horyzont EPG | `5 dni` |
| Kopiuj EPG SAT → IPTV | Kopiowanie dopasowanych wydarzeń z SAT | **`Tak`** |
| Preferuj EPG z SAT | Pierwszeństwo EPG SAT przy nakładaniu danych | `Nie` |
| Czułość mapowania | Ścisłe / zbalansowane / elastyczne | `Zbalansowane` |

**Ważne o EPG SAT:** w aktualnym kodzie opcja **„Kopiuj EPG SAT → IPTV” domyślnie ma wartość „Tak”**. Jeśli chcesz przetestować wyłącznie dopasowanie XMLTV, wyłącz ją w ustawieniach zaawansowanych. Wtyczka zachowuje wcześniej zapisane ustawienia, więc stan na Twoim tunerze może być inny niż wartości domyślne.

## Menu Narzędzia

- **Ustawienia zaawansowane** — dodatkowe opcje źródeł, importu, mapowania i zapisu.
- **Język interfejsu** — automatycznie, polski lub angielski.
- **Wymuś pełny import + nowe mapowanie** — ponowna analiza kanałów i XMLTV.
- **Zbuduj mapowanie bez importu** — przygotowanie przypisań bez importowania wydarzeń.
- **Uzupełnij prawdziwe picony IPTV (bez atrap)** — samodzielne wyszukiwanie logo.
- **Napraw błędne referencje IPTV (kopie bezpieczeństwa)** — opcja wymagająca potwierdzenia; po naprawie uruchom ponownie GUI.
- **Diagnostyka**, **Pokaż log** — kontrola działania.
- **Sprawdź aktualizację**, **Aktualizuj wtyczkę** — mechanizm sprawdzający wersję repozytorium.
- **Wyczyść cache mapowania**, **Wyczyść pliki tymczasowe** — czynności porządkowe.
- **Informacje o projekcie / QR**.

W bieżącym buildzie **nie ma** już pozycji „Usuń picony zastępcze RC8”.

## Aktualizacje

Aktualizacje można przeprowadzać z poziomu **AIO Panel**, instalatorem GitHub albo — gdy dostępna jest nowsza wersja rozpoznana przez mechanizm wtyczki — z jej menu **Narzędzia → Sprawdź aktualizację / Aktualizuj wtyczkę**.

**Ograniczenie RC11.1:** plik `version` ma wartość `3.2.6`, a poprawki RC11 i RC11.1 używają tego samego numeru głównego. Obecny aktualizator porównuje właśnie wersję numeryczną, dlatego może **nie wykryć zmiany samego oznaczenia RC/build**. W takiej sytuacji użyj instalatora GitHub lub aktualnego pakietu z zaufanego źródła.

## Pliki diagnostyczne na tunerze

| Plik | Zawartość |
|---|---|
| `/tmp/simpleiptvepg.log` | Log przebiegu operacji |
| `/etc/enigma2/simpleiptvepg_report.json` | Raport ostatniego importu i statystyki źródeł |
| `/etc/enigma2/simpleiptvepg_state.json` | Stan zadania i ostatni wynik |
| `/etc/enigma2/simpleiptvepg_mapping.json` | Przypisania XMLTV ↔ referencje IPTV |
| `/etc/enigma2/simpleiptvepg_overrides.json` | Opcjonalne własne przypisania |

**Przy zgłaszaniu problemów:** prześlij log, raport i przykład nazwy kanału bez EPG. Przed publicznym udostępnieniem danych usuń prywatne adresy strumieni, tokeny, loginy i hasła dostawców IPTV. Nie publikuj całych prywatnych list kanałów bez sprawdzenia ich zawartości.

## Ograniczenia i ważne informacje

- Wtyczka **nie tworzy własnych ramówek**. Kamera internetowa, niektóre kanały muzyczne i transmisje okazjonalne mogą nie mieć EPG w żadnym dostępnym XMLTV.
- Liczby w raporcie oznaczają m.in. dopasowane **referencje usług**, a nie zawsze unikalne stacje TV.
- Weryfikacja widoczności EPG odbywa się na **próbce**, a nie na wszystkich kanałach.
- Picon zostanie pobrany tylko wtedy, gdy znajdzie się wiarygodne logo. Nie każdy strumień ma własny logotyp.
- Standardowy import **nie przepisuje bukietów**. Funkcja naprawy referencji jest osobną operacją wymagającą potwierdzenia i tworzącą kopię plików, które zmienia.
- Wtyczka nie jest źródłem kanałów IPTV ani usług dostępu do telewizji.
- RC11.1 jest **wersją testową**. Skuteczność importu zależy od obrazu Enigma2, referencji kanałów oraz jakości i aktualności danych XMLTV.

## Rozwój od RC5 do RC11.1

Od wydania RC5 usprawniono przede wszystkim obsługę źródeł regionalnych i pełnego XMLTV, mapowanie kanałów, czytelność statusu pracy, interfejs PL/EN, pracę w tle, pobieranie prawdziwych piconów, ochronę i synchronizację referencji IPTV oraz diagnostykę. Usunięto także przestarzałą pozycję czyszczenia piconów zastępczych RC8 z menu Narzędzia.

Szczegółowa historia zmian znajduje się w [`src/CHANGELOG.txt`](src/CHANGELOG.txt).

## Autor i projekt

**Paweł Pawełek | AIO Team**  
**Repozytorium:** https://github.com/OliOli2013/SimpleIPTV_EPG  
**Kontakt projektu:** aio-iptv@wp.pl

---

## English — quick overview

**Simple IPTV EPG 3.2.6 RC11.1** is a testing-stage Enigma2 plugin for matching IPTV bouquet services with XMLTV schedules and filling in missing genuine channel logos (picons). It supports automatic multi-source EPG fallback, manual remapping, optional SAT-to-IPTV EPG cloning, background importing while the Enigma2 GUI is running, and a Polish/English interface.

**Install current source from GitHub:**

```sh
wget -O /tmp/simpleiptvepg_installer.sh https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh
sh /tmp/simpleiptvepg_installer.sh
```

Restart the Enigma2 GUI after installation, then choose **Tools → Force full import + remap**. The `main` branch may be newer than the IPK assets in GitHub Releases. Automatic version checking currently compares `3.2.6` numerically and may not detect a change between builds using the same version number. EPG coverage depends on available XMLTV data; cameras and unscheduled streams may have no guide data.

**Author:** Paweł Pawełek | AIO Team
