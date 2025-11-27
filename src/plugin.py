from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, ConfigSubsection, ConfigText, ConfigSelection, ConfigYesNo, getConfigListEntry
from Components.ScrollLabel import ScrollLabel
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Components.Language import language
from twisted.internet import reactor
import threading
import os
import json
import time
from datetime import datetime

# Importy lokalne
from .epgcore import EPGParser, EPGInjector, download_file
from .automapper import AutoMapper

# --- DETEKCJA JĘZYKA ---
def get_lang():
    try:
        lang = language.getLanguage()
        return "pl" if "pl" in lang.lower() else "en"
    except: return "en"

lang_code = get_lang()

TR = {
    "header": {"pl": "Simple IPTV EPG v1.2", "en": "Simple IPTV EPG v1.2"},
    "support_text": {"pl": "Wesprzyj rozwój wtyczki (Buy Coffee)", "en": "Support development"},
    "source_label": {"pl": "Wybierz Źródło:", "en": "Select Source:"},
    "custom_label": {"pl": "   >> Wpisz adres URL:", "en": "   >> Enter URL:"},
    "map_file_label": {"pl": "Plik mapowania:", "en": "Mapping File:"},
    "autoupdate_label": {"pl": "Auto-Aktualizacja (co 24h):", "en": "Auto-Update (every 24h):"},
    "btn_exit": {"pl": "Wyjdź", "en": "Exit"},
    "btn_import": {"pl": "Importuj", "en": "Import"},
    "btn_map": {"pl": "Mapuj", "en": "Map"},
    "status_ready": {"pl": "Gotowy. Wybierz opcje.\n", "en": "Ready. Select options.\n"},
    "downloading": {"pl": "Pobieranie...", "en": "Downloading..."},
    "success": {"pl": "ZAKOŃCZONO! Pobrane zdarzenia: {}", "en": "DONE! Events loaded: {}"},
    "restart_title": {"pl": "EPG Zaktualizowane!\nRestart GUI?", "en": "EPG Updated!\nRestart GUI?"},
    "mapping_start": {"pl": "Start mapowania (to potrwa chwilę)...", "en": "Starting mapping..."},
    "mapping_success": {"pl": "Mapowanie OK! Kanałów: {}", "en": "Mapping OK! Channels: {}"},
    "no_map": {"pl": "Brak pliku mapowania!", "en": "No mapping file!"}
}

def _(key): return TR[key].get(lang_code, TR[key]["en"]) if key in TR else key

# --- KONFIGURACJA ---
config.plugins.SimpleIPTV_EPG = ConfigSubsection()

EPG_SOURCES = [
    ("https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", "EPG Share PL (Polska - Polecane)"),
    ("https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz", "EPG Share ALL (Świat)"),
    ("https://iptv-epg.org/files/epg-pl.xml.gz", "IPTV-EPG.org (PL)"),
    ("https://epg.ovh/pl.xml", "EPG OVH (PL - Basic)"),
    ("CUSTOM", "--- Custom URL ---")
]

config.plugins.SimpleIPTV_EPG.source_select = ConfigSelection(default="https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", choices=EPG_SOURCES)
config.plugins.SimpleIPTV_EPG.custom_url = ConfigText(default="http://", fixed_size=False, visible_width=80)
config.plugins.SimpleIPTV_EPG.mapping_file = ConfigText(default="/etc/enigma2/iptv_mapping.json", fixed_size=False)
config.plugins.SimpleIPTV_EPG.auto_update = ConfigYesNo(default=False)
config.plugins.SimpleIPTV_EPG.last_update = ConfigText(default="0", fixed_size=False)

DEBUG_LOG_FILE = "/tmp/simple_epg.log"

def write_log(msg):
    try:
        with open(DEBUG_LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except: pass

def load_json(path):
    try:
        with open(path, 'r') as f: return json.load(f)
    except: return {}

def save_json(data, path):
    try:
        with open(path, 'w') as f: json.dump(data, f, indent=4)
    except: pass

# --- GLOBALNA KLASA WORKER (LOGIKA W TLE) ---
class EPGWorker:
    def __init__(self):
        self.lock = threading.Lock()

    def get_url(self):
        val = config.plugins.SimpleIPTV_EPG.source_select.value
        return config.plugins.SimpleIPTV_EPG.custom_url.value if val == "CUSTOM" else val

    def run_import(self, callback_log=None, silent=False):
        """
        Główna funkcja importu.
        callback_log: funkcja do wysyłania logów do GUI
        silent: True = tryb cichy (bez pytań, bez restartu GUI, tylko wczytanie do cache)
        """
        url = self.get_url()
        ext = ".xml.gz" if ".gz" in url else ".xml"
        temp_path = "/tmp/epg_temp" + ext
        
        if callback_log: callback_log(_("downloading"))
        write_log("Start Download...")
        
        if not download_file(url, temp_path):
            if callback_log: callback_log("Download Error!")
            return False

        mapping = load_json(config.plugins.SimpleIPTV_EPG.mapping_file.value)
        if not mapping:
            if callback_log: callback_log(_("no_map"))
            return False

        parser = EPGParser(temp_path)
        injector = EPGInjector()
        
        count = 0
        batch = 0
        
        for service_ref, event_data in parser.load_events(mapping):
            injector.add_event(service_ref, event_data)
            count += 1
            batch += 1
            if batch >= 5000: # Większy bufor dla płynności
                injector.commit()
                batch = 0
        
        injector.commit()
        
        # Zapis czasu aktualizacji
        config.plugins.SimpleIPTV_EPG.last_update.value = str(int(time.time()))
        config.plugins.SimpleIPTV_EPG.save()

        if callback_log: callback_log(_("success").format(count))
        write_log(f"Import finished. Events: {count}")
        
        # W trybie silent nie restartujemy GUI, eEPGCache sam sobie poradzi z odświeżeniem
        # ewentualnie można wymusić przeładowanie EPG w C++
        return True

# --- SCREEN KONFIGURACJI ---
class IPTV_EPG_Config(ConfigListScreen, Screen):
    skin = """
        <screen name="IPTV_EPG_Config" position="center,center" size="900,650" title="Simple IPTV EPG v1.2">
            <widget name="qrcode" position="20,10" size="130,130" transparent="1" alphatest="on" />
            <widget name="support_text" position="160,40" size="600,30" font="Regular;24" foregroundColor="#00ff00" transparent="1" />
            <widget name="author_info" position="160,80" size="600,25" font="Regular;18" foregroundColor="#aaaaaa" transparent="1" />
            <widget name="header_title" position="20,150" size="860,50" font="Regular;34" halign="center" valign="center" foregroundColor="#fcc400" backgroundColor="#202020" transparent="1" />
            <widget name="config" position="20,210" size="860,150" font="Regular;22" itemHeight="35" scrollbarMode="showOnDemand" />
            <widget name="label_status" position="20,380" size="860,30" font="Regular;22" foregroundColor="#00aaff" />
            <widget name="status" position="20,415" size="860,170" font="Regular;18" foregroundColor="#dddddd" backgroundColor="#101010" />
            <eLabel position="20,600" size="860,2" backgroundColor="#555555" />
            <ePixmap pixmap="skin_default/buttons/red.png" position="30,610" size="30,40" alphatest="on" />
            <widget name="key_red" position="65,610" zPosition="1" size="200,40" font="Regular;20" valign="center" transparent="1" />
            <ePixmap pixmap="skin_default/buttons/green.png" position="330,610" size="30,40" alphatest="on" />
            <widget name="key_green" position="365,610" zPosition="1" size="200,40" font="Regular;20" valign="center" transparent="1" />
            <ePixmap pixmap="skin_default/buttons/yellow.png" position="630,610" size="30,40" alphatest="on" />
            <widget name="key_yellow" position="665,610" zPosition="1" size="200,40" font="Regular;20" valign="center" transparent="1" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self["header_title"] = Label(_("header"))
        self["qrcode"] = Pixmap()
        self["support_text"] = Label(_("support_text"))
        self["author_info"] = Label("v1.2 | Enhanced Junk Filter & AutoUpdate")
        self["key_red"] = Label(_("btn_exit"))
        self["key_green"] = Label(_("btn_import"))
        self["key_yellow"] = Label(_("btn_map"))
        self["label_status"] = Label("Log:")
        self["status"] = ScrollLabel(_("status_ready"))
        
        self.worker = EPGWorker()
        self.list = []
        self.createConfigList()
        ConfigListScreen.__init__(self, self.list)
        
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], {
            "red": self.close,
            "green": self.start_import_gui,
            "yellow": self.start_mapping,
            "cancel": self.close,
            "save": self.start_import_gui,
            "left": self.keyLeft,
            "right": self.keyRight
        }, -2)
        
        self.onLayoutFinish.append(self.load_qr_code)

    def load_qr_code(self):
        try:
            plugin_path = os.path.dirname(__file__)
            qr_path = os.path.join(plugin_path, "Kod_QR_buycoffee.png")
            if os.path.exists(qr_path): self["qrcode"].instance.setPixmapFromFile(qr_path)
        except: pass

    def createConfigList(self):
        self.list = []
        self.list.append(getConfigListEntry(_("source_label"), config.plugins.SimpleIPTV_EPG.source_select))
        if config.plugins.SimpleIPTV_EPG.source_select.value == "CUSTOM":
            self.list.append(getConfigListEntry(_("custom_label"), config.plugins.SimpleIPTV_EPG.custom_url))
        self.list.append(getConfigListEntry(_("map_file_label"), config.plugins.SimpleIPTV_EPG.mapping_file))
        self.list.append(getConfigListEntry(_("autoupdate_label"), config.plugins.SimpleIPTV_EPG.auto_update))

    def updateConfigList(self):
        self.createConfigList()
        self["config"].setList(self.list)

    def keyLeft(self):
        ConfigListScreen.keyLeft(self)
        self.updateConfigList()

    def keyRight(self):
        ConfigListScreen.keyRight(self)
        self.updateConfigList()

    def log(self, message):
        reactor.callFromThread(self.gui_update_log, message)

    def gui_update_log(self, message):
        try:
            t = datetime.now().strftime("%H:%M:%S")
            old = self["status"].getText()
            self["status"].setText(old + f"[{t}] {message}\n")
            self["status"].lastPage()
        except: pass

    def save_settings(self):
        for x in self["config"].list: x[1].save()
        config.plugins.SimpleIPTV_EPG.save()

    # --- IMPORT RĘCZNY Z GUI ---
    def start_import_gui(self):
        self.save_settings()
        self.log("--- START IMPORT (GUI) ---")
        threading.Thread(target=self.thread_import).start()

    def thread_import(self):
        result = self.worker.run_import(callback_log=self.log, silent=False)
        if result:
            reactor.callFromThread(self.ask_restart)

    def ask_restart(self):
        self.session.openWithCallback(
            self.do_restart,
            MessageBox,
            _("restart_title"),
            MessageBox.TYPE_YESNO
        )

    def do_restart(self, answer):
        if answer:
            from enigma import quitMainloop
            quitMainloop(3)

    # --- MAPOWANIE ---
    def start_mapping(self):
        self.save_settings()
        self.log("--- START MAPPING ---")
        threading.Thread(target=self.thread_mapping).start()

    def thread_mapping(self):
        try:
            url = self.worker.get_url()
            ext = ".xml.gz" if ".gz" in url else ".xml"
            temp_path = "/tmp/epg_temp" + ext
            
            self.log(_("downloading"))
            if not download_file(url, temp_path):
                self.log("Download FAIL")
                return

            mapper = AutoMapper(log_callback=self.log)
            self.log(_("mapping_start"))
            
            mapping = mapper.generate_mapping(temp_path)
            save_json(mapping, config.plugins.SimpleIPTV_EPG.mapping_file.value)
            
            self.log(_("mapping_success").format(len(mapping)))
        except Exception as e:
            self.log(f"ERROR: {e}")

# --- AUTO UPDATE SYSTEM ---
def AutoUpdateCheck():
    """Sprawdza czy należy uruchomić aktualizację"""
    if config.plugins.SimpleIPTV_EPG.auto_update.value:
        try:
            last_upd = int(config.plugins.SimpleIPTV_EPG.last_update.value)
        except: last_upd = 0
        
        now = int(time.time())
        # 86400 sekund = 24h
        if (now - last_upd) > 86400:
            write_log("[AutoUpdate] Triggering background update...")
            worker = EPGWorker()
            # Uruchamiamy w wątku, żeby nie blokować startu Enigmy
            threading.Thread(target=worker.run_import, kwargs={'silent': True}).start()
        else:
            write_log("[AutoUpdate] Not yet. Time left: " + str(86400 - (now - last_upd)) + "s")
    
    # Zaplanuj kolejne sprawdzenie za 1h (3600s)
    reactor.callLater(3600, AutoUpdateCheck)

def StartSession(**kwargs):
    """Uruchamiane przy starcie sesji Enigmy"""
    write_log("Plugin Loaded. Initializing AutoUpdate timer...")
    # Pierwsze sprawdzenie po 60s od startu systemu, żeby dać czas na sieć
    reactor.callLater(60, AutoUpdateCheck)

def main(session, **kwargs): session.open(IPTV_EPG_Config)

def Plugins(**kwargs):
    return [
        PluginDescriptor(name="Simple IPTV EPG", description="Importer EPG Auto/Manual", where=PluginDescriptor.WHERE_PLUGINMENU, icon="plugin.png", fnc=main),
        PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=StartSession)
    ]
