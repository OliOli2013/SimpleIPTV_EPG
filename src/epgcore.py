import xml.etree.cElementTree as ET
import gzip
import datetime
import time
import urllib.request
import urllib.error
import shutil
import ssl
import os
import subprocess
from enigma import eEPGCache

def check_gzip_integrity(filepath):
    """Sprawdza czy plik to poprawne archiwum GZIP (Magic Bytes)."""
    try:
        with open(filepath, 'rb') as f:
            # GZIP musi zaczynać się od 1f 8b
            return f.read(2) == b'\x1f\x8b'
    except:
        return False

def download_file(url, target_path):
    print(f"[EPG Core] Cel: {target_path} Z: {url}")
    
    # Usuwamy stary plik dla pewności
    if os.path.exists(target_path):
        try: os.remove(target_path)
        except: pass

    success = False

    # --- METODA 1: CURL (Najpotężniejsza) ---
    print(f"[EPG Core] Próba 1: CURL...")
    try:
        # -k (insecure), -L (follow redirects), -m 120 (max time), -A (UserAgent)
        cmd = f"curl -k -L -m 120 -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' -o '{target_path}' '{url}'"
        result = os.system(cmd)
        
        if result == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
            if check_gzip_integrity(target_path):
                print("[EPG Core] CURL: Sukces!")
                return True
            else:
                print("[EPG Core] CURL: Pobrany plik nie jest GZIPem!")
    except Exception as e:
        print(f"[EPG Core] Błąd CURL: {e}")

    # --- METODA 2: WGET (Systemowy) ---
    print(f"[EPG Core] Próba 2: WGET...")
    try:
        if os.path.exists(target_path): os.remove(target_path)
        # --no-check-certificate, --timeout=120
        cmd = f"wget --no-check-certificate --timeout=120 --tries=2 -U 'Mozilla/5.0' -O '{target_path}' '{url}'"
        os.system(cmd)
        
        if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
            if check_gzip_integrity(target_path):
                print("[EPG Core] WGET: Sukces!")
                return True
    except Exception as e:
        print(f"[EPG Core] Błąd WGET: {e}")

    # --- METODA 3: Python URLLIB (Ostatnia deska) ---
    print(f"[EPG Core] Próba 3: Python URLLIB...")
    try:
        if os.path.exists(target_path): os.remove(target_path)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except: ctx = None
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=120) as response: # 120 sekund!
            with open(target_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
        
        if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
            if check_gzip_integrity(target_path):
                print("[EPG Core] URLLIB: Sukces!")
                return True
    except Exception as e:
        print(f"[EPG Core] Błąd URLLIB: {e}")

    return False

class EPGParser:
    def __init__(self, source_path):
        self.source_path = source_path

    def parse_timestamp(self, xmltv_date):
        try:
            if not xmltv_date: return 0
            return int(datetime.datetime.strptime(xmltv_date[:14], "%Y%m%d%H%M%S").timestamp())
        except: return 0

    def clean_text(self, text):
        if not text: return ""
        if isinstance(text, bytes): text = text.decode('utf-8', 'ignore')
        return str(text).strip()

    def load_events(self, channel_map):
        if not os.path.exists(self.source_path): return
        opener = gzip.open if self.source_path.endswith('.gz') else open
        
        try:
            with opener(self.source_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'programme':
                        try:
                            channel_id = elem.get('channel')
                            if channel_id in channel_map:
                                service_refs_list = channel_map[channel_id]
                                if isinstance(service_refs_list, str): service_refs_list = [service_refs_list]

                                start = self.parse_timestamp(elem.get('start'))
                                stop = self.parse_timestamp(elem.get('stop'))
                                if start > 0 and stop > start:
                                    duration = stop - start
                                    title = ""
                                    desc = ""
                                    for child in elem:
                                        if child.tag == 'title': title = self.clean_text(child.text)
                                        elif child.tag == 'desc': desc = self.clean_text(child.text)
                                    
                                    if not title: title = "Bez tytułu"
                                    event_tuple = (int(start), int(duration), title, desc)
                                    
                                    for ref in service_refs_list:
                                        yield ref, event_tuple
                        except: pass
                        elem.clear()
                    elif elem.tag == 'tv': elem.clear()
        except Exception as e: print(f"XML Error: {e}")

class EPGInjector:
    def __init__(self):
        self.epg_cache = eEPGCache.getInstance()
        self.events_buffer = {} 

    def add_event(self, service_ref, event_data):
        if service_ref not in self.events_buffer: self.events_buffer[service_ref] = []
        start, duration, title, desc = event_data
        self.events_buffer[service_ref].append((start, duration, title[:254], "", desc, 0))

    def commit(self):
        for service_ref, events in self.events_buffer.items():
            try: self.epg_cache.importEvents(str(service_ref), events)
            except: pass
        self.events_buffer.clear()
