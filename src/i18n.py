# -*- coding: utf-8 -*-
"""Simple IPTV EPG UI localisation (Py2/Py3). No additional locale packages."""
from __future__ import absolute_import

from Components.Language import language
import re

TRANSLATIONS = {
    'Picony: %s nowych, %s zastąpionych atrap, %s usług bez źródła logo.': 'Picons: %s new, %s placeholders replaced, %s services without genuine logos.',
    'Uzupełnij prawdziwe picony IPTV (bez atrap)': 'Find genuine IPTV logos (no placeholders)',
    'Usuń picony zastępcze RC8 (tylko nasze)': 'Remove RC8 generated picons (ours only)',
    'Nie znaleziono piconów zastępczych RC8.': 'No RC8 generated picons found.',
    'Znaleziono %s piconów zastępczych utworzonych przez RC8.\nUsunięte będą TYLKO nasze oznaczone grafiki, nie prawdziwe logotypy.\nPo usunięciu inne wtyczki będą mogły zapisać brakujące picony.\n\nUsunąć?': 'Found %s RC8 text placeholders.\nOnly our marked images will be removed, never real logos.\nOther plugins can then install missing picons.\n\nRemove?',
    'Błąd kontroli piconów: %s': 'Picon scan error: %s',
    'Usunięto %s atrap RC8. Błędy: %s. Prawdziwe picony zachowano.': 'Removed %s RC8 placeholders. Errors: %s. Genuine picons retained.',
    'Błąd usuwania piconów: %s': 'Picon cleanup error: %s',
    'Język interfejsu: Automatycznie / Polski / English': 'Interface language: Auto / Polish / English',
    'Język został zapisany.': 'Language setting saved.',
    'Import rozpoczęty. Możesz zamknąć wtyczkę i oglądać TV.\nPobieranie EPG i piconów będzie kontynuowane w tle.\nNie restartuj GUI Enigma2 do zakończenia.': 'Import started. You can close the plugin and watch TV.\nEPG and picon downloads will continue in the background.\nDo not restart Enigma2 GUI until finished.',
    'Możesz zamknąć wtyczkę. Import i picony będą działały w tle.': 'You may close the plugin. EPG import and picons continue in the background.',
    'Pobieranie i mapowanie EPG trwa w tle.': 'Downloading and mapping EPG in the background.',
    'Interfejs': 'Interface language',
    'Automatycznie (język Enigma2)': 'Automatic (Enigma2 language)',
    'Polski': 'Polish', 'Angielski': 'English',
    'Źródło EPG': 'EPG source', 'Automatyczny import': 'Automatic import',
    'Uzupełniaj picony IPTV': 'Fill IPTV picons',
    'Ustawienia zaawansowane • OK zapisuje': 'Advanced settings • OK saves',
    'AUTO EPG • prosta konfiguracja • Narzędzia: zaawansowane': 'AUTO EPG • simple setup • Tools: advanced',
    'ZAMKNIJ': 'CLOSE', 'ZAPISZ': 'SAVE', 'IMPORTUJ EPG': 'IMPORT EPG',
    'WRÓĆ': 'BACK', 'TEST ŹRÓDŁA': 'TEST SOURCE', 'NARZĘDZIA': 'TOOLS',
    'Trwa zadanie: %s': 'Task in progress: %s',
    'PRACA W TOKU: %s': 'WORKING: %s',
    'STATUS • ostatni udany import: %s': 'STATUS • last successful import: %s',
    'Źródło: %s\nIPTV: %s | SAT: %s | XMLTV kanały: %s | zdarzenia: %s | błędy importu: %s': 'Source: %s\nIPTV: %s | SAT: %s | XMLTV channels: %s | events: %s | import errors: %s',
    'Inne zadanie już trwa: %s': 'Another task is already running: %s',
    'Błąd zapisu ustawień: %s': 'Unable to save settings: %s',
    'Ustawienia zapisane do /etc/enigma2/settings.': 'Settings saved to /etc/enigma2/settings.',
    'Zadanie działa w tle. Zamknięcie okna NIE zatrzyma importu.\n\nZamknąć okno?': 'The task runs in the background. Closing this window will NOT stop importing.\n\nClose the window?',
    'Start importu EPG...': 'Starting EPG import...',
    'Import EPG zakończony poprawnie.': 'EPG import completed successfully.',
    'Import EPG zakończył się błędem: %s': 'EPG import failed: %s',
    'Import zakończony. SAT: %s kanałów | XMLTV: %s kanałów / %s zdarzeń.': 'Import completed. SAT: %s channels | XMLTV: %s channels / %s events.',
    'Import nie powiódł się: %s': 'Import failed: %s',
    'Testowanie źródła EPG...': 'Testing EPG source...',
    'Źródło działa. Opóźnienie: %sms': 'Source available. Latency: %s ms',
    'Źródło nie działa: %s': 'Source unavailable: %s',
    'Nie udało się wykonać testu źródła.': 'Source test failed.',
    'Ustawienia zaawansowane': 'Advanced settings',
    'Wymuś pełny import + nowe mapowanie': 'Force full import + remap',
    'Zbuduj mapowanie bez importu': 'Build mapping only',
    'Uzupełnij picony IPTV (bez EPG)': 'Fill IPTV picons (no EPG)',
    'Diagnostyka': 'Diagnostics', 'Pokaż log': 'Show log',
    'Sprawdź aktualizację': 'Check for updates', 'Aktualizuj wtyczkę': 'Update plugin',
    'Wyczyść cache mapowania': 'Clear mapping cache',
    'Wyczyść pliki tymczasowe': 'Clear temporary files',
    'Informacje o projekcie / QR': 'Project information / QR',
    'Simple IPTV EPG • Narzędzia': 'Simple IPTV EPG • Tools',
    'Aktualizacja pobierze pakiet z oficjalnego repozytorium projektu i zainstaluje go. Kontynuować?': 'The updater will download and install the plugin from the official repository. Continue?',
    'Wyczyszczono cache mapowania (%s plików).': 'Mapping cache cleared (%s files).',
    'Usunięto %s plików tymczasowych.': 'Removed %s temporary files.',
    'Picony: %s nowych plików, %s usług rozpoznanych.': 'Picons: %s new files, %s services identified.',
    'Błąd piconów: %s': 'Picon error: %s',
    'Mapowanie gotowe: %s/%s grup, XML ID: %s.': 'Mapping complete: %s/%s groups, XML IDs: %s.',
    'Mapowanie nie powiodło się: %s': 'Mapping failed: %s',
    'Nie udało się sprawdzić wersji.': 'Unable to check version.',
    'Dostępna jest nowsza wersja: %s (zainstalowana: %s).': 'New version available: %s (installed: %s).',
    'Masz aktualną wersję: %s.': 'Installed version is current: %s.',
    'Aktualizacja zakończona.': 'Update completed.',
    'Aktualizacja nie powiodła się.': 'Update failed.',
    'DIAGNOSTYKA': 'DIAGNOSTICS', 'ODŚWIEŻ': 'REFRESH', 'WYCZYŚĆ LOG': 'CLEAR LOG',
    'Wersja wtyczki: %s': 'Plugin version: %s',
    'Wybrane źródło: %s': 'Selected source: %s',
    'Auto-import: %s h': 'Automatic import: %s h',
    'Ostatnia próba: %s': 'Last attempt: %s',
    'Ostatni sukces: %s': 'Last successful import: %s',
    'Ostatni wynik: %s': 'Last result: %s',
    'Ostatni błąd: %s': 'Last error: %s',
    'Ostatnie źródło: %s': 'Last source: %s',
    'IPTV / SAT: %s / %s': 'IPTV / SAT: %s / %s',
    'XMLTV kanały / zdarzenia: %s / %s': 'XMLTV channels / events: %s / %s',
    'Błędy eEPGCache: %s': 'eEPGCache errors: %s',
    'Picony IPTV: %s': 'IPTV picons: %s',
    'Uzupełniające źródła: %s': 'Supplementary feeds: %s',
    'Mapowanie BMX / EPGImport:': 'BMX / EPGImport mapping:',
    '  pliki sources.xml: %s': '  sources.xml files: %s',
    '  wykryte EPG XMLTV: %s': '  detected XMLTV feeds: %s',
    '  trafienia BMX: %s': '  BMX matches: %s',
    'Cache mapowania:': 'Mapping cache:',
    '  źródło: %s': '  source: %s',
    '  czułość: %s': '  sensitivity: %s',
    '  grupy / dopasowane: %s / %s': '  groups / matched: %s / %s',
    '  zapisano: %s': '  saved: %s',
    'Pliki diagnostyczne:': 'Diagnostic files:',
    'Ostatni raport: %s': 'Last report: %s',
    'Worker: %s': 'Worker: %s',
    'dostępny': 'available', 'brak': 'missing',
    'bezczynny': 'idle', 'aktywny: %s': 'active: %s', 'wyłączony': 'off',
    'Brak logu.': 'No log available.',
    'Log wyczyszczony z poziomu GUI.': 'Log cleared via GUI.',
    'Zeskanuj QR\ni odwiedź stronę projektu': 'Scan the QR code\nto visit the project page',
    '%s %s\n\nTwórca: %s\nE-mail: %s\n\nStrona projektu:\n%s\n\nRepozytorium: GitHub / OliOli2013': '%s %s\n\nAuthor: %s\nE-mail: %s\n\nProject website:\n%s\n\nRepository: GitHub / OliOli2013',
    'Chcesz wesprzeć dalszy rozwój darmowych projektów Enigma2?\nZeskanuj dodatkowy kod QR.': 'Want to support further development of free Enigma2 projects?\nScan the second QR code.',
    'Automatyczny import EPG zakończony. XMLTV: %s kanałów / %s zdarzeń, SAT: %s kanałów.': 'Automatic EPG import complete. XMLTV: %s channels / %s events, SAT: %s channels.',
    'Automatyczny import EPG nie powiódł się: %s': 'Automatic EPG import failed: %s',
    'AIO XMLTV + SAT EPG importer dla kanałów IPTV': 'AIO XMLTV + SAT EPG importer for IPTV channels',
    'sprawdź log': 'check log', 'nieznany błąd': 'unknown error', 'błąd': 'error',
    'Źródło EPG': 'EPG source', 'Zakres importu (dni)': 'Import range (days)',
    'Własny URL XML/XML.GZ': 'Custom XML/XML.GZ URL',
    'Uzupełniaj brakujące EPG z innych źródeł': 'Fill missing EPG from other sources',
    'Szukaj piconów w katalogu internetowym': 'Search online picon catalogue',
    'Kopiuj EPG SAT → IPTV': 'Copy SAT EPG → IPTV', 'Preferuj EPG z SAT': 'Prefer SAT EPG',
    'Czułość automatycznego mapowania': 'Auto-mapping sensitivity',
    'Powiadom po imporcie w tle': 'Notify after background import',
    'Zapisz bazę EPG po imporcie': 'Save EPG cache after import',
    'Zachowaj pobrany XMLTV w /tmp': 'Keep downloaded XMLTV in /tmp',
    'Opóźnienie auto-importu po starcie': 'Auto-import delay after boot',
}


def lang():
    """Resolve live setting on each call, avoiding frozen language at module import."""
    try:
        from .settings import cfg
        choice = cfg.ui_language.value
        if choice in ('pl', 'en'):
            return choice
    except Exception:
        pass
    try:
        code = (language.getLanguage() or '').lower().replace('_', '-').split('-', 1)[0]
        return 'pl' if code == 'pl' else 'en'
    except Exception:
        return 'en'


def T(message):
    if lang() == 'en':
        return TRANSLATIONS.get(message, message)
    return message


LOG_PREFIXES = (
    (r'^Analiza bukietów Enigma2', 'Scanning Enigma2 bouquets'),
    (r'^Wykryto IPTV live:', 'Detected live IPTV:'),
    (r'^Źródło ', 'Source '),
    (r'^XMLTV poprawny:', 'Valid XMLTV:'),
    (r'^Pobieranie nie powiodło się', 'Download failed'),
    (r'^POBIERANIE: pobrano ', 'DOWNLOADING: received '),
    (r'^POBIERANIE:', 'DOWNLOADING:'),
    (r'^Odrzucono nieprawidłowy XMLTV', 'Rejected invalid XMLTV'),
    (r'^Mapowanie pozostałych kanałów', 'Mapping remaining channels'),
    (r'^Mapowanie:', 'Mapping:'),
    (r'^Kontrola zgodnosci nazw IPTV/XMLTV:', 'IPTV/XMLTV name check:'),
    (r'^Kontrola dodatkowego XMLTV:', 'Extra XMLTV validation:'),
    (r'^Uzupełnianie braków EPG', 'Filling EPG gaps'),
    (r'^Po uzupełnieniu:', 'After supplementary feed:'),
    (r'^Dodatkowe EPG wedlug kraju:', 'Regional EPG feeds:'),
    (r'^Picony:', 'Picons:'),
    (r'^Ochrona EPG SAT:', 'SAT EPG protection:'),
    (r'^Ochrona IPTV:', 'IPTV protection:'),
    (r'^Nie udało się', 'Unable to'),
    (r'^Błąd pobierania:', 'Download error:'),
    (r'^Wczytano mapowanie', 'Loaded mapping'),
    (r'^Wykryto', 'Detected'),
    (r'^Baza EPG została zapisana', 'EPG database saved'),
    (r'^Kontrola EPG na kanałach IPTV:', 'IPTV EPG visibility check:'),
)


def T_log(message):
    text = T(message)
    if lang() != 'en' or text != message:
        return text
    for pattern, replacement in LOG_PREFIXES:
        text = re.sub(pattern, replacement, text, count=1)
    return text
