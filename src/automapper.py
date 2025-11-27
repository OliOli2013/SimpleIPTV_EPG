import os
import re
import xml.etree.cElementTree as ET
import gzip
import json
import time
from difflib import get_close_matches

CACHE_FILE = "/tmp/enigma_services.json"
CACHE_MAX_AGE = 120  # Cache ważny 2 minuty

def _load_services_cached(bouquets_path):
    if os.path.exists(CACHE_FILE):
        try:
            stat = os.stat(CACHE_FILE)
            if time.time() - stat.st_mtime < CACHE_MAX_AGE:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except: pass

    services = []
    try:
        files = [f for f in os.listdir(bouquets_path) if f.endswith('.tv') and 'userbouquet' in f]
    except OSError:
        return []

    for filename in files:
        try:
            path = os.path.join(bouquets_path, filename)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#SERVICE '):
                        if any(x in line for x in ['4097:', '5001:', '5002:', '1:0:']):
                            parts = line.split(':')
                            potential_name = parts[-1]
                            if "###" in potential_name or "---" in potential_name or len(potential_name) < 2:
                                continue
                            ref_clean = line.replace('#SERVICE ', '').strip()
                            services.append({'full_ref': ref_clean, 'name': potential_name})
                    elif line.startswith('#DESCRIPTION'):
                        if services and "###" not in line:
                            services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
        except:
            continue

    seen = set()
    unique = []
    for s in services:
        if s['full_ref'] not in seen:
            seen.add(s['full_ref'])
            unique.append(s)

    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(unique, f)
    except: pass

    return unique

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        
        # --- ROZBUDOWANE ALIASY (Z DODANYM TVP3) ---
        self.CHANNEL_ALIASES = {
            "TVP1": ["TVP 1", "TVP1 HD", "TVP1 FHD", "TVP1 PL", "PROGRAM 1"],
            "TVP2": ["TVP 2", "TVP2 HD", "TVP2 FHD", "TVP 2 HD", "PROGRAM 2"],
            "POLSAT": ["POLSAT HD", "POLSAT FHD", "POLSAT PL", "POLSAT (FHD)"],
            "TVN": ["TVN HD", "TVN FHD", "TVN PL", "TVN (HD)"],
            "TVN 24": ["TVN24", "TVN 24 HD", "TVN24 BIS"],
            "EUROSPORT 1": ["EUROSPORT 1 HD", "EUROSPORT 1 FHD", "EUROSPORT 1 PL"],
            "CANAL+ SPORT": ["CANAL+ SPORT HD", "C+ SPORT", "CANAL PLUS SPORT"],
            "HBO": ["HBO HD", "HBO FHD", "HBO PL"],
            
            # --- NOWE ALIASY REGIONALNE ---
            "TVP3KRAKOW":   ["TVP3Krakow.pl", "TVP3KrakowHD", "TVP3Krakow"],
            "TVP3WARSZAWA": ["TVP3Warszawa.pl", "TVP3WarsawHD"],
            "TVP3GDANSK":   ["TVP3Gdansk.pl", "TVP3GdanskHD"],
            "TVP3POZNAN":   ["TVP3Poznan.pl", "TVP3PoznanHD"],
            "TVP3WROCLAW":  ["TVP3Wroclaw.pl", "TVP3WroclawHD"],
            "TVP3KATOWICE": ["TVP3Katowice.pl", "TVP3KatowiceHD"]
        }
        
        self.junk_words = [
            'HD', 'FHD', 'UHD', '4K', '8K', 'SD', 'HEVC', 'H265', 'H264', 'AVC', 'AAC', 'AC3', 'DD+',
            'FULL', 'FULLHD', 'ULTRA', 'ULTRAHD', 'HIGH', 'LOW', 'QUALITY', 'BITRATE', 'HDR', '1080', '720',
            'PL', 'POL', 'POLISH', '(PL)', '[PL]', '|PL|', 'PL.', 'PL:', 'PL-', '-PL', '_PL',
            'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'UPDATE', 'TEST',
            'SUB', 'DUB', 'LEKTOR', 'NAPISY', 'SUBS', 'MULTI', 'AUDIO', 'ORG', 'ORIGINAL',
            'TV', 'CHANNEL', 'KANAL', 'KANAŁ', 'STREAM', 'LIVE', 'TELEWIZJA', 'SAT', 'CABLE', 'IPTV',
            'PPV', 'PPV1', 'PPV2', 'REC', 'TIMESHIFT', 'TS', 'CATCHUP', 'ARCHIVE',
            'OTV', 'INFO', 'NA', 'ZYWO', 'MAC', 'PORTAL', 'KANALY', 'DLA', 'DZIECI',
            'SEQ', 'H.', 'P.', 'S.', 'M3U', 'LIST', 'PLAYLIST', 'PLUS', '+'
        ]

    def _simplify_name(self, text):
        if not text: return ""
        if isinstance(text, bytes): text = text.decode('utf-8', 'ignore')
        text = text.upper()
        text = text.replace('+', ' PLUS ').replace('&', ' AND ')
        text = re.sub(r'[^A-Z0-9\s]', ' ', text)
        clean_words = []
        for w in text.split():
            if w not in self.junk_words:
                clean_words.append(w)
        return "".join(clean_words)

    def get_enigma_services(self):
        services = _load_services_cached(self.bouquets_path)
        if self.log:
            self.log(f"Załadowano {len(services)} kanałów (z cache/dysku)")
        return services

    def get_xmltv_channels(self, xml_path):
        exact_map = {}
        if not os.path.exists(xml_path):
            return {}
        opener = gzip.open if xml_path.endswith('.gz') else open
        
        if self.log: self.log("Indeksowanie XML (Szybki tryb)...")
        try:
            with opener(xml_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'channel':
                        xml_id = elem.get('id')
                        display_name = ""
                        for child in elem:
                            if child.tag == 'display-name':
                                display_name = child.text
                                break
                        
                        candidates = []
                        if display_name:
                            candidates.append(self._simplify_name(display_name))
                        if xml_id:
                            candidates.append(self._simplify_name(xml_id.replace('.pl', '')))
                        
                        for clean_name in candidates:
                            if clean_name and len(clean_name) > 1:
                                exact_map[clean_name] = xml_id
                        
                        elem.clear()
                    elif elem.tag == 'programme':
                        break
        except Exception: pass
        return exact_map
    
    def find_best_match(self, iptv_name, xml_candidates, xml_index):
        match = get_close_matches(iptv_name, xml_candidates, n=1, cutoff=0.85)
        if match:
            return xml_index[match[0]]
        return None

    def generate_mapping(self, xml_path):
        e2_services = self.get_enigma_services()
        xml_index = self.get_xmltv_channels(xml_path)
        xml_candidates = list(xml_index.keys())

        final_mapping = {}
        matched_count = 0
        total_refs_count = 0

        # Budowanie Inverse Map dla Aliasów
        alias_to_canonical = {}
        for canonical, aliases in self.CHANNEL_ALIASES.items():
            for a in aliases:
                alias_to_canonical[self._simplify_name(a)] = canonical
        
        if self.log: self.log(f"Mapowanie {len(e2_services)} kanałów...")

        for service in e2_services:
            iptv_clean = self._simplify_name(service['name'])
            if len(iptv_clean) < 2: continue

            # 1. Dokładne trafienie
            xml_id = xml_index.get(iptv_clean)

            # 2. Aliasy
            if not xml_id:
                canonical = alias_to_canonical.get(iptv_clean)
                if canonical:
                    canon_clean = self._simplify_name(canonical)
                    xml_id = xml_index.get(canon_clean)

            # 3. Fuzzy
            if not xml_id:
                xml_id = self.find_best_match(iptv_clean, xml_candidates, xml_index)

            if xml_id:
                if xml_id not in final_mapping:
                    final_mapping[xml_id] = []
                    matched_count += 1
                final_mapping[xml_id].append(service['full_ref'])
                total_refs_count += 1

        for xml_id in final_mapping:
            final_mapping[xml_id] = list(dict.fromkeys(final_mapping[xml_id]))

        if self.log:
            self.log(f"Unikalnych EPG: {matched_count}")
            self.log(f"Przypisanych kanałów: {total_refs_count}")
            
        return final_mapping
