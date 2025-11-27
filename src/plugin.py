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

# --- SYSTEM TŁUMACZEŃ ---
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
    "custom_label": {"pl": "   >> Wpisz adres URL:", "en": "   >> Enter URL:"},
    "map_file_label": {"pl": "Plik mapowania:", "en": "Mapping File:"},
    "btn_exit": {"pl": "Wyjdź", "en": "Exit"},
    "btn_import": {"pl": "Importuj", "en": "Import"},
    "btn_map": {"pl": "Mapuj", "en": "Map"},
    "btn_bg": {"pl": "Pobierz w tle", "en": "Background"},
    "status_ready": {
        "pl": "Gotowy. Wybierz źródło i wciśnij MAPUJ.\nZielony = Podgląd | Niebieski = W tle",
        "en": "Ready. Select source and press MAP.\nGreen = View Log | Blue = Background"
    },
    "help_text": {"pl": "Lewo/Prawo - zmiana źródła", "en": "Left/Right - change source"},
    "downloading": {"pl": "Pobieranie pliku (Czekaj...)...", "en": "Downloading file..."},
    "download_ok": {"pl": "Pobieranie zakończone.", "en": "Download finished."},
    "download_fail": {"pl": "BŁĄD POBIERANIA! Sprawdź adres.", "en": "DOWNLOAD ERROR! Check URL."},
    "no_map": {"pl": "BRAK MAPOWANIA! Najpierw użyj żółtego.", "en": "NO MAPPING! Use Yellow first."},
    "import_start": {"pl": "Start importu ({} grup)...", "en": "Starting import ({} groups)..."},
    "injected": {"pl": "Przetworzono {} zdarzeń...", "en": "Processed {} events..."},
    "success": {"pl": "SUKCES! Łącznie {} zdarzeń.", "en": "SUCCESS! Total {} events."},
    "restart_title": {
        "pl": "Pobieranie EPG zakończone sukcesem!\nCzy chcesz zrestartować GUI teraz?",
        "en": "EPG Download successful!\nDo you want to restart GUI now?"
    },
    "bg_started": {
        "pl": "Uruchomiono w tle.\nMożesz oglądać TV. Wróć tu, aby sprawdzić postęp.",
        "en": "Background task started.\nYou can watch TV. Return here to check progress."
    },
    "mapping_start": {"pl": "Analiza pliku i parowanie...", "en": "Analyzing file and mapping..."},
    "mapping_success": {"pl": "SUKCES: Połączono {} kanałów!", "en": "SUCCESS: Mapped {} channels!"},
    "press_green": {"pl": "Teraz naciśnij ZIELONY lub NIEBIESKI.", "en": "Now press GREEN or BLUE."}
}

def _(key): return TR[key].get(lang_code, TR[key]["en"]) if key in TR else key

# --- KONFIGURACJA ---
config.plugins.SimpleIPTV_EPG = ConfigSubsection()

# NOWA CZYSTA LISTA ŹRÓDEŁ
EPG_SOURCES = [
    ("https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", "EPG Share PL (Polska - Polecane)"),
    ("https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz", "EPG Share ALL (Cały Świat - Duży!)"),
    ("https://iptv-epg.org/files/epg-pl.xml.gz", "IPTV-EPG.org (Polska)"),
    ("https://epg.ovh/pl.xml", "EPG.ovh (Polska XML)"),
    ("https://epg.one/pl.xml", "EPG.one (Polska XML)"),
    ("https://iptv-org.github.io/epg/guides/pl.xml", "IPTV-Org Polska (XML)"),
    ("https://iptv-org.github.io/epg/guides/us.xml", "IPTV-Org USA"),
    ("https://iptv-org.github.io/epg/guides/uk.xml", "IPTV-Org UK"),
    ("https://iptv-org.github.io/epg/guides/de.xml", "IPTV-Org Niemcy"),
    ("https://iptv-org.github.io/epg/guides/es.xml", "IPTV-Org Hiszpania"),
    ("https://iptv-org.github.io/epg/guides/fr.xml", "IPTV-Org Francja"),
    ("CUSTOM", "--- Własny Adres URL ---")
]

config.plugins.SimpleIPTV_EPG.source_select = ConfigSelection(default="https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz", choices=EPG_SOURCES)
config.plugins.SimpleIPTV_EPG.custom_url = ConfigText(default="http://", fixed_size=False, visible_width=80)
config.plugins.SimpleIPTV_EPG.mapping_file = ConfigText(default="/etc/enigma2/iptv_mapping.json", fixed_size=False)

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

# --- STAN GLOBALNY (Pamięć procesu w tle) ---
class GlobalState:
    is_running = False
    log_buffer = []
    
    @staticmethod
    def add_log(msg):
        t = datetime.now().strftime("%H:%M:%S")
        line = f"[{t}] {msg}"
        GlobalState.log_buffer.append(line)
        # Trzymaj ostatnie 50 linii w pamięci dla GUI
        if len(GlobalState.log_buffer) > 50: GlobalState.log_buffer.pop(0)
        write_log(msg)

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
        self.buildConfigList(init_phase=True)
        
        ConfigListScreen.__init__(self, self.list)
        
        self["actions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], {
            "red": self.close,
            "green": self.start_import,
            "yellow": self.start_mapping,
            "blue": self.hide_background,
            "cancel": self.close,
            "save": self.start_import,
            "left": self.keyLeft,
            "right": self.keyRight
        }, -2)
        
        self.onLayoutFinish.append(self.load_qr_code)
        
        # Odzyskanie stanu po powrocie z tła
        if GlobalState.is_running:
            self.refresh_log()

    def load_qr_code(self):
        try:
            plugin_path = os.path.dirname(__file__)
            qr_path = os.path.join(plugin_path, "Kod_QR_buycoffee.png")
            if os.path.exists(qr_path): self["qrcode"].instance.setPixmapFromFile(qr_path)
        except: pass

    def buildConfigList(self, init_phase=False):
        self.list = []
        self.list.append(getConfigListEntry(_("source_label"), config.plugins.SimpleIPTV_EPG.source_select))
        if config.plugins.SimpleIPTV_EPG.source_select.value == "CUSTOM":
            self.list.append(getConfigListEntry(_("custom_label"), config.plugins.SimpleIPTV_EPG.custom_url))
        self.list.append(getConfigListEntry(_("map_file_label"), config.plugins.SimpleIPTV_EPG.mapping_file))
        
        if not init_phase:
            self["config"].setList(self.list)

    def keyLeft(self): ConfigListScreen.keyLeft(self); self.buildConfigList()
    def keyRight(self): ConfigListScreen.keyRight(self); self.buildConfigList()

    def refresh_log(self):
        if GlobalState.is_running:
            try:
                text = "\n".join(GlobalState.log_buffer)
                self["status"].setText(text)
                self["status"].lastPage()
                # Odświeżanie co 1s jest wystarczające
                reactor.callLater(1, self.refresh_log)
            except: pass

    def log(self, message):
        GlobalState.add_log(message)

    def ask_restart(self):
        self.session.openWithCallback(self.do_restart, MessageBox, _("restart_title"), MessageBox.TYPE_YESNO)

    def do_restart(self, answer):
        if answer:
            from enigma import quitMainloop
            quitMainloop(3)

    def hide_background(self):
        """
        Jeśli proces działa -> ukryj.
        Jeśli nie działa -> uruchom import w tle.
        """
        if GlobalState.is_running:
            self.session.open(MessageBox, _("bg_started"), MessageBox.TYPE_INFO, timeout=3)
            self.close()
        else:
            self.start_import(background=True)

    def start_import(self, background=False):
        if GlobalState.is_running:
            # Jeśli już działa, a chcemy wejść w tło, to po prostu zamykamy
            if background:
                self.session.open(MessageBox, _("bg_started"), MessageBox.TYPE_INFO, timeout=3)
                self.close()
            return
        
        self.save_config_only()
        GlobalState.is_running = True
        GlobalState.log_buffer = []
        
        self.log("--- START IMPORTU ---")
        self.refresh_log()
        
        if background:
            self.session.open(MessageBox, _("bg_started"), MessageBox.TYPE_INFO, timeout=3)
            self.close()
        
        t = threading.Thread(target=self.worker_import)
        t.start()

    def start_mapping(self):
        if GlobalState.is_running: return
        self.save_config_only()
        GlobalState.is_running = True
        GlobalState.log_buffer = []
        self.log("--- START MAPOWANIA ---")
        self.refresh_log()
        t = threading.Thread(target=self.worker_mapping)
        t.start()

    def save_config_only(self):
        for x in self["config"].list: x[1].save()
        config.plugins.SimpleIPTV_EPG.save()

    def _get_url(self):
        val = config.plugins.SimpleIPTV_EPG.source_select.value
        return config.plugins.SimpleIPTV_EPG.custom_url.value if val == "CUSTOM" else val

    def worker_import(self):
        try:
            url = self._get_url()
            # Proste ustalanie rozszerzenia, żeby obsłużyć też .xml
            ext = ".xml"
            if ".gz" in url: ext = ".xml.gz"
            xml_file = "/tmp/epg_temp" + ext
            
            self.log(f"Pobieranie...")
            if not download_file(url, xml_file):
                self.log(_("download_fail"))
                GlobalState.is_running = False
                return

            mapping = load_json(config.plugins.SimpleIPTV_EPG.mapping_file.value)
            if not mapping:
                self.log(_("no_map"))
                GlobalState.is_running = False
                return

            self.log(_("import_start").format(len(mapping)))
            parser = EPGParser(xml_file)
            injector = EPGInjector()
            
            count = 0
            batch = 0
            for ref, data in parser.load_events(mapping):
                injector.add_event(ref, data)
                count += 1
                batch += 1
                
                if batch >= 2000:
                    injector.commit()
                    batch = 0
                    if count % 2000 == 0: self.log(_("injected").format(count))
            
            injector.commit()
            self.log(_("success").format(count))
            reactor.callFromThread(self.ask_restart)
            
        except Exception as e:
            self.log(f"ERROR: {e}")
        
        GlobalState.is_running = False

    def worker_mapping(self):
        try:
            url = self._get_url()
            ext = ".xml"
            if ".gz" in url: ext = ".xml.gz"
            xml_file = "/tmp/epg_temp" + ext
            
            self.log(f"Pobieranie...")
            if not download_file(url, xml_file):
                self.log(_("download_fail"))
                GlobalState.is_running = False
                return
            
            self.log(_("mapping_start"))
            mapper = AutoMapper(log_callback=GlobalState.add_log)
            new_map = mapper.generate_mapping(xml_file)
            save_json(new_map, config.plugins.SimpleIPTV_EPG.mapping_file.value)
            self.log(_("mapping_success").format(len(new_map)))
            self.log(_("press_green"))
        except Exception as e:
            self.log(f"ERROR: {e}")
        GlobalState.is_running = False

def main(session, **kwargs): session.open(IPTV_EPG_Config)
def Plugins(**kwargs):
    return [PluginDescriptor(name="Simple IPTV EPG v1.0", description="Importer EPG", where=PluginDescriptor.WHERE_PLUGINMENU, icon="plugin.png", fnc=main)]
