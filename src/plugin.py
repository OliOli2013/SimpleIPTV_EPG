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
from twisted.internet import reactor, task
from twisted.web.client import getPage
import threading
import os
import json
import time
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError

# Importy lokalne - upewnij się, że epgcore i automapper są zaktualizowane!
from .epgcore import EPGParser, EPGInjector, download_file, inject_sat_fallback, inject_sat_clone_fallback, check_url_alive
from .automapper import AutoMapper, _load_services_cached

# --- KONFIGURACJA GIT ---
GITHUB_USER = "OliOli2013"
GITHUB_REPO = "SimpleIPTV_EPG"
GITHUB_BRANCH = "main"
GITHUB_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/"

def get_lang():
    try:
        lang = language.getLanguage()
        return "pl" if "pl" in lang.lower() else "en"
    except: return "en"

lang_code = get_lang()

TR = {
    "header": {"pl": "Simple IPTV EPG v1.1", "en": "Simple IPTV EPG v1.1"},
    "support_text": {"pl": "Wesprzyj rozwój wtyczki (Buy Coffee)", "en": "Support development"},
    "author_details": {
        "pl": "Twórca: Paweł Pawełek | Data: {} | email: msisytem@t.pl", 
        "en": "Creator: Paweł Pawełek | Date: {} | email: msisytem@t.pl"
    },
    "help_arrows": {"pl": "< Zmień źródło strzałkami Lewo/Prawo >", "en": "< Change source with Left/Right arrows >"},
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
    "success": {"pl": "ZAKOŃCZONO! XML: {} | SAT: {}", "en": "DONE! XML: {} | SAT: {}"},
    "restart_title": {"pl": "EPG Zaktualizowane!\nRestart GUI?", "en": "EPG Updated!\nRestart GUI?"},
    "mapping_start": {"pl": "Start mapowania", "en": "Starting mapping"},
    "mapping_success": {"pl": "Mapowanie OK! Kanałów: {}", "en": "Mapping OK! Channels: {}"},
    "no_map": {"pl": "Brak pliku mapowania!", "en": "No mapping file!"},
    "check_update": {"pl": "Sprawdzanie wersji na GitHub...", "en": "Checking GitHub version..."},
    "update_ok": {"pl": "Masz najnowszą wersję.", "en": "You have the latest version."},
    "update_avail": {"pl": "Dostępna nowa wersja: {}\nCzy chcesz zaktualizować wtyczkę teraz?", "en": "New version available: {}\nDo you want to update plugin now?"},
    "update_start": {"pl": "Pobieranie aktualizacji...", "en": "Downloading update..."},
    "update_done": {"pl": "Aktualizacja zakończona sukcesem!\nWymagany restart GUI.", "en": "Update successful!\nGUI Restart required."},
    "update_fail": {"pl": "Aktualizacja nieudana. Sprawdź logi.", "en": "Update failed. Check logs."},
    "timeout_error": {"pl": "BŁĄD: Przekroczono limit czasu (5 min)!", "en": "ERROR: Timeout exceeded (5 min)!"},
    "import_crash": {"pl": "CRASH: Błąd krytyczny importu: {}", "en": "CRASH: Critical import error: {}"},
    "sat_clone_start": {"pl": "1/4 Klonowanie EPG z SAT...", "en": "1/4 Cloning SAT EPG..."},
    "xml_url_dead": {"pl": "BŁĄD: Źródło XML jest niedostępne (404/Down)!", "en": "ERROR: XML Source unreachable (404/Down)!"}
}

def _(key): return TR[key].get(lang_code, TR[key]["en"]) if key in TR else key

config.plugins.SimpleIPTV_EPG = ConfigSubsection()

EPG_SOURCES = [
    ("https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", "EPG Share PL (Polska - Polecane)"),
    ("https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz", "EPG Share ALL (Świat - Duży plik)"),
    ("https://raw.githubusercontent.com/globetvapp/epg/main/Poland/poland2.xml.gz", "GlobeTV Polska (GitHub)"),
    ("https://iptv-epg.org/files/epg-pl.xml.gz", "IPTV-EPG.org (Polska)"),
    ("https://epg.ovh/pl.gz", "EPG OVH (PL - Basic)"),
    ("https://epg.ovh/plar.gz", "EPG OVH (PL + Opisy)"),
    ("https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/PlutoTV/pl.xml.gz", "PlutoTV PL (GitHub)"),
    ("https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/SamsungTVPlus/pl.xml.gz", "Samsung TV Plus PL"),
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
        injector = EPGInjector()
        injected_refs = set()

        # KROK 1: Sprawdź czy URL żyje (Head Request)
        if not check_url_alive(url):
            if callback_log: callback_log(_("xml_url_dead"))
            write_log(f"URL Dead: {url}")
            return False

        # KROK 2: AGRESYWNY SAT CLONE (Zanim cokolwiek pobierzemy)
        # Kopiuje EPG z SAT do IPTV jeśli nazwy są identyczne
        if callback_log: callback_log(_("sat_clone_start"))
        cloned_refs = inject_sat_clone_fallback(injector, log_cb=write_log)
        injected_refs.update(cloned_refs)
        
        if callback_log: callback_log(f"Sklonowano z SAT: {len(cloned_refs)} kanałów")

        # KROK 3: Pobieranie XML
        if callback_log: callback_log(_("downloading"))
        write_log("Start Download...")
        if not download_file(url, temp_path, retries=3, timeout=120):
            if callback_log: callback_log("Download Error!")
            return False
            
        # KROK 4: Automapowanie (tylko brakujących)
        # Generujemy mapę w locie tylko dla kanałów, które nie dostały EPG z SAT Clone
        mapper = AutoMapper(log_callback=write_log)
        
        if callback_log: callback_log("2/4 Mapowanie XML...")
        # Ważne: exclude_refs zapobiega mapowaniu kanałów, które już mają EPG
        mapping = mapper.generate_mapping(temp_path, exclude_refs=injected_refs)

        # KROK 5: Parsowanie i Inject XML
        if callback_log: callback_log("3/4 Import XML...")
        write_log("Start Parsing XML...")
        parser = EPGParser(temp_path)
        
        count_xml = 0
        batch = 0
        
        for service_ref, event_data in parser.load_events(mapping):
            # Podwójne zabezpieczenie: jeśli ref już jest w injected, pomiń
            if service_ref in injected_refs: continue
            
            injector.add_event(service_ref, event_data)
            injected_refs.add(service_ref)
            count_xml += 1
            batch += 1
            
            if batch >= 2000:
                injector.commit()
                batch = 0
                if callback_log: callback_log(f"XML: {count_xml}...")
        
        injector.commit()

        # KROK 6: Tradycyjny SAT Fallback (dla resztek - ręczna mapa w epgcore)
        if callback_log: callback_log("4/4 SAT Fallback (Final)...")
        count_sat_fallback = inject_sat_fallback(injector, injected_refs, log_cb=write_log)
        
        config.plugins.SimpleIPTV_EPG.last_update.value = str(int(time.time()))
        config.plugins.SimpleIPTV_EPG.save()
        
        total_sat = len(cloned_refs) + count_sat_fallback
        msg = _("success").format(count_xml, total_sat)
        if callback_log: callback_log(msg)
        write_log(f"KONIEC. XML: {count_xml}, SAT Clone: {len(cloned_refs)}, SAT Fallback: {count_sat_fallback}")
        
        # Sprzątanie
        try: os.remove(temp_path)
        except: pass
        
        return True

class IPTV_EPG_Config(ConfigListScreen, Screen):
    skin = """
        <screen name="IPTV_EPG_Config" position="center,center" size="900,680" title="Simple IPTV EPG v1.1">
            <widget name="qrcode" position="20,10" size="130,130" transparent="1" alphatest="on" />
            <widget name="support_text" position="160,30" size="700,30" font="Regular;24" foregroundColor="#00ff00" transparent="1" />
            <widget name="author_info" position="160,70" size="700,50" font="Regular;20" foregroundColor="#aaaaaa" transparent="1" />
            
            <widget name="header_title" position="20,150" size="860,50" font="Regular;34" halign="center" valign="center" foregroundColor="#fcc400" backgroundColor="#202020" transparent="1" />
            
            <widget name="help_arrows" position="20,200" size="860,25" font="Regular;20" halign="center" foregroundColor="#00aaff" transparent="1" />
            <widget name="config" position="20,230" size="860,150" font="Regular;22" itemHeight="35" scrollbarMode="showOnDemand" />
            
            <widget name="label_status" position="20,400" size="860,30" font="Regular;22" foregroundColor="#00aaff" />
            <widget name="status" position="20,435" size="860,170" font="Regular;18" foregroundColor="#dddddd" backgroundColor="#101010" />
            
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
        self["help_arrows"] = Label(_("help_arrows"))
        
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
            if getattr(self, 'dot_task', None) and self.dot_task.running:
                 self.anim_prefix = message
            else:
                 self["status"].setText(old + f"[{t}] {message}\n")
                 self["status"].lastPage()
        except: pass

    def animate_dots(self, prefix):
        self.dots = 0
        self.anim_prefix = prefix
        self["status"].setText(prefix)
        def _dot():
            self.dots = (self.dots + 1) % 4
            self["status"].setText(f"{self.anim_prefix}" + "." * self.dots)
        self.dot_task = task.LoopingCall(_dot)
        self.dot_task.start(0.3) 

    def stop_dots(self):
        if getattr(self, 'dot_task', None):
            try: self.dot_task.stop()
            except: pass

    def save_settings(self):
        for x in self["config"].list: x[1].save()
        config.plugins.SimpleIPTV_EPG.save()

    def start_import_gui(self):
        self.save_settings()
        self.log("--- START IMPORT (GUI) ---")
        self.animate_dots("Inicjalizacja") 

        def _run_with_timeout():
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.worker.run_import, callback_log=self.log, silent=False)
                    # Timeout 5 minut (300s)
                    result = future.result(timeout=300)
                    
                    reactor.callFromThread(self.stop_dots)
                    if result: 
                        reactor.callFromThread(self.gui_update_log, "SUKCES! Zakończono.")
                        reactor.callFromThread(self.ask_restart)
                    else:
                        reactor.callFromThread(self.gui_update_log, "BŁĄD IMPORTU!")
            except TimeoutError:
                reactor.callFromThread(self.stop_dots)
                reactor.callFromThread(self.gui_update_log, _("timeout_error"))
            except Exception as e:
                reactor.callFromThread(self.stop_dots)
                reactor.callFromThread(self.gui_update_log, _("import_crash").format(e))

        threading.Thread(target=_run_with_timeout, daemon=True).start()

    def ask_restart(self):
        self.session.openWithCallback(self.do_restart, MessageBox, _("restart_title"), MessageBox.TYPE_YESNO)

    def do_restart(self, answer):
        if answer:
            from enigma import quitMainloop
            quitMainloop(3)

    def start_mapping(self):
        self.save_settings()
        self.log("--- START MAPPING ---")
        self.animate_dots(_("mapping_start"))
        threading.Thread(target=self.thread_mapping, daemon=True).start()

    def thread_mapping(self):
        try:
            url = self.worker.get_url()
            ext = ".xml.gz" if ".gz" in url else ".xml"
            temp_path = "/tmp/epg_temp" + ext
            
            # Pobieramy plik, żeby mieć na czym pracować
            if not download_file(url, temp_path, retries=3, timeout=60):
                reactor.callFromThread(self.stop_dots)
                reactor.callFromThread(self.gui_update_log, "Download FAIL")
                return

            mapper = AutoMapper(log_callback=None)
            # Przy ręcznym mapowaniu generujemy wszystko (brak exclude)
            mapping = mapper.generate_mapping(temp_path)
            save_json(mapping, config.plugins.SimpleIPTV_EPG.mapping_file.value)
            
            reactor.callFromThread(self.stop_dots)
            reactor.callFromThread(self.gui_update_log, _("mapping_success").format(len(mapping)))
        except Exception as e:
            reactor.callFromThread(self.stop_dots)
            reactor.callFromThread(self.gui_update_log, f"ERROR: {e}")

    # --- OBSŁUGA AKTUALIZACJI ---
    def check_github_update(self):
        self.log(_("check_update"))
        version_url = GITHUB_BASE_URL + "version"
        getPage(str.encode(version_url)).addCallback(self.github_callback).addErrback(self.github_error)

    def github_callback(self, data):
        try:
            remote_version = data.decode('utf-8').strip()
            local_version = "1.1" 
            
            if remote_version > local_version:
                self.log(f"Nowa wersja: {remote_version}")
                self.session.openWithCallback(
                    self.perform_update_question, 
                    MessageBox, 
                    _("update_avail").format(remote_version), 
                    MessageBox.TYPE_YESNO
                )
            elif remote_version == local_version:
                self.log(_("update_ok"))
                self.session.open(MessageBox, _("update_ok") + f"\n(v{local_version})", MessageBox.TYPE_INFO)
            else:
                self.session.open(MessageBox, f"Dev/Test Version.\nGitHub: {remote_version} | Local: {local_version}", MessageBox.TYPE_INFO)
        except: pass

    def github_error(self, error):
        self.session.open(MessageBox, "GitHub Error: " + str(error), MessageBox.TYPE_ERROR)

    def perform_update_question(self, answer):
        if answer:
            self.animate_dots(_("update_start"))
            threading.Thread(target=self.thread_perform_update, daemon=True).start()

    def thread_perform_update(self):
        FILES_TO_UPDATE = ["plugin.py", "epgcore.py", "automapper.py", "version"]
        success = True
        plugin_path = os.path.dirname(__file__)

        try:
            for fname in FILES_TO_UPDATE:
                url = GITHUB_BASE_URL + fname
                target_tmp = f"/tmp/{fname}"
                target_final = os.path.join(plugin_path, fname)
                
                # Używamy epgcore.download_file
                if download_file(url, target_tmp, retries=2, timeout=10):
                    shutil.move(target_tmp, target_final)
                    reactor.callFromThread(self.gui_update_log, f"Zaktualizowano: {fname}")
                else:
                    success = False
                    reactor.callFromThread(self.gui_update_log, f"Błąd pobierania: {fname}")
                    break
            
            reactor.callFromThread(self.stop_dots)
            
            if success:
                reactor.callFromThread(self.session.openWithCallback, self.do_restart, MessageBox, _("update_done"), MessageBox.TYPE_YESNO)
            else:
                reactor.callFromThread(self.session.open, MessageBox, _("update_fail"), MessageBox.TYPE_ERROR)

        except Exception as e:
            reactor.callFromThread(self.stop_dots)
            reactor.callFromThread(self.gui_update_log, f"Update Crash: {e}")

def AutoUpdateCheck():
    if config.plugins.SimpleIPTV_EPG.auto_update.value:
        try: last_upd = int(config.plugins.SimpleIPTV_EPG.last_update.value)
        except: last_upd = 0
        now = int(time.time())
        if (now - last_upd) > 86400:
            write_log("[AutoUpdate] Triggering background update...")
            worker = EPGWorker()
            threading.Thread(target=worker.run_import, kwargs={'silent': True}, daemon=True).start()
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
