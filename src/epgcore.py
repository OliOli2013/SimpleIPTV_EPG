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
from enigma import eEPGCache, eServiceCenter, eServiceReference

# Logowanie
DEBUG_FILE = "/tmp/simple_epg.log"
def log_debug(msg):
    try:
        with open(DEBUG_FILE, "a") as f: f.write(f"[CORE] {msg}\n")
    except: pass

# --- TOOLS ---
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
    for attempt in range(retries):
        try:
            cmd = ["curl", "-k", "-L", "-m", str(timeout), "-o", target_path, url]
            subprocess.run(cmd, capture_output=True, timeout=timeout+10)
            if os.path.exists(target_path) and os.path.getsize(target_path) > 1000: return True
        except: pass
        time.sleep(2)
    return False

# --- NORMALIZACJA ---
def get_extended_core_name(name):
    if not name: return ""
    name = name.upper()
    replacements = {'+': 'PLUS', '&': 'AND', '24': 'TWENTYFOUR', 'Ł': 'L', 'Ś': 'S', 'Ć': 'C', 'Ż': 'Z', 'Ź': 'Z', 'Ą': 'A', 'Ę': 'E', 'Ó': 'O', 'Ń': 'N'}
    for old, new in replacements.items(): name = name.replace(old, new)
    trash = ['FULLHD', 'FHD', 'UHD', '4K', 'HEVC', 'H265', 'H.265', 'HD', 'SD', 'PL', 'POL', '(PL)', '[PL]', 'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'TEST', 'SUB', 'DUB', 'LEKTOR', 'OTV', 'V2', 'V3', 'ORG', 'PL:', '|PL|', '[STREAM]', '(TV)', '[YT]', '(YT)', 'TV', 'CHANNEL', 'LIVE', 'POLSKA', 'KANAL', 'POLAND', 'INTERNATIONAL', 'EU', 'EUROPE']
    for t in trash: name = name.replace(t, '')
    name = re.sub(r'[^A-Z0-9]', '', name)
    return name.strip()

# --- EPG ---
def get_sat_epg_events(sat_ref, start_ts, end_ts):
    cache = eEPGCache.getInstance()
    events = cache.lookupEvent([sat_ref, 2, start_ts, end_ts])
    out = []
    if events:
        for ev in events: 
            out.append((ev[0], ev[1], ev[2], ev[3] if len(ev) > 3 else ""))
    return out

# --- SCAN RAM ---
def get_all_services_from_memory():
    sat_map = {}   
    iptv_list = [] 
    
    serviceHandler = eServiceCenter.getInstance()
    ref_root = eServiceReference('1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet')
    list_root = serviceHandler.list(ref_root)
    
    if list_root:
        bouquets = list_root.getContent("SN")
        for b_ref_str, b_name in bouquets:
            ref_bouquet = eServiceReference(b_ref_str)
            list_bouquet = serviceHandler.list(ref_bouquet)
            
            if list_bouquet:
                services = list_bouquet.getContent("SN")
                for s_ref, s_name in services:
                    if "---" in s_name or "###" in s_name: continue
                    ref_lower = s_ref.lower()
                    
                    # Definicja IPTV (rozszerzona o MAC/Stalker 1:0:1...http)
                    is_iptv = False
                    if '4097:' in s_ref or '5001:' in s_ref or '5002:' in s_ref: is_iptv = True
                    elif any(x in ref_lower for x in ['http', 'https', '%3a', 'rtmp']): is_iptv = True
                    
                    # Definicja SAT
                    is_sat = ('1:0:' in s_ref) and not is_iptv
                    
                    if is_sat:
                        core = get_extended_core_name(s_name)
                        if len(core) > 1: sat_map[core] = s_ref
                    elif is_iptv:
                        iptv_list.append({'ref': s_ref, 'name': s_name})
                            
    return sat_map, iptv_list

# --- INJECT ---
def inject_sat_clone_by_name(injector, log_cb=None):
    log_debug("Start RAM Scan...")
    sat_map, iptv_list = get_all_services_from_memory()
    log_debug(f"RAM: SAT={len(sat_map)}, IPTV={len(iptv_list)}")
    if log_cb: log_cb(f"Analiza: SAT={len(sat_map)} | IPTV={len(iptv_list)}")

    injected = set()
    now = int(time.time()); end = now + 7 * 86400
    matched_count = 0
    
    for idx, iptv in enumerate(iptv_list):
        core_key = get_extended_core_name(iptv['name'])
        sat_ref = sat_map.get(core_key)
        
        # Smart Match (fallback)
        if not sat_ref and len(core_key) > 3:
             for k, v in sat_map.items():
                 if (core_key in k or k in core_key) and abs(len(k) - len(core_key)) < 3:
                     sat_ref = v; break

        if sat_ref:
            events = get_sat_epg_events(sat_ref, now, end)
            if events:
                for start, dur, title, desc in events:
                    injector.add_event(iptv['ref'], (start, dur, title[:240], desc[:1024]))
                injected.add(iptv['ref'])
                matched_count += 1

        if log_cb and idx % 500 == 0:
            percent = int((idx + 1) * 100 / max(len(iptv_list), 1))
            log_cb(f"Łączenie SAT: {percent}%")

    if log_cb: log_cb(f"SAT: Zgrano {matched_count} kanałów")
    if injected: injector.commit()
    return injected

def inject_sat_fallback(injector, injected_refs, log_cb=None): return 0

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
                        if progress_cb and count % 10000 == 0: progress_cb(f"[XML] Eventy: {count}")
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
