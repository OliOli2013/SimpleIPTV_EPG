import os
import re
import xml.etree.cElementTree as ET
import gzip
import json
import time
from difflib import get_close_matches

CACHE_FILE = "/tmp/enigma_services.json"
CACHE_MAX_AGE = 120 

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
    except OSError: return []

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
                            if "###" in potential_name or "---" in potential_name or len(potential_name) < 2: continue
                            ref_clean = line.replace('#SERVICE ', '').strip()
                            services.append({'full_ref': ref_clean, 'name': potential_name})
                    elif line.startswith('#DESCRIPTION'):
                        if services and "###" not in line:
                            services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
        except: continue

    seen = set()
    unique = []
    for s in services:
        if s['full_ref'] not in seen:
            seen.add(s['full_ref'])
            unique.append(s)
            
    with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(unique, f)
    return unique

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        self.CHANNEL_ALIASES = {
            "TVP1": ["TVP 1", "TVP1 HD", "TVP1 FHD", "TVP1 PL", "PROGRAM 1"],
            "TVP2": ["TVP 2", "TVP2 HD", "TVP2 FHD", "TVP 2 HD", "PROGRAM 2"],
            "POLSAT": ["POLSAT HD", "POLSAT FHD", "POLSAT PL"],
            "TVN": ["TVN HD", "TVN FHD", "TVN PL"],
            "TVN 24": ["TVN24", "TVN 24 HD", "TVN24 BIS"],
            "EUROSPORT 1": ["EUROSPORT 1 HD", "EUROSPORT 1 FHD", "EUROSPORT 1 PL"],
            "CANAL+ SPORT": ["CANAL+ SPORT HD", "C+ SPORT"],
            "HBO": ["HBO HD", "HBO FHD", "HBO PL"]
        }
        self.junk_words = [
            'HD', 'FHD', 'UHD', '4K', 'SD', 'HEVC', 'H265', 'PL', 'POL', '(PL)', '[PL]',
            'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'TEST', 'SUB', 'DUB', 'LEKTOR',
            'TV', 'CHANNEL', 'KANAL', 'STREAM', 'LIVE', 'FHD', 'UHD', '4K'
        ]

    def _simplify_name(self, text):
        if not text: return ""
        text = text.upper().replace('+', ' PLUS ').replace('&', ' AND ')
        text = re.sub(r'[^A-Z0-9\s]', ' ', text)
        clean_words = [w for w in text.split() if w not in self.junk_words]
        return "".join(clean_words)

    def get_enigma_services(self):
        return _load_services_cached(self.bouquets_path)

    def get_xmltv_channels(self, xml_path):
        exact_map = {}
        if not os.path.exists(xml_path): return {}
        opener = gzip.open if xml_path.endswith('.gz') else open
        try:
            with opener(xml_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'channel':
                        xml_id = elem.get('id')
                        display_name = ""
                        for child in elem:
                            if child.tag == 'display-name':
                                display_name = child.text; break
                        
                        candidates = []
                        if display_name: candidates.append(self._simplify_name(display_name))
                        if xml_id: candidates.append(self._simplify_name(xml_id.replace('.pl', '')))
                        
                        for clean_name in candidates:
                            if clean_name and len(clean_name) > 1: exact_map[clean_name] = xml_id
                        elem.clear()
                    elif elem.tag == 'programme': break
        except: pass
        return exact_map
    
    def find_best_match(self, iptv_name, xml_candidates, xml_index):
        match = get_close_matches(iptv_name, xml_candidates, n=1, cutoff=0.85)
        return xml_index[match[0]] if match else None

    # [UPDATE] Nowy argument exclude_refs
    def generate_mapping(self, xml_path, exclude_refs=None):
        if exclude_refs is None: exclude_refs = set()
        
        e2_services = self.get_enigma_services()
        xml_index = self.get_xmltv_channels(xml_path)
        xml_candidates = list(xml_index.keys())

        final_mapping = {}
        matched_count = 0
        skipped_count = 0

        alias_to_canonical = {}
        for canonical, aliases in self.CHANNEL_ALIASES.items():
            for a in aliases: alias_to_canonical[self._simplify_name(a)] = canonical
        
        if self.log: self.log(f"Mapowanie... (Pominięto {len(exclude_refs)} już zrobionych)")

        for service in e2_services:
            # POMIJANIE TYCH CO MAJĄ JUŻ EPG Z SAT
            if service['full_ref'] in exclude_refs:
                skipped_count += 1
                continue

            iptv_clean = self._simplify_name(service['name'])
            if len(iptv_clean) < 2: continue

            xml_id = xml_index.get(iptv_clean)
            if not xml_id:
                canonical = alias_to_canonical.get(iptv_clean)
                if canonical: xml_id = xml_index.get(self._simplify_name(canonical))
            if not xml_id:
                xml_id = self.find_best_match(iptv_clean, xml_candidates, xml_index)

            if xml_id:
                if xml_id not in final_mapping: final_mapping[xml_id] = []
                final_mapping[xml_id].append(service['full_ref'])
                matched_count += 1

        for xml_id in final_mapping:
            final_mapping[xml_id] = list(dict.fromkeys(final_mapping[xml_id]))

        if self.log:
            self.log(f"Zmapowano z XML: {matched_count} kanałów")
            
        return final_mapping
