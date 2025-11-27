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
from twisted.web.client import getPage
import threading
import os
import json
import time
from datetime import datetime

# Importy lokalne
from .epgcore import EPGParser, EPGInjector, download_file
from .automapper import AutoMapper

def get_lang():
    try:
        lang = language.getLanguage()
        return "pl" if "pl" in lang.lower() else "en"
    except: return "en"

lang_code = get_lang()

TR = {
    "header": {"pl": "Simple IPTV EPG v1.3", "en": "Simple IPTV EPG v1.3"},
    "support_text": {"pl": "Wesprzyj rozwój wtyczki (Buy Coffee)", "en": "Support development"},
    "author_details": {
        "pl": "Twórca: Paweł Pawełek | Data: {} | email: msisytem@t.pl", 
        "en": "Creator: Paweł Pawełek | Date: {} | email: msisytem@t.pl"
    },
    "source_label": {"pl": "Wybierz Źródło:", "en": "Select Source:"},
    "custom_label": {"pl": "   >> Wpisz adres URL:", "en": "   >> Enter URL:"},
    "map_file_label": {"pl": "Plik mapowania:", "en": "Mapping File:"},
    "autoupdate_label": {"pl": "Auto-Aktualizacja (co 24h):", "en": "Auto-Update (every 24h):"},
    "btn_exit": {"pl": "Wyjdź", "en": "Exit"},
    "btn_import": {"pl": "Importuj", "en": "Import"},
    "btn_map": {"pl": "Mapuj", "en": "Map"},
    "btn_update": {"pl": "Aktualizuj (GitHub)", "en": "Update (GitHub)"},
    "status_ready": {"pl": "Gotowy. Wybierz opcje.\n", "en": "Ready. Select options.\n"},
    "downloading": {"pl": "Pobieranie...", "en": "Downloading..."},
    "success": {"pl": "ZAKOŃCZONO! Pobrane zdarzenia: {}", "en": "DONE! Events loaded: {}"},
    "restart_title": {"pl": "EPG Zaktualizowane!\nRestart GUI?", "en": "EPG Updated!\nRestart GUI?"},
    "mapping_start": {"pl": "Start mapowania (Turbo Mode)...", "en": "Starting mapping (Turbo Mode)..."},
    "mapping_success": {"pl": "Mapowanie OK! Kanałów: {}", "en": "Mapping OK! Channels: {}"},
    "no_map": {"pl": "Brak pliku mapowania!", "en": "No mapping file!"},
    "check_update": {"pl": "Sprawdzanie wersji na GitHub...", "en": "Checking GitHub version..."},
    "update_ok": {"pl": "Masz najnowszą wersję.", "en": "You have the latest version."},
    "update_avail": {"pl": "Dostępna nowa wersja! Sprawdź GitHub.", "en": "New version available! Check GitHub."}
}

def _(key): return TR[key].get(lang_code, TR[key]["en"]) if key in TR else key

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

class EPGWorker:
    def __init__(self):
        self.lock = threading.Lock()
    def get_url(self):
        val = config.plugins.SimpleIPTV_EPG.source_select.value
        return config.plugins.SimpleIPTV_EPG.custom_url.value if val == "CUSTOM" else val
    def run_import(self, callback_log=None, silent=False):
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
            if batch >= 5000:
                injector.commit()
                batch = 0
        injector.commit()
        config.plugins.SimpleIPTV_EPG.last_update.value = str(int(time.time()))
        config.plugins.SimpleIPTV_EPG.save()
        if callback_log: callback_log(_("success").format(count))
        write_log(f"Import finished. Events: {count}")
        return True

class IPTV_EPG_Config(ConfigListScreen, Screen):
    # POPRAWIONY SKIN: STOPKA + NIEBIESKI PRZYCISK
    skin = """
        <screen name="IPTV_EPG_Config" position="center,center" size="900,680" title="Simple IPTV EPG v1.3">
            <widget name="qrcode" position="20,10" size="130,130" transparent="1" alphatest="on" />
            
            <widget name="support_text" position="160,30" size="700,30" font="Regular;24" foregroundColor="#00ff00" transparent="1" />
            <widget name="author_info" position="160,70" size="700,50" font="Regular;20" foregroundColor="#aaaaaa" transparent="1" />
            
            <widget name="header_title" position="20,150" size="860,50" font="Regular;34" halign="center" valign="center" foregroundColor="#fcc400" backgroundColor="#202020" transparent="1" />
            
            <widget name="config" position="20,210" size="860,150" font="Regular;22" itemHeight="35" scrollbarMode="showOnDemand" />
            
            <widget name="label_status" position="20,380" size="860,30" font="Regular;22" foregroundColor="#00aaff" />
            <widget name="status" position="20,415" size="860,190" font="Regular;18" foregroundColor="#dddddd" backgroundColor="#101010" />
            
            <eLabel position="20,620" size="860,2" backgroundColor="#555555" />

            <ePixmap pixmap="skin_default/buttons/red.png" position="30,630" size="30,40" alphatest="on" />
            <widget name="key_red" position="65,630" zPosition="1" size="180,40" font="Regular;20" valign="center" transparent="1" />
            
            <ePixmap pixmap="skin_default/buttons/green.png" position="250,630" size="30,40" alphatest="on" />
            <widget name="key_green" position="285,630" zPosition="1" size="180,40" font="Regular;20" valign="center" transparent="1" />
            
            <ePixmap pixmap="skin_default/buttons/yellow.png" position="470,630" size="30,40" alphatest="on" />
            <widget name="key_yellow" position="505,630" zPosition="1" size="180,40" font="Regular;20" valign="center" transparent="1" />

            <ePixmap pixmap="skin_default/buttons/blue.png" position="690,630" size="30,40" alphatest="on" />
            <widget name="key_blue" position="725,630" zPosition="1" size="180,40" font="Regular;20" valign="center" transparent="1" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self["header_title"] = Label(_("header"))
        self["qrcode"] = Pixmap()
        self["support_text"] = Label(_("support_text"))
        
        # WYPEŁNIENIE DANYCH AUTORA
        date_str = datetime.now().strftime("%d.%m.%Y")
        self["author_info"] = Label(_("author_details").format(date_str))
        
        self["key_red"] = Label(_("btn_exit"))
        self["key_green"] = Label(_("btn_import"))
        self["key_yellow"] = Label(_("btn_map"))
        self["key_blue"] = Label(_("btn_update"))
        
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
            "blue": self.check_github_update,
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

    def start_import_gui(self):
        self.save_settings()
        self.log("--- START IMPORT (GUI) ---")
        threading.Thread(target=self.thread_import).start()

    def thread_import(self):
        result = self.worker.run_import(callback_log=self.log, silent=False)
        if result: reactor.callFromThread(self.ask_restart)

    def ask_restart(self):
        self.session.openWithCallback(self.do_restart, MessageBox, _("restart_title"), MessageBox.TYPE_YESNO)

    def do_restart(self, answer):
        if answer:
            from enigma import quitMainloop
            quitMainloop(3)

    def start_mapping(self):
        self.save_settings()
        self.log("--- START MAPPING (TURBO) ---")
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

    # --- CHECK UPDATE GITHUB ---
    def check_github_update(self):
        self.log(_("check_update"))
        # URL do pliku version.txt w repozytorium (PRZYKŁADOWY - Podmień na swój prawdziwy!)
        GITHUB_VERSION_URL = "https://raw.githubusercontent.com/TWOJE_KONTO/REPO/main/version.txt"
        
        # Na razie, jako placeholder, wyświetlam info:
        self.session.open(MessageBox, "Funkcja sprawdzania wersji GitHub.\nPodmień URL w kodzie (linia check_github_update).", MessageBox.TYPE_INFO)
        
        # Prawdziwa logika (odkomentuj jak będziesz miał URL):
        # getPage(str.encode(GITHUB_VERSION_URL)).addCallback(self.github_callback).addErrback(self.github_error)

    def github_callback(self, data):
        try:
            remote_version = data.decode('utf-8').strip()
            local_version = "1.3"
            if remote_version > local_version:
                self.log(_("update_avail"))
                self.session.open(MessageBox, _("update_avail") + f"\nRemote: {remote_version}, Local: {local_version}", MessageBox.TYPE_INFO)
            else:
                self.log(_("update_ok"))
                self.session.open(MessageBox, _("update_ok"), MessageBox.TYPE_INFO)
        except: pass

    def github_error(self, error):
        self.log("GitHub Check Error")

def AutoUpdateCheck():
    if config.plugins.SimpleIPTV_EPG.auto_update.value:
        try: last_upd = int(config.plugins.SimpleIPTV_EPG.last_update.value)
        except: last_upd = 0
        now = int(time.time())
        if (now - last_upd) > 86400:
            write_log("[AutoUpdate] Triggering background update...")
            worker = EPGWorker()
            threading.Thread(target=worker.run_import, kwargs={'silent': True}).start()
    reactor.callLater(3600, AutoUpdateCheck)

def StartSession(**kwargs):
    write_log("Plugin Loaded. Initializing AutoUpdate timer...")
    reactor.callLater(60, AutoUpdateCheck)

def main(session, **kwargs): session.open(IPTV_EPG_Config)

def Plugins(**kwargs):
    return [
        PluginDescriptor(name="Simple IPTV EPG", description="Importer EPG Auto/Manual", where=PluginDescriptor.WHERE_PLUGINMENU, icon="plugin.png", fnc=main),
        PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=StartSession)
    ]
