import xml.etree.cElementTree as ET
import gzip
import datetime
import time
import urllib.request
import urllib.error
import shutil
import ssl
import os
import subprocess # [UPDATE] Do bezpiecznego wywołania curl/wget
from enigma import eEPGCache
from .automapper import _load_services_cached

# --- MAPA SAT FALLBACK ---
SAT_FALLBACK_MAP = {
    "TVP 1 HD": "1:0:19:3ABD:13F0:13E:820000:0:0:0:", 
    "TVP 2 HD": "1:0:19:3ABE:13F0:13E:820000:0:0:0:",
    "POLSAT HD": "1:0:19:332D:3390:71:820000:0:0:0:",
    "TVN HD": "1:0:19:3DCD:640:13E:820000:0:0:0:",
    "TVP INFO HD": "1:0:19:1234:5678:9ABC:0:0:0:0:",
    # Dodaj więcej według potrzeb
}

def check_gzip_integrity(filepath):
    try:
        with open(filepath, 'rb') as f:
            return f.read(2) == b'\x1f\x8b'
    except: return False

# [UPDATE] Funkcja download z użyciem subprocess i timeoutem
def download_file(url, target_path, retries=3, timeout=120):
    print(f"[EPG Core] Download: {url} -> {target_path}")
    if os.path.exists(target_path):
        try: os.remove(target_path)
        except: pass

    for attempt in range(retries):
        if attempt > 0: time.sleep(2)
        
        # Metoda 1: CURL (subprocess)
        try:
            # -m sets max time, -k allow insecure, -L follow redirects
            cmd = ["curl", "-k", "-L", "-m", str(timeout), "-A", "Mozilla/5.0", "-o", target_path, url]
            result = subprocess.run(cmd, capture_output=True, timeout=timeout+10)
            if result.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                if check_gzip_integrity(target_path): return True
        except Exception as e:
            print(f"[Download] Curl Error: {e}")

        # Metoda 2: Wget (subprocess)
        if not os.path.exists(target_path):
            try:
                cmd = ["wget", "--no-check-certificate", f"--timeout={timeout}", "-O", target_path, url]
                subprocess.run(cmd, capture_output=True, timeout=timeout+10)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                     if check_gzip_integrity(target_path): return True
            except: pass
            
        # Metoda 3: Python Native
        if not os.path.exists(target_path):
            try:
                ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r, open(target_path, 'wb') as f:
                    shutil.copyfileobj(r, f)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                     if check_gzip_integrity(target_path): return True
            except: pass

    return False

def get_sat_epg_events(sat_ref, start_ts, end_ts):
    cache = eEPGCache.getInstance()
    # Query: [ref, type=2(time), start, end]
    events = cache.lookupEvent([sat_ref, 2, start_ts, end_ts])
    out = []
    if events:
        for ev in events:
            # (start, duration, title, short_desc, long_desc...)
            start = ev[0]
            dur = ev[1]
            title = ev[2]
            desc = ev[3] if len(ev) > 3 else "" 
            out.append((start, dur, title, desc))
    return out

# [UPDATE] Batch processing dla SAT Fallback
def inject_sat_fallback(injector, injected_refs, log_cb=None):
    all_services = _load_services_cached('/etc/enigma2/')
    
    # 1. Znajdź brakujące kanały
    missing_epg = [s for s in all_services if s['full_ref'] not in injected_refs]
    if not missing_epg: return 0

    if log_cb: log_cb(f"Analiza SAT Fallback: {len(missing_epg)} kanałów bez EPG")

    # 2. Grupuj zapytania (SAT_REF -> Lista IPTV_REF)
    # Zamiast pytać enigmę dla każdego kanału IPTV, pytamy raz dla referencji SAT
    sat_batch_map = {}
    
    for s in missing_epg:
        name = s['name'].upper().strip()
        sat_ref = SAT_FALLBACK_MAP.get(name)
        if sat_ref:
            if sat_ref not in sat_batch_map:
                sat_batch_map[sat_ref] = []
            sat_batch_map[sat_ref].append(s['full_ref'])

    count_injected = 0
    now = int(time.time())
    end_time = now + (3 * 24 * 3600) # +3 dni

    # 3. Wykonaj zapytania Batch
    for sat_ref, iptv_refs in sat_batch_map.items():
        events = get_sat_epg_events(sat_ref, now, end_time)
        if events:
            # Aplikuj te same eventy do wszystkich zmapowanych kanałów IPTV
            for start, dur, title, desc in events:
                event_data = (start, dur, title, desc)
                for iptv_ref in iptv_refs:
                    injector.add_event(iptv_ref, event_data)
            
            added_count = len(iptv_refs)
            count_injected += added_count
            if log_cb: log_cb(f"[SAT] {sat_ref} -> {added_count} x IPTV")

    if count_injected > 0:
        injector.commit()
        
    return count_injected

class EPGParser:
    def __init__(self, source_path):
        self.source_path = source_path
        
    def parse_timestamp(self, xmltv_date):
        try: return int(datetime.datetime.strptime(xmltv_date[:14], "%Y%m%d%H%M%S").timestamp())
        except: return 0
        
    # [UPDATE] Dodane czyszczenie pamięci (elem.clear) i obsługa błędów
    def load_events(self, channel_map):
        if not os.path.exists(self.source_path): return
        opener = gzip.open if self.source_path.endswith('.gz') else open
        
        try:
            with opener(self.source_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'programme':
                        try:
                            chid = elem.get('channel')
                            if chid in channel_map:
                                refs = channel_map[chid]
                                start = self.parse_timestamp(elem.get('start'))
                                stop = self.parse_timestamp(elem.get('stop'))
                                if start > 0 and stop > start:
                                    dur = stop - start
                                    title = ""; desc = ""
                                    for child in elem:
                                        if child.tag == 'title': title = child.text
                                        elif child.tag == 'desc': desc = child.text
                                    
                                    # [Optimization] Skracanie tekstów, żeby nie zapchać RAM/Cache
                                    event_tuple = (int(start), int(dur), str(title or "No Title")[:240], str(desc or "")[:1024])
                                    for r in refs: yield r, event_tuple
                        except: pass
                        finally:
                            elem.clear() # [CRITICAL] Zwolnij pamięć po elemencie
                    elif elem.tag == 'tv': 
                        elem.clear()
        except Exception as e:
            print(f"[EPGParser] Error: {e}")

class EPGInjector:
    def __init__(self):
        self.epg_cache = eEPGCache.getInstance()
        self.events_buffer = {} 

    def add_event(self, service_ref, event_data):
        if service_ref not in self.events_buffer: self.events_buffer[service_ref] = []
        start, duration, title, desc = event_data
        # E2 import format: (start, duration, title, short_desc, long_desc, type)
        self.events_buffer[service_ref].append((start, duration, title, "", desc, 0))

    def commit(self):
        if not self.events_buffer: return
        for service_ref, events in self.events_buffer.items():
            try: self.epg_cache.importEvents(str(service_ref), events)
            except: pass
        self.events_buffer.clear()
