import os
import re
import xml.etree.cElementTree as ET
import gzip
import json
import time

CACHE_FILE = "/tmp/enigma_services.json"
CACHE_MAX_AGE = 300 

def _load_services_cached(bouquets_path):
    if os.path.exists(CACHE_FILE):
        try:
            stat = os.stat(CACHE_FILE)
            if time.time() - stat.st_mtime < CACHE_MAX_AGE:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
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
                        if services and "###" not in line: services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
        except: continue

    # Deduplikacja
    seen = set(); unique = []
    for s in services:
        if s['full_ref'] not in seen:
            seen.add(s['full_ref'])
            unique.append(s)
            
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(unique, f)
    except: pass
    return unique

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        # Rozszerzone śmieciowe słowa dla lepszego czyszczenia nazw IPTV
        self.junk_words = [
            'HD', 'FHD', 'UHD', '4K', 'SD', 'HEVC', 'H265', 'H.265', 'PL', 'POL', '(PL)', '[PL]',
            'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'TEST', 'SUB', 'DUB', 'LEKTOR',
            'TV', 'CHANNEL', 'KANAL', 'STREAM', 'LIVE', 'AAC', 'AC3', 'DD+', 'HQ', 'LOW', 'MAIN',
            'PL/EU', 'ORG', 'OFFICIAL', 'V2', 'V3', 'OTV'
        ]
        # Aliasy do mapowania XML <-> IPTV (Klucz = Nazwa w IPTV lub XML uproszczona, Wartość = Nazwa szukana)
        self.CHANNEL_ALIASES = {
            "TVP1": ["TVP 1", "PROGRAM 1"],
            "TVP2": ["TVP 2", "PROGRAM 2"],
            "TVN24": ["TVN 24", "TVN 24 BIS"],
            "POLSAT": ["POLSAT NEWS", "POLSAT SPORT"],
            # Dodaj więcej jeśli specyficzne mapowania nie działają
        }

    def _simplify_name(self, text):
        if not text: return ""
        text = text.upper()
        # Zamień znaki
        text = text.replace('+', ' PLUS ').replace('&', ' AND ').replace('Ł', 'L').replace('Ś', 'S').replace('Ć', 'C').replace('Ż', 'Z').replace('Ź', 'Z')
        # Usuń wszystko co nie jest literą/cyfrą
        text = re.sub(r'[^A-Z0-9\s]', ' ', text)
        # Podziel i usuń junk words
        words = text.split()
        clean_words = [w for w in words if w not in self.junk_words and len(w) > 0]
        return "".join(clean_words) # Zwraca np "TVP1" z "TVP 1 HD"

    def get_enigma_services(self): return _load_services_cached(self.bouquets_path)

    # [UPDATE] Szybsze indeksowanie XML
    def get_xmltv_channels(self, xml_path):
        norm_map = {} # { "TVP1": "tvp1.pl", "POLSAT": "polsat.pl" }
        
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
                                display_name = child.text
                                break
                        
                        # Indeksujemy ID
                        if xml_id:
                            simple_id = self._simplify_name(xml_id.replace('.pl', ''))
                            if simple_id: norm_map[simple_id] = xml_id
                        
                        # Indeksujemy Display Name
                        if display_name:
                            simple_name = self._simplify_name(display_name)
                            if simple_name: norm_map[simple_name] = xml_id
                            
                        elem.clear()
                    elif elem.tag == 'programme': break
        except: pass
        return norm_map

    # [UPDATE] Zoptymalizowane mapowanie (Słownikowe zamiast pętli difflib)
    def generate_mapping(self, xml_path, exclude_refs=None, progress_callback=None):
        if exclude_refs is None: exclude_refs = set()

        if self.log: self.log("Wczytywanie usług Enigma2...")
        e2_services = self.get_enigma_services()
        
        if self.log: self.log("Indeksowanie XMLTV (może chwilę potrwać)...")
        xml_map_norm = self.get_xmltv_channels(xml_path)
        
        final_mapping = {} # { "xml_id": ["ref1", "ref2"] }
        matched_count = 0
        total = len(e2_services)

        for idx, service in enumerate(e2_services):
            if progress_callback and idx % 200 == 0:
                progress_callback(idx + 1, total)

            if service['full_ref'] in exclude_refs: continue

            # Normalizacja nazwy IPTV
            iptv_name_clean = self._simplify_name(service['name'])
            if len(iptv_name_clean) < 2: continue

            # 1. Próba bezpośredniego trafienia w znormalizowany XML
            xml_id = xml_map_norm.get(iptv_name_clean)

            # 2. Próba "zawiera się" (np. IPTV: "CANALPLUSSPORT" -> XML: "CANALPLUS")
            # Uwaga: To może dawać fałszywe trafienia, więc ostrożnie
            if not xml_id:
                # Sprawdź czy nazwa kanału zawiera się w kluczach XML (dla krótkich nazw ryzykowne)
                pass

            if xml_id:
                final_mapping.setdefault(xml_id, []).append(service['full_ref'])
                matched_count += 1
            
        # Deduplikacja referencji w mapowaniu
        for xml_id in final_mapping:
            final_mapping[xml_id] = list(set(final_mapping[xml_id]))

        if self.log: self.log(f"Zmapowano metodą Fast: {matched_count} kanałów")
        return final_mapping
