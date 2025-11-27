import os
import re
import xml.etree.cElementTree as ET
import gzip
import json
from difflib import get_close_matches

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        
        # --- SŁOWNIK ALIASÓW ---
        # Pomaga połączyć nazwy, które nie mają ze sobą nic wspólnego tekstowo
        self.CHANNEL_ALIASES = {
            "TVP1": ["TVP 1", "TVP1 HD", "TVP1 FHD", "TVP1 PL", "PROGRAM 1"],
            "TVP2": ["TVP 2", "TVP2 HD", "TVP2 FHD", "TVP 2 HD", "PROGRAM 2"],
            "POLSAT": ["POLSAT HD", "POLSAT FHD", "POLSAT PL", "POLSAT (FHD)"],
            "TVN": ["TVN HD", "TVN FHD", "TVN PL", "TVN (HD)"],
            "TVN 24": ["TVN24", "TVN 24 HD", "TVN24 BIS"],
            "EUROSPORT 1": ["EUROSPORT 1 HD", "EUROSPORT 1 FHD", "EUROSPORT 1 PL"],
            "CANAL+ SPORT": ["CANAL+ SPORT HD", "C+ SPORT", "CANAL PLUS SPORT"],
            "HBO": ["HBO HD", "HBO FHD", "HBO PL"]
        }
        
        # Słowa do usunięcia (bez zmian)
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

    def _normalize_string(self, text):
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
        services = []
        try:
            files = [f for f in os.listdir(self.bouquets_path) if f.endswith('.tv') and 'userbouquet' in f]
        except: return []

        for filename in files:
            try:
                path = os.path.join(self.bouquets_path, filename)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#SERVICE '):
                            if any(x in line for x in ['4097:', '5001:', '5002:', '1:0:']):
                                parts = line.split(':')
                                potential_name = parts[-1]
                                if "###" in potential_name or "---" in potential_name: continue
                                ref_clean = line.replace('#SERVICE ', '').strip()
                                services.append({'full_ref': ref_clean, 'name': potential_name})
                        elif line.startswith('#DESCRIPTION'):
                            if services and "###" not in line and "---" not in line:
                                services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
            except: continue
        return services

    def get_xmltv_channels_index(self, xml_path):
        index = {}
        if not os.path.exists(xml_path): return {}
        opener = gzip.open if xml_path.endswith('.gz') else open
        
        if self.log: self.log("Indeksowanie XMLTV...")
        try:
            with opener(xml_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'channel':
                        xml_id = elem.get('id')
                        disp = ""
                        for child in elem:
                            if child.tag == 'display-name' and child.text:
                                disp = child.text
                                break
                        
                        # Zapisz zarówno fingerprint jak i oryginalną nazwę dla Fuzzy Logic
                        fp = self._normalize_string(disp if disp else xml_id)
                        if fp:
                            index[fp] = xml_id
                        
                        # Dodaj też surowy ID jako klucz, czasem pomaga
                        if xml_id:
                            index[xml_id.upper()] = xml_id
                            
                        elem.clear()
                    elif elem.tag == 'programme': break
        except: pass
        return index

    def generate_mapping(self, xml_path):
        e2_services = self.get_enigma_services()
        xml_index = self.get_xmltv_channels_index(xml_path)
        
        # Lista wszystkich kluczy XML do fuzzy matchingu
        xml_candidates = list(xml_index.keys())
        
        final_mapping = {}
        matched_count = 0
        
        if self.log: self.log(f"Parowanie {len(e2_services)} kanałów (Fuzzy+Alias)...")

        for service in e2_services:
            iptv_name_raw = service['name'].upper()
            iptv_fp = self._normalize_string(iptv_name_raw)
            
            if len(iptv_fp) < 2: continue
            
            best_xml_id = None

            # 1. Dokładne trafienie (Fingerprint)
            if iptv_fp in xml_index:
                best_xml_id = xml_index[iptv_fp]

            # 2. Aliasy (jeśli brak dokładnego)
            if not best_xml_id:
                for canonical, aliases in self.CHANNEL_ALIASES.items():
                    # Sprawdź czy nazwa IPTV jest w aliasach
                    found_alias = False
                    for alias in aliases:
                        if alias in iptv_name_raw: # Np. "TVP 1" w "TVP 1 HD"
                             # Teraz szukaj canonical (np. TVP1) w XML
                             canon_fp = self._normalize_string(canonical)
                             if canon_fp in xml_index:
                                 best_xml_id = xml_index[canon_fp]
                                 found_alias = True
                                 break
                    if found_alias: break

            # 3. Fuzzy Matching (difflib) - wolne, ale skuteczne
            if not best_xml_id:
                # Szukamy 1 najlepszego dopasowania z pewnością > 0.85
                match = get_close_matches(iptv_fp, xml_candidates, n=1, cutoff=0.85)
                if match:
                    best_xml_id = xml_index[match[0]]

            if best_xml_id:
                if best_xml_id not in final_mapping:
                    final_mapping[best_xml_id] = []
                    matched_count += 1
                final_mapping[best_xml_id].append(service['full_ref'])

        return final_mapping
