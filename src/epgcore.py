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
    try:
        with open(filepath, 'rb') as f:
            return f.read(2) == b'\x1f\x8b'
    except: return False

# --- ZMODYFIKOWANA FUNKCJA DOWNLOAD ---
def download_file(url, target_path, retries=3):
    print(f"[EPG Core] Cel: {target_path} Z: {url}")
    
    # Cleanup przed pobraniem
    if os.path.exists(target_path):
        try: os.remove(target_path)
        except: pass

    # Pętla prób
    for attempt in range(retries):
        if attempt > 0:
            print(f"[EPG Core] Ponawiam próbę {attempt+1}/{retries}...")
            time.sleep(2) # Odczekaj chwilę

        success = False
        
        # Metoda 1: CURL
        try:
            cmd = f"curl -k -L -m 120 -A 'Mozilla/5.0' -o '{target_path}' '{url}'"
            if os.system(cmd) == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                if check_gzip_integrity(target_path): success = True
        except: pass

        # Metoda 2: WGET (jeśli CURL zawiódł)
        if not success:
            try:
                if os.path.exists(target_path): os.remove(target_path)
                cmd = f"wget --no-check-certificate --timeout=120 -O '{target_path}' '{url}'"
                os.system(cmd)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                    if check_gzip_integrity(target_path): success = True
            except: pass
            
        # Metoda 3: Python (jeśli oba zawiodły)
        if not success:
            try:
                if os.path.exists(target_path): os.remove(target_path)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, context=ctx, timeout=120) as r, open(target_path, 'wb') as f:
                    shutil.copyfileobj(r, f)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                     if check_gzip_integrity(target_path): success = True
            except: pass

        if success:
            print("[EPG Core] Sukces!")
            return True
            
    print("[EPG Core] Błąd pobierania po wszystkich próbach.")
    return False

class EPGParser:
    def __init__(self, source_path):
        self.source_path = source_path

    def parse_timestamp(self, xmltv_date):
        try:
            if not xmltv_date: return 0
            return int(datetime.datetime.strptime(xmltv_date[:14], "%Y%m%d%H%M%S").timestamp())
        except: return 0

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
                                service_refs = channel_map[channel_id]
                                start = self.parse_timestamp(elem.get('start'))
                                stop = self.parse_timestamp(elem.get('stop'))
                                if start > 0 and stop > start:
                                    duration = stop - start
                                    title = ""
                                    desc = ""
                                    for child in elem:
                                        if child.tag == 'title': title = child.text
                                        elif child.tag == 'desc': desc = child.text
                                    
                                    if not title: title = "No Title"
                                    # Limit E2 description size
                                    if desc and len(desc) > 1000: desc = desc[:1000] + "..."
                                    
                                    event_tuple = (int(start), int(duration), str(title), str(desc))
                                    for ref in service_refs:
                                        yield ref, event_tuple
                        except: pass
                        elem.clear()
                    elif elem.tag == 'tv': elem.clear()
        except: pass

class EPGInjector:
    def __init__(self):
        self.epg_cache = eEPGCache.getInstance()
        self.events_buffer = {} 

    def add_event(self, service_ref, event_data):
        if service_ref not in self.events_buffer: self.events_buffer[service_ref] = []
        start, duration, title, desc = event_data
        # E2 format: (start, duration, title, short_desc, long_desc, type)
        self.events_buffer[service_ref].append((start, duration, title[:240], "", desc, 0))

    def commit(self):
        for service_ref, events in self.events_buffer.items():
            try: self.epg_cache.importEvents(str(service_ref), events)
            except: pass
        self.events_buffer.clear()
