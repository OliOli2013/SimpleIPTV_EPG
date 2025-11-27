import os
import re
import xml.etree.cElementTree as ET
import gzip
import json
import time  # Dodano do obsługi pauz dla procesora

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        
        # Lista słów ignorowanych
        self.junk_words = {
            'HD', 'FHD', 'UHD', '4K', '8K', 'SD', 'HEVC', 'H265', 'H264', 'AAC', 'AC3',
            'PL', 'POL', '(PL)', '[PL]', '|PL|', 'PL.', 'PL:', 'PL-',
            'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'UPDATE',
            'SUB', 'DUB', 'LEKTOR', 'NAPISY', 'MULTI',
            'TV', 'CHANNEL', 'STREAM', 'LIVE', '24/7',
            'PPV', 'PPV1', 'PPV2', 'PPV3', 'PPV4', 'PPV5', 'PPV6',
            'OTV', 'INFO', 'NA', 'ZYWO', 'REC', 'TIMESHIFT', 'CATCHUP',
            'MAC', 'PORTAL', 'KANALY', 'KANAŁY', 'DLA', 'DZIECI',
            'LOW', 'HIGH', 'ORIGINAL', 'SEQ', 'H.', 'P.', 'S.',
            'HOME', 'OFFICE', 'MOBILE', 'FULL', 'READY', '1080P', '720P'
        }
        
        # Pre-kompilacja Regex dla wydajności (Fix przycięć)
        self.re_plus = re.compile(r'\+')
        self.re_and = re.compile(r'&')
        self.re_brackets = re.compile(r'\[.*?\]')
        self.re_parenthesis_pl = re.compile(r'\(PL\)')
        self.re_chars = re.compile(r'[#|_.\-\(\):]')

    def _simplify_name(self, name):
        try:
            if not name: return ""
            if isinstance(name, bytes): name = name.decode('utf-8', 'ignore')
            
            name = name.upper()
            
            # Szybkie zamiany na skompilowanych wzorcach
            name = self.re_plus.sub('PLUS', name)
            name = self.re_and.sub('AND', name)
            name = self.re_brackets.sub('', name)
            name = self.re_parenthesis_pl.sub('', name)
            name = self.re_chars.sub(' ', name)
            
            parts = name.split()
            clean_parts = []
            for word in parts:
                if word not in self.junk_words:
                    # Zachowaj jeśli dłuższe niż 1 lub cyfra
                    if len(word) > 1 or word.isdigit():
                        clean_parts.append(word)
            
            return "".join(clean_parts)
        except:
            return ""

    def get_enigma_services(self):
        services = []
        try:
            files = [f for f in os.listdir(self.bouquets_path) if f.endswith('.tv') and 'userbouquet' in f]
        except OSError: return []

        for filename in files:
            try:
                path = os.path.join(self.bouquets_path, filename)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#SERVICE 4097:') or line.startswith('#SERVICE 5001:') or line.startswith('#SERVICE 5002:'):
                            parts = line.split(':')
                            potential_name = parts[-1]
                            
                            if "###" in potential_name or "---" in potential_name: continue
                            if len(potential_name) < 2: continue
                                
                            ref_clean = line.replace('#SERVICE ', '').strip()
                            services.append({'full_ref': ref_clean, 'name': potential_name})
                        elif line.startswith('#DESCRIPTION'):
                            if services and "###" not in line:
                                services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
            except: continue
        return services

    def get_xmltv_data(self, xml_path):
        exact_map = {}
        buckets = {}
        
        if not os.path.exists(xml_path): return {}, {}
        
        opener = gzip.open if xml_path.endswith('.gz') else open
        if self.log: self.log("Indeksowanie XML...")
        
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
                        if display_name: candidates.append(self._simplify_name(display_name))
                        candidates.append(self._simplify_name(xml_id.replace('.pl', '')))
                        
                        for clean_name in candidates:
                            if len(clean_name) > 1:
                                exact_map[clean_name] = xml_id
                                first_char = clean_name[0]
                                if first_char not in buckets: buckets[first_char] = []
                                buckets[first_char].append((clean_name, xml_id))
                                
                        elem.clear()
                    elif elem.tag == 'programme':
                        break
        except Exception: pass
        return exact_map, buckets

    def generate_mapping(self, xml_path):
        e2_services = self.get_enigma_services()
        if self.log: self.log(f"Analiza {len(e2_services)} kanałów z tunera...")
        
        exact_map, buckets = self.get_xmltv_data(xml_path)
        
        final_mapping = {}
        matched_count = 0
        processed = 0
        total = len(e2_services)

        if self.log: self.log("Inteligentne parowanie (Anti-Freeze)...")

        for service in e2_services:
            processed += 1
            
            # FIX ZAWIESZANIA:
            # Co 200 kanałów dajemy procesorowi 10ms przerwy, aby odświeżył GUI
            if processed % 200 == 0:
                time.sleep(0.01) 
            
            # Logujemy rzadziej, żeby nie zamulać (co 1000)
            if self.log and processed % 1000 == 0:
                self.log(f"Przetworzono {processed}/{total}...")

            try:
                iptv_clean = self._simplify_name(service['name'])
                if len(iptv_clean) < 2: continue

                xml_id = None

                # 1. Dokładne
                if iptv_clean in exact_map:
                    xml_id = exact_map[iptv_clean]
                
                # 2. Bucketing (Szybkie zawieranie)
                if not xml_id:
                    first_char = iptv_clean[0]
                    if first_char in buckets:
                        for xml_name, xid in buckets[first_char]:
                            if len(xml_name) > 2 and xml_name in iptv_clean:
                                if len(iptv_clean) - len(xml_name) < 5:
                                    xml_id = xid
                                    break
                
                if xml_id:
                    if xml_id not in final_mapping:
                        final_mapping[xml_id] = []
                        matched_count += 1
                    final_mapping[xml_id].append(service['full_ref'])

            except Exception: continue

        if self.log: self.log(f"Unikalne EPG: {matched_count}")
        return final_mapping
