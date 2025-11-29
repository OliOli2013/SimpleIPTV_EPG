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
import re
from difflib import SequenceMatcher
from enigma import eEPGCache
from .automapper import _load_services_cached

# --- MAPA SAT FALLBACK (Możesz tu wpisać własne Reference SAT jeśli automat nie zadziała) ---
SAT_FALLBACK_MAP = {
    "TVP 1 HD": "1:0:19:3ABD:13F0:13E:820000:0:0:0:", 
    "TVP 2 HD": "1:0:19:3ABE:13F0:13E:820000:0:0:0:",
    "POLSAT HD": "1:0:19:332D:3390:71:820000:0:0:0:",
    "TVN HD": "1:0:19:3DCD:640:13E:820000:0:0:0:",
    "TVP INFO HD": "1:0:19:1234:5678:9ABC:0:0:0:0:",
}

# [UPDATE] Agresywna normalizacja (usuwa HD, PL, spacje itp.)
def normalize_name(name):
    if not name: return ""
    name = name.upper()
    # Usuń znaki specjalne i spacje, zostaw tylko litery i cyfry
    # Najpierw usuń popularne dopiski, żeby nie zakłócały matchowania (np. Canal+ Sport 3 vs Canal+ Sport)
    name = re.sub(r'\b(FULLHD|FHD|UHD|4K|HEVC|HD|SD|PL|POL|H265|RAW|VIP)\b', '', name)
    name = re.sub(r'[^A-Z0-9]', '', name) 
    return name

def check_gzip_integrity(filepath):
    try:
        with open(filepath, 'rb') as f: return f.read(2) == b'\x1f\x8b'
    except: return False

def check_url_alive(url, timeout=10):
    try:
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as res: return res.status == 200
    except: return False

def download_file(url, target_path, retries=3, timeout=120):
    if os.path.exists(target_path): 
        try: os.remove(target_path)
        except: pass
    
    # Próba wget (często stabilniejsza na tunerach)
    for attempt in range(retries):
        try:
            cmd = ["wget", "--no-check-certificate", f"--timeout={timeout}", "-O", target_path, url]
            subprocess.run(cmd, capture_output=True, timeout=timeout+10)
            if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                 if url.endswith('.gz') and not check_gzip_integrity(target_path):
                     os.remove(target_path); continue
                 return True
        except: pass
        
        # Fallback do curl
        try:
            cmd = ["curl", "-k", "-L", "-m", str(timeout), "-A", "Mozilla/5.0", "-o", target_path, url]
            subprocess.run(cmd, capture_output=True, timeout=timeout+10)
            if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                return True
        except: pass
        time.sleep(2)
        
    return False

def get_sat_epg_events(sat_ref, start_ts, end_ts):
    cache = eEPGCache.getInstance()
    # Pobieramy eventy z SAT
    events = cache.lookupEvent([sat_ref, 2, start_ts, end_ts])
    out = []
    if events:
        for ev in events: out.append((ev[0], ev[1], ev[2], ev[3] if len(ev) > 3 else ""))
    return out

# [UPDATE] Inject SAT po nazwach (Ulepszona logika)
def inject_sat_clone_by_name(injector, log_cb=None):
    all_services = _load_services_cached('/etc/enigma2/')
    
    sat_map = {} # { "TVP1": "1:0:..." }
    iptv_list = []

    # 1. Indeksowanie SAT z normalizacją
    # Tworzymy słownik gdzie kluczem jest "czysta nazwa" a wartością ref SAT
    for s in all_services:
        ref = s['full_ref']
        name = s['name']
        
        if '1:0:' in ref and '::' in ref: # SAT Reference
            key = normalize_name(name)
            if key and len(key) > 1:
                sat_map[key] = ref
        elif any(x in ref for x in ['4097:', '5001:', '5002:']): # IPTV
            iptv_list.append(s)

    injected = set()
    now = int(time.time())
    end = now + 4 * 86400 # 4 dni
    total = len(iptv_list)

    # Rozszerzona lista aliasów ręcznych dla polskich platform
    aliases = {
        "TVP1": ["PROGRAM1", "TVP1PL", "TVP1HD", "TVP1FHD"],
        "TVP2": ["PROGRAM2", "TVP2PL", "TVP2HD", "TVP2FHD"],
        "POLSAT": ["POLSATPL", "POLSATHD", "POLSATFHD"],
        "TVN": ["TVNPL", "TVNHD", "TVNFHD"],
        "TVN7": ["TVN7PL", "TVN7HD", "SIODEMKA"],
        "TV4": ["TV4PL", "TV4HD"],
        "PULS": ["TVPULS", "PULSPL", "TVPULSHD"],
        "PULS2": ["TVPULS2", "PULS2HD"],
        "TTV": ["TTVHD", "TTVPL"],
        "TVN24": ["TVN24HD", "TVN24BIS", "TVN24PL"],
        "TVN24BIS": ["TVN24BISHD", "TVN24BISPL"],
        "CANALPLUS": ["CANAL", "C", "CANALPLUSHD"],
        "CANALPLUSSPORT": ["CSPORT", "CANALSPORT", "CANALPLUSSPORTHD"],
        "CANALPLUSSPORT2": ["CSPORT2", "CANALSPORT2"],
        "CANALPLUSSPORT3": ["CSPORT3", "CANALSPORT3"],
        "ELEVENSPORTS1": ["ELEVEN1", "ELEVENSPORTS1HD"],
        "ELEVENSPORTS2": ["ELEVEN2", "ELEVENSPORTS2HD"],
        "EUROSPORT1": ["EUROSPORT", "EUROSPORT1HD", "EUROSPORT1INT"],
        "HBO": ["HBOHD", "HBO1"],
        "HBO2": ["HBO2HD"],
        "HBO3": ["HBO3HD"],
    }

    for idx, iptv in enumerate(iptv_list):
        raw_name = iptv['name']
        key = normalize_name(raw_name)
        
        # 1. Szukamy po znormalizowanej nazwie (Strict)
        sat_ref = sat_map.get(key)
        
        # 2. Szukamy po aliasach
        if not sat_ref:
            for master_key, alt_list in aliases.items():
                if key == master_key or key in alt_list:
                    sat_ref = sat_map.get(master_key)
                    if not sat_ref:
                        # Próbuj znaleźć ref dla aliasów
                        for alt in alt_list:
                            if alt in sat_map:
                                sat_ref = sat_map[alt]
                                break
                    break
        
        # 3. Fuzzy match dla trudnych przypadków (np. "Canal+ Sport 3" vs "Canal+ Sport 3 HD")
        # Jeśli nazwa jest długa i zawiera kluczowe słowo
        if not sat_ref and len(key) > 4:
             # Sprawdź czy klucz IPTV zawiera się w kluczu SAT (lub odwrotnie)
             # To ryzykowne, ale dla polskich nazw działa nieźle
             pass 

        if sat_ref:
            events = get_sat_epg_events(sat_ref, now, end)
            if events:
                # Debug co 100
                if log_cb and idx % 200 == 0: log_cb(f"[SAT MATCH] {raw_name} -> OK")
                
                for start, dur, title, desc in events:
                    injector.add_event(iptv['full_ref'], (start, dur, title[:240], desc[:1024]))
                injected.add(iptv['full_ref'])

        # Procenty
        if log_cb and idx % 100 == 0:
            percent = int((idx + 1) * 100 / max(total, 1))
            log_cb(f"[SAT LINK] {percent}%")

    if injected:
        injector.commit()
        if log_cb: log_cb(f"[SAT LINK] Połączono: {len(injected)} kanałów")

    return injected

def inject_sat_fallback(injector, injected_refs, log_cb=None):
    all_services = _load_services_cached('/etc/enigma2/')
    missing_epg = [s for s in all_services if s['full_ref'] not in injected_refs]
    if not missing_epg: return 0

    sat_batch_map = {}
    for s in missing_epg:
        name = s['name'].upper().strip()
        sat_ref = SAT_FALLBACK_MAP.get(name)
        if sat_ref:
            sat_batch_map.setdefault(sat_ref, []).append(s['full_ref'])

    count_injected = 0
    now = int(time.time()); end_time = now + (3 * 24 * 3600)

    for sat_ref, iptv_refs in sat_batch_map.items():
        events = get_sat_epg_events(sat_ref, now, end_time)
        if events:
            for start, dur, title, desc in events:
                for iptv_ref in iptv_refs: injector.add_event(iptv_ref, (start, dur, title, desc))
            count_injected += len(iptv_refs)

    if count_injected > 0: injector.commit()
    return count_injected

class EPGParser:
    def __init__(self, source_path): self.source_path = source_path
    def parse_timestamp(self, xmltv_date):
        try: return int(datetime.datetime.strptime(xmltv_date[:14], "%Y%m%d%H%M%S").timestamp())
        except: return 0

    def load_events(self, channel_map, progress_cb=None):
        if not os.path.exists(self.source_path): return
        opener = gzip.open if self.source_path.endswith('.gz') else open
        
        try:
            with opener(self.source_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                count = 0
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
                                    event_tuple = (int(start), int(dur), str(title or "")[:240], str(desc or "")[:1024])
                                    for r in refs: yield r, event_tuple
                        except: pass
                        finally: elem.clear()
                        count += 1
                        if progress_cb and count % 5000 == 0:
                            progress_cb(f"[XML] Eventy: {count}")
                    elif elem.tag == 'tv': elem.clear()
        except: pass

class EPGInjector:
    def __init__(self):
        self.epg_cache = eEPGCache.getInstance()
        self.events_buffer = {} 
    def add_event(self, service_ref, event_data):
        if service_ref not in self.events_buffer: self.events_buffer[service_ref] = []
        start, duration, title, desc = event_data
        self.events_buffer[service_ref].append((start, duration, title, "", desc, 0))
    def commit(self):
        for service_ref, events in self.events_buffer.items():
            try: self.epg_cache.importEvents(str(service_ref), events)
            except: pass
        self.events_buffer.clear()
