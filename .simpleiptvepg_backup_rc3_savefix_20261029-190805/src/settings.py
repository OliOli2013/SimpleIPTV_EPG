# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

from Components.Language import language
from Components.config import (
    ConfigSelection, ConfigSubsection, ConfigText, ConfigYesNo, config,
)

from .sources import source_choices


def get_lang():
    try:
        code = language.getLanguage() or ""
        return "pl" if "pl" in code.lower() else "en"
    except Exception:
        return "en"


LANG = get_lang()

if not hasattr(config.plugins, "SimpleIPTV_EPG"):
    config.plugins.SimpleIPTV_EPG = ConfigSubsection()

cfg = config.plugins.SimpleIPTV_EPG
cfg.source_select = ConfigSelection(default="AUTO_PL", choices=source_choices(LANG))
cfg.custom_url = ConfigText(default="https://", fixed_size=False, visible_width=80)
cfg.auto_interval = ConfigSelection(default="24", choices=[
    ("0", "Wyłączony / Off"), ("6", "6 h"), ("12", "12 h"), ("24", "24 h"), ("48", "48 h"),
])
cfg.import_days = ConfigSelection(default="5", choices=[("2", "2"), ("3", "3"), ("5", "5"), ("7", "7"), ("10", "10")])
cfg.fill_missing = ConfigYesNo(default=True)
cfg.picons_enabled = ConfigYesNo(default=True)
cfg.picons_online = ConfigYesNo(default=True)
cfg.clone_sat = ConfigYesNo(default=False)
cfg.prefer_sat = ConfigYesNo(default=False)
cfg.mapping_sensitivity = ConfigSelection(default="balanced", choices=[
    ("strict", "Ścisłe / Strict"), ("balanced", "Zbalansowane / Balanced"), ("flexible", "Elastyczne / Flexible"),
])
cfg.notify_done = ConfigYesNo(default=True)
cfg.save_epg_cache = ConfigYesNo(default=True)
cfg.keep_xml_cache = ConfigYesNo(default=False)
cfg.boot_delay = ConfigSelection(default="120", choices=[("60", "60 s"), ("120", "120 s"), ("300", "300 s")])


def save_config():
    try:
        cfg.save()
    except Exception:
        pass


TR = {
    "title": {"pl": "Simple IPTV EPG", "en": "Simple IPTV EPG"},
    "source": {"pl": "Źródło EPG", "en": "EPG source"},
    "custom": {"pl": "Własny URL XML/XML.GZ", "en": "Custom XML/XML.GZ URL"},
    "interval": {"pl": "Automatyczny import", "en": "Automatic import"},
    "days": {"pl": "Zakres importu (dni)", "en": "Import range (days)"},
    "fill_missing": {"pl": "Uzupełniaj brakujące EPG z innych źródeł", "en": "Fill missing EPG from other feeds"},
    "picons_enabled": {"pl": "Uzupełniaj picony IPTV", "en": "Fill IPTV picons"},
    "picons_online": {"pl": "Szukaj piconów w katalogu internetowym", "en": "Search online logo catalogue"},
    "clone_sat": {"pl": "Kopiuj EPG SAT → IPTV", "en": "Clone SAT EPG → IPTV"},
    "prefer_sat": {"pl": "Preferuj EPG z SAT", "en": "Prefer SAT EPG"},
    "sensitivity": {"pl": "Czułość automatycznego mapowania", "en": "Auto-mapping sensitivity"},
    "notify": {"pl": "Powiadom po imporcie w tle", "en": "Notify after background import"},
    "save_cache": {"pl": "Zapisz bazę EPG po imporcie", "en": "Save EPG cache after import"},
    "keep_xml": {"pl": "Zachowaj pobrany XMLTV w /tmp", "en": "Keep downloaded XMLTV in /tmp"},
    "boot_delay": {"pl": "Opóźnienie auto-importu po starcie", "en": "Auto-import delay after boot"},
    "ready": {"pl": "Gotowy. Zielony: import EPG | Żółty: test źródła | Niebieski: narzędzia | INFO: projekt/QR", "en": "Ready. Green: import EPG | Yellow: source test | Blue: tools | INFO: project/QR"},
    "busy": {"pl": "Inne zadanie jest już wykonywane.", "en": "Another task is already running."},
}


def tr(key):
    item = TR.get(key, {})
    return item.get(LANG, item.get("en", key))
