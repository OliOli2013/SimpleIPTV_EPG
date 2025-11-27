import xml.etree.cElementTree as ET
import gzip
import datetime
import time
import urllib.request
import urllib.error
import shutil
import ssl
import os
from enigma import eEPGCache
from .automapper import _load_services_cached

# --- MAPA SAT FALLBACK ---
# Format: "NAZWA KANAŁU": "SERVICE_REF_SAT"
# Możesz tu wpisać kluczowe kanały, których brakuje w XML
SAT_FALLBACK_MAP = {
    # Przykłady (Należy podać prawdziwe referencje z HotBird/Astra)
    "TVP 1 HD": "1:0:19:3ABD:13F0:13E:820000:0:0:0:", 
    "TVP 2 HD": "1:0:19:3ABE:13F0:13E:820000:0:0:0:",
    "POLSAT HD": "1:0:19:332D:3390:71:820000:0:0:0:",
    "TVN HD": "1:0:19:3DCD:640:13E:820000:0:0:0:",
    "TVP INFO HD": "1:0:19:1234:5678:9ABC:0:0:0:0:", # Przykładowy dummy
}

def check_gzip_integrity(filepath):
    try:
        with open(filepath, 'rb') as f:
            return f.read(2) == b'\x1f\x8b'
    except: return False

def download_file(url, target_path, retries=3):
    print(f"[EPG Core] Cel: {target_path} Z: {url}")
    if os.path.exists(target_path):
        try: os.remove(target_path)
        except: pass

    for attempt in range(retries):
        if attempt > 0: time.sleep(2)
        success = False
        try:
            cmd = f"curl -k -L -m 120 -A 'Mozilla/5.0' -o '{target_path}' '{url}'"
            if os.system(cmd) == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                if check_gzip_integrity(target_path): success = True
        except: pass

        if not success:
            try:
                if os.path.exists(target_path): os.remove(target_path)
                cmd = f"wget --no-check-certificate --timeout=120 -O '{target_path}' '{url}'"
                os.system(cmd)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                     if check_gzip_integrity(target_path): success = True
            except: pass
            
        if not success:
            try:
                if os.path.exists(target_path): os.remove(target_path)
                ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, context=ctx, timeout=120) as r, open(target_path, 'wb') as f:
                    shutil.copyfileobj(r, f)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                     if check_gzip_integrity(target_path): success = True
            except: pass

        if success: return True
    return False

# --- POBIERANIE DANYCH Z SATELITY ---
def get_sat_epg_events(sat_ref, start_ts, end_ts):
    """Pobiera zdarzenia z cache Enigmy dla danego SAT Refa"""
    cache = eEPGCache.getInstance()
    # Query: [ref, type=2(time), start, end]
    events = cache.lookupEvent([sat_ref, 2, start_ts, end_ts])
    out = []
    if events:
        for ev in events:
            # Format: (start, duration, title, short_desc, long_desc)
            # lookupEvent zwraca różne pola zależnie od wersji Enigmy, zazwyczaj:
            # (start, duration, title, short_desc, ?, ?, ...)
            # Bezpiecznie bierzemy 0,1,2,3(lub 4)
            start = ev[0]
            dur = ev[1]
            title = ev[2]
            # Czasem opis jest w index 3 lub 4
            desc = ev[3] if len(ev) > 3 else "" 
            out.append((start, dur, title, desc))
    return out

def inject_sat_fallback(injector, injected_refs, log_cb=None):
    """
    Sprawdza, które kanały IPTV nie dostały EPG z XML
    i próbuje pobrać je z SAT_FALLBACK_MAP.
    """
    # 1. Pobierz wszystkie kanały z bukietów
    all_services = _load_services_cached('/etc/enigma2/')
    
    missing_epg = []
    ref_to_name = {}
    
    for s in all_services:
        ref = s['full_ref']
        name = s['name'].upper().strip()
        ref_to_name[ref] = name
        
        if ref not in injected_refs:
            missing_epg.append(ref)

    if not missing_epg:
        return 0

    if log_cb: log_cb(f"Sprawdzanie SAT Fallback dla {len(missing_epg)} kanałów...")

    count_injected = 0
    now = int(time.time())
    end_time = now + (3 * 24 * 3600) # +3 dni

    for iptv_ref in missing_epg:
        name = ref_to_name.get(iptv_ref, "")
        if not name: continue
        
        # Sprawdź czy mamy mapowanie dla tej nazwy
        # Można tu dodać logikę fuzzy match, ale na razie simple dict
        sat_ref = SAT_FALLBACK_MAP.get(name)
        
        if sat_ref:
            events = get_sat_epg_events(sat_ref, now, end_time)
            if events:
                for start, dur, title, desc in events:
                    injector.add_event(iptv_ref, (start, dur, title, desc))
                count_injected += 1
                if log_cb: log_cb(f"[SAT MATCH] {name} -> {len(events)} events")

    if count_injected > 0:
        injector.commit()
        
    return count_injected

class EPGParser:
    def __init__(self, source_path):
        self.source_path = source_path
    def parse_timestamp(self, xmltv_date):
        try: return int(datetime.datetime.strptime(xmltv_date[:14], "%Y%m%d%H%M%S").timestamp())
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
                                    event_tuple = (int(start), int(dur), str(title or "No Title"), str(desc or ""))
                                    for r in refs: yield r, event_tuple
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
        self.events_buffer[service_ref].append((start, duration, title[:240], "", desc, 0))

    def commit(self):
        for service_ref, events in self.events_buffer.items():
            try: self.epg_cache.importEvents(str(service_ref), events)
            except: pass
        self.events_buffer.clear()
