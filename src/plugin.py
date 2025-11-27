from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, ConfigSubsection, ConfigText, ConfigSelection, getConfigListEntry
from Components.ScrollLabel import ScrollLabel
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Components.Language import language
import threading
import os
import json
from datetime import datetime
from twisted.internet import reactor

# Importy lokalne
from .epgcore import EPGParser, EPGInjector, download_file
from .automapper import AutoMapper

# --- STAN GLOBALNY (PAMIĘĆ W TLE) ---
class GlobalState:
    is_running = False
    current_task = ""
    log_buffer = []
    
    @staticmethod
    def add_log(msg):
        t = datetime.now().strftime("%H:%M:%S")
        line = f"[{t}] {msg}"
        GlobalState.log_buffer.append(line)
        # Trzymaj tylko ostatnie 50 linii w pamięci RAM
        if len(GlobalState.log_buffer) > 50:
            GlobalState.log_buffer.pop(0)
        
        # Zapis do pliku
        try:
            with open("/tmp/simple_epg.log", "a") as f:
                f.write(line + "\n")
        except: pass

# --- TŁUMACZENIA ---
def get_lang():
    try:
        lang = language.getLanguage()
        return "pl" if "pl" in lang.lower() else "en"
    except: return "en"

lang_code = get_lang()

TR = {
    "header": {"pl": "Simple IPTV EPG v1.0", "en": "Simple IPTV EPG v1.0"},
    "support_text": {"pl": "Wesprzyj rozwój wtyczki (Buy Coffee)", "en": "Support development"},
    "source_label": {"pl": "Wybierz Źródło:", "en": "Select Source:"},
    "btn_exit": {"pl": "Wyjdź", "en": "Exit"},
    "btn_import": {"pl": "Importuj", "en": "Import"},
    "btn_map": {"pl": "Mapuj", "en": "Map"},
    "btn_bg": {"pl": "Ukryj (W tle)", "en": "Hide (Background)"},
    "status_ready": {"pl": "Gotowy. Wybierz opcję.", "en": "Ready."},
    "status_running": {"pl": "PROCES TRWA W TLE...", "en": "RUNNING IN BACKGROUND..."},
    "task_finished": {"pl": "Pobieranie zakończone! Zrestartować GUI?", "en": "Finished! Restart GUI?"},
    "bg_info": {"pl": "Wtyczka pracuje w tle. Możesz tu wrócić w każdej chwili.", "en": "Running in background. You can return here anytime."}
}

def _(key): return TR[key].get(lang_code, TR[key]["en"]) if key in TR else key

# --- KONFIGURACJA ---
config.plugins.SimpleIPTV_EPG = ConfigSubsection()

EPG_SOURCES = [
    ("https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", "EPG Share PL (Polecane)"),
    ("https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz", "EPG Share ALL (Świat)"),
    ("https://iptv-epg.org/files/epg-pl.xml.gz", "IPTV-EPG.org"),
    ("https://epg.ovh/pl.gz", "EPG OVH"),
    ("CUSTOM", "--- Własny Adres ---")
]

config.plugins.SimpleIPTV_EPG.source_select = ConfigSelection(default="https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", choices=EPG_SOURCES)
config.plugins.SimpleIPTV_EPG.custom_url = ConfigText(default="http://", fixed_size=False, visible_width=80)
config.plugins.SimpleIPTV_EPG.mapping_file = ConfigText(default="/etc/enigma2/iptv_mapping.json", fixed_size=False)

def load_json(path):
    try:
        with open(path, 'r') as f: return json.load(f)
    except: return {}

def save_json(data, path):
    try:
        with open(path, 'w') as f: json.dump(data, f, indent=4)
    except: pass

class IPTV_EPG_Config(ConfigListScreen, Screen):
    skin = """
        <screen name="IPTV_EPG_Config" position="center,center" size="900,650" title="Simple IPTV EPG v1.0">
            <widget name="qrcode" position="20,10" size="130,130" transparent="1" alphatest="on" />
            <widget name="support_text" position="160,40" size="600,30" font="Regular;24" foregroundColor="#00ff00" transparent="1" />
            <widget name="author_info" position="160,80" size="600,25" font="Regular;18" foregroundColor="#aaaaaa" transparent="1" />
            
            <widget name="header_title" position="20,150" size="860,50" font="Regular;34" halign="center" valign="center" foregroundColor="#fcc400" backgroundColor="#202020" transparent="1" />
            
            <widget name="config" position="20,210" size="860,120" font="Regular;22" itemHeight="35" scrollbarMode="showOnDemand" />
            
            <widget name="label_status" position="20,370" size="860,30" font="Regular;22" foregroundColor="#00aaff" />
            <widget name="status" position="20,405" size="860,180" font="Regular;18" foregroundColor="#dddddd" backgroundColor="#101010" />
            
            <eLabel position="20,600" size="860,2" backgroundColor="#555555" />

            <ePixmap pixmap="skin_default/buttons/red.png" position="30,610" size="30,40" alphatest="on" />
            <widget name="key_red" position="65,610" zPosition="1" size="150,40" font="Regular;20" valign="center" transparent="1" />
            <ePixmap pixmap="skin_default/buttons/green.png" position="240,610" size="30,40" alphatest="on" />
            <widget name="key_green" position="275,610" zPosition="1" size="180,40" font="Regular;20" valign="center" transparent="1" />
            <ePixmap pixmap="skin_default/buttons/yellow.png" position="480,610" size="30,40" alphatest="on" />
            <widget name="key_yellow" position="515,610" zPosition="1" size="150,40" font="Regular;20" valign="center" transparent="1" />
            <ePixmap pixmap="skin_default/buttons/blue.png" position="690,610" size="30,40" alphatest="on" />
            <widget name="key_blue" position="725,610" zPosition="1" size="160,40" font="Regular;20" valign="center" transparent="1" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self["header_title"] = Label(_("header"))
        self["qrcode"] = Pixmap()
        self["support_text"] = Label(_("support_text"))
        self["author_info"] = Label("v1.0 | by Pawel Pawełek | msisystem@t.pl")
        
        self["key_red"] = Label(_("btn_exit"))
        self["key_green"] = Label(_("btn_import"))
        self["key_yellow"] = Label(_("btn_map"))
        self["key_blue"] = Label(_("btn_bg"))
        
        self["label_status"] = Label("Log:")
        self["status"] = ScrollLabel(_("status_ready"))
        
        self.list = []
        self.buildConfigList()
        ConfigListScreen.__init__(self, self.list)
        
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], {
            "red": self.close,
            "green": self.start_import,
            "yellow": self.start_mapping,
            "blue": self.hide_background, # Niebieski = Ukryj
            "cancel": self.close,
            "save": self.start_import,
            "left": self.keyLeft, "right": self.keyRight
        }, -2)
        
        self.onLayoutFinish.append(self.load_qr_code)
        
        # TIMER DO ODŚWIEŻANIA GUI
        self.timer = threading.Timer(1.0, self.refresh_log)
        
        # Jeśli wtyczka już działała w tle, odzyskaj stan!
        if GlobalState.is_running:
            self["status"].setText("\n".join(GlobalState.log_buffer))
            self["status"].lastPage()
            self.refresh_log() # Uruchom odświeżanie

    def load_qr_code(self):
        try:
            plugin_path = os.path.dirname(__file__)
            qr_path = os.path.join(plugin_path, "Kod_QR_buycoffee.png")
            if os.path.exists(qr_path): self["qrcode"].instance.setPixmapFromFile(qr_path)
        except: pass

    def buildConfigList(self):
        self.list = []
        self.list.append(getConfigListEntry(_("source_label"), config.plugins.SimpleIPTV_EPG.source_select))
        if config.plugins.SimpleIPTV_EPG.source_select.value == "CUSTOM":
            self.list.append(getConfigListEntry("   URL:", config.plugins.SimpleIPTV_EPG.custom_url))
        self.list.append(getConfigListEntry("Map:", config.plugins.SimpleIPTV_EPG.mapping_file))
        self["config"].setList(self.list)

    def keyLeft(self): ConfigListScreen.keyLeft(self); self.updateConfigList()
    def keyRight(self): ConfigListScreen.keyRight(self); self.updateConfigList()
    def updateConfigList(self): self.buildConfigList(); self["config"].setList(self.list)

    # --- LOGOWANIE ---
    def refresh_log(self):
        """Funkcja wywoływana cyklicznie, aby pobrać logi z GlobalState"""
        if GlobalState.is_running:
            try:
                # Pobierz ostatnie wpisy z bufora
                text = "\n".join(GlobalState.log_buffer)
                self["status"].setText(text)
                self["status"].lastPage()
                # Zaplanuj kolejne odświeżenie za 1s
                reactor.callLater(1, self.refresh_log)
            except: pass

    def log(self, message):
        """Loguje do stanu globalnego (widoczne w GUI i pliku)"""
        GlobalState.add_log(message)

    def ask_restart(self):
        self.session.openWithCallback(self.do_restart, MessageBox, _("task_finished"), MessageBox.TYPE_YESNO)

    def do_restart(self, answer):
        if answer:
            from enigma import quitMainloop
            quitMainloop(3)

    # --- AKCJE ---
    def hide_background(self):
        """Ukrywa wtyczkę, ale proces trwa."""
        if GlobalState.is_running:
            self.session.open(MessageBox, _("bg_info"), MessageBox.TYPE_INFO, timeout=3)
            self.close() # Zamykamy okno, wątek trwa w GlobalState
        else:
            # Jeśli nic nie robimy, to po prostu zamknij
            self.close()

    def start_import(self):
        if GlobalState.is_running:
            self.log("Proces już trwa!")
            return
        
        GlobalState.is_running = True
        GlobalState.log_buffer = [] # Czyść log
        config.plugins.SimpleIPTV_EPG.save()
        
        self.log("--- START IMPORTU ---")
        self.refresh_log() # Start odświeżania GUI
        
        t = threading.Thread(target=self.worker_import)
        t.start()

    def start_mapping(self):
        if GlobalState.is_running:
            self.log("Proces już trwa!")
            return

        GlobalState.is_running = True
        GlobalState.log_buffer = []
        config.plugins.SimpleIPTV_EPG.save()
        
        self.log("--- START MAPOWANIA ---")
        self.refresh_log()
        
        t = threading.Thread(target=self.worker_mapping)
        t.start()

    # --- WORKERY (WĄTKI) ---
    def _get_url(self):
        val = config.plugins.SimpleIPTV_EPG.source_select.value
        return config.plugins.SimpleIPTV_EPG.custom_url.value if val == "CUSTOM" else val

    def worker_import(self):
        try:
            url = self._get_url()
            xml_file = "/tmp/epg_temp.xml.gz"
            
            self.log(f"Pobieranie: {url}")
            if not download_file(url, xml_file):
                self.log("BŁĄD POBIERANIA!")
                GlobalState.is_running = False
                return

            mapping = load_json(config.plugins.SimpleIPTV_EPG.mapping_file.value)
            if not mapping:
                self.log("BRAK MAPY! Użyj Żółtego.")
                GlobalState.is_running = False
                return

            self.log(f"Start importu ({len(mapping)} kanałów)...")
            parser = EPGParser(xml_file)
            injector = EPGInjector()
            
            count = 0
            batch = 0
            
            for ref, data in parser.load_events(mapping):
                injector.add_event(ref, data)
                count += 1
                batch += 1
                if batch >= 100:
                    injector.commit()
                    batch = 0
                    if count % 200 == 0: # Częstsze logowanie!
                        self.log(f"Wstrzyknięto {count}...")
            
            injector.commit()
            self.log(f"GOTOWE! Łącznie {count}.")
            reactor.callFromThread(self.ask_restart)
            
        except Exception as e:
            self.log(f"ERROR: {e}")
        
        GlobalState.is_running = False

    def worker_mapping(self):
        try:
            url = self._get_url()
            xml_file = "/tmp/epg_temp.xml.gz"
            
            self.log(f"Pobieranie...")
            if not download_file(url, xml_file):
                self.log("BŁĄD POBIERANIA!")
                GlobalState.is_running = False
                return
            
            self.log("Analiza EPG...")
            # Przekazujemy funkcję logującą
            mapper = AutoMapper(log_callback=GlobalState.add_log)
            new_map = mapper.generate_mapping(xml_file)
            
            save_json(new_map, config.plugins.SimpleIPTV_EPG.mapping_file.value)
            self.log(f"Zapisano mapę: {len(new_map)} kanałów.")
            self.log("Teraz naciśnij ZIELONY.")
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            
        GlobalState.is_running = False

def main(session, **kwargs): session.open(IPTV_EPG_Config)
def Plugins(**kwargs):
    return [PluginDescriptor(name="Simple IPTV EPG v1.0", description="Importer EPG", where=PluginDescriptor.WHERE_PLUGINMENU, icon="plugin.png", fnc=main)]
