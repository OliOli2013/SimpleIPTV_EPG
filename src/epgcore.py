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
from .automapper import _load_services_cached

# --- MAPA SAT FALLBACK (Dla nazw, które się różnią, np. TVP1 -> 1:0:...) ---
SAT_FALLBACK_MAP = {
    "TVP 1 HD": "1:0:19:3ABD:13F0:13E:820000:0:0:0:", 
    "TVP 2 HD": "1:0:19:3ABE:13F0:13E:820000:0:0:0:",
    "POLSAT HD": "1:0:19:332D:3390:71:820000:0:0:0:",
    "TVN HD": "1:0:19:3DCD:640:13E:820000:0:0:0:",
    "TVP INFO HD": "1:0:19:1234:5678:9ABC:0:0:0:0:",
}

def check_gzip_integrity(filepath):
    try:
        with open(filepath, 'rb') as f:
            return f.read(2) == b'\x1f\x8b'
    except: return False

def check_url_alive(url, timeout=10):
    """Sprawdza czy URL istnieje (HEAD request) przed pobieraniem"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as res:
            return res.status == 200
    except Exception as e:
        print(f"[EPG Check] URL dead: {url} | Error: {e}")
        return False

def download_file(url, target_path, retries=3, timeout=120):
    if os.path.exists(target_path):
        try: os.remove(target_path)
        except: pass

    # 1. Quick check
    if not check_url_alive(url):
        return False

    for attempt in range(retries):
        if attempt > 0: time.sleep(2)
        try:
            cmd = ["curl", "-k", "-L", "-m", str(timeout), "-A", "Mozilla/5.0", "-o", target_path, url]
            subprocess.run(cmd, capture_output=True, timeout=timeout+10)
            if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                if check_gzip_integrity(target_path): return True
        except: pass

        if not os.path.exists(target_path):
            try:
                cmd = ["wget", "--no-check-certificate", f"--timeout={timeout}", "-O", target_path, url]
                subprocess.run(cmd, capture_output=True, timeout=timeout+10)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
                     if check_gzip_integrity(target_path): return True
            except: pass
            
    return False

def get_sat_epg_events(sat_ref, start_ts, end_ts):
    cache = eEPGCache.getInstance()
    events = cache.lookupEvent([sat_ref, 2, start_ts, end_ts])
    out = []
    if events:
        for ev in events:
            # (start, duration, title, short_desc, ...)
            out.append((ev[0], ev[1], ev[2], ev[3] if len(ev) > 3 else ""))
    return out

def inject_sat_clone_fallback(injector, log_cb=None):
    """
    AGRESYWNY FALLBACK:
    Jeśli kanał IPTV nazywa się tak samo jak kanał SAT (np. 'TVP 1 HD'),
    skopiuj EPG z SAT natychmiast.
    Zwraca zestaw (set) referencji, które zostały zaktualizowane.
    """
    all_services = _load_services_cached('/etc/enigma2/')
    
    # 1. Znajdź wszystkie kanały SAT (1:0:...) i zrób mapę NAZWA -> REF
    # Filtrujemy tylko realne serwisy SAT (zazwyczaj namespace != 0)
    sat_services = {}
    iptv_services = []

    for s in all_services:
        ref = s['full_ref']
        name = s['name'].upper().strip()
        if not name: continue

        if '1:0:' in ref and '::' in ref: # Uproszczone wykrywanie SAT
             sat_services[name] = ref
        elif any(x in ref for x in ['4097:', '5001:', '5002:']):
             iptv_services.append(s)

    injected_refs = set()
    count_cloned = 0
    now = int(time.time())
    end = now + (3 * 86400) # 3 dni

    if log_cb: log_cb(f"Skanowanie SAT Clones dla {len(iptv_services)} kanałów IPTV...")

    # 2. Iteruj po IPTV i szukaj identycznej nazwy w SAT
    for iptv in iptv_services:
        name = iptv['name'].upper().strip()
        sat_ref = sat_services.get(name)
        
        if sat_ref:
            events = get_sat_epg_events(sat_ref, now, end)
            if events:
                for start, dur, title, desc in events:
                    injector.add_event(iptv['full_ref'], (start, dur, title[:240], desc[:1024]))
                
                injected_refs.add(iptv['full_ref'])
                count_cloned += 1
                # Opcjonalnie loguj co 50
                # if count_cloned % 50 == 0 and log_cb: log_cb(f"Sklonowano {count_cloned}...")

    if count_cloned > 0:
        injector.commit()
        if log_cb: log_cb(f"[SAT CLONE] Sukces: {count_cloned} kanałów zaktualizowanych bezpośrednio z SAT.")
    
    return injected_refs

def inject_sat_fallback(injector, injected_refs, log_cb=None):
    """
    TRADYCYJNY FALLBACK:
    Dla kanałów, które NIE dostały EPG ani z XML, ani z CLONE,
    spróbuj użyć mapowania ręcznego (SAT_FALLBACK_MAP).
    """
    all_services = _load_services_cached('/etc/enigma2/')
    missing_epg = [s for s in all_services if s['full_ref'] not in injected_refs]
    
    if not missing_epg: return 0

    sat_batch_map = {}
    for s in missing_epg:
        name = s['name'].upper().strip()
        sat_ref = SAT_FALLBACK_MAP.get(name)
        if sat_ref:
            if sat_ref not in sat_batch_map: sat_batch_map[sat_ref] = []
            sat_batch_map[sat_ref].append(s['full_ref'])

    count_injected = 0
    now = int(time.time())
    end_time = now + (3 * 24 * 3600)

    for sat_ref, iptv_refs in sat_batch_map.items():
        events = get_sat_epg_events(sat_ref, now, end_time)
        if events:
            for start, dur, title, desc in events:
                for iptv_ref in iptv_refs:
                    injector.add_event(iptv_ref, (start, dur, title, desc))
            count_injected += len(iptv_refs)

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
                                    event_tuple = (int(start), int(dur), str(title or "")[:240], str(desc or "")[:1024])
                                    for r in refs: yield r, event_tuple
                        except: pass
                        finally: elem.clear()
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
