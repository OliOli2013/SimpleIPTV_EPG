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
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError

# Importy lokalne
from .epgcore import EPGParser, EPGInjector, download_file, inject_sat_fallback, inject_sat_clone_by_name, check_url_alive
from .automapper import AutoMapper

# --- KONFIGURACJA ---
GITHUB_USER = "OliOli2013"
GITHUB_REPO = "SimpleIPTV_EPG"
GITHUB_BRANCH = "main"
GITHUB_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/"
PLUGIN_VERSION = "1.3"

# LIMIT CZASU (45 minut)
OPERATION_TIMEOUT = 2700 

def get_lang():
    try:
        lang = language.getLanguage()
        return "pl" if "pl" in lang.lower() else "en"
    except: return "en"

lang_code = get_lang()

TR = {
    "header": { "pl": f"Simple IPTV EPG v{PLUGIN_VERSION} (Fast)", "en": f"Simple IPTV EPG v{PLUGIN_VERSION} (Fast)" },
    "support_text": { "pl": "Wesprzyj rozwój wtyczki (Buy Coffee)", "en": "Support development (Buy Coffee)" },
    "author_details": { "pl": "Twórca: Paweł Pawełek | Data: 30.11.2025 | email: msisytem@t.pl", "en": "Author: Paweł Pawełek | Date: 30.11.2025 | email: msisytem@t.pl" },
    "help_arrows": { "pl": "< Zmień źródło strzałkami Lewo/Prawo >", "en": "< Change source using Left/Right arrows >" },
    "source_label": { "pl": "Wybierz Źródło EPG:", "en": "Select EPG Source:" },
    "custom_label": { "pl": "   >> Wpisz własny URL:", "en": "   >> Enter Custom URL:" },
    "map_file_label": { "pl": "Plik mapowania (Cache):", "en": "Mapping File (Cache):" },
    "autoupdate_label": { "pl": "Auto-Aktualizacja (co 24h):", "en": "Auto-Update (every 24h):" },
    "btn_hide": { "pl": "Ukryj w tle", "en": "Hide in background" }, 
    "btn_import": { "pl": "Importuj EPG", "en": "Import EPG" },
    "btn_map": { "pl": "Mapuj Kanały", "en": "Map Channels" },
    "btn_update": { "pl": "Aktualizuj Wtyczkę", "en": "Update Plugin" },
    "status_ready": { "pl": "Gotowy. Wybierz opcję z menu poniżej.\n", "en": "Ready. Select an option from the menu below.\n" },
    "downloading": { "pl": "Pobieranie pliku EPG...", "en": "Downloading EPG file..." },
    "success": { "pl": "ZAKOŃCZONO!\nZaimportowano XML: {} | Połączono z SAT: {}", "en": "SUCCESS!\nXML Imported: {} | SAT Linked: {}" },
    "restart_title": { "pl": "EPG Zaktualizowane pomyślnie!\nWymagany restart GUI. Zrestartować teraz?", "en": "EPG Updated Successfully!\nGUI Restart required. Restart now?" },
    "mapping_start": { "pl": "Rozpoczynam mapowanie kanałów...", "en": "Starting channel mapping process..." },
    "mapping_success": { "pl": "Mapowanie zakończone! Zmapowano kanałów: {}", "en": "Mapping complete! Channels mapped: {}" },
    "no_map": { "pl": "Brak pliku mapowania! Najpierw wykonaj 'Mapuj'.", "en": "No mapping file found! Please run 'Map Channels' first." },
    "check_update": { "pl": "Sprawdzanie dostępności aktualizacji na GitHub...", "en": "Checking for updates on GitHub..." },
    "update_ok": { "pl": "Posiadasz najnowszą wersję wtyczki.", "en": "You have the latest version installed." },
    "update_avail": { "pl": "Dostępna nowa wersja: {}\nCzy chcesz zaktualizować wtyczkę teraz?", "en": "New version available: {}\nDo you want to update the plugin now?" },
    "update_start": { "pl": "Pobieranie i instalowanie aktualizacji...", "en": "Downloading and installing update..." },
    "update_done": { "pl": "Aktualizacja zakończona sukcesem!\nWymagany restart GUI.", "en": "Update successful!\nGUI Restart is required." },
    "update_fail": { "pl": "Aktualizacja nieudana. Sprawdź połączenie lub logi.", "en": "Update failed. Check internet connection or logs." },
    "timeout_error": { "pl": "BŁĄD: Przekroczono limit czasu (45 min)! Plik jest zbyt duży.", "en": "ERROR: Timeout (45 min)! Source file is too big." },
    "import_crash": { "pl": "CRASH: Wystąpił błąd krytyczny: {}", "en": "CRASH: Critical error: {}" },
    "xml_url_dead": { "pl": "BŁĄD: Wybrane źródło XML jest niedostępne (Offline/404)!", "en": "ERROR: Selected XML Source is unreachable (Offline/404)!" },
    "sat_smart_match": { "pl": "Inteligentne łączenie (SAT <-> IPTV)...", "en": "Smart Linking (SAT <-> IPTV)..." },
    "sat_fallback": { "pl": "Uzupełnianie braków z SAT...", "en": "Filling gaps from SAT..." },
    "hidden_msg": { "pl": "Wtyczka pracuje w tle.\nMożesz oglądać TV. Powiadomię Cię komunikatem, gdy skończę.", "en": "Plugin running in background.\nYou can watch TV. I will notify you via popup when done." }
}

def _(key): return TR[key].get(lang_code, TR[key]["en"]) if key in TR else key

config.plugins.SimpleIPTV_EPG = ConfigSubsection()

EPG_SOURCES = [
    ("https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", "PL - EPG Share (Polecane)"),
    ("http://epg.ovh/pl.xml.gz", "PL - EPG.OVH"),
    ("https://epg.pw/xmltv/epg.xml", "EPG.PW (Multi-Language)"),
    ("https://iptv-org.github.io/epg/guides/pl.xml.gz", "PL - IPTV-Org"),
    ("https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz", "GLOBAL - All Sources (HUGE FILE!)"),
    ("https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz", "UK - United Kingdom"),
    ("https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz", "DE - Germany/DACH"),
    ("https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz", "IT - Italy"),
    ("https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz", "ES - Spain"),
    ("CUSTOM", "--- Custom URL ---")
]

config.plugins.SimpleIPTV_EPG.source_select = ConfigSelection(default="https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", choices=EPG_SOURCES)
config.plugins.SimpleIPTV_EPG.custom_url = ConfigText(default="http://", fixed_size=False, visible_width=80)
config.plugins.SimpleIPTV_EPG.mapping_file = ConfigText(default="/etc/enigma2/iptv_mapping.json", fixed_size=False)
config.plugins.SimpleIPTV_EPG.auto_update = ConfigYesNo(default=False)
config.plugins.SimpleIPTV_EPG.last_update = ConfigText(default="0", fixed_size=False)

def write_log(msg):
    try:
        with open("/tmp/simple_epg.log", "a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except: pass

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

        def progress_wrapper(msg):
            if callback_log: callback_log(msg)

        if not check_url_alive(url):
            if callback_log: callback_log(_("xml_url_dead"))
            return False

        if callback_log: callback_log(_("sat_smart_match"))
        cloned_refs = inject_sat_clone_by_name(injector, log_cb=progress_wrapper)
        injected_refs.update(cloned_refs)
        
        if callback_log: callback_log(_("downloading"))
        write_log("Start Download...")
        
        if not download_file(url, temp_path, retries=3, timeout=600):
            if callback_log: callback_log("Download Error!")
            return False
            
        mapper = AutoMapper(log_callback=write_log)
        def mapping_progress(current, total):
            if callback_log and current % 100 == 0: 
                percent = int(current * 100 / max(total, 1))
                callback_log(f"Mapping: {percent}% ({current}/{total})")

        mapping = mapper.generate_mapping(temp_path, exclude_refs=injected_refs, progress_callback=mapping_progress)

        if callback_log: callback_log("Import XML...")
        write_log("Start Parsing XML...")
        parser = EPGParser(temp_path)
        
        count_xml = 0
        batch = 0
        
        for service_ref, event_data in parser.load_events(mapping, progress_cb=progress_wrapper):
            if service_ref in injected_refs: continue
            
            injector.add_event(service_ref, event_data)
            injected_refs.add(service_ref)
            count_xml += 1
            batch += 1
            
            if batch >= 2000:
                injector.commit()
                batch = 0
        
        injector.commit()

        if callback_log: callback_log(_("sat_fallback"))
        count_sat_fallback = inject_sat_fallback(injector, injected_refs, log_cb=write_log)
        
        config.plugins.SimpleIPTV_EPG.last_update.value = str(int(time.time()))
        config.plugins.SimpleIPTV_EPG.save()
        
        total_sat = len(cloned_refs) + count_sat_fallback
        msg = _("success").format(count_xml, total_sat)
        if callback_log: callback_log(msg)
        
        try: os.remove(temp_path)
        except: pass
        
        return True

class IPTV_EPG_Config(ConfigListScreen, Screen):
    skin = """
        <screen name="IPTV_EPG_Config" position="center,center" size="900,680" title="Simple IPTV EPG v1.3 (Global)">
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
        self["author_info"] = Label(_("author_details").format(datetime.now().strftime("%d.%m.%Y")))
        self["key_red"] = Label(_("btn_hide"))
        self["key_green"] = Label(_("btn_import"))
        self["key_yellow"] = Label(_("btn_map"))
        self["key_blue"] = Label(_("btn_update"))
        
        self["label_status"] = Label("Log:")
        self["status"] = ScrollLabel(_("status_ready"))
        
        self.worker = EPGWorker()
        self.list = []
        self.createConfigList()
        ConfigListScreen.__init__(self, self.list)
        
        # KEY MAPPING: 
        # cancel (EXIT) - Zamyka
        # red - Ukrywa
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], {
            "red": self.minimize_window,
            "green": self.start_import_gui,
            "yellow": self.start_mapping,
            "blue": self.check_github_update,
            "cancel": self.close,        
            "save": self.start_import_gui,
            "left": self.keyLeft,
            "right": self.keyRight
        }, -1) 
        
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
    def keyLeft(self): ConfigListScreen.keyLeft(self); self.updateConfigList()
    def keyRight(self): ConfigListScreen.keyRight(self); self.updateConfigList()

    def minimize_window(self):
        self.hide()
        self.session.open(MessageBox, _("hidden_msg"), MessageBox.TYPE_INFO, timeout=5)

    def log(self, message): reactor.callFromThread(self.gui_update_log, message)

    def gui_update_log(self, message):
        try:
            if "[" in message and "%" in message:
                 self["status"].setText(message)
            else:
                 t = datetime.now().strftime("%H:%M:%S")
                 old = self["status"].getText()
                 self["status"].setText(old + f"[{t}] {message}\n")
                 self["status"].lastPage()
        except: pass

    def animate_percent(self, prefix, current, total):
        try:
            percent = int(current * 100 / max(total, 1))
            self["status"].setText(f"{prefix} | %: {percent}% ({current}/{total})")
        except: pass

    def save_settings(self):
        for x in self["config"].list: x[1].save()
        config.plugins.SimpleIPTV_EPG.save()

    def start_import_gui(self):
        self.save_settings()
        self["status"].setText(_("status_ready"))

        def _run_with_timeout():
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.worker.run_import, callback_log=self.log, silent=False)
                    result = future.result(timeout=OPERATION_TIMEOUT)
                    if result: 
                        reactor.callFromThread(self.gui_update_log, "OK! Finished.")
                        reactor.callFromThread(self.ask_restart)
                    else:
                        reactor.callFromThread(self.gui_update_log, "IMPORT ERROR!")
            except TimeoutError:
                reactor.callFromThread(self.gui_update_log, _("timeout_error"))
                reactor.callFromThread(self.session.open, MessageBox, _("timeout_error"), MessageBox.TYPE_ERROR)
            except Exception as e:
                reactor.callFromThread(self.gui_update_log, _("import_crash").format(e))

        threading.Thread(target=_run_with_timeout, daemon=True).start()

    def ask_restart(self):
        self.session.openWithCallback(self.do_restart, MessageBox, _("restart_title"), MessageBox.TYPE_YESNO)

    def do_restart(self, answer):
        if answer: from enigma import quitMainloop; quitMainloop(3)

    def start_mapping(self):
        self.save_settings()
        self["status"].setText(_("mapping_start"))
        threading.Thread(target=self.thread_mapping, daemon=True).start()

    def thread_mapping(self):
        try:
            url = self.worker.get_url()
            ext = ".xml.gz" if ".gz" in url else ".xml"
            temp_path = "/tmp/epg_temp" + ext
            
            if not download_file(url, temp_path, retries=3, timeout=600):
                reactor.callFromThread(self.gui_update_log, "Download FAIL")
                return

            mapper = AutoMapper(log_callback=lambda msg: reactor.callFromThread(self.gui_update_log, msg))
            
            def progress_cb(current, total):
                reactor.callFromThread(self.animate_percent, "Map", current, total)

            mapping = mapper.generate_mapping(temp_path, progress_callback=progress_cb, exclude_refs=set())
            save_json(mapping, config.plugins.SimpleIPTV_EPG.mapping_file.value)
            
            reactor.callFromThread(self.gui_update_log, _("mapping_success").format(len(mapping)))
        except Exception as e:
            reactor.callFromThread(self.gui_update_log, f"ERROR: {e}")

    def check_github_update(self):
        self.log(_("check_update"))
        version_url = GITHUB_BASE_URL + "version"
        getPage(str.encode(version_url)).addCallback(self.github_callback).addErrback(self.github_error)

    def github_callback(self, data):
        try:
            remote_version = data.decode('utf-8').strip()
            local_version = PLUGIN_VERSION
            if remote_version > local_version:
                self.log(f"New version found: {remote_version}")
                # Używamy callFromThread na wszelki wypadek, jeśli callback przychodzi z innego wątku
                reactor.callFromThread(self.session.openWithCallback, self.perform_update_question, MessageBox, _("update_avail").format(remote_version), MessageBox.TYPE_YESNO)
            elif remote_version == local_version:
                self.log(_("update_ok"))
                reactor.callFromThread(self.session.open, MessageBox, _("update_ok") + f"\n(v{local_version})", MessageBox.TYPE_INFO)
            else:
                self.session.open(MessageBox, f"Dev/Test Version.\nGitHub: {remote_version} | Local: {local_version}", MessageBox.TYPE_INFO)
        except: pass

    def github_error(self, error): 
        reactor.callFromThread(self.session.open, MessageBox, "GitHub Error: " + str(error), MessageBox.TYPE_ERROR)

    def perform_update_question(self, answer):
        if answer:
            self["status"].setText(_("update_start"))
            threading.Thread(target=self.thread_perform_update, daemon=True).start()

    def thread_perform_update(self):
        FILES = ["plugin.py", "epgcore.py", "automapper.py", "version"]
        success = True
        plugin_path = os.path.dirname(__file__)
        try:
            for fname in FILES:
                url = GITHUB_BASE_URL + fname
                target_tmp = f"/tmp/{fname}"
                target_final = os.path.join(plugin_path, fname)
                if download_file(url, target_tmp, retries=2, timeout=10):
                    shutil.move(target_tmp, target_final)
                    reactor.callFromThread(self.gui_update_log, f"Updated: {fname}")
                else:
                    success = False; break
            if success: reactor.callFromThread(self.session.openWithCallback, self.do_restart, MessageBox, _("update_done"), MessageBox.TYPE_YESNO)
            else: reactor.callFromThread(self.session.open, MessageBox, _("update_fail"), MessageBox.TYPE_ERROR)
        except Exception as e:
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
        PluginDescriptor(name="Simple IPTV EPG", description="International EPG Importer (Fast)", where=PluginDescriptor.WHERE_PLUGINMENU, icon="plugin.png", fnc=main),
        PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=StartSession)
    ]
