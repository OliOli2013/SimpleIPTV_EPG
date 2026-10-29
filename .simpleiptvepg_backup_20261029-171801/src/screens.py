# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import os
import glob
import sys
import time

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Components.config import getConfigListEntry
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from twisted.internet import reactor

from .compat import io_open, to_text
from .constants import (
    AIO_BG, AIO_CYAN, AIO_DIVIDER, AIO_MUTED, AIO_PANEL, AIO_SUBTLE,
    AIO_TEXT, AIO_YELLOW, LOG_FILE, MAPPING_FILE, OVERRIDES_FILE,
    PLUGIN_AUTHOR, PLUGIN_BUILD, PLUGIN_EMAIL, PLUGIN_TITLE, PLUGIN_VERSION, PROJECT_NAME,
    PROJECT_URL, REPORT_FILE, STATE_FILE,
)
from .epgimport_bridge import discover_bmx_sources
from .logger import clear_log, log_message
from .settings import cfg, save_config, tr
from .storage import load_json, load_state
from .worker import GLOBAL_WORKER

PLUGIN_PATH = os.path.dirname(os.path.abspath(__file__))
ACTIVE_SESSION = None


def set_active_session(session):
    global ACTIVE_SESSION
    if session is not None:
        ACTIVE_SESSION = session


def _asset(name):
    return os.path.join(PLUGIN_PATH, name)


def _desktop_width():
    try:
        from enigma import getDesktop
        return int(getDesktop(0).size().width())
    except Exception:
        return 1280


def _layout():
    width = _desktop_width()
    if width <= 1000:
        return (900, 590, 20, 24, 18, 15)
    if width <= 1500:
        return (1040, 650, 22, 26, 19, 16)
    return (1180, 720, 24, 28, 20, 17)


def _footer_text():
    py = "Py%s" % sys.version_info[0]
    return "%s %s %s | %s | %s | by %s | %s" % (
        PLUGIN_TITLE, PLUGIN_VERSION, PLUGIN_BUILD, py, PROJECT_NAME, PLUGIN_AUTHOR, PLUGIN_EMAIL)


def _fmt_time(value):
    try:
        value = int(value or 0)
        if not value:
            return "—"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))
    except Exception:
        return "—"


def _main_skin():
    w, h, margin, title_fs, body_fs, small_fs = _layout()
    header_h = 84
    footer_h = 38
    buttons_h = 42
    config_y = 118
    config_h = 250 if h >= 650 else 210
    status_y = config_y + config_h + 14
    status_h = h - status_y - buttons_h - footer_h - 34
    qr = 58
    qr_x = w - margin - qr
    pp = 44
    return '''
    <screen name="SimpleIPTVEPGMain" position="center,center" size="%(w)d,%(h)d" title="%(title)s" backgroundColor="%(bg)s" flags="wfNoBorder">
        <eLabel position="0,0" size="%(w)d,%(header_h)d" backgroundColor="%(panel)s" zPosition="0" />
        <widget name="pp_logo" position="%(margin)d,20" size="%(pp)d,%(pp)d" pixmap="%(pp_logo)s" alphatest="on" zPosition="5" />
        <widget name="title" position="%(title_x)d,15" size="%(title_w)d,34" font="Regular;%(title_fs)d" foregroundColor="%(text)s" transparent="1" zPosition="5" />
        <widget name="subtitle" position="%(title_x)d,50" size="%(title_w)d,26" font="Regular;%(small_fs)d" foregroundColor="%(muted)s" transparent="1" zPosition="5" />
        <widget name="project_qr" position="%(qr_x)d,13" size="%(qr)d,%(qr)d" pixmap="%(qr_path)s" alphatest="on" zPosition="5" />
        <eLabel position="%(margin)d,94" size="%(inner)d,2" backgroundColor="%(cyan)s" zPosition="1" />

        <eLabel position="%(margin)d,%(config_y)d" size="%(inner)d,%(config_h)d" backgroundColor="%(panel)s" zPosition="0" />
        <widget name="config" position="%(cfg_x)d,%(cfg_y)d" size="%(cfg_w)d,%(cfg_h)d" font="Regular;%(body_fs)d" itemHeight="34" foregroundColor="%(text)s" backgroundColor="%(panel)s" selectionForegroundColor="%(bg)s" selectionBackgroundColor="%(cyan)s" scrollbarMode="showOnDemand" zPosition="5" />

        <eLabel position="%(margin)d,%(status_y)d" size="%(inner)d,%(status_h)d" backgroundColor="%(panel)s" zPosition="0" />
        <widget name="status_title" position="%(status_x)d,%(status_title_y)d" size="%(status_w)d,26" font="Regular;%(body_fs)d" foregroundColor="%(yellow)s" transparent="1" zPosition="5" />
        <widget name="status" position="%(status_x)d,%(status_text_y)d" size="%(status_w)d,%(status_text_h)d" font="Regular;%(small_fs)d" foregroundColor="%(subtle)s" transparent="1" scrollbarMode="showOnDemand" zPosition="5" />

        <eLabel position="%(margin)d,%(button_y)d" size="%(button_w)d,34" backgroundColor="#B71C1C" zPosition="0" />
        <widget name="key_red" position="%(margin)d,%(button_y)d" size="%(button_w)d,34" font="Regular;%(small_fs)d" halign="center" valign="center" foregroundColor="#FFFFFF" transparent="1" zPosition="5" />
        <eLabel position="%(green_x)d,%(button_y)d" size="%(button_w)d,34" backgroundColor="#1B7F3A" zPosition="0" />
        <widget name="key_green" position="%(green_x)d,%(button_y)d" size="%(button_w)d,34" font="Regular;%(small_fs)d" halign="center" valign="center" foregroundColor="#FFFFFF" transparent="1" zPosition="5" />
        <eLabel position="%(yellow_x)d,%(button_y)d" size="%(button_w)d,34" backgroundColor="#B78A00" zPosition="0" />
        <widget name="key_yellow" position="%(yellow_x)d,%(button_y)d" size="%(button_w)d,34" font="Regular;%(small_fs)d" halign="center" valign="center" foregroundColor="#FFFFFF" transparent="1" zPosition="5" />
        <eLabel position="%(blue_x)d,%(button_y)d" size="%(button_w)d,34" backgroundColor="#1565C0" zPosition="0" />
        <widget name="key_blue" position="%(blue_x)d,%(button_y)d" size="%(button_w)d,34" font="Regular;%(small_fs)d" halign="center" valign="center" foregroundColor="#FFFFFF" transparent="1" zPosition="5" />

        <eLabel position="0,%(footer_y)d" size="%(w)d,%(footer_h)d" backgroundColor="%(panel)s" zPosition="0" />
        <widget name="footer" position="%(margin)d,%(footer_text_y)d" size="%(inner)d,24" font="Regular;%(small_fs)d" foregroundColor="%(muted)s" halign="center" transparent="1" zPosition="5" />
    </screen>''' % {
        "w": w, "h": h, "title": PLUGIN_TITLE, "bg": AIO_BG, "panel": AIO_PANEL,
        "header_h": header_h, "margin": margin, "pp": pp, "pp_logo": _asset("pp_logo.png"),
        "title_x": margin + pp + 16, "title_w": w - (margin + pp + 16) - margin - qr - 18,
        "title_fs": title_fs, "text": AIO_TEXT, "small_fs": small_fs, "muted": AIO_MUTED,
        "qr_x": qr_x, "qr": qr, "qr_path": _asset("qr_project.png"), "inner": w - 2 * margin,
        "cyan": AIO_CYAN, "config_y": config_y, "config_h": config_h,
        "cfg_x": margin + 14, "cfg_y": config_y + 12, "cfg_w": w - 2 * margin - 28, "cfg_h": config_h - 24,
        "body_fs": body_fs, "status_y": status_y, "status_h": status_h,
        "status_x": margin + 14, "status_title_y": status_y + 9, "status_w": w - 2 * margin - 28,
        "status_text_y": status_y + 38, "status_text_h": max(34, status_h - 46), "subtle": AIO_SUBTLE,
        "yellow": AIO_YELLOW,
        "button_y": h - footer_h - buttons_h - 8, "button_w": int((w - 2 * margin - 24) / 4),
        "green_x": margin + int((w - 2 * margin - 24) / 4) + 8,
        "yellow_x": margin + 2 * (int((w - 2 * margin - 24) / 4) + 8),
        "blue_x": margin + 3 * (int((w - 2 * margin - 24) / 4) + 8),
        "footer_y": h - footer_h, "footer_h": footer_h, "footer_text_y": h - footer_h + 7,
    }


class SimpleIPTVEPGMain(Screen, ConfigListScreen):
    skin = _main_skin()

    def __init__(self, session):
        Screen.__init__(self, session)
        set_active_session(session)
        self.closed = False
        self.log_lines = []
        self.list = []
        ConfigListScreen.__init__(self, self.list, session=session)
        self["title"] = Label("%s  %s %s" % (PLUGIN_TITLE, PLUGIN_VERSION, PLUGIN_BUILD))
        self["subtitle"] = Label("AIO XMLTV + SAT EPG • automatyczne mapowanie • diagnostyka")
        self["pp_logo"] = Pixmap()
        self["project_qr"] = Pixmap()
        self["status_title"] = Label("STATUS")
        self["status"] = ScrollLabel("")
        self["key_red"] = Label("ZAMKNIJ")
        self["key_green"] = Label("IMPORTUJ EPG")
        self["key_yellow"] = Label("TEST ŹRÓDŁA")
        self["key_blue"] = Label("NARZĘDZIA")
        self["footer"] = Label(_footer_text())
        self["actions"] = ActionMap(
            ["SetupActions", "ColorActions", "DirectionActions", "MenuActions", "InfobarEPGActions"],
            {
                "cancel": self.key_close,
                "red": self.key_close,
                "green": self.key_import,
                "yellow": self.key_probe,
                "blue": self.key_tools,
                "menu": self.key_tools,
                "info": self.key_project,
                "showEventInfo": self.key_project,
                "left": self.key_left,
                "right": self.key_right,
                "ok": self.key_save,
            }, -2)
        self.onClose.append(self._on_close)
        self._rebuild_config()
        self._refresh_summary()
        if GLOBAL_WORKER.running:
            self._append("Trwa zadanie: %s" % (GLOBAL_WORKER.task_name or "EPG"))
        else:
            self._append(tr("ready"))

    def _on_close(self):
        self.closed = True

    def _rebuild_config(self):
        entries = [getConfigListEntry(tr("source"), cfg.source_select)]
        if cfg.source_select.value == "CUSTOM":
            entries.append(getConfigListEntry(tr("custom"), cfg.custom_url))
        entries.extend([
            getConfigListEntry(tr("interval"), cfg.auto_interval),
            getConfigListEntry(tr("days"), cfg.import_days),
            getConfigListEntry(tr("clone_sat"), cfg.clone_sat),
            getConfigListEntry(tr("prefer_sat"), cfg.prefer_sat),
            getConfigListEntry(tr("sensitivity"), cfg.mapping_sensitivity),
            getConfigListEntry(tr("notify"), cfg.notify_done),
            getConfigListEntry(tr("save_cache"), cfg.save_epg_cache),
            getConfigListEntry(tr("keep_xml"), cfg.keep_xml_cache),
            getConfigListEntry(tr("boot_delay"), cfg.boot_delay),
        ])
        self.list = entries
        self["config"].setList(entries)

    def _refresh_summary(self):
        state = load_state()
        if GLOBAL_WORKER.running:
            title = "PRACA W TOKU: %s" % (GLOBAL_WORKER.task_name or "EPG")
        else:
            title = "STATUS • ostatni udany import: %s" % _fmt_time(state.get("last_success"))
        self["status_title"].setText(title)
        if not self.log_lines:
            summary = (
                "Źródło: %s\nIPTV: %s | SAT: %s | XMLTV kanały: %s | zdarzenia: %s | błędy importu: %s"
                % (state.get("last_source") or "—", state.get("last_iptv", "—"), state.get("last_sat", "—"),
                   state.get("last_xml_channels", "—"), state.get("last_xml_events", "—"), state.get("last_inject_errors", "—")))
            self["status"].setText(summary)

    def _append(self, message):
        text = to_text(message or "").strip()
        if not text:
            return
        self.log_lines.append(text)
        self.log_lines = self.log_lines[-80:]
        if not self.closed:
            self["status"].setText("\n".join(self.log_lines))
            self["status"].lastPage()

    def _worker_log(self, message):
        reactor.callFromThread(self._append, message)

    def _busy(self):
        if GLOBAL_WORKER.running:
            self.session.open(MessageBox, "Inne zadanie już trwa: %s" % (GLOBAL_WORKER.task_name or "EPG"), MessageBox.TYPE_INFO, timeout=5)
            return True
        return False

    def key_left(self):
        old = cfg.source_select.value
        ConfigListScreen.keyLeft(self)
        if old != cfg.source_select.value:
            self._rebuild_config()

    def key_right(self):
        old = cfg.source_select.value
        ConfigListScreen.keyRight(self)
        if old != cfg.source_select.value:
            self._rebuild_config()

    def key_save(self):
        save_config()
        self._append("Ustawienia zapisane.")

    def key_close(self):
        save_config()
        if GLOBAL_WORKER.running:
            self.session.openWithCallback(
                self._close_after_background_info, MessageBox,
                "Zadanie działa w tle. Zamknięcie okna NIE zatrzyma importu.\n\nZamknąć okno?",
                MessageBox.TYPE_YESNO)
        else:
            self.close()

    def _close_after_background_info(self, answer):
        if answer:
            self.close()

    def key_import(self, force=False):
        save_config()
        if self._busy():
            return
        self.log_lines = []
        self._append("Start importu EPG...")
        ok = GLOBAL_WORKER.start_import(self._worker_log, self._done_import, silent=False, force_mapping=bool(force))
        if ok:
            self._refresh_summary()

    def _done_import(self, ok, result, silent):
        self._refresh_summary()
        if self.closed:
            if cfg.notify_done.value and ACTIVE_SESSION is not None:
                ACTIVE_SESSION.open(MessageBox, "Import EPG zakończony poprawnie." if ok else "Import EPG zakończył się błędem: %s" % result.get("error", "nieznany błąd"), MessageBox.TYPE_INFO, timeout=8)
            return
        if ok:
            msg = "Import zakończony. SAT: %s kanałów | XMLTV: %s kanałów / %s zdarzeń." % (
                result.get("sat_channels", 0), result.get("xml_service_refs", 0), result.get("xml_events", 0))
        else:
            msg = "Import nie powiódł się: %s" % result.get("error", "sprawdź log")
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=9)

    def key_probe(self):
        save_config()
        if self._busy():
            return
        self.log_lines = []
        self._append("Testowanie źródła EPG...")
        GLOBAL_WORKER.start_probe(self._worker_log, self._done_probe)

    def _done_probe(self, ok, result, silent):
        if self.closed:
            return
        items = result.get("sources", [])
        if items:
            last = items[-1]
            msg = ("Źródło działa. Opóźnienie: %sms" % last.get("latency_ms", "—")) if ok else ("Źródło nie działa: %s" % last.get("message", "błąd"))
        else:
            msg = "Nie udało się wykonać testu źródła."
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=8)

    def key_tools(self):
        choices = [
            ("Wymuś pełny import + nowe mapowanie", "force_import"),
            ("Zbuduj mapowanie bez importu", "mapping"),
            ("Diagnostyka", "diag"),
            ("Pokaż log", "log"),
            ("Sprawdź aktualizację", "check_update"),
            ("Aktualizuj wtyczkę", "update"),
            ("Wyczyść cache mapowania", "clear_map"),
            ("Wyczyść pliki tymczasowe", "clear_tmp"),
            ("Informacje o projekcie / QR", "project"),
        ]
        self.session.openWithCallback(self._tool_selected, ChoiceBox, title="Simple IPTV EPG • Narzędzia", list=choices)

    def _tool_selected(self, selected):
        if not selected:
            return
        action = selected[1]
        if action == "force_import":
            self.key_import(force=True)
        elif action == "mapping":
            if not self._busy():
                self.log_lines = []
                GLOBAL_WORKER.start_mapping(self._worker_log, self._done_mapping)
        elif action == "diag":
            self.session.open(DiagnosticsScreen)
        elif action == "log":
            self.session.open(LogScreen)
        elif action == "check_update":
            if not self._busy():
                self.log_lines = []
                GLOBAL_WORKER.start_version_check(self._worker_log, self._done_version)
        elif action == "update":
            if not self._busy():
                self.session.openWithCallback(self._confirm_update, MessageBox,
                    "Aktualizacja pobierze pakiet z oficjalnego repozytorium projektu i zainstaluje go. Kontynuować?",
                    MessageBox.TYPE_YESNO)
        elif action == "clear_map":
            count = GLOBAL_WORKER.clear_mapping_cache()
            self._append("Wyczyszczono cache mapowania (%s plików)." % count)
        elif action == "clear_tmp":
            count = GLOBAL_WORKER.clear_temp()
            self._append("Usunięto %s plików tymczasowych." % count)
        elif action == "project":
            self.key_project()

    def _done_mapping(self, ok, result, silent):
        if self.closed:
            return
        msg = "Mapowanie gotowe: %s/%s grup, XML ID: %s." % (
            result.get("matched_groups", 0), result.get("groups", 0), result.get("xml_ids", 0)) if ok else "Mapowanie nie powiodło się: %s" % result.get("error", "sprawdź log")
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=8)

    def _done_version(self, ok, result, silent):
        if self.closed:
            return
        if not ok:
            msg = result.get("error", "Nie udało się sprawdzić wersji.")
        elif result.get("newer"):
            msg = "Dostępna jest nowsza wersja: %s (zainstalowana: %s)." % (result.get("remote"), result.get("local"))
        else:
            msg = "Masz aktualną wersję: %s." % result.get("local")
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=9)

    def _confirm_update(self, answer):
        if answer:
            self.log_lines = []
            GLOBAL_WORKER.start_update(self._worker_log, self._done_update)

    def _done_update(self, ok, result, silent):
        if self.closed:
            return
        msg = result.get("message") or result.get("error") or ("Aktualizacja zakończona." if ok else "Aktualizacja nie powiodła się.")
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=12)

    def key_project(self):
        self.session.open(ProjectScreen)


def _simple_skin(name, title, width=980, height=610):
    dw = _desktop_width()
    if dw <= 1000:
        width, height = 880, 550
    elif dw > 1500:
        width, height = 1080, 660
    margin = 24
    return '''
    <screen name="%(name)s" position="center,center" size="%(w)d,%(h)d" title="%(title)s" backgroundColor="%(bg)s" flags="wfNoBorder">
        <eLabel position="0,0" size="%(w)d,72" backgroundColor="%(panel)s" zPosition="0" />
        <widget name="title" position="%(m)d,17" size="%(iw)d,36" font="Regular;26" foregroundColor="%(text)s" transparent="1" zPosition="5" />
        <eLabel position="%(m)d,84" size="%(iw)d,2" backgroundColor="%(cyan)s" zPosition="1" />
        <eLabel position="%(m)d,104" size="%(iw)d,%(content_h)d" backgroundColor="%(panel)s" zPosition="0" />
        <widget name="content" position="%(cx)d,120" size="%(cw)d,%(ch)d" font="Regular;19" foregroundColor="%(subtle)s" transparent="1" scrollbarMode="showOnDemand" zPosition="5" />
        <widget name="key_red" position="%(m)d,%(by)d" size="190,34" font="Regular;17" foregroundColor="#FFFFFF" backgroundColor="#B71C1C" halign="center" valign="center" zPosition="5" />
        <widget name="key_green" position="%(gx)d,%(by)d" size="190,34" font="Regular;17" foregroundColor="#FFFFFF" backgroundColor="#1B7F3A" halign="center" valign="center" zPosition="5" />
        <widget name="footer" position="%(m)d,%(fy)d" size="%(iw)d,24" font="Regular;15" foregroundColor="%(muted)s" halign="center" transparent="1" zPosition="5" />
    </screen>''' % {
        "name": name, "title": title, "w": width, "h": height, "bg": AIO_BG, "panel": AIO_PANEL,
        "m": margin, "iw": width - 2 * margin, "text": AIO_TEXT, "cyan": AIO_CYAN,
        "content_h": height - 104 - 102, "cx": margin + 14, "cw": width - 2 * margin - 28,
        "ch": height - 104 - 132, "subtle": AIO_SUBTLE, "by": height - 78,
        "gx": margin + 205, "fy": height - 34, "muted": AIO_MUTED,
    }


class DiagnosticsScreen(Screen):
    skin = _simple_skin("SimpleIPTVEPGDiagnostics", "Diagnostyka")

    def __init__(self, session):
        Screen.__init__(self, session)
        self["title"] = Label("Simple IPTV EPG • DIAGNOSTYKA")
        self["content"] = ScrollLabel("")
        self["key_red"] = Label("ZAMKNIJ")
        self["key_green"] = Label("ODŚWIEŻ")
        self["footer"] = Label(_footer_text())
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], {
            "cancel": self.close, "red": self.close, "green": self.refresh,
            "up": self["content"].pageUp, "down": self["content"].pageDown,
        }, -2)
        self.refresh()

    def refresh(self):
        state = load_state()
        report = load_json(REPORT_FILE, {})
        mapping = load_json(MAPPING_FILE, {})
        meta = mapping.get("_meta", {}) if isinstance(mapping, dict) else {}
        lines = [
            "Wersja wtyczki: %s" % PLUGIN_VERSION,
            "Python: %s.%s.%s" % sys.version_info[:3],
            "Wybrane źródło: %s" % cfg.source_select.value,
            "Auto-import: %s h" % (cfg.auto_interval.value if cfg.auto_interval.value != "0" else "wyłączony"),
            "Ostatnia próba: %s" % _fmt_time(state.get("last_attempt")),
            "Ostatni sukces: %s" % _fmt_time(state.get("last_success")),
            "Ostatni wynik: %s" % (state.get("last_result") or "—"),
            "Ostatni błąd: %s" % (state.get("last_error") or "—"),
            "Ostatnie źródło: %s" % (state.get("last_source") or "—"),
            "IPTV / SAT: %s / %s" % (state.get("last_iptv", "—"), state.get("last_sat", "—")),
            "XMLTV kanały / zdarzenia: %s / %s" % (state.get("last_xml_channels", "—"), state.get("last_xml_events", "—")),
            "Błędy eEPGCache: %s" % state.get("last_inject_errors", "—"),
            "",
            "Mapowanie BMX / EPGImport:",
            "  pliki sources.xml: %s" % len(glob.glob("/etc/epgimport/bouquetmakerxtream*.sources.xml")),
            "  wykryte EPG XMLTV: %s" % len(discover_bmx_sources()),
            "  trafienia BMX: %s" % ((report.get("mapping") or {}).get("bmx_matches", "—") if isinstance(report, dict) else "—"),
            "",
            "Cache mapowania:",
            "  źródło: %s" % (meta.get("source_url") or "—"),
            "  czułość: %s" % (meta.get("sensitivity") or "—"),
            "  grupy / dopasowane: %s / %s" % (meta.get("groups", "—"), meta.get("matched_groups", "—")),
            "  zapisano: %s" % _fmt_time(meta.get("saved_at")),
            "",
            "Pliki diagnostyczne:",
            "  %s" % LOG_FILE,
            "  %s" % STATE_FILE,
            "  %s" % REPORT_FILE,
            "  %s" % MAPPING_FILE,
            "  %s" % OVERRIDES_FILE,
            "",
            "Ostatni raport: %s" % ("dostępny" if report else "brak"),
            "Worker: %s" % (("aktywny: %s" % GLOBAL_WORKER.task_name) if GLOBAL_WORKER.running else "bezczynny"),
        ]
        self["content"].setText("\n".join(lines))


class LogScreen(Screen):
    skin = _simple_skin("SimpleIPTVEPGLog", "Log")

    def __init__(self, session):
        Screen.__init__(self, session)
        self["title"] = Label("Simple IPTV EPG • LOG")
        self["content"] = ScrollLabel("")
        self["key_red"] = Label("ZAMKNIJ")
        self["key_green"] = Label("WYCZYŚĆ LOG")
        self["footer"] = Label(_footer_text())
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], {
            "cancel": self.close, "red": self.close, "green": self.clear,
            "up": self["content"].pageUp, "down": self["content"].pageDown,
        }, -2)
        self.refresh()

    def refresh(self):
        try:
            with io_open(LOG_FILE, "r") as handle:
                text = handle.read()
        except Exception:
            text = "Brak logu."
        self["content"].setText(text[-40000:])
        self["content"].lastPage()

    def clear(self):
        clear_log()
        log_message("Log wyczyszczony z poziomu GUI.")
        self.refresh()


def _project_skin():
    dw = _desktop_width()
    w, h = (900, 570) if dw <= 1000 else ((1040, 640) if dw <= 1500 else (1160, 690))
    m = 28
    q = 222
    return '''
    <screen name="SimpleIPTVEPGProject" position="center,center" size="%(w)d,%(h)d" title="Projekt" backgroundColor="%(bg)s" flags="wfNoBorder">
        <eLabel position="0,0" size="%(w)d,80" backgroundColor="%(panel)s" zPosition="0" />
        <widget name="pp_logo" position="%(m)d,18" size="44,44" pixmap="%(pp)s" alphatest="on" zPosition="5" />
        <widget name="title" position="%(tx)d,18" size="%(tw)d,38" font="Regular;28" foregroundColor="%(text)s" transparent="1" zPosition="5" />
        <eLabel position="%(m)d,94" size="%(iw)d,2" backgroundColor="%(cyan)s" zPosition="1" />
        <widget name="qr_project" position="%(m)d,128" size="%(q)d,%(q)d" pixmap="%(qr)s" alphatest="on" zPosition="5" />
        <widget name="qr_caption" position="%(m)d,%(qcy)d" size="%(q)d,58" font="Regular;18" foregroundColor="%(cyan)s" halign="center" transparent="1" zPosition="5" />
        <widget name="info" position="%(ix)d,126" size="%(info_w)d,260" font="Regular;20" foregroundColor="%(text)s" transparent="1" zPosition="5" />
        <eLabel position="%(ix)d,402" size="%(info_w)d,1" backgroundColor="%(div)s" zPosition="1" />
        <widget name="support_qr" position="%(ix)d,420" size="90,90" pixmap="%(sqr)s" alphatest="on" zPosition="5" />
        <widget name="support" position="%(sx)d,424" size="%(sw)d,80" font="Regular;18" foregroundColor="%(subtle)s" transparent="1" zPosition="5" />
        <widget name="key_red" position="%(m)d,%(by)d" size="210,36" font="Regular;18" foregroundColor="#FFFFFF" backgroundColor="#B71C1C" halign="center" valign="center" zPosition="5" />
        <widget name="footer" position="%(m)d,%(fy)d" size="%(iw)d,24" font="Regular;15" foregroundColor="%(muted)s" halign="center" transparent="1" zPosition="5" />
    </screen>''' % {
        "w": w, "h": h, "bg": AIO_BG, "panel": AIO_PANEL, "m": m, "pp": _asset("pp_logo.png"),
        "tx": m + 60, "tw": w - 2 * m - 60, "text": AIO_TEXT, "iw": w - 2 * m, "cyan": AIO_CYAN,
        "q": q, "qr": _asset("qr_project.png"), "qcy": 128 + q + 10,
        "ix": m + q + 38, "info_w": w - (m + q + 38) - m, "div": AIO_DIVIDER,
        "sqr": _asset("qr_support.png"), "sx": m + q + 38 + 106,
        "sw": w - (m + q + 38 + 106) - m, "subtle": AIO_SUBTLE,
        "by": h - 76, "fy": h - 31, "muted": AIO_MUTED,
    }


class ProjectScreen(Screen):
    skin = _project_skin()

    def __init__(self, session):
        Screen.__init__(self, session)
        self["pp_logo"] = Pixmap()
        self["qr_project"] = Pixmap()
        self["support_qr"] = Pixmap()
        self["title"] = Label("%s • %s" % (PROJECT_NAME, PLUGIN_TITLE))
        self["qr_caption"] = Label("Zeskanuj QR\ni odwiedź stronę projektu")
        self["info"] = Label(
            "%s %s\n\nTwórca: %s\nE-mail: %s\n\nStrona projektu:\n%s\n\nRepozytorium: GitHub / OliOli2013" % (
                PLUGIN_TITLE, PLUGIN_VERSION, PLUGIN_AUTHOR, PLUGIN_EMAIL, PROJECT_URL))
        self["support"] = Label("Chcesz wesprzeć dalszy rozwój darmowych projektów Enigma2?\nZeskanuj dodatkowy kod QR.")
        self["key_red"] = Label("ZAMKNIJ")
        self["footer"] = Label(_footer_text())
        self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "cancel": self.close, "red": self.close,
        }, -2)
